#!/usr/bin/env python3
"""rg2sing 0.3.3: local Rosegarden analysis, diagnostic MIDI/WAV/MP3.
NOT A NEURAL SINGING SYNTHESIZER. A real singing engine is an external renderer.
"""
import argparse,collections,gzip,json,math,os,pathlib,shutil,struct,subprocess,sys,wave
import xml.etree.ElementTree as ET

TICKS_QUARTER=960  # Rosegarden's canonical internal quarter-note duration
SAMPLE_RATE=22050
PARTS=('Soprani','Alti','Tenors','Basses')

def properties(e):
    return {p.get('name'):next((v for k,v in p.attrib.items() if k!='name'),None) for p in e.findall('property')}

def source_xml(path):
    data=pathlib.Path(path).read_bytes()
    if data[:2]==b'\x1f\x8b':data=gzip.decompress(data)
    return ET.fromstring(data)

def parse(path):
    root=source_xml(path); comp=root.find('composition')
    composition_end=int(comp.get('endMarker','0'))
    tempos=sorted([(int(e.get('time','0')),float(e.get('tempo','12000000'))/100000) for e in comp.findall('tempo')]);tempos=tempos or [(0,120.0)]
    tracks=[];warnings=[]
    for seg in root.findall('segment'):
        label=seg.get('label',''); start=int(seg.get('start','0')); end_raw=seg.get('endmarker'); end=int(end_raw) if end_raw is not None else None; repeat=seg.get('repeat')=='true'
        time=0;pending=0;events=[]
        # Rosegarden emits absoluteTime only at some events. After a note/rest
        # the NEXT event without absoluteTime is positioned after its duration.
        # Consecutive lyrics at one onset and their following note share the onset.
        for i, child in enumerate(seg):
            if child.tag not in ('event','chord'):
                continue
            # Rosegarden chords are containers of simultaneous note events.
            # seg.findall('event') would silently discard all their notes.
            cluster = list(child.findall('event')) if child.tag == 'chord' else [child]
            if not cluster:
                continue
            explicit = child.get('absoluteTime')
            if explicit is None:
                explicit = next((x.get('absoluteTime') for x in cluster if x.get('absoluteTime') is not None),None)
            if explicit is not None:
                # Rosegarden absoluteTime is absolute in the composition,
                # whereas `time` is a segment-relative cursor.  A segment
                # starting at -960 with absoluteTime="0" therefore refers
                # to relative tick 960, NOT to its first event.
                time=int(explicit)-start;pending=0
            elif pending:
                time+=pending;pending=0
            advance=0
            for subindex, e in enumerate(cluster):
                typ=e.get('type'); dur=int(e.get('duration','0')); prop=properties(e)
                evt={'tick':time,'duration':dur,'type':typ,'properties':prop,
                     'index':i*100+subindex}
                if child.tag == 'chord':
                    evt['chord_id']=f'{label}:{i}'
                events.append(evt)
                if typ in ('note','rest'):
                    advance=max(advance,dur)
            pending=advance
        # A .rg segment may contain serialized trailing rests *after* its
        # endmarker (observed in Alti). These are not part of the segment's
        # playable timeline. Distinguish them from genuine out-of-bound notes.
        # Some valid Rosegarden scores omit the segment-level endmarker.
        # Infer the exclusive end from the last musical event; otherwise
        # end=0 would clip nearly the entire segment at the pickup.
        musical=[e for e in events if e['type'] in ('note','rest')]
        if end is None:
            inferred=max((e['tick']+e['duration'] for e in musical),default=0)
            end=start+inferred
            warnings.append(f'{label}: endmarker absent, fin inférée à {end} (durée {inferred} ticks)')
        extent=end-start
        inside=[e for e in musical if extent<=0 or e['tick']<extent]
        outside=[e for e in musical if extent>0 and e['tick']>=extent]
        candidate=max((e['tick']+e['duration'] for e in inside),default=0)
        if outside:
            trailing_rests=sum(e['type']=='rest' for e in outside)
            trailing_notes=sum(e['type']=='note' for e in outside)
            if trailing_notes:
                warnings.append(f'{label}: {trailing_notes} note(s) after endmarker; discarded, check Rosegarden')
            if trailing_rests:
                warnings.append(f'{label}: {trailing_rests} trailing rest(s) after endmarker ignored (not part of the playable segment)')
        if extent>0 and candidate>extent:
            warnings.append(f'{label}: {candidate-extent} tick(s) at segment boundary exceed endmarker; verify truncation')
        tracks.append({'label':label,'track_id':int(seg.get('track','-1')),'start':start,'end':end,'repeat':repeat,'events':events,'inferred_end':candidate})
    # Explicit repeats are rendered up to the beginning of the corresponding closing segment.
    segments=[]
    for tr in tracks:
        base=tr['label'].replace(' (end)','')
        next_starts=[x['start'] for x in tracks if x['track_id']==tr['track_id'] and x['start']>tr['start']]
        # A repeated segment with no later segment on its track continues
        # until the composition end marker (which may include a trailing bar).
        stop=min(next_starts) if next_starts else (composition_end if tr['repeat'] and composition_end>tr['start'] else tr['end'])
        length=tr['end']-tr['start']
        offsets=[0]
        if tr['repeat'] and length>0:
            # Round to the nearest complete iteration. E.g. a 960-tick
            # pickup can leave a small trailing margin in endMarker: that
            # margin must NOT create a phantom fourth verse.
            count=max(1,math.floor((stop-tr['start'])/length+0.5))
            offsets=[i*length for i in range(count)]
        for iteration,offset in enumerate(offsets):
            placed=[]
            for e in tr['events']:
                if e['tick']>=length and length>0:continue
                if e['type'] not in ('note','rest','text'):continue
                if e['type']=='text' and e['properties'].get('type')!='lyric':continue
                evt=dict(e);evt['tick']=tr['start']+offset+e['tick'];evt['duration']=min(e['duration'],max(length-e['tick'],0)) if e['type']!='text' and length>0 else e['duration']
                if tr['repeat'] and e['type']=='text':
                    verse=e['properties'].get('verse')
                    if verse is not None and int(verse)!=iteration:continue
                placed.append(evt)
            segments.append({'part':base,'iteration':iteration,'track_id':tr['track_id'],'events':placed})
    return {'format_version':root.get('version'),'tempo':tempos,'segments':segments,'warnings':warnings}

def seconds(tick,tempos):
    out=0.; previous=0
    for i,(pos,bpm) in enumerate(tempos):
        if tick<=pos:break
        nex=min(tick,tempos[i+1][0]) if i+1<len(tempos) else tick
        if nex>pos:out+=(nex-pos)*60/(bpm*TICKS_QUARTER)
    return out

def validate(model):
    issues=list(model['warnings']);table={}
    for part in PARTS:
        events=[e for s in model['segments'] if s['part']==part for e in s['events']]
        notes=[e for e in events if e['type']=='note']
        lyrics=[e for e in events if e['type']=='text']
        table[part]={'notes':len(notes),'lyrics':len(lyrics),'earliest':min((e['tick'] for e in events),default=None),'latest':max((e['tick']+e['duration'] for e in notes),default=None)}
        if part!='Soprani' and not lyrics:issues.append(f'{part}: no lyrics in source; phonetic alignment requires external review / mapping')
    return table,issues

def vlq(n):
    n=max(0,int(n)); data=[n&127];n >>=7
    while n:data.insert(0,(n&127)|128);n>>=7
    return bytes(data)

def joined_notes(model, part):
    """Merge adjacent equal-pitch events carrying a Rosegarden tie."""
    notes=[]
    for seg in model['segments']:
        if seg['part']!=part:continue
        for e in seg['events']:
            if e['type']!='note' or 'pitch' not in e['properties']:continue
            notes.append(e)
    notes.sort(key=lambda e:(e['tick'],e['index']))
    merged=[]
    for e in notes:
        p=e['properties']; pitch=int(p['pitch']); tick=e['tick'];dur=e['duration']
        prev=merged[-1] if merged else None
        if (prev and prev['pitch']==pitch and prev['end']==tick
            and (str(p.get('tiedback','')).lower()=='true' or prev['tiedforward'])):
            prev['end']+=dur
            prev['tiedforward']=str(p.get('tiedforward','')).lower()=='true'
        else:
            merged.append({'tick':tick,'end':tick+dur,'pitch':pitch,
                'tiedforward':str(p.get('tiedforward','')).lower()=='true'})
    return merged

def write_midi(model,out):
    tracks=[]
    tev=[]
    for tick,bpm in model['tempo']:
        micro=round(60_000_000/bpm);tev.append((tick,0,b'\xff\x51\x03'+micro.to_bytes(3,'big')))
    tracks.append(mtrack(tev))
    for ch,part in enumerate(PARTS):
        ev=[]
        for n in joined_notes(model,part):
            pitch=max(0,min(127,n['pitch']));st=n['tick'];end=n['end']
            ev.extend([(st,2,bytes([0x90|ch,pitch,80])),(end,1,bytes([0x80|ch,pitch,0]))])
        tracks.append(mtrack(ev))
    raw=b'MThd'+struct.pack('>IHHH',6,1,len(tracks),TICKS_QUARTER)
    for b in tracks:raw+=b'MTrk'+struct.pack('>I',len(b))+b
    pathlib.Path(out).write_bytes(raw)

def mtrack(ev):
    raw=bytearray();previous=0
    for tick,priority,event in sorted(ev,key=lambda x:(x[0],x[1])):
        raw.extend(vlq(tick-previous));raw.extend(event);previous=tick
    raw+=b'\x00\xff\x2f\x00';return bytes(raw)

def render_preview(model,outdir):
    # Harmonic organ-like pitch diagnostic ONLY. Not articulated singing.
    nmax=max((n['tick']+n['duration'] for s in model['segments'] for n in s['events'] if n['type']=='note'),default=0)
    size=round((seconds(nmax,model['tempo'])+0.5)*SAMPLE_RATE)
    # limit memory for unexpectedly malformed source
    if size>20_000_000:raise ValueError('Unreasonable timeline length')
    import array
    stems=[]
    for idx,part in enumerate(PARTS):
        samples=array.array('f',[0.0])*size
        for n in joined_notes(model,part):
            pitch=n['pitch'];hz=440*2**((int(pitch)-69)/12)
            st=round(seconds(n['tick'],model['tempo'])*SAMPLE_RATE)
            ed=min(size,round(seconds(n['end'],model['tempo'])*SAMPLE_RATE))
            if ed<=st:continue
            fade=max(1,min(220,int((ed-st)*.15)))
            for j in range(st,ed):
                phase=2*math.pi*hz*(j-st)/SAMPLE_RATE
                env=min(1,(j-st)/fade,(ed-j)/fade)
                samples[j]+=.12*env*(math.sin(phase)+.18*math.sin(2*phase)+.07*math.sin(3*phase))
        dest=outdir/(part+'.wav');write_wave(dest,samples);stems.append(samples)
    mixed=array.array('f',[0.0])*size
    for samples in stems:
        for i,v in enumerate(samples): mixed[i]+=v*.7
    write_wave(outdir/'preview_choeur.wav',mixed)
    return outdir/'preview_choeur.wav'

def write_wave(path,samples):
    import array
    ints=array.array('h',(int(max(-1,min(1,v))*32767) for v in samples))
    with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(SAMPLE_RATE);w.writeframes(ints.tobytes())

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.epilog = 'Décompresser et analyser le XML Rosegarden (.rg), extraire les notes et leur chronologie ; outil d’import bas niveau.'
    p.add_argument('source',help='Rosegarden .rg (never uploaded)')
    p.add_argument('--output-dir',default='rg2sing_output')
    p.add_argument('--render',choices=['diagnostic','none'],default='diagnostic')
    p.add_argument('--mp3',action='store_true',help='encode diagnostic preview to MP3 with local ffmpeg')
    args=p.parse_args();out=pathlib.Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    model=parse(args.source);table,issues=validate(model)
    (out/'score.json').write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf8')
    (out/'diagnostic.json').write_text(json.dumps({'parts':table,'issues':issues,'important':'Preview is an electronic instrumental diagnostic, NOT a vocal synthesis'},ensure_ascii=False,indent=2),encoding='utf8')
    write_midi(model,out/'score.mid')
    if args.render=='diagnostic':
        src=render_preview(model,out)
        if args.mp3:
            if not shutil.which('ffmpeg'):print('WARNING: ffmpeg not installed; skipping MP3',file=sys.stderr)
            else:subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(src),'-codec:a','libmp3lame','-q:a','3',str(out/'preview_choeur.mp3')],check=True)
    print('Output:',out.resolve());print('Parts:',json.dumps(table,ensure_ascii=False));print('Warnings:',len(issues));print('IMPORTANT: no articulated vocals; voicebanks and neural engine not installed.')
    for issue in issues:print(' WARNING:',issue)

if __name__=='__main__':main()

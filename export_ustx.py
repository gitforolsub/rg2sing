#!/usr/bin/env python3
"""Convert an rg2sing score to an OpenUtau USTX draft, entirely offline.

Voice-bank, phonemizer, consonant timing and alternate-voice lyric placement
must be reviewed IN OPENUTAU before expecting intelligible sung audio.
"""
import argparse, collections, json, pathlib, re, sys



def yaml_scalar(value):
    """Scalar encoding compatible with YAML 1.2, without PyYAML dependency."""
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is True: return 'true'
    if value is False: return 'false'
    if value is None: return 'null'
    if isinstance(value, (int, float)): return json.dumps(value, allow_nan=False)
    raise TypeError(type(value))


def yaml_lines(value, indent=0):
    """Write block-style YAML (rather than JSON, which OpenUtau may reject)."""
    pad = ' ' * indent
    if isinstance(value, dict):
        for key, item in value.items():
            label = str(key)
            if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9-]*', label):
                label = yaml_scalar(label)
            if isinstance(item, (dict, list)) and item:
                yield pad + label + ':'
                yield from yaml_lines(item, indent + 2)
            elif isinstance(item, dict):
                yield pad + label + ': {}'
            elif isinstance(item, list):
                yield pad + label + ': []'
            else:
                yield pad + label + ': ' + yaml_scalar(item)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)) and item:
                yield pad + '-'
                yield from yaml_lines(item, indent + 2)
            elif isinstance(item, dict):
                yield pad + '- {}'
            elif isinstance(item, list):
                yield pad + '- []'
            else:
                yield pad + '- ' + yaml_scalar(item)
    else:
        yield pad + yaml_scalar(value)


def write_ustx(document, path):
    path.write_text('\n'.join(yaml_lines(document)) + '\n', encoding='utf-8')

PARTS = ('Soprani', 'Alti', 'Tenors', 'Basses')

def as_bool(x):
    return x is True or str(x).lower() == 'true'

def segment_notes(model, part):
    grouped=[]
    for seg in model['segments']:
        if seg['part'] != part: continue
        ev=seg['events']
        notes=sorted((e for e in ev if e['type']=='note' and 'pitch' in e['properties']),key=lambda e:(e['tick'],e['index']))
        texts=collections.defaultdict(list)
        for e in ev:
            if e['type']=='text' and e['properties'].get('type')=='lyric':
                texts[e['tick']].append(e['properties'].get('text',''))
        prev=None
        for n in notes:
            tick=n['tick'];prop=n['properties']; dur=n['duration'];pitch=int(prop['pitch'])
            # USTX prolongation = '+'; Rosegarden tiedback joins same-pitch notes.
            tiedback=as_bool(prop.get('tiedback'))
            if tiedback and prev and prev['end']==tick and prev['pitch']==pitch:
                prev['duration']+=dur
                prev['end']+=dur
                continue
            label=texts[tick].pop(0) if texts[tick] else None
            word_continues = bool(label and re.search(r'-+\s*$', re.sub(r'\s*\([^)]*\)\s*$', '', label)))
            if label is not None:
                label=label.strip()
                # A plain dash, underscore, or explicit tie is a continuation.
                if label in ('-', '_', '--', '—'):
                    label='+'
                else:
                    # A trailing hyphen means word continues at next syllable;
                    # strip it WITHOUT conflating with melisma notation.
                    label=re.sub(r'\s*\([^)]*\)\s*$','',label)  # editorial annotation in lyrics
                    label=re.sub(r'-+$','',label).strip() or '+'
            elif tiedback or (prev and as_bool(prev['properties'].get('tiedforward'))):
                label='+'
            grouped.append({'tick':tick,'duration':dur,'end':tick+dur,'pitch':pitch,'lyric':label,'word_continues':word_continues,'properties':prop,'iteration':seg['iteration']})
            prev=grouped[-1]
    return sorted(grouped,key=lambda n:(n['tick'],n['pitch']))

def export(model, name, other_lyrics='placeholder'):
    allnotes={p:segment_notes(model,p) for p in PARTS}
    sop=allnotes['Soprani']
    bytime=collections.defaultdict(list)
    for note in sop:
        if note['lyric'] not in (None,'+'):
            bytime[note['tick']].append(note['lyric'])
    for part in PARTS[1:]:
        for n in allnotes[part]:
            if n['lyric'] is None:
                # Conservative approach: match only syllabic onset that coincides
                # exactly with Soprani, and otherwise leave an explicit placeholder.
                labels=bytime.get(n['tick'],[])
                n['lyric']=labels[0] if labels else ('+' if as_bool(n['properties'].get('tiedback')) else 'a')
    for n in sop:
        if n['lyric'] is None:n['lyric']='a' # flag unassigned notes in diagnostics
    tracks=[];voice_parts=[]
    for idx,part in enumerate(PARTS):
        tracks.append({'track_name':part,'track_color':['Red','Orange','Blue','Green'][idx], 'singer':'','phonemizer':'','mute':False,'solo':False,'volume':0.0})
        notes=[]
        for n in allnotes[part]:
            notes.append({
                'position':round(n['tick']/2),
                'duration':max(10,round(n['duration']/2)),
                'tone':n['pitch'],
                'lyric':n['lyric'],
                # OpenUtau UNote.Validate() accesses pitch.snapFirst unconditionally.
                # Absent pitch is deserialized as null, causing NullReferenceException.
                'pitch': {
                    'data': [
                        {'x': -40, 'y': 0, 'shape': 'io'},
                        {'x': 40, 'y': 0, 'shape': 'io'},
                    ],
                    'snap_first': False,
                },
                'vibrato': {
                    'length': 0, 'period': 175, 'depth': 25,
                    'in': 10, 'out': 10, 'shift': 0,
                    'drift': 0, 'vol_link': 0,
                },
                'phoneme_expressions': [],
                'phoneme_overrides': [],
            })
        voice_parts.append({'name':part,'track_no':idx,'position':0,'duration':max((n['position']+n['duration'] for n in notes),default=0),'notes':notes,'curves':[]})
    return {'name':name,'ustx_version':'0.6','resolution':480,'key':0,
       'time_signatures':[{'bar_position':0,'beat_per_bar':4,'beat_unit':4}],
       'tempos':[{'position':round(t/2),'bpm':float(b)} for t,b in model['tempo']],
       'tracks':tracks,'voice_parts':voice_parts,'wave_parts':[]},allnotes

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('score_json',type=pathlib.Path)
    ap.add_argument('--output',type=pathlib.Path,default=pathlib.Path('chorale.ustx'))
    args=ap.parse_args()
    model=json.loads(args.score_json.read_text(encoding='utf-8'))
    doc,notes=export(model,args.score_json.stem)
    # OpenUtau uses a YAML parser; use explicit block-style YAML rather than JSON.
    write_ustx(doc, args.output)
    diagnostic={'important':'DRAFT export. Singer and phonemizer must be set in OpenUtau. Lyric mapping to A/T/B is HEURISTIC, not verified.',
        'parts':{p:{'notes':len(ns),'placeholder_a':sum(n['lyric']=='a' for n in ns),'continuations':sum(n['lyric']=='+' for n in ns),'ties_merged':None} for p,ns in notes.items()}}
    diag=args.output.with_suffix('.alignment.json');diag.write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2),encoding='utf8')
    print('Wrote',args.output,'and',diag)
    print('CAUTION: Review lyrics on A/T/B and configure DiffSinger voicebanks in OpenUtau.')
if __name__=='__main__':main()

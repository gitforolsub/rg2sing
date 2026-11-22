#!/usr/bin/env python3
"""rg2sing 0.5: préparation, contrôle, rendu découpé et assemblage des pupitres.

N'effectue aucune transmission réseau. Ne devine pas les phonèmes manquants.
Les attributions A/T/B restent des propositions à vérifier.
"""
import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

PARTS = ('Soprani','Alti','Tenors','Basses')
RENDER_PARTS = PARTS + ('Soprani_divisi',)
SR = 44100
HOP = 512
ROOT = Path('/output/partition/full')
SCRIPT_DIR = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


from french_phonemes import VOWELS

def is_vowel(ph):
    return ph in VOWELS

def nucleus(phs):
    return next((p for p in reversed(phs) if is_vowel(p)),None)


def initial_reviews(score_path,seed_path,out,overwrite=False):
    # Import de la version 0.3.3/0.4.1, y compris fusion des notes liées.
    from rg2sing import seconds
    from export_ustx import segment_notes
    score=read(score_path)
    def create_review(model,part,end_tick):
        rows=[]
        source_notes=segment_notes(model,part)
        # A chord has multiple simultaneous pitches; the monophonic stem
        # carries the upper pitch and the rest are recorded for divisi.
        onsets=collections.defaultdict(list)
        for nn in source_notes: onsets[nn['tick']].append(nn)
        for onset, candidates in sorted(onsets.items()):
            n=max(candidates,key=lambda item:item['pitch'])
            if n['tick']>=end_tick:continue
            stop=min(n['end'],end_tick)
            if stop<=n['tick']:continue
            start=round(seconds(n['tick'],model['tempo'])*SR/HOP)
            end=round(seconds(stop,model['tempo'])*SR/HOP)
            if end<=start:raise ValueError(f'Note trop brève : {part}, tick {n["tick"]}')
            rows.append({'tick':n['tick'],'end_tick':stop,'start_frame':start,
                         'end_frame':end,'midi':n['pitch'],
                         'syllable':next((v['lyric'] for v in candidates if v['lyric'] not in (None,'')),n['lyric'] or ''),
                         'secondary_pitches':[v['pitch'] for v in candidates if v is not n],
                         'phonemes':[]})
        return {'schema':'rg2sing-phoneme-review-v0.4','sample_rate':SR,
                'hop_size':HOP,'part':part,'end_tick':end_tick,'notes':rows}
    seed=read(seed_path)
    samples=seed.get('notes',[])
    by_pos={(n['tick'],n['midi']):n.get('phonemes',[]) for n in samples}
    lex=collections.defaultdict(set)
    for n in samples:
        if n.get('phonemes') and n['phonemes']!=['+']:
            lex[n['syllable'].casefold()].add(tuple(n['phonemes']))
    unambiguous={k:list(next(iter(v))) for k,v in lex.items() if len(v)==1}
    end_tick=max((n['tick']+n['duration'] for s in score['segments'] for n in s['events'] if n['type']=='note'),default=0)+1
    soprano=create_review(score,'Soprani',end_tick)
    for n in soprano['notes']:
        key=(n['tick'],n['midi']);word=(n['syllable'] or '').casefold()
        if key in by_pos and by_pos[key]:
            n['phonemes']=list(by_pos[key]); n['origin']='reference_verified'
        elif word in unambiguous:
            n['phonemes']=list(unambiguous[word]);n['origin']='lexicon_proposed'
        else:
            n['phonemes']=[];n['origin']='missing'
    # Les reprises du soprano servent de référence temporelle et phonétique,
    # mais ne prouvent pas la synchronisation syllabique des autres pupitres.
    ref=soprano['notes']
    by_tick={n['tick']:n for n in ref}
    for part in PARTS:
        destination=out/f'{part}.review.json'
        if destination.exists() and not overwrite:
            print(f'Conservé (pas écrasé) : {destination}')
            continue
        if part=='Soprani':
            doc=soprano
        else:
            doc=create_review(score,part,end_tick)
            last=None
            j=0
            for n in doc['notes']:
                # Progression monotone dans le soprano; prolongation vocale sur
                # notes subdivisées (ne relance pas la consonne à chaque note).
                while j+1<len(ref) and ref[j+1]['tick']<=n['tick']:
                    j+=1
                base=by_tick.get(n['tick'])
                if base is not None:
                    n['syllable']=base['syllable']
                    n['phonemes']=list(base['phonemes'])
                    n['origin']='soprano_same_tick_proposed'
                    last=base
                elif ref and ref[j]['tick']<=n['tick']:
                    prior=ref[j]
                    n['syllable']='+' # prolongation : noyau vocalique seul
                    vowel=nucleus(prior['phonemes'])
                    n['phonemes']=[vowel] if vowel else []
                    n['origin']='soprano_vowel_extension_proposed' if vowel else 'missing'
                    last=prior
                else:
                    n['syllable']='?';n['phonemes']=[];n['origin']='missing'
        doc['instructions']='Vérifier les phonèmes et le report des syllabes, en particulier dans A/T/B. Ne pas remplacer des phonèmes manquants par une voyelle arbitraire.'
        write(destination,doc)
        print(f'{part}: {len(doc["notes"])} notes, {sum(bool(x["phonemes"]) for x in doc["notes"])} propositions renseignées -> {destination}')
    # Lexique mutualisé : facilite la correction des refrains et répétitions.
    lexfile=out/'lexicon.json'
    if not lexfile.exists() or overwrite:
        words=sorted({n['syllable'].casefold() for n in soprano['notes'] if n['syllable'] not in ('','+')})
        lexdoc={w:unambiguous.get(w,[]) for w in words}
        write(lexfile,lexdoc)
        print('Lexique éditable :',lexfile,'(',sum(not v for v in lexdoc.values()),'entrées à compléter)')
    status(out)


def apply_lexicon(out):
    lex=read(out/'lexicon.json')
    paths={p:out/f'{p}.review.json' for p in PARTS}
    docs={p:read(path) for p,path in paths.items()}
    sop=docs['Soprani']['notes']
    for n in sop:
        if n.get('origin')=='reference_verified' or n.get('origin')=='manual_verified':
            continue
        phones=lex.get(n['syllable'].casefold(),[])
        if phones:
            n['phonemes']=phones[:]
            n['origin']='lexicon_proposed'
    ref={n['tick']:n for n in sop}
    previous=sorted(sop,key=lambda x:x['tick'])
    for part in PARTS[1:]:
        j=0
        for n in docs[part]['notes']:
            if n.get('origin')=='manual_verified':continue
            while j+1<len(previous) and previous[j+1]['tick']<=n['tick']:
                j+=1
            if n['tick'] in ref:
                source=ref[n['tick']]
                n['phonemes']=list(source['phonemes'])
                n['syllable']=source['syllable']
                n['origin']='soprano_same_tick_proposed' if n['phonemes'] else 'missing'
            elif previous and previous[j]['tick']<=n['tick']:
                v=nucleus(previous[j]['phonemes'])
                n['phonemes']=[v] if v else []
                n['syllable']='+'
                n['origin']='soprano_vowel_extension_proposed' if v else 'missing'
    for p,path in paths.items():write(path,docs[p])
    status(out)


def status(out):
    print('\n--- Avancement des révisions ---')
    for part in RENDER_PARTS:
        file=out/f'{part}.review.json'
        if not file.exists():continue
        rows=read(file)['notes']
        missing=[n for n in rows if not n.get('phonemes')]
        proposed=sum(n.get('origin','').endswith('proposed') for n in rows)
        print(f'{part:9} : {len(rows)} notes, {len(missing)} sans phonèmes, {proposed} attributions proposées')
        if missing:
            print('  Exemples : '+', '.join(f"{n['tick']}:{n['syllable']}" for n in missing[:12]))
    print('Une proposition phonétique ne remplace pas une vérification à l’écoute.')
    lexfile=out/'lexicon.json'
    if lexfile.exists():
        lex=read(lexfile)
        print(f'Lexique : {len(lex)} syllabes, {sum(not x for x in lex.values())} sans phonèmes.')


def chunk_rows(rows,group_notes,start_tick,end_tick):
    selected=[n for n in rows if n['tick']>=start_tick and (end_tick is None or n['tick']<end_tick)]
    if not selected:raise ValueError('Aucune note dans la plage demandée')
    # Ne coupe aucune note, même lorsqu'elle franchit une barre de mesure.
    for i in range(0,len(selected),group_notes):
        yield i//group_notes, selected[i:i+group_notes]


def safe_wav(path):
    try:
        import soundfile as sf
        info=sf.info(path)
        return info.frames>100 and info.samplerate==SR and info.channels==1
    except Exception:return False


def render(args):
    import numpy as np
    import soundfile as sf
    if args.part not in RENDER_PARTS:raise ValueError('Choisir un pupitre SATB ou Soprani_divisi')
    review=read(args.work/f'{args.part}.review.json')
    rows=review['notes']
    missing=[n for n in rows if not n.get('phonemes') and n['tick']>=args.start_tick and (args.end_tick is None or n['tick']<args.end_tick)]
    if missing:
        raise ValueError(f'{len(missing)} notes sans phonèmes dans {args.part}; compléter {args.part}.review.json (première tick {missing[0]["tick"]}: {missing[0]["syllable"]})')
    if not args.allow_proposals:
        proposed=[n for n in rows if n['tick']>=args.start_tick and (args.end_tick is None or n['tick']<args.end_tick) and n.get('origin','').endswith('proposed')]
        if proposed:
            raise ValueError(f'{len(proposed)} phonétisations/alignements proposés non validés. Vérifier le JSON puis relancer avec --allow-proposals.')
    rendered_dir=args.work/'chunks'/args.part
    rendered_dir.mkdir(parents=True,exist_ok=True)
    stem=args.work/f'{args.part}.wav'
    selected=[n for n in rows if n['tick']>=args.start_tick and (args.end_tick is None or n['tick']<args.end_tick)]
    total_frames=max(n['end_frame'] for n in selected)
    # Longueur audio identique pour tous les pupitres : ce sont des stems alignés à t=0.
    target=np.zeros(total_frames*HOP,dtype=np.float32)
    counts=np.zeros(total_frames*HOP,dtype=np.float32)
    for idx, chunk in chunk_rows(rows,args.chunk_notes,args.start_tick,args.end_tick):
        key=hashlib.sha256(json.dumps({'chunk':chunk,'singer':args.singer,'speaker':args.speaker,
            'vocoder':args.vocoder,'steps':args.steps,'depth':args.depth,
            'caps':[args.max_consonant_ms,args.max_glide_ms,args.max_final_consonant_ms]},
            ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:12]
        # Le renderer ajoute 12 trames de silence en tête et en queue.
        base=int(chunk[0]['start_frame'])
        local=[]
        for n in chunk:
            c=dict(n)
            c['start_frame']=int(n['start_frame'])-base
            c['end_frame']=int(n['end_frame'])-base
            local.append(c)
        doc=dict(review,notes=local)
        dpath=rendered_dir/f'{idx:03}_{key}.json'
        wav=rendered_dir/f'{idx:03}_{key}.wav'
        if args.resume and safe_wav(wav):
            print(f'[{args.part} {idx:03}] WAV existant conservé')
        elif args.dry_run:
            print(f'[{args.part} {idx:03}] {len(local)} notes, ticks {chunk[0]["tick"]}..{chunk[-1]["end_tick"]}')
            continue
        else:
            from prepare_singing import make_duration_doc
            durations=make_duration_doc(doc,args.root,False,args.max_consonant_ms,args.max_glide_ms,args.max_final_consonant_ms,padding=12)
            write(dpath,durations)
            cmd=[sys.executable,str(args.renderer),'--input',str(dpath),'--output',str(wav),'--root',str(args.root),
                 '--singer',args.singer,'--vocoder',args.vocoder,'--pitch-mode','flat',
                 '--steps',str(args.steps),'--depth',str(args.depth)]
            if args.speaker:cmd+=['--speaker',args.speaker]
            print(f'[{args.part} {idx:03}] rendu de {len(local)} notes',flush=True)
            subprocess.run(cmd,check=True)
        if args.dry_run:continue
        audio,sr=sf.read(wav,dtype='float32')
        if sr!=SR or audio.ndim!=1:raise ValueError('WAV inattendu '+str(wav))
        # 12 trames d'amorce; ne pas les décaler dans la partition.
        audio=audio[12*HOP:]
        length=(local[-1]['end_frame'])*HOP
        audio=audio[:length]
        if len(audio)<length:raise ValueError('WAV plus court que le segment '+str(wav))
        start=base*HOP;stop=start+length
        if stop>len(target):raise AssertionError('Taille du stem insuffisante')
        # Fondu de 8 ms aux bords pour limiter les clics entre morceaux.
        fade=min(352,len(audio)//3)
        if fade:
            env=np.ones(len(audio),dtype='float32')
            env[:fade]=np.linspace(0,1,fade,dtype='float32')
            env[-fade:]=np.linspace(1,0,fade,dtype='float32')
            audio*=env
        target[start:stop]+=audio
        counts[start:stop]+=1
    if args.dry_run:return
    np.maximum(counts,1,out=counts)
    target/=counts
    sf.write(stem,np.clip(target,-1,1),SR,subtype='PCM_16')
    print('Stem :',stem,'Durée',round(len(target)/SR,2),'s')


def mix(args):
    import numpy as np
    import soundfile as sf
    paths=[args.work/f'{p}.wav' for p in PARTS]
    absent=[str(p) for p in paths if not p.exists()]
    if absent:raise ValueError('Stems manquants : '+', '.join(absent))
    tracks=[]
    for p in paths:
        wav,sr=sf.read(p,dtype='float32')
        if sr!=SR or wav.ndim!=1:raise ValueError(f'WAV mono 44100 Hz attendu : {p}')
        tracks.append(wav)
    n=max(len(t) for t in tracks)
    stereo=np.zeros((n,2),dtype='float32')
    # Répartition discrète: soprano gauche, alto mi-gauche, ténor mi-droite, basse droite.
    pans=(-0.5,-0.2,0.2,0.5)
    for t,pan in zip(tracks,pans):
        l=math.sqrt((1-pan)/2);r=math.sqrt((1+pan)/2)
        stereo[:len(t),0]+=t*l/4
        stereo[:len(t),1]+=t*r/4
    divisi_path=args.work/'Soprani_divisi.wav'
    if divisi_path.exists():
        divisi,sr=sf.read(divisi_path,dtype='float32')
        if sr!=SR or divisi.ndim!=1:
            raise ValueError('Divisi doit être mono 44100 Hz')
        l=math.sqrt((1-pans[0])/2);r=math.sqrt((1+pans[0])/2)
        stereo[:len(divisi),0]+=divisi*l/4
        stereo[:len(divisi),1]+=divisi*r/4
        print('Divisi soprano ajouté :',divisi_path)
    peak=float(np.max(np.abs(stereo)))
    if peak>0.95:stereo*=0.95/peak
    out=args.work/'chorale_satb.wav'
    sf.write(out,stereo,SR,subtype='PCM_24')
    print('Mix WAV :',out)
    if shutil.which('ffmpeg'):
        mp3=args.work/'chorale_satb.mp3'
        subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(out),'-c:a','libmp3lame','-b:a','256k',str(mp3)],check=True)
        print('Mix MP3 :',mp3)


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.epilog = 'Sous-commandes : prepare, status, apply-lexicon, render, mix. Lancer chorale_full.py render -h pour les options de la synthèse.'
    sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare',help='Créer les quatre fichiers de révision éditables')
    prep.add_argument('--score',default='/output/partition/score.json')
    prep.add_argument('--seed',default='/output/partition/soprano_phonemes.json')
    prep.add_argument('--work',type=Path,default=ROOT)
    prep.add_argument('--overwrite',action='store_true')
    change=sub.add_parser('apply-lexicon',help='Reporter le lexique édité sur les quatre pupitres')
    change.add_argument('--work',type=Path,default=ROOT)
    info=sub.add_parser('status')
    info.add_argument('--work',type=Path,default=ROOT)
    rr=sub.add_parser('render',formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    rr.add_argument('--part',required=True,choices=RENDER_PARTS)
    rr.add_argument('--work',type=Path,default=ROOT)
    rr.add_argument('--root',type=Path,default=Path('/models/UFR-V1.0/UFR-V1.0'))
    rr.add_argument('--renderer',type=Path,default=Path('/scripts/render_millefeuille_duration.py'))
    rr.add_argument('--singer',default='MonteCristo_ALYS')
    rr.add_argument('--speaker',default=None)
    rr.add_argument('--vocoder',default='nsf',choices=['nsf','potluck','tgm'])
    rr.add_argument('--steps',type=int,default=20)
    rr.add_argument('--depth',type=float,default=0.6)
    rr.add_argument('--chunk-notes',type=int,default=20)
    rr.add_argument('--start-tick',type=int,default=0)
    rr.add_argument('--end-tick',type=int,default=None)
    rr.add_argument('--max-consonant-ms',type=float,default=100)
    rr.add_argument('--max-glide-ms',type=float,default=55)
    rr.add_argument('--max-final-consonant-ms',type=float,default=65)
    rr.add_argument('--allow-proposals',action='store_true',help='Accepter explicitement les alignements A/T/B heuristiques')
    rr.add_argument('--resume',action='store_true')
    rr.add_argument('--dry-run',action='store_true')
    mm=sub.add_parser('mix')
    mm.add_argument('--work',type=Path,default=ROOT)
    a=p.parse_args()
    if a.command=='prepare':initial_reviews(a.score,a.seed,a.work,a.overwrite)
    elif a.command=='apply-lexicon':apply_lexicon(a.work)
    elif a.command=='status':status(a.work)
    elif a.command=='render':
        if a.chunk_notes<1:rr.error('--chunk-notes doit être positif')
        render(a)
    elif a.command=='mix':mix(a)

if __name__=='__main__':main()

#!/usr/bin/env python3
"""rg2sing 0.4 alpha: Rosegarden score -> syllable review -> DiffSinger duration JSON -> WAV.

No automatic French G2P is attempted. All phonemes must be confirmed in the
editable review file before inference. Runs entirely offline in the GPU container.
"""
import argparse
import json
import pathlib
import sys
import math

from rg2sing import seconds
from export_ustx import segment_notes
from millefeuille_duration_v3 import session, allocate, show_profile

SR, HOP = 44100, 512


def frame(t):
    return int(round(t * SR / HOP))


def create_review(score, part, end_tick):
    tempos = score['tempo']
    notes = segment_notes(score, part)
    rows = []
    for n in notes:
        if n['tick'] >= end_tick:
            continue
        last_tick = min(n['end'], end_tick)
        if last_tick <= n['tick']:
            continue
        start = frame(seconds(n['tick'], tempos))
        end = frame(seconds(last_tick, tempos))
        if end <= start:
            raise ValueError(f'Note trop brève pour le pas audio: {n}')
        label = n['lyric'] or ''
        rows.append({'tick': n['tick'], 'end_tick': last_tick,
                     'start_frame':start, 'end_frame':end,
                     'midi':n['pitch'], 'syllable':label,
                     'phonemes':[],
                     'comment':'Renseigner les phonèmes tels que fr/..., ou + pour prolongation' if label != '+' else 'Prolongation (utiliser +)'})
    if not rows:
        raise ValueError(f'Aucune note pour {part} avant tick {end_tick}')
    return {'schema':'rg2sing-phoneme-review-v0.4', 'sample_rate': SR,'hop_size': HOP,
            'part':part,'end_tick':end_tick,
            'notes':rows,
            'instructions': 'Editer phonemes pour chaque note. Phonemes exacts de millefeuille_v001.phonemes.json. Pour une note melismatique, phonemes=["+"] ; il faut alors la réunir avec la note précédente dans une version ultérieure.'}


def make_duration_doc(review, root, profile=False, max_consonant_ms=100, max_glide_ms=55, max_final_consonant_ms=65, padding=12):
    import numpy as np
    bank=pathlib.Path(root)
    core=bank/'0_CORE'
    phmap=json.loads((core/'dsacoustic/millefeuille_v001.phonemes.json').read_text())
    rows=review['notes']
    if not rows:
        raise ValueError('Aucune note')
    if any(n['phonemes']==['+'] for n in rows):
        raise ValueError('Mélismes (+) présents: il faut les regrouper manuellement avant le rendu alpha')
    if any(not n['phonemes'] for n in rows):
        missing=[f"tick {n['tick']}: {n['syllable']}" for n in rows if not n['phonemes']]
        raise ValueError('Phonétisation à compléter dans le JSON : '+', '.join(missing[:15]))
    bad=sorted({ph for n in rows for ph in n['phonemes'] if ph not in phmap})
    if bad:
        raise ValueError(f'Phonèmes inconnus dans Millefeuille : {bad}')
    # Respect exact score onsets and rests: all group sizes derived from absolute frames.
    groups=[['SP']]; durations=[padding]; midi=[0]; pos=0
    for i,n in enumerate(rows):
        start=int(n['start_frame']);end=int(n['end_frame'])
        if i==0:
            if start>0:
                groups.append(['SP']);durations.append(start);midi.append(0)
        else:
            prev=int(rows[i-1]['end_frame'])
            if start < prev:
                raise ValueError(f'Chevauchement de notes à tick {n["tick"]}')
            if start > prev:
                groups.append(['SP']); durations.append(start-prev); midi.append(0)
        duration=end-start
        if duration < len(n['phonemes']):
            raise ValueError(f'Pas assez de trames pour les phonèmes à tick {n["tick"]}')
        groups.append(list(n['phonemes']));durations.append(duration);midi.append(int(n['midi']))
    groups.append(['SP']);durations.append(padding);midi.append(0)
    tokens=[p for g in groups for p in g]
    word_div=np.array([[len(g) for g in groups]],dtype=np.int64)
    word_dur=np.array([durations],dtype=np.int64)
    ph_midi=np.array([[m for g,m in zip(groups,midi) for _ in g]],dtype=np.int64)
    langmap=json.loads((core/'dsacoustic/millefeuille_v001.languages.json').read_text())
    tok=np.array([[phmap[p] for p in tokens]],dtype=np.int64)
    langs=np.full(tok.shape,langmap['fr'],dtype=np.int64)
    emb=np.fromfile(bank/'MonteCristo_ALYS/dsdur/embs/millefeuille_v001.alys.emb',dtype='<f4')
    if emb.size!=256:
        raise ValueError('Embedding dsdur doit avoir 256 dimensions')
    ling=session(core/'dsdur/millefeuille_v001.linguistic.onnx',profile)
    enc,masks=ling.run(['encoder_out','x_masks'],{'tokens':tok,'languages':langs,'word_div':word_div,'word_dur':word_dur})
    if profile: print('Linguistique',show_profile(ling))
    dur_model=session(core/'dsdur/millefeuille_v001.dur.onnx',profile)
    predicted=dur_model.run(['ph_dur_pred'],{'encoder_out':enc,'x_masks':masks,'ph_midi':ph_midi,
         'spk_embed':np.broadcast_to(emb.reshape(1,1,256),(1,len(tokens),256)).copy()})[0].reshape(-1)
    if profile:print('Durée',show_profile(dur_model))
    max_frames=round(max_consonant_ms*SR/1000/HOP) if max_consonant_ms else 0
    max_frames=max(1,max_frames) if max_consonant_ms else 0
    glide_frames=max(1,round(max_glide_ms*SR/1000/HOP)) if max_glide_ms else 0
    final_frames=max(1,round(max_final_consonant_ms*SR/1000/HOP)) if max_final_consonant_ms else 0
    phones=[]; k=0;pos=0
    for group,size in zip(groups,durations):
        if group==['SP']:
            counts=[size]
        else:
            counts,_=allocate(predicted[k:k+len(group)],group,size,max_frames,glide_frames,final_frames)
        for p,c in zip(group,counts):
            phones.append({'phoneme':p,'frames':int(c),'start_frame':pos,
                'start_seconds':pos*HOP/SR,'predicted':float(predicted[k])})
            pos+=int(c);k+=1
    assert k==len(tokens) and pos==sum(durations)
    return {'sample_rate':SR,'hop_size':HOP,'groups':groups,'word_div':[len(g) for g in groups],
            'word_dur':durations,'midi':midi,'phonemes':phones,'consonant_max_ms':max_consonant_ms,'glide_max_ms':max_glide_ms,'final_consonant_max_ms':max_final_consonant_ms}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--score',default='/output/partition/score.json')
    ap.add_argument('--review',default='/output/partition/soprano_phonemes.json')
    ap.add_argument('--duration-json',default='/output/partition/soprano_duration.json')
    ap.add_argument('--part',default='Soprani')
    ap.add_argument('--end-tick',type=int,default=15360,help='limite absolue en ticks (15360 = 4 mesures en 4/4)')
    ap.add_argument('--root',default='/models/UFR-V1.0/UFR-V1.0')
    ap.add_argument('--max-consonant-ms',type=float,default=100)
    ap.add_argument('--max-glide-ms',type=float,default=55)
    ap.add_argument('--max-final-consonant-ms',type=float,default=65)
    ap.add_argument('--profile',action='store_true')
    ap.add_argument('--render',action='store_true',help='Lire le JSON édité et calculer les durées CUDA')
    ap.add_argument('--overwrite-review',action='store_true',help='réécrire le fichier de révision en écrasant les modifications')
    a=ap.parse_args()
    review_path=pathlib.Path(a.review)
    if not a.render:
        score=json.loads(pathlib.Path(a.score).read_text(encoding='utf8'))
        if review_path.exists() and not a.overwrite_review:
            raise SystemExit(f'{review_path} existe. Ne pas écraser des corrections manuelles; utiliser --overwrite-review si souhaité.')
        doc=create_review(score,a.part,a.end_tick)
        review_path.parent.mkdir(parents=True,exist_ok=True)
        review_path.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf8')
        print(f'Révision créée: {review_path} ({len(doc["notes"])} notes). Compléter les listes phonemes avant --render.')
        return
    review=json.loads(review_path.read_text(encoding='utf8'))
    if review.get('schema')!='rg2sing-phoneme-review-v0.4':
        raise ValueError('Format de révision non reconnu')
    if min(a.max_consonant_ms,a.max_glide_ms,a.max_final_consonant_ms)<0:
        ap.error('Les plafonds ne peuvent pas être négatifs')
    result=make_duration_doc(review,a.root,a.profile,a.max_consonant_ms,a.max_glide_ms,a.max_final_consonant_ms)
    out=pathlib.Path(a.duration_json);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(f'Durées écrites: {out}; {len(result["phonemes"])} phonèmes; {sum(result["word_dur"])} trames')

if __name__=='__main__':main()

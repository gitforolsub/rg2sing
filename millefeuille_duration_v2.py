#!/usr/bin/env python3
"""Prédiction de durée Millefeuille et contrainte expérimentale des consonnes.

Le groupe est fourni en phonèmes de la banque, pas en graphèmes.
Les durées de groupe sont respectées exactement. Cette heuristique n'est pas
une implémentation de la phonétisation française ni de la prosodie OpenUtau.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort

SAMPLE_RATE = 44100
HOP = 512


def session(path, profile=False):
    opts = ort.SessionOptions()
    opts.enable_profiling = profile
    sess = ort.InferenceSession(str(path), sess_options=opts,
                                providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
    sess.disable_fallback()
    if 'CUDAExecutionProvider' not in sess.get_providers():
        raise RuntimeError('CUDAExecutionProvider indisponible')
    return sess


def show_profile(sess):
    f = Path(sess.end_profiling())
    events = json.loads(f.read_text(encoding='utf8'))
    counts = {}
    for e in events:
        if e.get('cat') == 'Node':
            k = e.get('args', {}).get('provider', 'inconnu')
            counts[k] = counts.get(k, 0) + 1
    f.unlink(missing_ok=True)
    return counts


def largest_remainder(weights, total):
    """Apportionne un entier exactement sans introduire de zéro négatif."""
    if total < 0: raise ValueError('Total négatif')
    a = np.asarray(weights, dtype=np.float64)
    a = np.maximum(a, 1e-8)
    raw = a / a.sum() * total
    base = np.floor(raw).astype(int)
    for i in np.argsort(-(raw-base), kind='stable')[:total-int(base.sum())]:
        base[i] += 1
    return base


def allocate(predictions, phonemes, total, max_consonant_frames=0):
    """Au moins 1 trame/phonème, plafond facultatif s'il existe une voyelle.

    Au lieu de plafonner chaque consonne indépendamment après répartition,
    redistribue l'excédent aux voyelles par la méthode du plus fort reste.
    """
    n=len(phonemes)
    if total < n: raise ValueError('Durée insuffisante pour les phonèmes')
    pred=np.asarray(predictions, dtype=float)
    if len(pred)!=n or not np.isfinite(pred).all():
        raise ValueError('Prédictions de durée invalides')
    pred=np.maximum(pred, 0.001)
    counts=largest_remainder(pred,total-n)+1
    vowels=[i for i,p in enumerate(phonemes) if p.startswith('fr/') and p[3:] in {
        'a','ah','an','e','eh','eu','euh','i','in','o','oh','on','ou','u','un','y','oe','oeh','wa','w','ai','ei','au','uy'
    }]
    # Le jeu exact des voyelles dépend du dictionnaire de la banque.
    if max_consonant_frames and vowels:
        extra=0
        for i,p in enumerate(phonemes):
            if i in vowels or p in {'SP','AP','EP'}:
                continue
            if counts[i]>max_consonant_frames:
                extra += int(counts[i]-max_consonant_frames)
                counts[i]=max_consonant_frames
        if extra:
            portions=largest_remainder(pred[vowels],extra)
            for i,more in zip(vowels,portions): counts[i]+=more
    if counts.sum()!=total or (counts<1).any():
        raise AssertionError('Répartition incorrecte')
    return counts.tolist(), vowels


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', default='/models/UFR-V1.0/UFR-V1.0')
    ap.add_argument('--words',default='fr/m fr/ah|fr/l fr/ah')
    ap.add_argument('--midi',default='69,67')
    ap.add_argument('--seconds',default='0.5,0.5')
    ap.add_argument('--padding',type=int,default=12)
    ap.add_argument('--max-consonant-ms',type=float,default=100.0,
                    help='0 désactive la contrainte')
    ap.add_argument('--output',default='/output/duree_diagnostic_v2.json')
    ap.add_argument('--profile',action='store_true')
    a=ap.parse_args()
    words=[w.split() for w in a.words.split('|')]
    midi=[int(x) for x in a.midi.split(',')]
    seconds=[float(x) for x in a.seconds.split(',')]
    if not words or any(not w for w in words) or len(words)!=len(midi) or len(words)!=len(seconds):
        ap.error('Nombre de groupes, notes et durées différent')
    if a.padding<1 or any(s<=0 or s>15 for s in seconds) or a.max_consonant_ms<0:
        ap.error('Paramètres de durée invalides')
    frames=[max(1,round(s*SAMPLE_RATE/HOP)) for s in seconds]
    groups=[['SP'],*words,['SP']]
    group_durations=[a.padding,*frames,a.padding]
    group_midi=[0,*midi,0]
    tokens=[ph for g in groups for ph in g]
    root=Path(a.root)
    core=root/'0_CORE'
    phones=json.loads((core/'dsacoustic/millefeuille_v001.phonemes.json').read_text())
    langs=json.loads((core/'dsacoustic/millefeuille_v001.languages.json').read_text())
    missing=sorted(set(tokens)-set(phones))
    if missing: raise ValueError(f'Phonèmes absents de la banque: {missing}')
    emb=np.fromfile(root/'MonteCristo_ALYS/dsdur/embs/millefeuille_v001.alys.emb',dtype='<f4')
    if emb.size!=256 or not np.isfinite(emb).all():
        raise RuntimeError('Embedding de durée invalide')
    ids=np.array([[phones[p] for p in tokens]],dtype=np.int64)
    lang=np.full(ids.shape,langs['fr'],dtype=np.int64)
    div=np.array([[len(g) for g in groups]],dtype=np.int64)
    dur=np.array([group_durations],dtype=np.int64)
    ph_midi=np.array([[m for g,m in zip(groups,group_midi) for _ in g]],dtype=np.int64)
    ling=session(core/'dsdur/millefeuille_v001.linguistic.onnx',a.profile)
    t=time.perf_counter()
    enc,masks=ling.run(['encoder_out','x_masks'],{'tokens':ids,'languages':lang,'word_div':div,'word_dur':dur})
    print(f'Linguistique: {time.perf_counter()-t:.3f}s')
    if a.profile: print('Providers linguistique:',show_profile(ling))
    predictor=session(core/'dsdur/millefeuille_v001.dur.onnx',a.profile)
    t=time.perf_counter()
    pred=predictor.run(['ph_dur_pred'],{'encoder_out':enc,'x_masks':masks,'ph_midi':ph_midi,
        'spk_embed':np.broadcast_to(emb.reshape(1,1,256),(1,len(tokens),256)).copy()})[0].reshape(-1)
    print(f'Durée: {time.perf_counter()-t:.3f}s')
    if a.profile: print('Providers durée:',show_profile(predictor))
    maxframes=round(a.max_consonant_ms*SAMPLE_RATE/1000/HOP) if a.max_consonant_ms else 0
    maxframes=max(1,maxframes) if a.max_consonant_ms else 0
    output=[]
    idx=0; pos=0
    for group,gframes in zip(groups,group_durations):
        vals=pred[idx:idx+len(group)]
        allocated,vowels=allocate(vals,group,gframes,maxframes)
        for j,(p,raw,count) in enumerate(zip(group,vals,allocated)):
            output.append({'phoneme':p,'predicted':float(raw),'frames':int(count),
                'start_frame':pos,'start_seconds':pos*HOP/SAMPLE_RATE})
            print(f'{p:8} prédit={raw:8.3f} alloué={count:3} trames ({count*HOP/SAMPLE_RATE*1000:.0f} ms)')
            pos+=int(count)
        if group not in (['SP'],) and not vowels:
            print('ATTENTION: voyelle non reconnue dans le groupe',group,
                  '— pas de plafonnement consonantique')
        idx+=len(group)
    doc={'sample_rate':SAMPLE_RATE,'hop_size':HOP,'groups':groups,'word_div':[len(g) for g in groups],
         'word_dur':group_durations,'midi':group_midi,'phonemes':output,
         'consonant_max_ms':a.max_consonant_ms}
    dst=Path(a.output);dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf8')
    print('Diagnostic:',dst)

if __name__=='__main__':main()

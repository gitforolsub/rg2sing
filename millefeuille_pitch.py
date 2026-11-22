#!/usr/bin/env python3
"""DiffSinger dspitch (Millefeuille/UFR) : hauteur MIDI -> f0 par trame.

Ne modifie pas les durées phonétiques. La courbe fournie est en MIDI, et
seules les trames correspondant à SP/AP/EP sont imposées au silence.
"""
import csv
import json
from pathlib import Path
import time
import numpy as np

SILENCE = {'SP', 'AP', 'EP'}


def _dtype(meta):
    t=meta.type
    if t == 'tensor(int64)': return np.int64
    if t == 'tensor(int32)': return np.int32
    if t == 'tensor(float)': return np.float32
    if t == 'tensor(double)': return np.float64
    if t == 'tensor(bool)': return np.bool_
    if t == 'tensor(uint8)': return np.uint8
    raise RuntimeError(f'Type ONNX non pris en charge : {meta.name} {t}')


def _feed(session, values, stage):
    # Valider chaque signature avant ONNX Runtime pour éviter tout repli arbitraire.
    feed={}
    for m in session.get_inputs():
        if m.name not in values:
            known=', '.join(values)
            raise RuntimeError(f'{stage}: entrée inconnue {m.name} {m.type}, shape={m.shape}; connues={known}')
        arr=np.asarray(values[m.name],dtype=_dtype(m))
        rank=len(m.shape)
        if arr.ndim != rank:
            raise RuntimeError(f'{stage}.{m.name}: dimension attendue {m.shape}, fournie {arr.shape}')
        for i,(got,expected) in enumerate(zip(arr.shape,m.shape)):
            if isinstance(expected,int) and expected>0 and got != expected:
                raise RuntimeError(f'{stage}.{m.name}: axe {i} attendu={expected}, fourni={got}')
        feed[m.name]=arr
    return feed


def inspect(session, label):
    print(f'{label} ONNX — entrées:')
    for m in session.get_inputs(): print(f'  {m.name:16} {m.type:17} {m.shape}')
    print(f'{label} ONNX — sorties:')
    for m in session.get_outputs(): print(f'  {m.name:16} {m.type:17} {m.shape}')


def predict_pitch(doc, root, new_session, profile=False, steps=10, seed=12345,
                  pitch_output=None, inspect_only=False, max_deviation=12.0):
    """Retourne (f0[1,frames], résumé) ou None pour inspection.

    doc = JSON du moteur dsdur, avec groups/midi/phonemes et durées en frames.
    """
    root=Path(root); core=root/'0_CORE'; pdir=core/'dspitch'
    ling_path=pdir/'millefeuille_v001.linguistic.onnx'
    pitch_path=pdir/'millefeuille_v001.pitch.onnx'
    if not ling_path.is_file() or not pitch_path.is_file():
        raise FileNotFoundError(f'Modèles dspitch introuvables: {ling_path} et {pitch_path}')
    ling=new_session(ling_path,profile)
    pitch=new_session(pitch_path,profile)
    inspect(ling,'Linguistique dspitch')
    inspect(pitch,'Prédiction dspitch')
    if inspect_only:return None

    groups=doc['groups']; midis=doc['midi']; phones=doc['phonemes']
    if len(groups) != len(midis):raise ValueError('Nombre de groupes et notes incohérent')
    tokens=[p for g in groups for p in g]
    if tokens != [p['phoneme'] for p in phones]:raise ValueError('Ordre des phonèmes incohérent')
    counts=np.array([int(p['frames']) for p in phones],dtype=np.int64)
    if (counts<=0).any():raise ValueError('Durée nulle dans un phonème')
    frame_count=int(counts.sum())
    ph_midi=np.array([m for g,m in zip(groups,midis) for _ in g],dtype=np.float32)
    frame_midi=np.repeat(ph_midi,counts)
    frame_silence=np.repeat(np.array([p in SILENCE for p in tokens],dtype=bool),counts)
    frame_midi=np.where(frame_silence,0.0,frame_midi)
    ph_midi=np.where(np.array([p in SILENCE for p in tokens]),0.0,ph_midi)
    mapping=json.loads((core/'dsacoustic/millefeuille_v001.phonemes.json').read_text())
    languages=json.loads((core/'dsacoustic/millefeuille_v001.languages.json').read_text())
    raw_tokens=np.array([[mapping[p] for p in tokens]],dtype=np.int64)
    langs=np.full(raw_tokens.shape,languages['fr'],dtype=np.int64)
    ph_dur=counts[None,:]
    ling_values={'tokens':raw_tokens,'languages':langs,'ph_dur':ph_dur,
                 'durations':ph_dur}
    t0=time.perf_counter()
    ling_out=ling.run(None,_feed(ling,ling_values,'linguistic'))
    ling_named=dict(zip([o.name for o in ling.get_outputs()],ling_out))
    if 'encoder_out' not in ling_named:
        raise RuntimeError(f'dspitch linguistic n’a pas encoder_out; sorties={list(ling_named)}')
    print(f'dspitch linguistic: {time.perf_counter()-t0:.3f}s')
    encoder=ling_named['encoder_out']
    if encoder.ndim!=3 or encoder.shape[1]!=len(tokens):
        raise RuntimeError(f'encoder_out inattendu : {encoder.shape}, phonèmes={len(tokens)}')

    # Convention DiffSinger: note_midi/note_dur par phonème, pitch (bruit)
    # et expr/retake par trame.
    rand=np.random.default_rng(seed)
    noise=rand.standard_normal((1,frame_count)).astype(np.float32)
    emb_path=root/'MonteCristo_ALYS/dspitch/embs/millefeuille_v001.alys.emb'
    # Compatibilité avec une banque plaçant les embeddings directement dans dspitch.
    if not emb_path.exists():
        emb_path=root/'MonteCristo_ALYS/dspitch/millefeuille_v001.alys.emb'
    values={
        'encoder_out':encoder,'x_masks':ling_named.get('x_masks'),
        'ph_dur':ph_dur,'durations':ph_dur,
        'note_midi':ph_midi[None,:],
        'note_rest':(ph_midi[None,:]<=0),
        'note_dur':ph_dur,
        'pitch':noise,
        'pitch_noise':noise,
        'expr':np.ones((1,frame_count),dtype=np.float32),
        'retake':np.ones((1,frame_count),dtype=bool),
        'steps':np.array(steps,dtype=np.int64),
    }
    if any(m.name=='spk_embed' for m in pitch.get_inputs()):
        emb=np.fromfile(emb_path,dtype='<f4')
        if emb.size!=256:raise RuntimeError(f'Embedding dspitch invalide: {emb_path}: {emb.size} floats')
        # L'entrée de l'embedding peut être token ou frame; se fier à la forme
        # déclarée lorsqu'elle est fixée, sinon utiliser n_ph, convention du prédicteur.
        meta=next(m for m in pitch.get_inputs() if m.name=='spk_embed')
        if len(meta.shape)!=3:raise RuntimeError(f'spk_embed pitch, forme inconnue : {meta.shape}')
        # spk_embed est défini par trame (n_frames), et non par phonème (n_tokens).
        length=frame_count
        values['spk_embed']=np.broadcast_to(emb.reshape(1,1,256),(1,length,256)).copy()
    if any(m.name=='x_masks' for m in pitch.get_inputs()) and values['x_masks'] is None:
        raise RuntimeError('Le modèle exige x_masks absent du modèle linguistique')
    t0=time.perf_counter()
    out=pitch.run(None,_feed(pitch,values,'pitch'))
    result=dict(zip([o.name for o in pitch.get_outputs()],out))
    print(f'dspitch prédiction: {time.perf_counter()-t0:.3f}s')
    result_key='pitch_pred' if 'pitch_pred' in result else (next(iter(result)) if len(result)==1 else None)
    if result_key is None:raise RuntimeError(f'Sorties ambigües dspitch: {list(result)}')
    pred=np.asarray(result[result_key],dtype=np.float32).reshape(-1)
    if pred.size!=frame_count:raise RuntimeError(f'dspitch prédit {pred.size} trames, attendu {frame_count}')
    if not np.isfinite(pred).all():raise RuntimeError('Valeurs dspitch NaN ou infinies')
    voiced=(~frame_silence)&(frame_midi>0)
    if not voiced.any():raise RuntimeError('Aucune trame chantée')
    print(f'dspitch sortie MIDI : min={pred[voiced].min():.2f} max={pred[voiced].max():.2f}, moyenne={pred[voiced].mean():.2f}')
    # Le modèle prédit une valeur MIDI (non des Hz) ; refuser l'export
    # si cette hypothèse contredit grossièrement les données.
    err=np.abs(pred[voiced]-frame_midi[voiced]);bad=err>max_deviation
    if np.mean(bad)>.15:
        raise RuntimeError(f'Courbe dspitch aberrante : {bad.mean():.1%} des trames diffèrent de >{max_deviation} demi-tons de la partition. Refus du rendu.')
    f0=np.where(voiced,440.0*np.exp2((pred-69.0)/12.0),0.0).astype(np.float32)[None,:]
    if pitch_output:
        p=Path(pitch_output);p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('w',newline='',encoding='utf8') as fh:
            writer=csv.writer(fh);writer.writerow(['frame','seconds','score_midi','predicted_midi','f0_hz','silence'])
            for i in range(frame_count):writer.writerow([i,i*512/44100,round(float(frame_midi[i]),4),round(float(pred[i]),4),round(float(f0[0,i]),4),int(frame_silence[i])])
        print('Diagnostic hauteur :',p)
    return f0,{'frames':frame_count,'pitch_min_midi':float(pred[voiced].min()),'pitch_max_midi':float(pred[voiced].max()),'deviation_median_semitones':float(np.median(err))}

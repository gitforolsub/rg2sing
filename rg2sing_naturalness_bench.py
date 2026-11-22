#!/usr/bin/env python3
"""Banc d'essai local de naturel rg2sing : compare un même extrait avec plusieurs réglages.

Lit PART.review.json déjà préparé, sélectionne N notes à partir de --start-tick,
calcule les durées DiffSinger et les WAV, puis fournit un comparatif sonore et CSV.
Ne modifie ni la partition, ni les revues, ni singers.json. Aucun accès réseau.

Exemple :
 rg2sing_naturalness_bench.py --work /output/tests/louange-v092/full \\
    --part Tenors --start-tick 0 --notes 14 --resume
"""
import argparse
import csv
import json
import math
import re
import subprocess
import sys
from pathlib import Path

SR = 44100
HOP = 512
DEFAULT_ROOT = Path('/models/UFR-V1.0/UFR-V1.0')
DEFAULT_SCRIPTS = Path(__file__).resolve().parent

# Une variable à la fois : isoler les causes des différences à l'écoute.
PRESETS = (
    dict(name='01_reference',  consonant=100, glide=55, final=65, steps=20, depth=.6, vocoder='nsf'),
    dict(name='02_consonnes_courtes', consonant=65, glide=55, final=45, steps=20, depth=.6, vocoder='nsf'),
    dict(name='03_consonnes_souples', consonant=140, glide=55, final=90, steps=20, depth=.6, vocoder='nsf'),
    dict(name='04_glides_courts', consonant=100, glide=30, final=65, steps=20, depth=.6, vocoder='nsf'),
    dict(name='05_diffusion_40', consonant=100, glide=55, final=65, steps=40, depth=.6, vocoder='nsf'),
)

def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--work', type=Path, required=True, help='Répertoire contenant PART.review.json')
    p.add_argument('--part', default='Tenors', help='Pupitre à comparer, ex. Soprani, Alti, Tenors, Basses')
    p.add_argument('--start-tick', type=int, default=0, help='Première note à sélectionner (tick absolu normalisé)')
    p.add_argument('--notes', type=int, default=12, help='Nombre de notes consécutives à synthétiser')
    p.add_argument('--output-dir', type=Path, default=None, help='Dossier des résultats; par défaut WORK/naturalness/PART_TICK')
    p.add_argument('--settings', type=Path, default=Path('/scripts/singers.json'), help='Configuration des chanteurs (lecture seule)')
    p.add_argument('--root', type=Path, default=DEFAULT_ROOT, help='Répertoire racine de la banque UFR')
    p.add_argument('--renderer', type=Path, default=Path('/scripts/render_millefeuille_duration.py'))
    p.add_argument('--presets', nargs='+', default=None, help='Variantes à rendre (par défaut toutes les cinq)')
    p.add_argument('--resume', action='store_true', help='Réutiliser les WAV déjà produits')
    p.add_argument('--dry-run', action='store_true', help='Afficher les notes et variantes sans CUDA')
    p.add_argument('--version', action='version', version='rg2sing naturalness bench 0.1 (compatible rg2sing 0.9.5)')
    a = p.parse_args(argv)
    if a.notes < 1: p.error('--notes doit être >= 1')
    valid = {x['name'] for x in PRESETS}
    if a.presets and set(a.presets) - valid:
        p.error('Presets inconnus : ' + ', '.join(sorted(set(a.presets)-valid)) + ' ; disponibles : ' + ', '.join(sorted(valid)))
    return a

def choose_notes(doc, start_tick, count):
    notes = sorted(doc['notes'], key=lambda n: (n['tick'], n.get('midi', 0)))
    selected = [n for n in notes if int(n['tick']) >= start_tick][:count]
    if not selected: raise ValueError('Aucune note dans la plage demandée')
    for n in selected:
        if not n.get('phonemes'):
            raise ValueError(f"Note sans phonèmes à tick={n['tick']} syllabe={n.get('syllable')!r}")
    # Début du segment à zéro : durée et pauses internes rigoureusement conservées.
    base = int(selected[0]['start_frame'])
    if any(int(n['start_frame']) < base for n in selected): raise AssertionError('Chronologie invalide')
    result = []
    for n in selected:
        c = dict(n)
        c['start_frame'] = int(n['start_frame']) - base
        c['end_frame'] = int(n['end_frame']) - base
        result.append(c)
    return result

def load_settings(path, part):
    settings = json.loads(path.read_text(encoding='utf-8'))
    if part not in settings: raise ValueError(f'Pupitre {part} absent de {path}')
    item = settings[part]
    if not item.get('singer'): raise ValueError('singer absent de la configuration')
    return item

def phoneme_metrics(doc):
    from french_phonemes import VOWELS, GLIDES
    phones = doc['phonemes']
    total = sum(int(p['frames']) for p in phones if p['phoneme'] not in ('SP','AP','EP'))
    vowels = sum(int(p['frames']) for p in phones if p['phoneme'] in VOWELS)
    nasal_cons = sum(int(p['frames']) for p in phones if p['phoneme'] in ('fr/m','fr/n','fr/ng'))
    glides = sum(int(p['frames']) for p in phones if p['phoneme'] in GLIDES)
    return dict(vowel_percent=round(100*vowels/total, 1) if total else 0,
                nasal_consonants_ms=round(nasal_cons*HOP*1000/SR),
                glides_ms=round(glides*HOP*1000/SR),
                total_phonemes=len(phones))

def main(argv=None):
    a = parse_args(argv)
    review_path = a.work / f'{a.part}.review.json'
    if not review_path.is_file(): raise SystemExit(f'Révision introuvable : {review_path}')
    review = json.loads(review_path.read_text(encoding='utf-8'))
    notes = choose_notes(review, a.start_tick, a.notes)
    settings = load_settings(a.settings, a.part)
    variants = [x for x in PRESETS if a.presets is None or x['name'] in a.presets]
    outdir = a.output_dir or (a.work / 'naturalness' / f'{a.part}_{notes[0]["tick"]}')
    print(f'Pupitre={a.part}; chanteur={settings["singer"]}; speaker={settings.get("speaker")}; notes={len(notes)}')
    print('Séquence :', ' | '.join(f'{n.get("syllable", "")} ({n["tick"]})' for n in notes))
    print('Dossier :', outdir)
    if a.dry_run:
        for v in variants: print('  ', v)
        return
    if not a.renderer.is_file(): raise SystemExit(f'Moteur introuvable : {a.renderer}')
    if not a.root.is_dir(): raise SystemExit(f'Banque introuvable : {a.root}')
    import numpy as np
    import soundfile as sf
    from prepare_singing import make_duration_doc
    outdir.mkdir(parents=True, exist_ok=True)
    results=[]
    listening=[]
    for v in variants:
        prefix=outdir / v['name']
        duration_path=prefix.with_suffix('.json')
        wav_path=prefix.with_suffix('.wav')
        log_path=prefix.with_suffix('.log')
        print(f'[{v["name"]}]', flush=True)
        if a.resume and wav_path.is_file() and duration_path.is_file():
            duration_doc=json.loads(duration_path.read_text(encoding='utf-8'))
            print('  WAV existant conservé')
        else:
            duration_doc = make_duration_doc(dict(review, notes=notes), a.root, False,
                        v['consonant'], v['glide'], v['final'], padding=12)
            duration_path.write_text(json.dumps(duration_doc, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            cmd=[sys.executable, str(a.renderer), '--input',str(duration_path),
                 '--output',str(wav_path), '--root',str(a.root),
                 '--singer',settings['singer'], '--vocoder',v['vocoder'],
                 '--steps',str(v['steps']), '--depth',str(v['depth']), '--pitch-mode','flat']
            if settings.get('speaker'): cmd += ['--speaker',settings['speaker']]
            with log_path.open('w',encoding='utf-8') as log:
                log.write('Commande : '+' '.join(cmd)+'\n')
                log.flush()
                result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError(f'Rendu échoué pour {v["name"]}. Voir {log_path}')
        audio, sample_rate=sf.read(wav_path,dtype='float32')
        if sample_rate != SR or audio.ndim != 1: raise ValueError(f'Format WAV inattendu: {wav_path}')
        # Renderer padding 12 trames à l'entrée, et 12 à la sortie.
        expected=int(notes[-1]['end_frame'])*HOP
        audio=audio[12*HOP:12*HOP+expected]
        if len(audio) != expected: raise ValueError(f'Audio trop court: {wav_path}')
        metrics=phoneme_metrics(duration_doc)
        rms=float(np.sqrt(np.mean(audio**2)))
        peak=float(np.max(np.abs(audio)))
        results.append(dict(preset=v['name'],consonant_ms=v['consonant'],glide_ms=v['glide'],
                            final_consonant_ms=v['final'],steps=v['steps'],depth=v['depth'],
                            singer=settings['singer'],vocoder=v['vocoder'],
                            duration_s=round(len(audio)/SR,3),rms=round(rms,5),peak=round(peak,5),
                            **metrics,wav=str(wav_path),log=str(log_path)))
        # Comparaison à niveau égal pour éviter l'illusion "plus fort = mieux".
        gain=min(0.9/max(peak,1e-8), 0.075/max(rms,1e-8), 4.0)
        listening.append(audio*gain)
    report=outdir/'comparaison.csv'
    with report.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]))
        w.writeheader();w.writerows(results)
    # Pauses de 0.9 seconde entre variantes (même ordre que comparaison.csv).
    gap=np.zeros(int(.9*SR),dtype=np.float32)
    wav=np.concatenate([item for x in listening for item in (x,gap)])
    sf.write(outdir/'ecoute_enchainee.wav', np.clip(wav,-1,1),SR,subtype='PCM_16')
    print('Rapport :', report)
    print('Écoute séquentielle :', outdir/'ecoute_enchainee.wav')
    print('IMPORTANT : écouter sans confondre timbre, articulation et rendu d’ensemble.')

if __name__ == '__main__':
    main()

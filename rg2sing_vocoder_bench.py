#!/usr/bin/env python3
"""Compare les vocodeurs Millefeuille sur le MÊME spectrogramme acoustique.

Lit les notes d'une voix dans WORK/PART.review.json, construit le document
DiffSinger et calcule une seule fois mel/f0. Les autres vocodeurs relisent ce
même NPZ. Ne modifie ni le score, ni les revues, ni singers.json.

Exemple (dans le conteneur) :
  rg2sing_vocoder_bench.py --work /output/tests/louange-v092/full \
     --part Tenors --start-tick 24000 --notes 14
"""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


def args_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--work', type=Path, required=True, help='Dossier contenant PART.review.json')
    p.add_argument('--part', default='Tenors', help='Nom du pupitre')
    p.add_argument('--start-tick', type=int, default=24000, help='Position de la première note')
    p.add_argument('--notes', type=int, default=14, help='Nombre de notes à sélectionner')
    p.add_argument('--singers', type=Path, default=Path('/scripts/singers.json'), help='Configuration des voix en lecture seule')
    p.add_argument('--root', type=Path, default=Path('/models/UFR-V1.0/UFR-V1.0'), help='Banque Millefeuille')
    p.add_argument('--renderer', type=Path, default=Path('/scripts/render_millefeuille_duration.py'), help='Moteur avec --features-in/out')
    p.add_argument('--vocoders', nargs='+', choices=('nsf','potluck','tgm'), default=['nsf','potluck','tgm'], help='Vocodeurs à essayer')
    p.add_argument('--steps', type=int, default=20, help='Pas acoustiques, communs aux vocodeurs')
    p.add_argument('--depth', type=float, default=0.6, help='Profondeur de diffusion')
    p.add_argument('--max-consonant-ms', type=float, default=100)
    p.add_argument('--max-glide-ms', type=float, default=55)
    p.add_argument('--max-final-consonant-ms', type=float, default=65)
    p.add_argument('--output-dir', type=Path, default=None, help='Dossier du banc d’essai')
    p.add_argument('--dry-run', action='store_true', help='Afficher la sélection sans calcul CUDA')
    p.add_argument('--version', action='version', version='rg2sing vocoder bench 0.1')
    return p


def select_notes(doc, first_tick, number):
    if number < 1:
        raise ValueError('--notes doit être positif')
    seq = sorted(doc['notes'], key=lambda n: (int(n['tick']), int(n.get('midi', 0))))
    selected = [dict(n) for n in seq if int(n['tick']) >= first_tick][:number]
    if not selected:
        raise ValueError('Aucune note dans cette plage')
    for n in selected:
        if not n.get('phonemes'):
            raise ValueError(f"Phonèmes manquants à tick={n['tick']}")
    zero = int(selected[0]['start_frame'])
    for n in selected:
        n['start_frame'] = int(n['start_frame']) - zero
        n['end_frame'] = int(n['end_frame']) - zero
    return selected


def run_renderer(cmd, logfile):
    with logfile.open('w', encoding='utf-8') as output:
        output.write('Commande : ' + ' '.join(map(str,cmd)) + '\n')
        output.flush()
        return subprocess.run(cmd, stdout=output, stderr=subprocess.STDOUT, check=False).returncode


def write_listening(waves, dest):
    import numpy as np
    import soundfile as sf
    audio = []
    stats = []
    sample_rate = None
    for label, wav in waves:
        x, sr = sf.read(wav, dtype='float32', always_2d=False)
        if x.ndim != 1:
            raise ValueError(f'WAV non mono : {wav}')
        if sample_rate is None:
            sample_rate = sr
        if sr != sample_rate:
            raise ValueError('Fréquences différentes entre les vocodeurs')
        rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float64)))) if x.size else 0
        peak = float(np.max(np.abs(x))) if x.size else 0
        stats.append((label, rms, peak, len(x)/sr))
        # Comparaison sans normalisation : toute variation d'énergie appartient au vocodeur.
        audio.extend((np.zeros(int(sr*.8), dtype=np.float32), x))
    sf.write(dest, np.concatenate(audio), sample_rate, subtype='PCM_16')
    return stats


def main(argv=None):
    a = args_parser().parse_args(argv)
    review_path = a.work / f'{a.part}.review.json'
    if not review_path.is_file():
        raise SystemExit(f'Fichier absent : {review_path}')
    doc = json.loads(review_path.read_text(encoding='utf-8'))
    notes = select_notes(doc, a.start_tick, a.notes)
    settings = json.loads(a.singers.read_text(encoding='utf-8'))[a.part]
    singer = settings['singer']
    speaker = settings.get('speaker')
    out = a.output_dir or (a.work / 'vocoder_bench' / f'{a.part}_{notes[0]["tick"]}')
    print('Chanteur :', singer, 'speaker :', speaker)
    print('Paroles :', ' | '.join(n.get('syllable','') for n in notes))
    print('Sortie :', out)
    if a.dry_run:
        print('Vocodeurs :', ', '.join(a.vocoders))
        return 0
    from prepare_singing import make_duration_doc
    out.mkdir(parents=True, exist_ok=True)
    duration = make_duration_doc(dict(doc, notes=notes), a.root, False,
                                 a.max_consonant_ms, a.max_glide_ms,
                                 a.max_final_consonant_ms, padding=12)
    dur_file = out / 'duration.json'
    dur_file.write_text(json.dumps(duration, ensure_ascii=False, indent=2) + '\n',encoding='utf-8')
    features = out / 'same_mel_f0.npz'
    wavs=[]
    for i, voc in enumerate(a.vocoders):
        output = out / f'{i+1:02}_{voc}.wav'
        cmd = [sys.executable, str(a.renderer), '--input', str(dur_file),
               '--output', str(output), '--root', str(a.root), '--singer', singer,
               '--vocoder', voc, '--steps', str(a.steps), '--depth', str(a.depth), '--pitch-mode', 'flat']
        if speaker:
            cmd.extend(('--speaker', speaker))
        cmd.extend(('--features-out', str(features)) if i == 0 else ('--features-in', str(features)))
        log = out / f'{i+1:02}_{voc}.log'
        print(f'[{i+1}/{len(a.vocoders)}] {voc} ...', flush=True)
        status = run_renderer(cmd, log)
        if status:
            raise RuntimeError(f'Le rendu {voc} a échoué (code {status}). Voir {log}')
        wavs.append((voc, output))
    stats = write_listening(wavs, out / 'ecoute_enchainee.wav')
    with (out / 'comparaison.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(('vocoder','rms','peak','duration_seconds'))
        w.writerows(stats)
    print('Écoute :', out / 'ecoute_enchainee.wav')
    print('Rapport :', out / 'comparaison.csv')
    return 0


if __name__ == '__main__':
    sys.exit(main())

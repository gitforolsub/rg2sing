#!/usr/bin/env python3
"""Comparateur local des voix DiffSinger UFR (rg2sing 0.4.3).

Par défaut : toutes les variantes acoustiques, un seul vocodeur (nsf), pitch flat.
Les résultats et les logs sont conservés dans --output-dir ; --resume saute les WAV valides.
"""
import argparse
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

DEFAULT_ROOT = '/models/UFR-V1.0/UFR-V1.0'
DEFAULT_INPUT = '/output/partition/soprano_duration_v3.json'
DEFAULT_OUTPUT = '/output/partition/comparaison_voix'


def safe_name(s):
    return re.sub(r'[^a-zA-Z0-9._-]+', '_', s).strip('_') or 'unnamed'


def discover(root, singer_filter, speaker_filter):
    variants = []
    for cfg in sorted(root.glob('*/dsconfig.yaml')):
        singer = cfg.parent.name
        if singer_filter and not any(f.casefold() in singer.casefold() for f in singer_filter):
            continue
        data = yaml.safe_load(cfg.read_text(encoding='utf8')) or {}
        for speaker in data.get('speakers', []):
            if speaker_filter and not any(f.casefold() in speaker.casefold() for f in speaker_filter):
                continue
            emb = cfg.parent / (speaker + '.emb')
            if not emb.is_file():
                print(f'IGNORÉ : embedding absent : {emb}', file=sys.stderr)
                continue
            variants.append((singer, speaker))
    return variants


def is_valid_wav(p):
    if not p.is_file() or p.stat().st_size <= 44:
        return False
    try:
        with p.open('rb') as f:
            h = f.read(12)
        return h[:4] == b'RIFF' and h[8:12] == b'WAVE'
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument('--root', default=DEFAULT_ROOT, help='Racine des voix UFR')
    ap.add_argument('--input', default=DEFAULT_INPUT, help='JSON de durée existant (v3)')
    ap.add_argument('--output-dir', default=DEFAULT_OUTPUT)
    ap.add_argument('--renderer', default='/scripts/render_millefeuille_duration.py')
    ap.add_argument('--vocoders', nargs='+', choices=['nsf', 'potluck', 'tgm', 'all'], default=['nsf'])
    ap.add_argument('--singer', action='append', default=[], help='Filtre partiel chanteuse ; répétable')
    ap.add_argument('--speaker', action='append', default=[], help='Filtre partiel variante ; répétable')
    ap.add_argument('--steps', type=int, default=20, help='Étapes acoustiques')
    ap.add_argument('--depth', type=float, default=0.6)
    ap.add_argument('--limit', type=int, default=0, help='Limiter à N rendus, 0 = tous')
    ap.add_argument('--dry-run', action='store_true', help='Afficher la liste sans calcul GPU')
    ap.add_argument('--resume', action='store_true', help='Sauter les WAV existants valides')
    ap.add_argument('--stop-on-error', action='store_true')
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        ap.error(f'Racine absente : {root}')
    if not args.dry_run:
        if not Path(args.input).is_file():
            ap.error(f'Entrée absente : {args.input}')
        if not Path(args.renderer).is_file():
            ap.error(f'Moteur absent : {args.renderer}')
    if not 1 <= args.steps <= 100 or not 0 < args.depth <= 0.6:
        ap.error('steps doit être entre 1 et 100 ; depth dans ]0, 0.6]')

    voices = discover(root, args.singer, args.speaker)
    vocoders = ['nsf', 'potluck', 'tgm'] if 'all' in args.vocoders else list(dict.fromkeys(args.vocoders))
    tasks = [(singer, speaker, vocoder) for singer, speaker in voices for vocoder in vocoders]
    if args.limit > 0:
        tasks = tasks[:args.limit]
    print(f'{len(voices)} variantes vocales, {len(vocoders)} vocodeur(s) ; {len(tasks)} rendus prévus.', flush=True)
    if not tasks:
        ap.error('Aucun embedding vocal correspondant aux filtres')

    outdir = Path(args.output_dir)
    if not args.dry_run:
        outdir.mkdir(parents=True, exist_ok=True)
    rows = []
    n_failed = 0
    for i, (singer, speaker, vocoder) in enumerate(tasks, 1):
        stem = f'{safe_name(singer)}__{safe_name(Path(speaker).name)}__{vocoder}__s{args.steps}__d{args.depth:g}'
        wav = outdir / (stem + '.wav')
        log = outdir / (stem + '.log')
        desc = f'[{i}/{len(tasks)}] {singer} / {Path(speaker).name} / {vocoder}'
        if args.dry_run:
            print(desc)
            continue
        if args.resume and is_valid_wav(wav):
            print(f'{desc} : existant, ignoré', flush=True)
            rows.append(dict(singer=singer, speaker=speaker, vocoder=vocoder, status='existing', seconds='', wav=str(wav), log=str(log)))
            continue
        print(desc, flush=True)
        command = [sys.executable, args.renderer, '--input', args.input,
                   '--root', str(root), '--singer', singer, '--speaker', speaker,
                   '--vocoder', vocoder, '--pitch-mode', 'flat',
                   '--steps', str(args.steps), '--depth', str(args.depth),
                   '--output', str(wav)]
        t0 = time.monotonic()
        with log.open('w', encoding='utf8') as stream:
            stream.write('Commande : ' + ' '.join(command) + '\n\n')
            stream.flush()
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
        elapsed = round(time.monotonic() - t0, 2)
        ok = result.returncode == 0 and is_valid_wav(wav)
        if not ok:
            n_failed += 1
            wav.unlink(missing_ok=True)  # Un échec ne doit pas laisser un WAV partiel trompeur.
        status = 'ok' if ok else f'error:{result.returncode}'
        print(f'  {status} ({elapsed:.2f}s) ; log : {log}', flush=True)
        rows.append(dict(singer=singer, speaker=speaker, vocoder=vocoder,
                         status=status, seconds=elapsed, wav=str(wav) if ok else '', log=str(log)))
        # Rapport réécrit à chaque itération : reste disponible en cas d'interruption.
        with (outdir / 'resultats.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['singer', 'speaker', 'vocoder', 'status', 'seconds', 'wav', 'log'])
            writer.writeheader()
            writer.writerows(rows)
        if not ok and args.stop_on_error:
            break

    if not args.dry_run:
        print(f'Fin : {len(rows) - n_failed} OK/existants, {n_failed} échec(s).')
        print(f'Rapport : {outdir / "resultats.csv"}')
        if n_failed:
            sys.exit(1)


if __name__ == '__main__':
    main()

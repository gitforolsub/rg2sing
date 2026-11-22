#!/usr/bin/env python3
"""Superpose plusieurs voix déjà synthétisées (même partition et origine temporelle).

Les fichiers WAV d'entrée doivent être des stems complets, alignés sur t=0.
Aucun décalage de hauteur, changement de durée ni accès réseau.
"""
import argparse
import math
from pathlib import Path
import shutil
import subprocess
import sys


def mix_voices(voices, output, peak_limit=0.95, equalize=False, write_mp3=False):
    import numpy as np
    import soundfile as sf

    prepared = []
    sr_ref = None
    for path, gain, pan, delay_ms in voices:
        path = Path(path)
        samples, sr = sf.read(path, dtype='float32', always_2d=True)
        if sr_ref is None:
            sr_ref = sr
        if sr != sr_ref:
            raise ValueError(f'Échantillonnage différent : {path} ({sr} contre {sr_ref} Hz)')
        if not np.isfinite(samples).all():
            raise ValueError(f'Échantillons non finis : {path}')
        mono = samples.mean(axis=1)  # Pour un stem stéréo existant, réduction mono avant spatialisation.
        rms = float(np.sqrt(np.mean(mono.astype(np.float64)**2))) if len(mono) else 0.0
        if not -1 <= pan <= 1:
            raise ValueError(f'Pan hors [-1,1] pour {path}')
        if delay_ms < 0:
            raise ValueError('Délai négatif interdit ; les stems sont alignés sur la partition')
        offset = int(round(delay_ms * sr / 1000))
        prepared.append((path, mono, float(gain), float(pan), offset, rms))
    if not prepared:
        raise ValueError('Au moins une voix est nécessaire')
    reference = max((x[-1] for x in prepared if x[-1] > 1e-8), default=0.0)
    duration = max(len(mono)+offset for _, mono, _, _, offset, _ in prepared)
    stereo = np.zeros((duration,2), dtype=np.float64)
    for path, mono, gain, pan, offset, rms in prepared:
        factor = min(reference/rms, 5.0) if equalize and rms > 1e-8 else 1.0
        # Panning à puissance constante. 0 = centre ; -1/+1 = gauche/droite.
        left = math.sqrt((1-pan)/2)
        right = math.sqrt((1+pan)/2)
        data = mono.astype(np.float64) * gain * factor
        stereo[offset:offset+len(data),0] += data * left
        stereo[offset:offset+len(data),1] += data * right
        print(f'{path.name}: {len(mono)/sr_ref:.3f}s, gain={gain:.2f}, pan={pan:+.2f}, '
              f'délai={offset/sr_ref*1000:.1f}ms, RMS={rms:.5f}, égalisation={factor:.2f}')
    peak = float(np.max(np.abs(stereo))) if duration else 0.0
    if peak > peak_limit:
        stereo *= peak_limit / peak
        print(f'Pic initial {peak:.3f} : réduction globale pour rester sous {peak_limit:.2f}')
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    sf.write(output, stereo.astype('float32'), sr_ref, subtype='PCM_24')
    print('Mix WAV :', output)
    if write_mp3:
        if shutil.which('ffmpeg') is None:
            raise RuntimeError('ffmpeg introuvable : WAV produit, MP3 non créé')
        mp3=output.with_suffix('.mp3')
        subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(output),
                        '-codec:a','libmp3lame','-b:a','256k',str(mp3)],check=True)
        print('Mix MP3 :',mp3)
    return output


def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Exemple : rg2sing_choir_layers.py --voice /tmp/A.wav 0.55 -0.3 0 '
               '--voice /tmp/B.wav 0.45 0.3 17 --output /tmp/duo.wav --mp3')
    ap.add_argument('--voice',nargs=4,action='append',required=True,
                    metavar=('WAV','GAIN','PAN','DELAY_MS'),
                    help='Répéter par chanteur. GAIN linéaire, PAN de -1 à +1, DELAY_MS >= 0.')
    ap.add_argument('--output',type=Path,required=True,help='Fichier WAV stéréo à produire')
    ap.add_argument('--peak',type=float,default=0.95,help='Plafond du pic final, réduction globale seulement (défaut 0.95)')
    ap.add_argument('--equalize-rms',action='store_true',help='Égaliser approximativement le RMS des stems (max facteur 5)')
    ap.add_argument('--mp3',action='store_true',help='Créer aussi un MP3 à 256 kbit/s avec ffmpeg')
    ap.add_argument('--version',action='version',version='rg2sing choir layers 0.9.6-exp1')
    args=ap.parse_args()
    if not 0 < args.peak <= 1:
        ap.error('--peak doit être entre 0 et 1')
    try:
        voices = [(p,float(g),float(pan),float(d)) for p,g,pan,d in args.voice]
        if any(g<0 for _,g,_,_ in voices):
            ap.error('GAIN doit être positif')
        mix_voices(voices,args.output,args.peak,args.equalize_rms,args.mp3)
    except (ValueError,OSError) as exc:
        ap.error(str(exc))

if __name__=='__main__':
    main()

#!/usr/bin/env python3
"""Répartition des durées des phonèmes de chant (correctif 0.4.1).

Distingue noyaux vocaliques, glides (/j,w,ɥ/) et consonnes.
Conserve exactement la durée de chaque groupe en trames.
"""
import numpy as np
from millefeuille_duration_v2 import session, show_profile, largest_remainder

# Correspondance avec les noms vus dans la banque UFR (fr/y pour /j/,
# fr/uy pour /ɥ/). Ne pas confondre fr/ih (/i/) avec fr/y.
from french_phonemes import VOWELS, GLIDES
SILENCES = {'SP', 'AP', 'EP'}


def allocate(predictions, phonemes, total, max_consonant_frames=0,
             max_glide_frames=0, max_final_consonant_frames=0):
    """Retourne (durées, indices des noyaux vocaliques), somme == total.

    La durée prédite sert de poids initial, puis on plafonne les sons non
    syllabiques. L'excédent est ajouté aux voyelles, sans déplacer les notes.
    """
    n = len(phonemes)
    if n == 0 or total < n:
        raise ValueError('Nombre de trames insuffisant pour les phonèmes')
    pred = np.asarray(predictions, dtype=np.float64)
    if pred.shape != (n,) or not np.isfinite(pred).all():
        raise ValueError('Prédictions de durée invalides')
    pred = np.maximum(pred, 0.001)
    vowels = [i for i, p in enumerate(phonemes) if p in VOWELS]
    if not vowels and not all(p in SILENCES for p in phonemes):
        raise ValueError('Aucun noyau vocalique reconnu pour : ' + str(phonemes))
    counts = largest_remainder(pred, total - n).astype(int) + 1
    surplus = 0
    for i, p in enumerate(phonemes):
        if i in vowels or p in SILENCES:
            continue
        cap = max_consonant_frames
        if p in GLIDES and max_glide_frames:
            cap = max_glide_frames
        elif i == n - 1 and max_final_consonant_frames:
            cap = max_final_consonant_frames
        if cap and counts[i] > cap:
            surplus += int(counts[i] - cap)
            counts[i] = cap
    if surplus:
        share = largest_remainder(pred[vowels], surplus)
        for i, add in zip(vowels, share):
            counts[i] += int(add)
    if (counts < 1).any() or sum(counts) != total:
        raise AssertionError('Durée de groupe non conservée')
    return counts.tolist(), vowels

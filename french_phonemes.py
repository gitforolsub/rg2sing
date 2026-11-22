#!/usr/bin/env python3
"""Correspondances phonétiques françaises vers UFR/Millefeuille v001.

Source unique pour french_align et suggest_espeak. Tout phonème absent
reste une erreur explicite; aucune approximation silencieuse.
"""
IPA = {
    'ɑ̃':'fr/en', 'ɔ̃':'fr/on', 'ɛ̃':'fr/in', 'œ̃':'fr/un',
    'a':'fr/ah', 'ɑ':'fr/ah', 'ɛ':'fr/ae', 'e':'fr/eh',
    'ə':'fr/ee', 'ø':'fr/ee', 'œ':'fr/oe',
    'i':'fr/ih', 'ɔ':'fr/oo', 'o':'fr/oh', 'u':'fr/ou', 'y':'fr/uh',
    'j':'fr/y', 'ɥ':'fr/uy', 'w':'fr/w',
    'b':'fr/b', 'd':'fr/d', 'f':'fr/f', 'ɡ':'fr/g', 'g':'fr/g',
    'k':'fr/k', 'l':'fr/l', 'm':'fr/m', 'n':'fr/n', 'p':'fr/p',
    'ʁ':'fr/r', 'r':'fr/r', 's':'fr/s', 'ʃ':'fr/sh',
    't':'fr/t', 'v':'fr/v', 'z':'fr/z', 'ʒ':'fr/j', 'ŋ':'fr/ng',
}
VOWELS = {'fr/'+v for v in 'ah ae eh ee ih oo oh ou uh en on in un oe'.split()}
GLIDES = {'fr/y', 'fr/uy', 'fr/w'}
ORDER = sorted(IPA, key=len, reverse=True)

#!/usr/bin/env python3
"""Résolution prudente d'homographes français en contexte.

Ne remplace ni un analyseur grammatical ni un modèle sémantique. Une ambiguïté
non résolue n'est jamais convertie arbitrairement en phonèmes.
"""
from dataclasses import dataclass
from french_words import clean

@dataclass(frozen=True)
class Resolution:
    phonemes: tuple[str, ...] | None
    status: str  # resolved | ambiguous | none
    reason: str

NONE = Resolution(None, 'none', '')

# Déterminants imposant un groupe nominal singulier pour le nom « fils ».
# Contrairement à « fils » pluriel, il n'existe pas de graphie « fils »
# au singulier pour le substantif textile « fil ».
SINGULAR_DETERMINERS = frozenset({
    'un', 'le', 'ce', 'cet', 'mon', 'ton', 'son', 'notre', 'votre',
    'leur', 'au', 'du',
})


def resolve(word: str, *, previous: str | None = None,
            preceding: tuple[str, ...] = ()) -> Resolution:
    """Retourne une lecture lexicale sûre ou signale une ambiguïté.

    ``previous`` est le mot précédent reconstruit, dans l'ordre des paroles.
    ``preceding`` permet de transmettre plus de contexte à l'avenir.
    """
    if clean(word) != 'fils':
        return NONE
    prev = clean(previous or '')
    if prev in SINGULAR_DETERMINERS:
        return Resolution(('fr/f', 'fr/ih', 'fr/s'), 'resolved',
                          f'« {previous} {word} » : groupe nominal singulier')
    if word[:1].isupper() and prev in {'au', 'du'}:
        return Resolution(('fr/f', 'fr/ih', 'fr/s'), 'resolved',
                          'titre au singulier')
    return Resolution(None, 'ambiguous',
                      '« fils » : /fis/ (descendant) ou /fil/ (fils textiles) ; contexte insuffisant')

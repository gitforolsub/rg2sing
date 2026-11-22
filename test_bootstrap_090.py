#!/usr/bin/env python3
"""Tests des choix généraux 0.9.0 ; sans GPU, réseau, eSpeak ni wordfreq."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from french_words import reconstruct
from french_align import align_word
from rg2sing_bootstrap import bootstrap


def notes_of(parts):
    return [dict(tick=i*480,end_tick=(i+1)*480,syllable=s,
                 word_continues=(i<len(parts)-1),phonemes=[],origin='missing')
            for i,s in enumerate(parts)]

class ContextualBootstrap090(unittest.TestCase):
    def test_louange_three_notes(self):
        notes=notes_of(['Lou','an','ge'])
        inventory={'fr/l','fr/ou','fr/en','fr/j','fr/ee'}
        frequency=lambda word: {'louange':4.2,'lou-an-ge':5.9}.get(word,0)
        with tempfile.TemporaryDirectory() as d, patch(
            'rg2sing_bootstrap.espeak_ipa',side_effect=lambda word,_:
            {'louange':'lˈuˈɑ̃ʒə-','lou-an-ge':'lˈuɑ̃ʒ'}.get(word)):
            path=Path(d)/'Soprani.review.json'
            report,n,isolated,_=bootstrap({'Soprani':(path,{'notes':notes})},
                                           inventory,'fake',frequency)
        self.assertEqual(n,3)
        self.assertEqual(isolated,0)
        self.assertEqual(report[0]['word'],'louange')
        self.assertEqual([r['phonemes'] for r in notes],
                         [['fr/l','fr/ou'],['fr/en'],['fr/j','fr/ee']])

    def test_lui_and_puissance(self):
        self.assertEqual(align_word('lui',['lui'],'lyˈi'),
                         [['fr/l','fr/uy','fr/ih']])
        self.assertEqual(align_word('puissance',['puis','sance'],'pyisˈɑ̃s'),
                         [['fr/p','fr/uy','fr/ih'],['fr/s','fr/en','fr/s']])

    def test_vie_score_error_not_a_dieresis(self):
        with self.assertRaisesRegex(ValueError,'vérifier la partition'):
            align_word('vie',['vi','e'],'vˈi')

    def test_true_hyphenated_compound_remains_possible(self):
        freq=lambda s: {'porteclé':0,'porte-clé':4.5}.get(s,0)
        word=reconstruct(notes_of(['porte','clé']),freq)[0]
        self.assertEqual(word['word'],'porte-clé')

    def test_plain_word_over_artificial_hyphen_frequency(self):
        freq=lambda s: {'faiblesse':4.5,'fai-blesse':6.0}.get(s,0)
        word=reconstruct(notes_of(['fai','blesse']),freq)[0]
        self.assertEqual(word['word'],'faiblesse')

if __name__ == '__main__':
    unittest.main()

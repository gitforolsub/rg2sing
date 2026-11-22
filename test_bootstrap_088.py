#!/usr/bin/env python3
"""Tests ciblés : une ambiguïté orthographique n'implique pas une ambiguïté phonétique."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rg2sing_bootstrap import bootstrap

class AmbiguousSpellingTests(unittest.TestCase):
    def run_case(self, alternative_ipa):
        notes = [
            {'syllable':'lou','word_continues':True,'tick':0,'end_tick':480,'phonemes':[], 'origin':'missing'},
            {'syllable':'ange','word_continues':False,'tick':480,'end_tick':960,'phonemes':[], 'origin':'missing'},
        ]
        frequencies = {'louange':4.0, 'lou-ange':3.6}
        f = lambda w: frequencies.get(w,0)
        inventory = {'fr/l','fr/ou','fr/en','fr/j','fr/ee'}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'Soprani.review.json'
            with patch('rg2sing_bootstrap.espeak_ipa', side_effect=lambda word, _: {
                'louange':'luɑ̃ʒ', 'lou-ange':alternative_ipa,
            }.get(word)):
                report, good, _, _ = bootstrap({'Soprani':(path,{'notes':notes})},inventory,'mock',f)
        return report,good,notes

    def test_same_phonetics_can_proceed(self):
        report, count, notes = self.run_case('luɑ̃ʒ')
        self.assertEqual(count,2)
        self.assertEqual(report[0]['status'],'proposed_word')
        self.assertTrue(all(note['phonemes'] for note in notes))

    def test_attested_plain_word_preferred_to_musical_hyphens(self):
        report, count, notes = self.run_case('luɑ̃s')
        self.assertEqual(count,2)
        self.assertEqual(report[0]['word'],'louange')
        self.assertEqual(report[0]['status'],'proposed_word')

    def test_unavailable_hyphenated_variant_does_not_block_plain_word(self):
        report, count, notes = self.run_case(None)
        self.assertEqual(count,2)
        self.assertEqual(report[0]['status'],'proposed_word')

if __name__ == '__main__': unittest.main()

#!/usr/bin/env python3
"""Tests du banc local de comparaison acoustique rg2sing."""
import unittest
from rg2sing_naturalness_bench import choose_notes, parse_args, phoneme_metrics

class BenchTests(unittest.TestCase):
    def test_selection_with_offset(self):
        notes=[dict(tick=500,start_frame=8,end_frame=16,phonemes=['fr/ah'],syllable='a'),
               dict(tick=600,start_frame=16,end_frame=28,phonemes=['fr/ah'],syllable='b'),
               dict(tick=700,start_frame=30,end_frame=35,phonemes=['fr/ah'],syllable='c')]
        got=choose_notes(dict(notes=notes),600,2)
        self.assertEqual([(n['start_frame'],n['end_frame']) for n in got],[(0,12),(14,19)])
        self.assertEqual(notes[1]['start_frame'],16)
    def test_missing_phonemes_rejected(self):
        with self.assertRaisesRegex(ValueError,'sans phonèmes'):
            choose_notes(dict(notes=[dict(tick=0,start_frame=0,end_frame=10,phonemes=[],syllable='?')]),0,1)
    def test_metrics(self):
        doc={'phonemes':[dict(phoneme='SP',frames=12),dict(phoneme='fr/m',frames=9),dict(phoneme='fr/ah',frames=24)]}
        out=phoneme_metrics(doc)
        self.assertAlmostEqual(out['vowel_percent'],72.7,places=1)
    def test_args(self):
        a=parse_args(['--work','/tmp/x','--notes','10','--dry-run'])
        self.assertEqual(a.notes,10)

if __name__=='__main__':unittest.main()

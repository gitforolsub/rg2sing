#!/usr/bin/env python3
"""Tests sans GPU du banc d'essai vocodeur."""
import unittest
from rg2sing_vocoder_bench import select_notes, args_parser

class VocoderBenchTests(unittest.TestCase):
    def test_selection_and_normalized_frames(self):
        doc = {'notes': [
            dict(tick=960, midi=60, start_frame=120, end_frame=150, phonemes=['fr/ah'], syllable='a'),
            dict(tick=1920, midi=62, start_frame=150, end_frame=180, phonemes=['fr/ee'], syllable='b'),
        ]}
        out = select_notes(doc, 960, 2)
        self.assertEqual([(v['start_frame'],v['end_frame']) for v in out],[(0,30),(30,60)])
        self.assertEqual(doc['notes'][0]['start_frame'],120)
    def test_missing_phonemes_refused(self):
        with self.assertRaisesRegex(ValueError,'Phonèmes manquants'):
            select_notes({'notes':[dict(tick=0, start_frame=0, end_frame=1, phonemes=[])]},0,1)
    def test_defaults(self):
        a = args_parser().parse_args(['--work','/tmp/test'])
        self.assertEqual(a.vocoders,['nsf','potluck','tgm'])

if __name__ == '__main__': unittest.main()

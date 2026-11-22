#!/usr/bin/env python3
import unittest
from rg2sing_lyrics import align_lyrics


def n(t, text=None):
    return {'tick': t, 'syllable': text}

class LyricAlignmentTests(unittest.TestCase):
    def test_different_rhythm_same_lyrics(self):
        # S: vie / nous / vi- / vons, quatre noires.
        # A/T/B: vie blanche, nous croche, vi croche, vons noire.
        ref=[n(84480,'vie'),n(85440,'nous'),n(86400,'vi'),n(87360,'vons')]
        other=[n(84480),n(86400),n(86880),n(87360)]
        result,diagnostic=align_lyrics(ref,other)
        self.assertEqual(result,[0,1,2,3])
        self.assertEqual(diagnostic['extension_notes'],[])
        self.assertEqual(diagnostic['unassigned_lyrics'],[])

    def test_extra_note_is_explicit_extension(self):
        ref=[n(0,'a'),n(960,'mour'),n(2880,'Dieu')]
        target=[n(0),n(960),n(1920),n(2880)]
        result,diagnostic=align_lyrics(ref,target)
        self.assertEqual(result,[0,1,None,2])
        self.assertEqual(diagnostic['extension_notes'],[2])

    def test_no_transposition_at_voice_crossing(self):
        ref=[n(0,'a'),n(480,'b'),n(960,'c')]
        target=[n(0),n(480),n(960)]
        result,_=align_lyrics(ref,target)
        self.assertEqual(result,[0,1,2])

    def test_missing_note_is_reported(self):
        ref=[n(0,'a'),n(480,'b'),n(960,'c')]
        target=[n(0),n(960)]
        _,diagnostic=align_lyrics(ref,target)
        self.assertEqual(len(diagnostic['unassigned_lyrics']),1)

if __name__=='__main__':unittest.main()

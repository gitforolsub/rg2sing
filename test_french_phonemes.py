#!/usr/bin/env python3
"""Tests des tables phonétiques partagées, sans GPU."""
import unittest
from french_phonemes import IPA, VOWELS, GLIDES
from french_align import tokenize_ipa
from suggest_espeak import phones_from_ipa

class PhonemeMapTests(unittest.TestCase):
    def test_eu_is_supported(self):
        self.assertEqual(IPA['ø'],'fr/ee')
        self.assertEqual(tokenize_ipa('djˈø'), ['fr/d','fr/y','fr/ee'])
        converted, errors=phones_from_ipa('djˈø', set(IPA.values()))
        self.assertEqual(errors,[])
        self.assertEqual(converted,['fr/d','fr/y','fr/ee'])
    def test_silent_mapping_is_unique(self):
        from french_align import IPA as A
        from suggest_espeak import IPA as B
        self.assertIs(A,B)
    def test_glide_and_affricate_distinct(self):
        self.assertIn('fr/y',GLIDES)
        self.assertNotIn('fr/j',GLIDES)  # /ʒ/ = consonne, pas /j/
        self.assertIn('fr/uh',VOWELS)
        self.assertNotIn('fr/uy',VOWELS)

if __name__=='__main__':unittest.main()

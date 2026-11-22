#!/usr/bin/env python3
"""Regression tests for Rosegarden . and + melismas; run with -v."""
import unittest
from rg2sing_bootstrap import extension_vowel, is_unvoiced_extension


class MelismaExtensionTests(unittest.TestCase):
    def test_empty_note_is_extension_candidate(self):
        self.assertTrue(is_unvoiced_extension({'syllable': ''}))
        self.assertTrue(is_unvoiced_extension({'syllable': '+'}))
        self.assertFalse(is_unvoiced_extension({'syllable': 'Sei'}))

    def test_contiguous_vowel_only(self):
        before = {'tick': 0, 'end_tick': 960, 'phonemes': ['fr/l', 'fr/ee']}
        self.assertEqual(extension_vowel(before, {'tick': 960}), 'fr/ee')
        self.assertIsNone(extension_vowel(before, {'tick': 1440}))

    def test_consonant_only_is_rejected(self):
        before = {'tick': 0, 'end_tick': 960, 'phonemes': ['fr/l']}
        self.assertIsNone(extension_vowel(before, {'tick': 960}))

    def test_repeated_extension_uses_previous_vowel(self):
        before = {'tick': 960, 'end_tick': 1920, 'phonemes': ['fr/ee']}
        self.assertEqual(extension_vowel(before, {'tick': 1920}), 'fr/ee')


if __name__ == '__main__':
    unittest.main()

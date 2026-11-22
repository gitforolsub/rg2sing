#!/usr/bin/env python3
"""Non-regression tests for SATB lyric contraction and melisma preservation."""
import unittest
from rg2sing_lyrics import align_lyrics, resolve_lyric_contractions


def ref(tick, end, text, continues=False):
    return {'tick': tick, 'end_tick': end, 'syllable': text,
            'word_continues': continues, 'phonemes': []}


def tgt(tick, end):
    return {'tick': tick, 'end': end}


class LyricContractionsTests(unittest.TestCase):
    def test_psaume23_sible_contracts_without_moving_de(self):
        reference = [ref(75840, 76800, "m’est"),
                     ref(76800, 77760, 'pos', True),
                     ref(77760, 79680, 'si', True),
                     ref(79680, 80640, 'ble'),
                     ref(80640, 81600, 'De')]
        target = [tgt(75840, 76800), tgt(76800, 77760),
                  tgt(77760, 80640), tgt(80640, 81600)]
        assigned, info = align_lyrics(reference, target)
        self.assertEqual(info['unassigned_lyrics'], [3])
        contractions, updated = resolve_lyric_contractions(reference, target, assigned, info)
        self.assertEqual(contractions[2]['syllable'], 'sible')
        self.assertFalse(contractions[2]['word_continues'])
        self.assertEqual(updated['unassigned_lyrics'], [])
        self.assertEqual(assigned[3], 4)
        self.assertEqual(updated['contracted_lyrics'][0]['source_ticks'], [77760, 79680])

    def test_unrelated_words_not_merged(self):
        reference = [ref(0, 960, 'nous'), ref(960, 1920, 'aimons'), ref(1920, 2880, 'Dieu')]
        target = [tgt(0, 1920), tgt(1920, 2880)]
        assigned, info = align_lyrics(reference, target)
        contractions, updated = resolve_lyric_contractions(reference, target, assigned, info)
        self.assertEqual(contractions, {})
        self.assertEqual(len(updated['unassigned_lyrics']), 1)

    def test_word_continuation_beyond_target_not_merged(self):
        reference = [ref(0, 960, 'si', True), ref(960, 1920, 'ble')]
        target = [tgt(0, 1440)]
        assigned, info = align_lyrics(reference, target)
        contractions, updated = resolve_lyric_contractions(reference, target, assigned, info)
        self.assertEqual(contractions, {})
        self.assertEqual(updated['unassigned_lyrics'], [1])

    def test_discontinuous_syllables_not_merged(self):
        reference = [ref(0, 960, 'si', True), ref(1440, 1920, 'ble')]
        target = [tgt(0, 1920)]
        assigned, info = align_lyrics(reference, target)
        contractions, updated = resolve_lyric_contractions(reference, target, assigned, info)
        self.assertEqual(contractions, {})
        self.assertEqual(updated['unassigned_lyrics'], [1])

    def test_original_melisma_extensions_untouched(self):
        reference = [ref(0, 960, 'a'), ref(960, 2880, 'mour'), ref(2880, 3840, 'Dieu')]
        target = [tgt(0, 960), tgt(960, 1920), tgt(1920, 2880), tgt(2880, 3840)]
        assigned, info = align_lyrics(reference, target)
        contractions, updated = resolve_lyric_contractions(reference, target, assigned, info)
        self.assertEqual(assigned, [0, 1, None, 2])
        self.assertEqual(updated['extension_notes'], [2])
        self.assertEqual(contractions, {})

    def test_multiple_syllable_contraction(self):
        reference = [ref(0, 480, 'im', True), ref(480, 960, 'pos', True),
                     ref(960, 1440, 'si', True), ref(1440, 1920, 'ble')]
        target = [tgt(0, 1920)]
        assigned, info = align_lyrics(reference, target)
        contractions, updated = resolve_lyric_contractions(reference, target, assigned, info)
        self.assertEqual(contractions[0]['syllable'], 'impossible')
        self.assertEqual(updated['unassigned_lyrics'], [])


if __name__ == '__main__':
    unittest.main()

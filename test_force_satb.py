#!/usr/bin/env python3
"""Non-régression : attribution volontaire des quatre pistes Rosegarden à SATB."""
import copy
import unittest
from rg2sing_staves import split_staff_model


def segment(track, text='Acoustic Grand Piano', tick=0, pitch=60, lyric='la'):
    return {'part': text, 'track_id': track, 'iteration': 0, 'events': [
        {'type': 'text', 'tick': tick, 'duration': 0,
         'properties': {'type': 'lyric', 'text': lyric}},
        {'type': 'note', 'tick': tick, 'duration': 480,
         'properties': {'pitch': str(pitch)}}]}


def model(ids):
    return {'tempo': [(0, 120)], 'segments': [
        segment(t, pitch=60+i) for i, t in enumerate(ids)]}


class ForceSATB(unittest.TestCase):
    def test_same_instrument_noncontiguous_unsorted(self):
        original = model([8, 0, 5, 2])
        snapshot = copy.deepcopy(original)
        score, diag = split_staff_model(original, force_satb=True)
        expected = {0: 'Soprani', 2: 'Alti', 5: 'Tenors', 8: 'Basses'}
        self.assertEqual([(s['track_id'], s['part']) for s in score['segments']],
                         [(t, expected[t]) for t in (8, 0, 5, 2)])
        self.assertEqual(diag['note_counts'], {p:1 for p in expected.values()})
        self.assertEqual(diag['layout'], 'satb-4staves')
        self.assertTrue(diag['forced_satb'])
        self.assertEqual(original, snapshot)
        self.assertEqual(score['segments'][0]['events'][0]['properties']['text'], 'la')

    def test_multiple_segments_one_track(self):
        m = model([0, 2, 5, 8])
        m['segments'].append(segment(2, text='Piano', tick=480, pitch=69))
        score, diag = split_staff_model(m, force_satb=True)
        self.assertEqual([s['part'] for s in score['segments']],
                         ['Soprani', 'Alti', 'Tenors', 'Basses', 'Alti'])
        self.assertEqual(diag['note_counts']['Alti'], 2)

    def test_reject_three_or_five_tracks(self):
        for ids in ([0, 2, 5], [0, 1, 2, 3, 4]):
            with self.subTest(ids=ids):
                with self.assertRaisesRegex(ValueError, 'exactement quatre pistes'):
                    split_staff_model(model(ids), force_satb=True)

    def test_no_force_does_not_guess(self):
        with self.assertRaisesRegex(ValueError, 'Disposition indéterminée'):
            split_staff_model(model([0, 2, 5, 8]))

    def test_reject_two_staves_override(self):
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            split_staff_model(model([0, 2, 5, 8]),
                              layout='satb-2staves', force_satb=True)

    def test_explicit_four_staves_accepts_named_subset(self):
        # Compatibilité avec le test de chronologie qui n'utilise qu'une voix.
        m = {'tempo': [(0, 120)], 'segments': [
            segment(0, text='Soprani', tick=-960, pitch=72)]}
        score, diag = split_staff_model(m, layout='satb-4staves')
        self.assertEqual(score['segments'][0]['part'], 'Soprani')
        self.assertEqual(score['segments'][0]['events'][1]['tick'], 0)
        self.assertEqual(diag['negative_tick_shift'], 960)
        self.assertEqual(diag['note_counts']['Soprani'], 1)

    def test_explicit_four_staves_rejects_unnamed_subset(self):
        with self.assertRaisesRegex(ValueError, 'Quatre voix SATB nommées'):
            split_staff_model(model([0, 2]), layout='satb-4staves')

    def test_only_noted_tracks_count(self):
        m = model([0, 2, 5, 8])
        m['segments'].append({'part':'Metronome', 'track_id': 4,
                              'iteration':0, 'events': []})
        score, diag = split_staff_model(m, force_satb=True)
        self.assertEqual(diag['track_count'], 4)
        self.assertEqual([s['part'] for s in score['segments'][:4]],
                         ['Soprani','Alti','Tenors','Basses'])


if __name__ == '__main__':
    unittest.main()

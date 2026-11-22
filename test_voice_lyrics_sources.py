#!/usr/bin/env python3
"""Tests de priorité des paroles par groupe de pupitres."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rg2sing_sync import build, read, PARTS


def piece(tenor_lyrics=True):
    def segment(part, names):
        events = []
        for idx, tick in enumerate((0, 960, 1920)):
            events.append({'tick': tick, 'duration': 960, 'type': 'note',
                           'properties': {'pitch': '60'}, 'index': idx * 10})
            if names:
                events.append({'tick': tick, 'duration': 0, 'type': 'text',
                               'properties': {'type': 'lyric', 'text': names[idx]},
                               'index': idx * 10 + 1})
        return {'part': part, 'iteration': 0, 'track_id': PARTS.index(part), 'events': events}
    return {'tempo': [(0, 120.0)], 'staff_layout': 'satb-4staves', 'segments': [
        segment('Soprani', ['Le', 'Sei-', 'gneur']),
        segment('Alti', None),
        segment('Tenors', ['Sur', "l'her-", 'be'] if tenor_lyrics else None),
        segment('Basses', None),
    ]}


class LyricsSources(unittest.TestCase):
    def run_piece(self, tenor_lyrics):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            build(piece(tenor_lyrics), work, {}, {p: {} for p in (*PARTS, 'Soprani_divisi')})
            return {part: [n['syllable'] for n in read(work / f'{part}.review.json')['notes']]
                    for part in PARTS}

    def test_distinct_soprano_tenor_sources(self):
        result = self.run_piece(True)
        self.assertEqual(result['Alti'], result['Soprani'])
        self.assertEqual(result['Tenors'], ['Sur', "l'her", 'be'])
        self.assertEqual(result['Basses'], result['Tenors'])

    def test_no_tenor_lyrics_uses_soprano(self):
        result = self.run_piece(False)
        self.assertEqual(result['Tenors'], result['Soprani'])
        self.assertEqual(result['Basses'], result['Tenors'])


if __name__ == '__main__':
    unittest.main()

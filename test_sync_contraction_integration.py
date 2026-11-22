#!/usr/bin/env python3
"""Test d'intégration sans partition réelle : import SATB et sortie review.json."""
import json
import tempfile
import unittest
from pathlib import Path
from rg2sing_sync import build, PARTS


def piece():
    def segment(part, notes, lyrics=None):
        events = []
        for i, (tick, dur, pitch) in enumerate(notes):
            if lyrics and tick in lyrics:
                events.append({'tick': tick, 'duration': 0, 'type': 'text',
                               'index': i*10,
                               'properties': {'type': 'lyric', 'text': lyrics[tick]}})
            events.append({'tick': tick, 'duration': dur, 'type': 'note',
                           'index': i*10+1, 'properties': {'pitch': str(pitch)}})
        return {'part': part, 'iteration': 0, 'track_id': PARTS.index(part), 'events': events}
    sop = [(75840,960,69),(76800,960,70),(77760,1920,70),
           (79680,960,70),(80640,960,67)]
    alt = [(75840,960,62),(76800,960,67),(77760,2880,68),
           (80640,960,67)]
    ten = [(75840,960,55),(76800,960,55),(77760,1920,55),
           (79680,960,53),(80640,960,53)]
    lyrics = {75840:'m’est',76800:'pos-',77760:'si-',79680:'ble',80640:'De'}
    return {'tempo': [(0,120.0)], 'segments': [
        segment('Soprani', sop, lyrics),
        segment('Alti', alt),
        segment('Tenors', ten, lyrics),
        segment('Basses', ten),
    ]}


class Integration(unittest.TestCase):
    def test_review_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            build(piece(), path, {}, {p:{} for p in (*PARTS,'Soprani_divisi')})
            alti = json.loads((path/'Alti.review.json').read_text())['notes']
            self.assertEqual({n['tick']:n['syllable'] for n in alti}[77760], 'sible')
            self.assertEqual({n['tick']:n['syllable'] for n in alti}[80640], 'De')
            diag = json.loads((path/'syllable_alignment.json').read_text())['Alti']
            self.assertEqual(diag['unassigned_lyrics'], [])
            self.assertEqual(diag['contracted_lyrics'][0]['merged_syllable'], 'sible')

if __name__ == '__main__':
    unittest.main()

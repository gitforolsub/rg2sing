#!/usr/bin/env python3
"""Régression : absoluteTime, segment sans endmarker, anacrouse, reprises."""
import gzip
import tempfile
import unittest
from pathlib import Path
from rg2sing import parse
from rg2sing_staves import split_staff_model


def create_rg(path, missing_endmarker):
    end = '' if missing_endmarker else ' endmarker="960"'
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<rosegarden-data version="19.12">
  <composition endMarker="4800">
    <track id="0" position="0"/>
  </composition>
  <segment track="0" label="Soprani" start="-960" repeat="true"{end}>
    <event type="note" duration="480"><property name="pitch" int="64"/></event>
    <event type="note" duration="480"><property name="pitch" int="65"/></event>
    <event type="note" absoluteTime="0" duration="960"><property name="pitch" int="67"/></event>
  </segment>
</rosegarden-data>'''
    path.write_bytes(gzip.compress(xml.encode('utf-8')))


class TestRosegardenTimeline(unittest.TestCase):
    def test_absolute_time_after_pickup_and_inferred_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'score.rg'
            create_rg(p, missing_endmarker=True)
            doc = parse(p)
            notes = [(e['tick'], int(e['properties']['pitch']))
                     for seg in doc['segments'] for e in seg['events']
                     if e['type'] == 'note']
            self.assertEqual(notes[:3], [(-960, 64), (-480, 65), (0, 67)])
            self.assertEqual(len(notes), 9)  # 3 notes x 3 reprises, no fourth
            shifted, diagnostic = split_staff_model(doc, layout='satb-4staves')
            self.assertEqual(diagnostic['negative_tick_shift'], 960)
            self.assertEqual(shifted['segments'][0]['events'][0]['tick'], 0)

    def test_explicit_endmarker_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'score.rg'
            create_rg(p, missing_endmarker=False)
            doc = parse(p)
            notes = [e for seg in doc['segments'] for e in seg['events']
                     if e['type'] == 'note']
            self.assertEqual(len(notes), 9)
            self.assertEqual([e['tick'] for e in notes[:3]], [-960, -480, 0])


if __name__ == '__main__':
    unittest.main()

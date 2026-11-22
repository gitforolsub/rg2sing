#!/usr/bin/env python3
"""Tests sans GPU, sans eSpeak ni wordfreq: frontière musicale et lexicale."""
import unittest
from french_words import reconstruct

VALUES={
    'dans':6.3, 'cette':6.3,'nuit':5.7,'les':7.0,'yeux':5.4,
    's\'accomplit':3.8,'s\'ac':2.6,'com':2.8,'plit':1.0,
    'au':6.5,'milieu':5.7,'des':6.9,'agnelles':3.2,
    'lesyeux':0.0,'cette nuit':0,'cette':6.3,'nu':3.1,'it':2.9,
}
def freq(word):return VALUES.get(word,0.0)
def n(i,s,end=None):return {'tick':i*10,'end_tick':(i+1)*10 if end is None else end,'syllable':s}

class TestFrenchWords(unittest.TestCase):
    def words(self, notes):return [x['word'] for x in reconstruct(notes,freq)]
    def test_cette_nuit(self):
        self.assertEqual(self.words([n(0,'Dans'),n(1,'cet'),n(2,'te'),n(3,'nuit')]),['dans','cette','nuit'])
    def test_accomplit_nasal(self):
        self.assertEqual(self.words([n(0,"s'ac"),n(1,'com'),n(2,'plit')]),["s'accomplit"])
    def test_liaison_words_separated(self):
        self.assertEqual(self.words([n(0,'les'),n(1,'yeux')]),['les','yeux'])
    def test_no_cross_silence(self):
        self.assertEqual(self.words([n(0,'cet',end=10),{'tick':20,'end_tick':30,'syllable':'te'}]),['cet','te'])
    def test_melisma_not_a_word(self):
        self.assertEqual(self.words([n(0,'nuit'),n(1,'+'),n(2,'les')]),['nuit','les'])
    def test_three_part_word(self):
        self.assertEqual(self.words([n(0,'au'),n(1,'mi'),n(2,'lieu')]),['au','milieu'])

if __name__=='__main__':unittest.main()

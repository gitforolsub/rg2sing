#!/usr/bin/env python3
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from french_words import reconstruct

class WordBoundaries(unittest.TestCase):
    def freq(self,x):return {'porte-clé':4.5,'porteclé':0,'tendresse':4.3,'austère':3.2,'offre':5.0}.get(x,1.0)
    def notes(self,parts):
        return [{'tick':i*480,'end_tick':(i+1)*480,'syllable':s,'word_continues':more}
                for i,(s,more) in enumerate(parts)]
    def test_three_syllables(self):
        ns=self.notes([('ten',True),('dres',True),('se',False)])
        r=reconstruct(ns,self.freq)
        self.assertEqual([(x['word'],x['start'],x['end']) for x in r],[('tendresse',0,3)])
    def test_compound(self):
        r=reconstruct(self.notes([('porte',True),('clé',False)]),self.freq)
        self.assertEqual(r[0]['word'],'porte-clé')
    def test_syllabic_continuation(self):
        r=reconstruct(self.notes([('aus',True),('tère',False)]),self.freq)
        self.assertEqual(r[0]['word'],'austère')
    def test_no_merging_across_words(self):
        r=reconstruct(self.notes([('les',False),('yeux',False)]),self.freq)
        self.assertEqual([x['word'] for x in r],['les','yeux'])
    def test_pause(self):
        ns=self.notes([('ten',True),('dres',False)])
        ns[1]['tick']=2000
        r=reconstruct(ns,self.freq)
        self.assertEqual(len(r),2)
        self.assertIn('uncertain',r[0])
    def test_blank(self):
        r=reconstruct(self.notes([('nuit',False),('',False),('où',False)]),self.freq)
        self.assertEqual([x['word'] for x in r],['nuit','où'])

    def test_word_level_bootstrap(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from rg2sing_bootstrap import bootstrap
        items=[('ten',True),('dres',True),('se',False),('of',True),('fre',False)]
        notes=[{**x,'phonemes':[],'origin':'missing'} for x in self.notes(items)]
        phones={'fr/t','fr/en','fr/d','fr/r','fr/ae','fr/s','fr/ee','fr/f','fr/oo'}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'Soprani.review.json'
            with patch('rg2sing_bootstrap.espeak_ipa',side_effect=lambda w,e:
                       {'tendresse':'tɑ̃dʁɛs','offre':'ɔfʁ'}.get(w)):
                _,done,_,_=bootstrap({'Soprani':(path,{'notes':notes})},phones,'mock',
                                      lambda w:{'tendresse':4.5,'offre':5.0}.get(w,0))
            self.assertEqual(done,5)
            self.assertEqual(notes[2]['phonemes'],['fr/s','fr/ee'])
            self.assertEqual(notes[4]['phonemes'],['fr/f','fr/r','fr/ee'])

if __name__=='__main__':unittest.main()

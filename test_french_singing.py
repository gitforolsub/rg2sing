#!/usr/bin/env python3
"""Tests de non-régression indépendants de CUDA et eSpeak."""
import unittest
from french_singing import correct_document

def note(t, s, ph):
    return {'tick':t,'syllable':s,'phonemes':list(ph),'midi':60,'start_frame':t,'end_frame':t+10}

class FrenchSingingTests(unittest.TestCase):
    def test_nasal_word(self):
        d = {'notes':[note(0,"s'ac",['fr/s','fr/ah','fr/k']),
                      note(10,'com',['fr/k','fr/oh','fr/m']),
                      note(20,'plit',['fr/p','fr/l','fr/ih'])]}
        out,c,w=correct_document(d)
        self.assertEqual(out['notes'][1]['phonemes'],['fr/k','fr/on'])
        self.assertEqual(out['notes'][0]['phonemes'],['fr/s','fr/ah'])
        self.assertEqual(len(c),2)
        self.assertEqual(d['notes'][1]['phonemes'],['fr/k','fr/oh','fr/m'])
    def test_liaison_context_only(self):
        d = {'notes':[note(0,'des',['fr/d','fr/eh']),note(10,'a',['fr/ah']),
                      note(20,'gnelles',['fr/n','fr/y','fr/ae','fr/l']),
                      note(30,'a',['fr/ah'])]}
        out,_,_=correct_document(d)
        self.assertEqual(out['notes'][1]['phonemes'],['fr/z','fr/ah'])
        self.assertEqual(out['notes'][3]['phonemes'],['fr/ah'])
    def test_les_anges_ont_no_extra_syllable(self):
        d={'notes':[note(0,'les',[]),note(10,'anges',[]),note(20,'ont',[])]}
        out,_,_=correct_document(d)
        self.assertEqual([n['phonemes'] for n in out['notes']],
                         [['fr/l','fr/eh'],['fr/z','fr/en'],['fr/j','fr/on']])
    def test_schwa_and_unrecognized_consonants(self):
        d={'notes':[note(0,'bre',['fr/b','fr/r']),note(10,'zzz',['fr/z'])]}
        out,_,warnings=correct_document(d)
        self.assertEqual(out['notes'][0]['phonemes'],['fr/b','fr/r','fr/ee'])
        self.assertEqual(len(warnings),1)
    def test_au_closed_o(self):
        d={'notes':[note(0,'Au',['fr/oo']),note(10,'plus',['fr/p','fr/l','fr/uh']),
                    note(20,'auS',['fr/oo']),note(30,'No',['fr/n','fr/oo'])]}
        out,changes,warnings=correct_document(d)
        self.assertEqual(out['notes'][0]['phonemes'],['fr/oh'])
        self.assertEqual(out['notes'][2]['phonemes'],['fr/oh'])
        self.assertEqual(out['notes'][3]['phonemes'],['fr/n','fr/oo'])
        self.assertEqual(len(changes),2)
        self.assertFalse(warnings)
    def test_bergers_not_bergeres(self):
        d={'notes':[note(0,'les',['fr/l','fr/eh']),
                    note(10,'ber',['fr/b','fr/ae','fr/r']),
                    note(20,'gers',['fr/j','fr/ae','fr/r']),
                    note(30,'sont',['fr/s','fr/on'])]}
        out,changes,warnings=correct_document(d)
        self.assertEqual(out['notes'][2]['phonemes'],['fr/j','fr/eh'])
        self.assertEqual(len(changes),1)
        self.assertFalse(warnings)
        out2,c2,_=correct_document(out)
        self.assertEqual(c2,[])
    def test_long_vowel_glides_preserved(self):
        d={'notes':[note(0,'nuit',['fr/n','fr/uy','fr/ih']),
                    note(10,'ciel',['fr/s','fr/y','fr/ae','fr/l'])]}
        out,c,_=correct_document(d)
        self.assertEqual(c,[])
        self.assertEqual(out,d)

    def test_generic_liaison_les_yeux(self):
        d={'notes':[note(0,'sous',['fr/s','fr/ou']),
                    note(10,'les',['fr/l','fr/eh']),
                    note(20,'yeux',['fr/y','fr/ee']),
                    note(30,'de',['fr/d','fr/ee'])]}
        out,changes,warnings=correct_document(d)
        self.assertEqual(out['notes'][2]['phonemes'],['fr/z','fr/y','fr/ee'])
        self.assertEqual(len(changes),1)
        out2,c2,w2=correct_document(out)
        self.assertEqual(c2,[])
        self.assertFalse(warnings+w2)

    def test_generic_liaison_des_amis_and_no_z_before_consonant(self):
        d={'notes':[note(0,'des',['fr/d','fr/eh']),
                    note(10,'amis',['fr/ah','fr/m','fr/ih']),
                    note(20,'les',['fr/l','fr/eh']),
                    note(30,'bergers',['fr/b','fr/ae','fr/r','fr/j','fr/eh'])]}
        out,changes,_=correct_document(d)
        self.assertEqual(out['notes'][1]['phonemes'][0],'fr/z')
        self.assertEqual(out['notes'][3]['phonemes'][0],'fr/b')
        self.assertEqual(len(changes),1)

    def test_no_liaison_across_pause_or_exception(self):
        d={'notes':[note(0,'les',['fr/l','fr/eh']),
                    note(20,'yeux',['fr/y','fr/ee']),
                    note(30,'les',['fr/l','fr/eh']),
                    note(40,'huit',['fr/uy','fr/ih','fr/t'])]}
        out,changes,_=correct_document(d)
        self.assertEqual(changes,[])
        self.assertEqual(out['notes'][1]['phonemes'],['fr/y','fr/ee'])

if __name__ == '__main__':unittest.main()

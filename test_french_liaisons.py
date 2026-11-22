#!/usr/bin/env python3
"""Tests de liaison en contexte, sans GPU ou service réseau."""
import unittest
from french_liaisons import apply_liaisons
from french_singing import correct_document

def n(t, word, phones, *, duration=10, continues=False, origin='espeak_word_proposed'):
    return {'tick':t,'end_tick':t+duration,'start_frame':t,'end_frame':t+duration,
            'syllable':word,'word_continues':continues,'phonemes':list(phones),
            'midi':60,'origin':origin}

class FrenchLiaisonsTests(unittest.TestCase):
    def test_permet_ainsi_continuous(self):
        doc={'notes':[n(0,'permet',['fr/p','fr/ae','fr/r','fr/m','fr/ae']),
                      n(10,'ainsi',['fr/in','fr/s','fr/ih'])]}
        result,changes,_=correct_document(doc)
        self.assertEqual(result['notes'][1]['phonemes'][0], 'fr/t')
        self.assertEqual(len(changes),1)
        result2,changes2,_=correct_document(result)
        self.assertFalse(changes2)

    def test_permet_ainsi_pause(self):
        doc={'notes':[n(0,'permet',['fr/p','fr/ae','fr/r','fr/m','fr/ae']),
                      n(12,'ainsi',['fr/in','fr/s','fr/ih'])]}
        result,changes,_=correct_document(doc)
        self.assertFalse(changes)
        self.assertEqual(result['notes'][1]['phonemes'][0],'fr/in')

    def test_soit_au(self):
        source={'notes':[n(0,'soit',['fr/s','fr/w','fr/ah']),n(10,'au',['fr/oh']),n(20,'Père',['fr/p','fr/ae','fr/r'])]}
        result,changes,warnings=correct_document(source)
        self.assertEqual(result['notes'][1]['phonemes'],['fr/t','fr/oh'])
        self.assertEqual(len(changes),1)
        self.assertEqual(warnings,[])
        self.assertEqual(source['notes'][1]['phonemes'],['fr/oh'])
        result2,changes2,_=correct_document(result)
        self.assertEqual(changes2,[])
    def test_son_amour(self):
        result,changes,_=correct_document({'notes':[n(0,'son',['fr/s','fr/on']),n(10,'amour',['fr/ah','fr/m','fr/ou','fr/r'])]})
        self.assertEqual(result['notes'][1]['phonemes'][0],'fr/n')
        self.assertEqual(len(changes),1)
    def test_link_z_and_context_in_word(self):
        result,_,_=correct_document({'notes':[n(0,'les',['fr/l','fr/eh']),n(10,'yeux',['fr/y','fr/ee'])]})
        self.assertEqual(result['notes'][1]['phonemes'][:2],['fr/z','fr/y'])
        result,changes,_=correct_document({'notes':[n(0,'of',['fr/oo'],continues=True),n(10,'fre',['fr/f','fr/r','fr/ee'])]})
        self.assertFalse(any(x['rule'].startswith('liaison_') for x in changes))
    def test_no_pause(self):
        result,changes,_=correct_document({'notes':[n(0,'soit',['fr/s','fr/w','fr/ah']),n(20,'au',['fr/oh'])]})
        self.assertEqual(result['notes'][1]['phonemes'],['fr/oh'])
        self.assertFalse(changes)
    def test_no_liaison_after_et_or_huit(self):
        result,changes,_=correct_document({'notes':[n(0,'et',['fr/eh']),n(10,'elle',['fr/ae','fr/l']),n(20,'les',['fr/l','fr/eh']),n(30,'huit',['fr/uy','fr/ih','fr/t'])]})
        self.assertFalse(changes)
    def test_no_duplicate_next_or_prior(self):
        result,changes,_=correct_document({'notes':[n(0,'son',['fr/s','fr/on']),n(10,'amour',['fr/n','fr/ah','fr/m','fr/ou','fr/r'])]})
        self.assertFalse(changes)
        result,changes,warnings=correct_document({'notes':[n(0,'soit',['fr/s','fr/w','fr/ah','fr/t']),n(10,'au',['fr/oh'])]})
        self.assertFalse(changes)
        self.assertEqual(len(warnings),1)
    def test_preserve_manual(self):
        result,changes,warnings=correct_document({'notes':[n(0,'son',['fr/s','fr/on']),n(10,'amour',['fr/ah','fr/m'],origin='manual_correction')]})
        self.assertFalse(changes)
        self.assertEqual(len(warnings),1)
        self.assertEqual(result['notes'][1]['phonemes'],['fr/ah','fr/m'])
    def test_no_liaison_other(self):
        result,changes,_=correct_document({'notes':[n(0,'sur',['fr/s','fr/uh','fr/r']),n(10,'une',['fr/uh','fr/n'])]})
        self.assertFalse(changes)

if __name__=='__main__':unittest.main()

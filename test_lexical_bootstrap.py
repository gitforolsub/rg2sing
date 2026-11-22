import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rg2sing_bootstrap import bootstrap

class LexicalBootstrapTests(unittest.TestCase):
    def test_replace_old_espeak_fils_for_all_parts(self):
        with tempfile.TemporaryDirectory() as td:
            docs={}
            for part in ('Soprani','Alti','Tenors','Basses'):
                doc={'notes':[
                    dict(tick=0,end_tick=960,syllable='au',word_continues=False,phonemes=['fr/oh'],origin='espeak_word_proposed'),
                    dict(tick=960,end_tick=1920,syllable='Fils',word_continues=False,phonemes=['fr/f','fr/ih','fr/l'],origin='espeak_word_proposed'),
                ]}
                docs[part]=(Path(td)/(part+'.review.json'),doc)
            inv={'fr/oh','fr/f','fr/ih','fr/l','fr/s'}
            with patch('rg2sing_bootstrap.espeak_ipa',return_value='fil'):
                report, *_ = bootstrap(docs,inv,'unused',lambda w: 5.0)
            for _,doc in docs.values():
                self.assertEqual(doc['notes'][1]['phonemes'],['fr/f','fr/ih','fr/s'])
                self.assertEqual(doc['notes'][1]['origin'],'lexical_context_proposed')

    def test_manual_correction_protected(self):
        with tempfile.TemporaryDirectory() as td:
            doc={'notes':[
                dict(tick=0,end_tick=960,syllable='au',word_continues=False,phonemes=['fr/oh'],origin='espeak_word_proposed'),
                dict(tick=960,end_tick=1920,syllable='Fils',word_continues=False,phonemes=['fr/f','fr/ih','fr/l'],origin='manual_correction'),
            ]}
            with patch('rg2sing_bootstrap.espeak_ipa',return_value='fil'):
                bootstrap({'Soprani':(Path(td)/'review.json',doc)}, {'fr/oh','fr/f','fr/ih','fr/l','fr/s'}, 'unused', lambda w:5.0)
            self.assertEqual(doc['notes'][1]['phonemes'],['fr/f','fr/ih','fr/l'])

if __name__ == '__main__':
    unittest.main()

import unittest
from unittest.mock import patch
from rg2sing_bootstrap import align_sung_word

INVENTORY={'fr/l','fr/ou','fr/en','fr/j','fr/ee','fr/v','fr/ih','fr/eh','fr/r','fr/on','fr/s','fr/d','fr/t'}

def word(text,syllables,uncertain=None,zipf=4.0):
    return {'word':text,'source':'rosegarden_hyphens','uncertain':uncertain,'zipf':zipf,
            'syllables':syllables}

class SungFallback(unittest.TestCase):
    def test_louange_spoken_fails_sung_succeeds(self):
        w=word('louange',['Lou','an','ge'])
        with patch('rg2sing_bootstrap.espeak_ipa',side_effect=lambda text,_: {
            'louange':'lwɑ̃ʒ', 'Lou-an-ge':'lˈuˈɑ̃ʒə-'}[text]):
            aligned,ipa,reason=align_sung_word(w,w['syllables'],'fake',INVENTORY)
        self.assertEqual(aligned,[['fr/l','fr/ou'],['fr/en'],['fr/j','fr/ee']])
        self.assertIn('lecture chantée',reason)

    def test_vie_error_not_auto_repaired(self):
        w=word('vie',['vi','e'])
        with patch('rg2sing_bootstrap.espeak_ipa',side_effect=lambda text,_: {
            'vie':'vi','vi-e':'vi'}[text]):
            aligned,ipa,reason=align_sung_word(w,w['syllables'],'fake',INVENTORY)
        self.assertIsNone(aligned)
        self.assertIn('noyaux',reason)

    def test_incomplete_word_not_repaired(self):
        w=word('vi',['vi'],uncertain='mot interrompu après un trait d’union')
        with patch('rg2sing_bootstrap.espeak_ipa',return_value='vi'):
            aligned,_,_=align_sung_word(w,w['syllables'],'fake',INVENTORY)
        self.assertIsNone(aligned)

    def test_plain_word_takes_precedence(self):
        w=word('louange',['Lou','an','ge'])
        with patch('rg2sing_bootstrap.espeak_ipa',return_value='lˈuˈɑ̃ʒə-') as fake:
            aligned,_,_=align_sung_word(w,w['syllables'],'fake',INVENTORY)
        self.assertEqual(len(aligned),3)
        self.assertEqual(fake.call_count,1)

if __name__=='__main__':unittest.main()

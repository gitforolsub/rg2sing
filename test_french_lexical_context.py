import unittest
from french_lexical_context import resolve

class LexicalContextTests(unittest.TestCase):
    def test_au_fils(self):
        r = resolve('Fils', previous='au')
        self.assertEqual(r.status, 'resolved')
        self.assertEqual(r.phonemes, ('fr/f','fr/ih','fr/s'))

    def test_un_fils(self):
        self.assertEqual(resolve('fils', previous='un').phonemes[-1], 'fr/s')

    def test_plural_ambiguous(self):
        r=resolve('fils', previous='grands', preceding=('le','tailleur','avait','deux'))
        self.assertEqual(r.status, 'ambiguous')
        self.assertIsNone(r.phonemes)

    def test_plural_des(self):
        self.assertEqual(resolve('fils', previous='des').status, 'ambiguous')

    def test_other_words_no_changes(self):
        self.assertEqual(resolve('fille', previous='une').status, 'none')

if __name__ == '__main__':
    unittest.main()

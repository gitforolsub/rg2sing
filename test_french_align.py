#!/usr/bin/env python3
"""Tests unitaires, hors GPU, hors eSpeak, hors réseau."""
import unittest
from french_align import tokenize_ipa, align_word, align_document, VOWELS


def note(t, s, phonemes=None, origin='lexicon_proposed'):
    return {'tick':t,'end_tick':t+10,'syllable':s,'phonemes':phonemes or [],'origin':origin}


def word(start,syllables,ipa):
    return {'start':start,'end':start+len(syllables),'word':''.join(syllables),
            'zipf':4.5,'syllables':syllables,'ticks':[start*10+i*10 for i in range(len(syllables))], 'ipa':ipa}


class AlignTests(unittest.TestCase):
    def test_espeak_hyphen(self):
        self.assertEqual(tokenize_ipa('lˈe-'), ['fr/l','fr/eh'])
        self.assertEqual(tokenize_ipa('sakɔ̃plˈi'), ['fr/s','fr/ah','fr/k','fr/on','fr/p','fr/l','fr/ih'])
    def test_espeak_nuit_glide(self):
        self.assertEqual(align_word('nuit', ['nuit'], 'nyˈi'),
                         [['fr/n','fr/uy','fr/ih']])
    def test_lui_glide(self):
        self.assertEqual(align_word('lui', ['lui'], 'lyˈi'),
                         [['fr/l','fr/uy','fr/ih']])
    def test_puissance_glide(self):
        self.assertEqual(align_word('puissance', ['puis','sance'], 'pyisɑ̃s'),
                         [['fr/p','fr/uy','fr/ih'],['fr/s','fr/en','fr/s']])
    def test_vie_score_not_silently_repaired(self):
        with self.assertRaisesRegex(ValueError, 'vérifier la partition'):
            align_word('vie',['vi','e'],'vi')
    def test_milieu_orthographic_onset(self):
        self.assertEqual(align_word('milieu',['mi','lieu'],'miljˈø'),
                         [['fr/m','fr/ih'],['fr/l','fr/y','fr/ee']])
    def test_existing_liaison_preserved(self):
        notes=[note(0,'les',['fr/l','fr/eh'],'reference_verified'),
               note(10,'yeux',['fr/z','fr/y','fr/ee'])]
        words=[word(0,['les'],'le'),word(1,['yeux'],'jø')]
        out,changes,issues,events=align_document({'notes':notes},words)
        self.assertEqual(out['notes'][1]['phonemes'][0],'fr/z')
    def test_existing_syllabic_onset_preserved(self):
        notes=[note(0,'les',['fr/l','fr/eh']),
               note(10,'anges',['fr/z','fr/en']),
               note(20,'ont',['fr/j','fr/on'])]
        words=[word(0,['les'],'le'),word(1,['anges'],'ɑ̃ʒ'),word(2,['ont'],'ɔ̃')]
        out,changes,issues,events=align_document({'notes':notes},words)
        self.assertEqual(out['notes'][1]['phonemes'],['fr/z','fr/en'])
        self.assertEqual(out['notes'][2]['phonemes'],['fr/j','fr/on'])
    def test_nasal(self):
        self.assertEqual(align_word("s'accomplit", ["s'ac",'com','plit'], 'sakɔ̃pli'),
                         [['fr/s','fr/ah'],['fr/k','fr/on'],['fr/p','fr/l','fr/ih']])
    def test_austere_s_retained(self):
        result=align_word('austère',['aus','tère'],'ostɛʁ')
        self.assertEqual(result,[['fr/oh'],['fr/s','fr/t','fr/ae','fr/r']])
        self.assertEqual(sum(len(x) for x in result),5)
    def test_bergers(self):
        self.assertEqual(align_word('bergers',['ber','gers'],'bɛʁʒe'),
                         [['fr/b','fr/ae','fr/r'],['fr/j','fr/eh']])
    def test_les_yeux(self):
        notes=[note(0,'les'),note(10,'yeux')]
        doc={'notes':notes}
        ws=[word(0,['les'],'le'),word(1,['yeux'],'jø')]
        out,changes,issues,events=align_document(doc,ws)
        self.assertFalse(issues)
        self.assertEqual(out['notes'][1]['phonemes'][0],'fr/z')
        self.assertEqual(out['notes'][1]['phonemes'][1],'fr/y')
        self.assertEqual(len(events),1)
    def test_cet_enfant_t_moved(self):
        notes=[note(0,'cet'),note(10,'en'),note(20,'fant')]
        ws=[word(0,['cet'],'sɛt'),word(1,['en','fant'],'ɑ̃fɑ̃')]
        out,changes,issues,events=align_document({'notes':notes},ws)
        self.assertFalse(issues)
        self.assertEqual([n['phonemes'] for n in out['notes']],
                         [['fr/s','fr/ae'],['fr/t','fr/en'],['fr/f','fr/en']])
    def test_invariant(self):
        words=[('saccomplit',['sac','com','plit'],'sakɔ̃pli'),
               ('austere',['aus','tère'],'ostɛʁ'),
               ('nuit',['nuit'],'nɥi')]
        for name,syll,ipa in words:
            got=align_word(name,syll,ipa)
            self.assertEqual(sum(len(x) for x in got),len(tokenize_ipa(ipa)))
            self.assertTrue(all(any(p in VOWELS for p in x) for x in got))
    def test_sung_schwa_from_musical_note(self):
        self.assertEqual(align_word('brebis',['bre','bis'],'bʁbi'),
                         [['fr/b','fr/r','fr/ee'],['fr/b','fr/ih']])
    def test_mismatch_requires_review(self):
        with self.assertRaisesRegex(ValueError,'noyaux'):
            align_word('roman',['ro','man','a'],'ʁomɑ̃')
    def test_unrecognized_fails(self):
        with self.assertRaisesRegex(ValueError,'non pris en charge'):
            align_word('test',['test'],'tɐst')
    def test_verified_not_overwritten(self):
        notes=[note(0,'aus',['fr/oh'],'reference_verified'),note(10,'tère',['fr/t','fr/ae','fr/r'])]
        ws=[word(0,['aus','tère'],'ostɛʁ')]
        out,changes,issues,_=align_document({'notes':notes},ws)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['decision'], 'safe')
    def test_austere_protected_correct_vowel_is_anchor(self):
        # Note 'aus' validée : ne pas la toucher, mais restaurer le /s/ manquant.
        notes=[note(0,'aus',['fr/oh'],'reference_verified'),
               note(10,'tère',['fr/t','fr/ae','fr/r'])]
        out,changes,issues,_=align_document({'notes':notes},[word(0,['aus','tère'],'ostɛʁ')])
        self.assertEqual(out['notes'][0]['phonemes'], ['fr/oh'])
        self.assertEqual(out['notes'][1]['phonemes'], ['fr/s','fr/t','fr/ae','fr/r'])
        self.assertEqual([c['decision'] for c in changes], ['safe'])

    def test_austere_vowel_mismatch_is_not_safe(self):
        notes=[note(0,'aus',['fr/oo'],'reference_verified'),
               note(10,'tère',['fr/t','fr/ae','fr/r'])]
        _,changes,_,_=align_document({'notes':notes},[word(0,['aus','tère'],'ostɛʁ')])
        self.assertFalse(any(c['decision']=='safe' for c in changes))

    def test_protected_syllable_does_not_get_overwritten(self):
        notes=[note(0,'aus',['fr/oh'],'reference_verified'),
               note(10,'tère',['fr/t','fr/ae','fr/r'],'manual_correction')]
        _,changes,_,_=align_document({'notes':notes},[word(0,['aus','tère'],'ostɛʁ')])
        self.assertFalse(any(c['decision']=='safe' for c in changes))

    def test_no_duplicate_transferred_t(self):
        notes=[note(0,'cet',['fr/s','fr/ae','fr/t']),
               note(10,'en',['fr/en']),note(20,'fant',['fr/f','fr/en'])]
        ws=[word(0,['cet'],'sɛt'),word(1,['en','fant'],'ɑ̃fɑ̃')]
        _,changes,_,_=align_document({'notes':notes},ws)
        self.assertFalse(any(c['decision']=='safe' for c in changes if c['tick']==10))

    def test_pause_no_liaison(self):
        notes=[note(0,'les'),note(20,'yeux')]
        ws=[{'start':0,'end':1,'word':'les','zipf':5,'syllables':['les'],'ticks':[0],'ipa':'le'},
            {'start':1,'end':2,'word':'yeux','zipf':5,'syllables':['yeux'],'ticks':[20],'ipa':'jø'}]
        out,changes,issues,events=align_document({'notes':notes},ws)
        self.assertEqual(out['notes'][1]['phonemes'][0],'fr/y')
        self.assertFalse(events)


    def test_safe_initial_consonant(self):
        from french_align import safe_insertion
        self.assertTrue(safe_insertion(['fr/ah'], ['fr/z','fr/ah']))
        self.assertTrue(safe_insertion(['fr/t','fr/ae'], ['fr/s','fr/t','fr/ae']))

    def test_reject_replace_or_remove(self):
        from french_align import safe_insertion
        self.assertFalse(safe_insertion(['fr/ah'], ['fr/ae']))
        self.assertFalse(safe_insertion(['fr/r','fr/ah'], ['fr/ah']))
        self.assertFalse(safe_insertion(['fr/ah'], ['fr/ah','fr/s']))
        self.assertFalse(safe_insertion(['fr/ah'], ['fr/y','fr/ah']))

    def test_mixed_word_group_review(self):
        from french_align import classify_changes
        notes=[note(0,'aus',['fr/oo']),note(10,'tère',['fr/t','fr/ae','fr/r'])]
        changes=[{'tick':0,'before':['fr/oo'],'after':['fr/oh']},
                 {'tick':10,'before':['fr/t','fr/ae','fr/r'],
                  'after':['fr/s','fr/t','fr/ae','fr/r']}]
        classify_changes(notes,changes,[word(0,['aus','tère'],'ostɛʁ')],[])
        self.assertEqual([c['decision'] for c in changes], ['review','review'])

    def test_insertion_word_group_safe(self):
        from french_align import classify_changes
        notes=[note(0,'en',['fr/en']),note(10,'fant',['fr/f','fr/en'])]
        changes=[{'tick':0,'before':['fr/en'],'after':['fr/t','fr/en']}]
        classify_changes(notes,changes,[word(0,['en','fant'],'ɑ̃fɑ̃')],[])
        self.assertEqual(changes[0]['decision'],'safe')


if __name__=='__main__':unittest.main()


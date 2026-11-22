#!/usr/bin/env python3
"""rg2sing 0.9.3 : amorçage d'une nouvelle composition à partir des MOTS.

Priorité aux frontières explicites de Rosegarden (word_continues), à défaut
à la reconstruction heuristique préexistante. eSpeak est exécuté uniquement
localement. Les cas ambigus restent sans phonèmes et sont diagnostiqués.
"""
import argparse
import csv
import json
import shutil
from pathlib import Path

from french_words import PARTS, reconstruct, espeak_ipa, clean
from french_align import align_word, VOWELS
from suggest_espeak import phones_from_ipa
from french_lexical_context import resolve as resolve_lexical

ROOT = Path('/models/UFR-V1.0/UFR-V1.0')


def load(p):
    return json.loads(p.read_text(encoding='utf-8'))


def save(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def align_sung_word(w, syllables, engine, inventory):
    """Aligner un mot en privilégiant son orthographe, avec repli musical.

    eSpeak peut produire une prononciation parlée contractée du mot soudé,
    mais une articulation explicite quand les syllabes lui sont fournies
    avec des tirets. Le repli n'est autorisé que si l'alignement est complet,
    compatible avec l'inventaire et sans inventer de syllabe.
    """
    word = w['word']
    if w.get('uncertain') not in (None, 'orthographe composée ambiguë'):
        return None, None, w['uncertain']
    ipa = espeak_ipa(word, engine)
    attempts = []

    def test(spelling, raw_ipa, source):
        if not raw_ipa:
            attempts.append(f'{source}: IPA indisponible')
            return None
        try:
            proposed = align_word(word, syllables, raw_ipa)
            missing = sorted({p for row in proposed for p in row if p not in inventory})
            if missing:
                raise ValueError('phonèmes absents de Millefeuille: ' + ', '.join(missing))
            if len(proposed) != len(syllables) or any(not row for row in proposed):
                raise ValueError('alignement incomplet')
            return proposed
        except ValueError as exc:
            attempts.append(f'{source}: {exc}')
            return None

    aligned = test(word, ipa, 'mot entier')
    if aligned is not None:
        # Les tirets Rosegarden signalent d'abord une continuité musicale ;
        # une graphie soudée attestée est prioritaire sur l'hypothèse composée.
        # Une fréquence lexicale n'est pas une preuve phonétique : les formes
        # fléchies rares (p. ex. errons) peuvent être absentes de wordfreq.
        # Accepter le mot entier lorsque la segmentation musicale et les
        # phonèmes passent les contrôles, malgré la graphie hypothétique.
        return aligned, ipa, ''

    # Un repli chanté n'est possible que pour un mot polysyllabique avec
    # frontières explicites et réellement continu, jamais sur un mélisme.
    if (len(syllables) >= 2 and w.get('source') == 'rosegarden_hyphens'
            and not w.get('uncertain') and w.get('zipf', 0) > 0):
        sung_spelling = '-'.join(syllables)
        sung_ipa = espeak_ipa(sung_spelling, engine)
        if sung_spelling.casefold() != word.casefold():
            candidate = test(sung_spelling, sung_ipa, 'syllabation chantée')
            if candidate is not None:
                return candidate, sung_ipa, 'lecture chantée après échec du mot soudé'

    return None, ipa, '; '.join(attempts) or 'prononciation indisponible'




def is_unvoiced_extension(note):
    """Signe + ou note sans nouveau texte ; ne pas traiter les vraies syllabes."""
    return str(note.get('syllable', '')).strip() in ('', '+')


def extension_vowel(previous, current):
    """Trouver la voyelle tenue uniquement si les deux notes sont jointives."""
    if previous is None or int(previous.get('end_tick', -1)) != int(current.get('tick', -2)):
        return None
    return next((ph for ph in reversed(previous.get('phonemes') or []) if ph in VOWELS), None)

def bootstrap(docs, inventory, engine, frequency):
    report=[]
    word_ok=isolated_ok=0
    blocked={}
    for part,(path,doc) in docs.items():
        notes=doc['notes']
        words=reconstruct(notes,frequency)
        covered=set()
        # Première passe : TOUJOURS consulter le mot complet, avant la syllabe.
        for wi,w in enumerate(words):
            a,b=w['start'],w['end']
            covered.update(range(a,b))
            syllables=[str(n.get('syllable','')) for n in notes[a:b]]
            status='review';reason=''
            aligned,ipa,reason=align_sung_word(w,syllables,engine,inventory)
            # Intervenir APRÈS la reconstruction du mot, mais AVANT d'accepter
            # la prononciation proposée par eSpeak. Ne pas inférer le sens d'un
            # homographe à partir de sa seule graphie.
            previous = words[wi-1]['word'] if wi else None
            lexical = resolve_lexical(w['word'], previous=previous)
            lexical_resolved = False
            if lexical.status == 'resolved':
                if len(syllables) == 1 and all(ph in inventory for ph in lexical.phonemes):
                    aligned = [list(lexical.phonemes)]
                    ipa = 'fis'  # uniquement pour le diagnostic, pas pour eSpeak
                    reason = lexical.reason
                    lexical_resolved = True
                else:
                    aligned = None
                    reason = 'lecture lexicale non alignable sur les notes'
            elif lexical.status == 'ambiguous':
                aligned = None
                reason = lexical.reason
            if (not lexical_resolved and w.get('uncertain') and
                    w['uncertain'] != 'orthographe composée ambiguë'):
                aligned=None
                reason=w['uncertain']
            if aligned is not None:
                if any(notes[i].get('phonemes') and str(notes[i].get('origin','')).startswith(('manual','reference_verified'))
                       and notes[i]['phonemes']!=aligned[i-a] for i in range(a,b)):
                    reason='phonèmes déjà validés: désaccord avec eSpeak'
                else:
                    for i,phones in zip(range(a,b),aligned):
                        n=notes[i]
                        if (not n.get('phonemes') or n.get('origin') in
                                ('espeak_isolated_proposed','lexicon_proposed',
                                 'missing','espeak_word_proposed')):
                            n['phonemes']=phones
                            n['origin']='lexical_context_proposed' if lexical_resolved else 'espeak_word_proposed'
                            word_ok+=1
                    status='proposed_word'
            report.append({'part':part,'tick':notes[a]['tick'],'word':w['word'],
                           'syllables':' | '.join(syllables),'ipa':ipa or '',
                           'phonemes':' | '.join(' '.join(x) for x in aligned) if aligned else '',
                           'status':status,'details':reason})
        # Deuxième passe : seulement les notes hors regroupement lexical,
        # et les mots MONOSYLLABIQUES non résolus. Jamais des fragments d'un
        # mot polysyllabique refusé : la lecture isolée serait trompeuse.
        simple_indices={w['start'] for j,w in enumerate(words)
                        if w['end']==w['start']+1 and not w.get('uncertain')
                        and resolve_lexical(w['word'],
                              previous=words[j-1]['word'] if j else None).status != 'ambiguous'}
        for i,n in enumerate(notes):
            if n.get('phonemes'):continue
            key=clean(str(n.get('syllable','')).strip())
            if not key or key=='+':continue
            if i not in simple_indices:continue
            ipa=espeak_ipa(key,engine)
            phones,issues=phones_from_ipa(ipa or '',inventory)
            if phones and not issues and any(p in VOWELS for p in phones):
                n['phonemes']=phones
                n['origin']='espeak_isolated_proposed'
                isolated_ok+=1
            else:
                blocked[(part,n['tick'])]='; '.join(issues) if issues else 'prononciation isolée indécidable'
        # Les marqueurs + et les notes sans texte explicite peuvent désigner
        # une continuation de voyelle (p. ex. « Le . Sei- » dans Rosegarden).
        # Jamais de nouvelle consonne sur cette note ; ne rien inventer si
        # une pause ou une syllabe précédente non résolue empêche l'inférence.
        for i, n in enumerate(notes):
            if not is_unvoiced_extension(n) or n.get('phonemes'):
                continue
            previous = notes[i - 1] if i else None
            vowel = extension_vowel(previous, n)
            if vowel is None:
                blocked[(part, n['tick'])] = 'prolongation sans voyelle précédente contiguë identifiable'
                continue
            n['phonemes'] = [vowel]
            n['origin'] = 'melisma_vowel_extension_proposed'
            n['melisma_of_tick'] = previous.get('melisma_of_tick', previous['tick'])
        save(path,doc)
    return report,word_ok,isolated_ok,blocked


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.epilog = 'Amorçage phonétique local eSpeak-NG : remplir les revues à partir des mots reconstruits, sans modifier le fichier .rg.'
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--root',type=Path,default=ROOT)
    a=p.parse_args()
    engine=shutil.which('espeak-ng') or shutil.which('espeak')
    if not engine:p.error('Installer espeak-ng dans le conteneur')
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        p.error('Installer wordfreq : /opt/venv/bin/pip install wordfreq')
    inventory=set(load(a.root/'0_CORE/dsacoustic/millefeuille_v001.phonemes.json'))
    docs={}
    for part in PARTS:
        path=a.work/f'{part}.review.json'
        if path.exists():docs[part]=(path,load(path))
    if not docs:p.error(f'Aucun fichier de révision dans {a.work}')
    def freq(w):return zipf_frequency(w,'fr',wordlist='best')
    report,word_ok,isolated_ok,blocked=bootstrap(docs,inventory,engine,freq)
    reportpath=a.work/'bootstrap_espeak.csv'
    with reportpath.open('w',encoding='utf-8',newline='') as out:
        wr=csv.DictWriter(out,fieldnames=['part','tick','word','syllables','ipa','phonemes','status','details'],delimiter=';')
        wr.writeheader();wr.writerows(report)
    # Le lexique de diagnostic est un reflet des syllabes présentes, même
    # lorsqu'une prononciation n'est pas disponible. Pas de faux "0 manquante".
    lexpath=a.work/'lexicon.json'
    lex=load(lexpath) if lexpath.exists() else {}
    for _,doc in docs.values():
        for n in doc['notes']:
            k=clean(str(n.get('syllable','')).strip())
            if k and k!='+':
                lex.setdefault(k,[])
                if n.get('phonemes') and not lex[k]:lex[k]=n['phonemes'][:]
    save(lexpath,lex)
    missing={name:sum(not n.get('phonemes') for n in doc['notes']) for name,(_,doc) in docs.items()}
    melismas={name:sum(not n.get('phonemes') and clean(str(n.get('syllable','')).strip()) in ('','+') for n in doc['notes']) for name,(_,doc) in docs.items()}
    print('Amorçage contextuel :',word_ok,'notes par mot entier,',isolated_ok,'notes isolées')
    print('Sans texte / marqueurs de mélisme à examiner séparément :',melismas)
    print('Notes sans phonèmes (y compris mélismes non résolus) :',missing)
    print('Rapport :',reportpath)

if __name__=='__main__':main()

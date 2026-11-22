#!/usr/bin/env python3
"""Liaisons françaises contrôlées par mots, phonèmes et continuité musicale.

Module autonome sans accès réseau. Les règles ici sont volontairement fermées :
seules des classes grammaticales à liaison stable sont automatisées. Les
liaisons facultatives et les ambiguïtés sémantiques restent à expertiser.
"""
from __future__ import annotations
import argparse
import copy
import csv
import datetime
import json
import re
import shutil
from pathlib import Path

from french_phonemes import VOWELS, GLIDES
from french_words import reconstruct, clean

PARTS = ('Soprani','Alti','Tenors','Basses','Soprani_divisi')
# Le mot précédent est déjà identifié par les tirets de Rosegarden.
# On n'ajoute donc pas de liaison dans un mot (p. ex. "of- | fre").
LINK_Z = frozenset(('les','des','mes','tes','ses','ces','nos','vos','leurs',
                    'aux','deux','trois','nous','vous','ils','elles'))
LINK_N = frozenset(('un','mon','ton','son','on','en'))
# 'permet' : liaison facultative en parole, retenue ici pour diction chorale soignée.
LINK_T = frozenset(('soit','est','sont','quand','permet'))
# Ces listes d'exceptions sont minimales : l'analyse de l'h aspiré exige
# ultérieurement un véritable lexique. Refuser plutôt qu'imposer une liaison
# dans les cas connus de blocage.
BLOCKED_ONSETS = frozenset(('huit','huitième','onze','onzième','haricot','héros',
                            'haine','haut','haute','honte','hasard'))
NO_LINK_PREV = frozenset(('et',))
ONSET_PHONES = frozenset(VOWELS | GLIDES)
PUNCT = re.compile(r'[.,;:!?…]$')


def word_text(word):
    return clean(word.get('word','')).replace('’', "'")


def continuous(prev, cur):
    """Aucune pause effective dans ce pupitre ; les ticks priment les frames."""
    if prev.get('end_tick') is not None and cur.get('tick') is not None:
        return int(cur['tick']) <= int(prev['end_tick'])
    if prev.get('end_frame') is not None and cur.get('start_frame') is not None:
        return int(cur['start_frame']) <= int(prev['end_frame'])
    # Sans données musicales, ne pas affirmer qu'il n'y a pas de silence.
    return False


def apply_liaisons(doc):
    """Retourne copie du document, modifications et avertissements.

    Les préfixes de liaison s'ajoutent sur la première syllabe du mot suivant.
    Ne touche ni au nombre de notes, ni aux durées, ni à un phonème manuel.
    """
    result=copy.deepcopy(doc)
    notes=result.get('notes',[])
    words=reconstruct(notes, lambda _: 0.0)
    changes=[]; warnings=[]
    for left,right in zip(words, words[1:]):
        prev=word_text(left); nxt=word_text(right)
        if not prev or not nxt or prev in NO_LINK_PREV or nxt in BLOCKED_ONSETS:
            continue
        required = ('fr/z' if prev in LINK_Z else
                    'fr/n' if prev in LINK_N else
                    'fr/t' if prev in LINK_T else None)
        if not required: continue
        a=left['end']-1; b=right['start']
        if b != a+1 or a < 0 or b >= len(notes):
            continue
        end_previous=notes[a]; begin_next=notes[b]
        if PUNCT.search(str(end_previous.get('syllable','')).strip()):
            continue
        if not continuous(end_previous,begin_next):
            continue
        phones=list(begin_next.get('phonemes') or [])
        if not phones: continue
        # La consonne peut déjà être à l'attaque du mot suivant.
        if phones[0] == required: continue
        if phones[0] not in ONSET_PHONES: continue
        # Ne pas la dupliquer si elle existe déjà en coda du mot précédent.
        previous_phones=list(end_previous.get('phonemes') or [])
        if previous_phones and previous_phones[-1] == required:
            warnings.append({'tick':begin_next.get('tick'), 'syllable':begin_next.get('syllable'),
                             'issue':'liaison déjà présente en fin du mot précédent',
                             'rule':f'liaison_{required[3:]}_{prev}',
                             'phonemes':previous_phones})
            continue
        if str(begin_next.get('origin','')).startswith(('manual','reference_verified')):
            warnings.append({'tick':begin_next.get('tick'),'syllable':begin_next.get('syllable'),
                             'issue':'liaison potentielle sur phonèmes vérifiés ; non modifiés',
                             'rule':f'liaison_{required[3:]}_{prev}', 'phonemes':phones})
            continue
        updated=[required,*phones]
        changes.append({'tick':begin_next.get('tick'), 'syllable':begin_next.get('syllable'),
                        'rule':f'liaison_{required[3:]}_{prev}',
                        'before':phones,'after':updated})
        begin_next['phonemes']=updated
        begin_next['origin']='french_context:liaison_'+required[3:]+'_'+prev
    return result,changes,warnings


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.epilog = 'Analyser ou appliquer les liaisons françaises entre mots, sous réserve de continuité musicale. --apply modifie les fichiers review.json et crée des sauvegardes.'
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--apply',action='store_true')
    args=p.parse_args(argv)
    rows=[]
    for part in PARTS:
        path=args.work/(part+'.review.json')
        if not path.is_file():continue
        doc=json.loads(path.read_text(encoding='utf-8'))
        new,changes,warnings=apply_liaisons(doc)
        print(f'{part}: {len(changes)} liaisons proposées, {len(warnings)} avertissements')
        rows.extend({'part':part,'kind':'change',**ch} for ch in changes)
        rows.extend({'part':part,'kind':'warning',**w} for w in warnings)
        if args.apply and changes:
            stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            shutil.copy2(path,path.with_name(path.name+'.before_liaison_'+stamp))
            path.write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=args.work/'french_liaisons_report.csv'
    with report.open('w',encoding='utf-8',newline='') as f:
        cols=['part','kind','tick','syllable','rule','before','after','issue','phonemes']
        writer=csv.DictWriter(f,fieldnames=cols,delimiter=';')
        writer.writeheader()
        for r in rows:
            writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,list) else v for k,v in r.items()})
    print('Rapport :',report)
    print('Modifications écrites.' if args.apply else 'Simulation uniquement.')


if __name__=='__main__':
    main()

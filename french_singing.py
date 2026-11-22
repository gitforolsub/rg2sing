#!/usr/bin/env python3
"""Corrections contextuelles de phonèmes français chantés pour rg2sing.

Première étape, délibérément prudente : reconnaît les groupes de syllabes
AVANT la correction; n'invente pas de liaison facultative; préserve les notes.
Ne transmet aucune donnée sur le réseau et ne dépend pas d'un dictionnaire manuel.

Usage: french_singing.py --work /output/partition/full [--apply]
"""
from __future__ import annotations
import argparse
import copy
import csv
import datetime
import json
from pathlib import Path
import re
import shutil

from french_phonemes import VOWELS
from french_liaisons import apply_liaisons
PARTS = ('Soprani', 'Alti', 'Tenors', 'Basses', 'Soprani_divisi')
# [Syllabes réelles] -> [phonèmes de chacune]. La règle porte sur le GROUPE,
# jamais sur une entrée globale de lexique qui pourrait avoir un autre contexte.
CONTEXT_RULES = (
    ('s_accomplit', ('s\'ac', 'com', 'plit'), (
        ('fr/s', 'fr/ah'), ('fr/k', 'fr/on'), ('fr/p', 'fr/l', 'fr/ih'))),
    ('liaison_des_agnelles', ('des', 'a', 'gnelles'), (
        ('fr/d','fr/eh'), ('fr/z','fr/ah'), ('fr/n','fr/y','fr/ae','fr/l'))),
    ('liaison_les_anges_ont', ('les', 'anges', 'ont'), (
        ('fr/l','fr/eh'), ('fr/z','fr/en'), ('fr/j','fr/on'))),
    # Dans « bergers », -ers final se réalise /e/, sans /r/ ; ne pas confondre avec « bergères ».
    ('bergers', ('ber', 'gers'), (
        ('fr/b', 'fr/ae', 'fr/r'), ('fr/j', 'fr/eh'))),
)
# E caducs avec note distincte : signalement + correction lorsque la graphie
# constitue une syllabe explicitement chantée et sans noyau.
# Le graphème « au », y compris la syllabe initiale de « austère », donne /o/ fermé.
# Millefeuille : fr/oh = /o/ ; fr/oo = /ɔ/ (attention aux noms trompeurs).
CLOSED_O_SYLLABLES = frozenset(('au', 'aus'))
SCHWA_ENDINGS = {
    'bre': ('fr/b','fr/r','fr/ee'),
    'ble': ('fr/b','fr/l','fr/ee'),
    'ple': ('fr/p','fr/l','fr/ee'),
    'ches': ('fr/sh','fr/ee'),
    'ges': ('fr/j','fr/ee'),
}


def normalized(s):
    return re.sub(r'[^\w\'’-]+$', '', str(s)).casefold().replace('’', "'")


def read(path):
    with path.open(encoding='utf-8') as f:
        return json.load(f)


def write(path, obj):
    with path.open('w', encoding='utf-8') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write('\n')


def correct_document(doc):
    """Renvoie une copie, les modifications proposées et les avertissements."""
    out = copy.deepcopy(doc)
    notes = out['notes']
    changes, warnings = [], []
    # Les pauses entre notes sont autorisées si les sylabes concernées
    # appartiennent à la même séquence écrite. On ne franchit pas les autres
    # syllabes, ni le signe mélismatique '+' sans examen humain.
    sylls = [normalized(n.get('syllable', '')) for n in notes]
    for label, words, phones in CONTEXT_RULES:
        size = len(words)
        for i in range(len(notes) - size + 1):
            if tuple(sylls[i:i+size]) != words:
                continue
            for j, target in enumerate(phones):
                n = notes[i+j]
                prior = n.get('phonemes') or []
                if prior != list(target):
                    changes.append({
                        'tick': n.get('tick'), 'syllable': n.get('syllable'),
                        'rule': label, 'before': prior, 'after': list(target)})
                    n['phonemes'] = list(target)
                    n['origin'] = 'french_context:'+label
    # Liaisons stables entre mots entiers, en respectant les pauses musicales.
    out, link_changes, link_warnings = apply_liaisons(out)
    notes = out['notes']
    changes.extend(link_changes)
    warnings.extend(link_warnings)

    for n, key in zip(notes, sylls):
        ph = n.get('phonemes') or []
        if key in CLOSED_O_SYLLABLES and ph == ['fr/oo']:
            target = ['fr/oh']
            changes.append({'tick':n.get('tick'), 'syllable':n.get('syllable'),
                            'rule':'au_o_ferme', 'before':ph,'after':target})
            n['phonemes'] = target
            n['origin'] = 'french_context:au_o_ferme'
            ph = target
        if ph and not any(p in VOWELS for p in ph):
            if key in SCHWA_ENDINGS:
                target = list(SCHWA_ENDINGS[key])
                changes.append({'tick':n.get('tick'), 'syllable':n.get('syllable'),
                                'rule':'schwa_sung', 'before':ph,'after':target})
                n['phonemes'] = target
                n['origin'] = 'french_context:schwa_sung'
            else:
                warnings.append({'tick':n.get('tick'), 'syllable':n.get('syllable'),
                                 'issue':'Aucun noyau vocalique', 'phonemes':ph})
        elif not ph and key not in ('+', ''):
            warnings.append({'tick':n.get('tick'), 'syllable':n.get('syllable'),
                             'issue':'Phonèmes manquants', 'phonemes':[]})
    return out, changes, warnings


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.epilog = 'Contrôles phonétiques français (liaisons et prononciation chantée). --apply modifie les fichiers de révision.'
    p.add_argument('--work', type=Path, default=Path('/output/partition/full'))
    p.add_argument('--apply', action='store_true', help='Écrire les corrections, après sauvegarde datée')
    p.add_argument('--report', type=Path, help='CSV des modifications et avertissements')
    args = p.parse_args(argv)
    report = args.report or (args.work/'french_singing_diagnostic.csv')
    report.parent.mkdir(parents=True, exist_ok=True)
    allrows=[]
    for part in PARTS:
        path=args.work/f'{part}.review.json'
        if not path.is_file():
            continue
        doc, changes, warnings = correct_document(read(path))
        print(f'{part}: {len(changes)} corrections contextuelles, {len(warnings)} avertissements')
        for c in changes:
            allrows.append({'part':part,'type':'correction', **c})
        for w in warnings:
            allrows.append({'part':part,'type':'avertissement',**w})
        if args.apply and changes:
            stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            shutil.copy2(path,path.with_name(path.name+'.before_french_'+stamp))
            write(path,doc)
    columns=['part','type','tick','syllable','rule','before','after','issue','phonemes']
    with report.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=columns, delimiter=';')
        writer.writeheader()
        for row in allrows:
            writer.writerow({k: json.dumps(v,ensure_ascii=False) if isinstance(v,list) else v
                             for k,v in row.items()})
    print(f'Rapport : {report}')
    print('Fichiers modifiés.' if args.apply else 'Simulation uniquement : ajouter --apply après examen.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

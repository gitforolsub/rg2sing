#!/usr/bin/env python3
"""rg2sing 0.8.4 - alignement contraint IPA -> phonèmes Millefeuille/notes.

Défaut : rapport uniquement. --apply : uniquement mots sûrs, après sauvegarde.
Aucune ressource réseau, aucune inférence GPU. Les exceptions sont signalées.
"""
from __future__ import annotations
import argparse, copy, csv, datetime, json, re, shutil, sys
from pathlib import Path

from french_words import PARTS, clean, reconstruct, espeak_ipa

# Correspondances de l'API français à l'inventaire des modèles UFR v1.
# Pour éviter des erreurs silencieuses, tout symbole inconnu bloque le mot.
from french_phonemes import IPA, VOWELS, GLIDES

# Un groupe consonantique conservé à l'attaque de la syllabe suivante.
# 'st' permet en particulier /o.stɛʁ/ (aus | tère).
ONSET_CLUSTERS = {
    ('fr/p','fr/l'), ('fr/p','fr/r'), ('fr/b','fr/l'), ('fr/b','fr/r'),
    ('fr/t','fr/r'), ('fr/d','fr/r'), ('fr/k','fr/l'), ('fr/k','fr/r'),
    ('fr/g','fr/l'), ('fr/g','fr/r'), ('fr/f','fr/l'), ('fr/f','fr/r'),
    ('fr/v','fr/r'), ('fr/s','fr/t'), ('fr/s','fr/k'), ('fr/s','fr/p'),
}
# Liaisons obligatoires/recommandées et non aspirées ; ne préjuge pas des facultatives.
LIAISON_Z = {'les','des','mes','tes','ses','ces','nos','vos','leurs','aux'}
LIAISON_T = {'cet'}
LIAISON_N = {'un','mon','ton','son'}
LIAISON_BLOCK = {'huit','huitième','onze','onzième'}
PUNCT = re.compile(r'[.!?;:]+$')


def tokenize_ipa(raw):
    """Interprète la sortie API d'eSpeak sans confondre prosodie et phonèmes.

    Le tiret eSpeak (ex. lˈe-) est une marque prosodique et non un phonème.
    Les séquences de voyelles adjacentes non explicitées restent analysées
    prudemment par align_word, plutôt que traitées comme une diphtongue.
    """
    import unicodedata
    s = unicodedata.normalize('NFC', raw)
    s = s.replace('ᵊ', 'ə').replace('ɹ', 'ʁ')
    s = re.sub(r'[ˈˌːˑ\s.͜͡‿|\-]', '', s)
    # Retrouver les nasales en représentation canonique décomposée :
    # U+0254 U+0303, etc. Il ne faut PAS normaliser le tout en NFD
    # sans normaliser également les clés du dictionnaire.
    norm = unicodedata.normalize('NFD', s)
    forms = sorted(((unicodedata.normalize('NFD', symbol), value)
                     for symbol, value in IPA.items()), key=lambda it: len(it[0]), reverse=True)
    phones = []
    i = 0
    while i < len(norm):
        match = next(((symbol, value) for symbol, value in forms
                      if norm.startswith(symbol, i)), None)
        if match is None:
            raise ValueError(f'symbole API non pris en charge {norm[i:i+8]!r} dans {raw!r}')
        symbol, value = match
        phones.append(value)
        i += len(symbol)
    return phones


def normalize_ui_glide(word, phones):
    """La séquence eSpeak /yi/ peut noter le /ɥi/ du digramme français « ui ».

    Seulement si elle est contiguë dans la transcription ET si le mot écrit
    contient « ui ». On ne transforme jamais un /y/ isolé ni deux syllabes
    dont la partition indique expressément la séparation.
    """
    if 'ui' not in clean(word):
        return list(phones), False
    result = list(phones)
    changed = False
    for i in range(len(result)-1):
        if result[i:i+2] == ['fr/uh', 'fr/ih']:
            result[i] = 'fr/uy'
            changed = True
    return result, changed


def phonetic_syllables(phones, count, written=None):
    """Syllabation sans perte, guidée par les débuts orthographiques des notes.

    On favorise la frontière où la consonne initiale de la syllabe écrite
    devient l'attaque de la syllabe phonétique, plutôt qu'un max-onset
    aveugle. Une frontière lexicale ambiguë n'est jamais corrigée de force.
    """
    positions = [i for i,p in enumerate(phones) if p in VOWELS]
    if len(positions) != count:
        raise ValueError(f'{len(positions)} noyaux API pour {count} notes musicales')
    letter_onsets = {
        'b':'fr/b','c':'fr/k','d':'fr/d','f':'fr/f','g':'fr/g',
        'j':'fr/j','k':'fr/k','l':'fr/l','m':'fr/m','n':'fr/n',
        'p':'fr/p','r':'fr/r','s':'fr/s','t':'fr/t','v':'fr/v',
        'z':'fr/z',
    }
    boundaries=[]
    for k in range(count-1):
        a,b=positions[k],positions[k+1]
        inter=phones[a+1:b]
        if not inter:
            cut=b
        elif len(inter)==1:
            cut=a+1
        elif tuple(inter) in ONSET_CLUSTERS or all(x in GLIDES for x in inter):
            cut=a+1
        elif len(inter)>2 and tuple(inter[-2:]) in ONSET_CLUSTERS:
            cut=b-2
        else:
            cut=b-1
        if written and inter:
            next_syllable = clean(str(written[k+1]))
            # 'lieu' commence par l et doit donc recevoir le /l/.
            # Chercher parmi les seules consonnes inter-vocaliques.
            expected = letter_onsets.get(next_syllable[:1])
            if expected in inter and tuple(inter) not in ONSET_CLUSTERS:
                cut = a+1+inter.index(expected)
        boundaries.append(cut)
    parts=[];start=0
    for end in boundaries+[len(phones)]:
        parts.append(list(phones[start:end]));start=end
    if [p for part in parts for p in part]!=list(phones):
        raise AssertionError('invariant de conservation des phonèmes violé')
    if any(not any(x in VOWELS for x in part) for part in parts):
        raise ValueError('syllabe sans noyau après répartition')
    return parts

def align_word(word, syllables, ipa, sung_schwa=True):
    """Renvoie les phonèmes des N notes ou une exception vérifiable."""
    phones=tokenize_ipa(ipa)
    count=len(syllables)
    phones, _glide_normalized = normalize_ui_glide(word, phones)
    nuclei=sum(p in VOWELS for p in phones)
    if nuclei==count-1 and sung_schwa:
        # e muet chanté : un seul candidat graphique, note musicale dédiée.
        # On ne déclenche pas pour 'é', 'è', ni si plusieurs endroits possibles.
        candidates=[i for i,part in enumerate(syllables)
                    if re.search(r'(?i)(?:e|es)$', str(part)) and
                    re.search(r'(?i)[bcdfghjklmnpqrstvwxz]', str(part))]
        # Dans la syllabation chantée, une dernière note écrite « se »,
        # « tre », « bre », etc. est un candidat plus précis qu'un fragment
        # intérieur terminé par « es » (p. ex. ten- | dres- | se).
        final = count - 1
        if len(candidates)>1 and final in candidates:
            last = clean(str(syllables[final]))
            if last.endswith('e') and not last.endswith('es'):
                candidates = [final]
        if len(candidates)==1:
            k=candidates[0]
            vowels=[i for i,p in enumerate(phones) if p in VOWELS]
            if k>=len(vowels):
                insert=len(phones)
            else:
                # Laisser au moins une consonne d'attaque à la voyelle suivante
                # lorsque plusieurs consonnes précèdent le noyau.
                prior=vowels[k]
                insert=max(0,prior-1)
            phones.insert(insert,'fr/ee')
            nuclei+=1
    if nuclei!=count:
        hint = (' ; vérifier la partition (note supplémentaire / diérèse non imposée automatiquement)'
                if nuclei < count else '')
        raise ValueError(f'{word}: {nuclei} noyaux prononcés pour {count} syllabes chantées ; e caduc/diérèse à décider' + hint)
    out=phonetic_syllables(phones,count,syllables)
    return out


def words_on_notes(notes, word_data):
    """Les index words générés par french_words.py s'appliquent au même review.
    Vérification stricte pour ne pas utiliser un rapport obsolète.
    """
    for w in word_data:
        start,end=w['start'],w['end']
        if not 0<=start<end<=len(notes):
            yield w,None,'index de notes invalide';continue
        syll=[str(n.get('syllable','')) for n in notes[start:end]]
        if syll!=w['syllables'] or [n.get('tick') for n in notes[start:end]]!=w.get('ticks'):
            yield w,None,'diagnostic des mots obsolète (syllabes ou ticks différents)';continue
        yield w,notes[start:end],None


def apply_liaisons(words,notes, proposed,accepted):
    """Traite la liaison entre *mots distincts*, jamais à travers une pause.
    La règle peut transférer un t/n final déjà prononcé ou ajouter /z/.
    """
    events=[]
    sorted_words=sorted(words,key=lambda x:x['start'])
    for left,right in zip(sorted_words,sorted_words[1:]):
        if left['end']!=right['start']:continue
        i=left['end']-1;j=right['start']
        if i not in accepted or j not in accepted:continue
        if notes[j].get('tick',0)>notes[i].get('end_tick',0):continue
        if PUNCT.search(str(notes[i].get('syllable',''))):continue
        a=clean(left['word']);b=clean(right['word'])
        if b in LIAISON_BLOCK:continue
        ph=proposed[j]
        if not ph or ph[0] not in VOWELS|GLIDES|{'fr/z','fr/t','fr/n'}:continue
        liaison = ('fr/z' if a in LIAISON_Z else
                   'fr/t' if a in LIAISON_T else
                   'fr/n' if a in LIAISON_N else None)
        if not liaison:continue
        if ph[0]==liaison:continue
        prev=proposed[i]
        if prev and prev[-1]==liaison:
            proposed[i]=prev[:-1]  # Transfer de consonne, pas duplication
            if not any(x in VOWELS for x in proposed[i]):
                proposed[i]=prev;continue
        proposed[j]=[liaison]+ph
        events.append({'tick':notes[j]['tick'],'rule':f'liaison {a} + {b}',
                       'phones':proposed[j]})
    return events


def safe_insertion(old, new):
    """Accepte uniquement une insertion de consonnes à l'attaque.

    Les voyelles/glides et l'ordre de tous les phonèmes existants sont
    strictement préservés. Une transcription remplacée, un transfert ou une
    altération de voyelle ne sont jamais considérés comme sûrs.
    """
    if not old or not new or old == new:
        return False
    if len(new) <= len(old) or new[-len(old):] != old:
        return False
    prefix = new[:-len(old)]
    return bool(prefix) and all(p not in VOWELS | GLIDES for p in prefix)


def anchored_word_insertions(notes, word, expected_parts, protect_verified=True):
    """Accepter uniquement des consonnes MANQUANTES sans changer l'existant.

    Sur un mot entier, la concaténation des phonèmes courants doit devenir
    exactement l'IPA resegmentée ; une syllabe déjà vérifiée peut servir
    d'ancre mais ne peut jamais être modifiée. Cette vérification permet par
    exemple de restaurer /s/ dans aus|tère, sans changer le /o/ de aus.
    """
    start, end = word['start'], word['end']
    current = [list(n.get('phonemes') or []) for n in notes[start:end]]
    if len(current) != len(expected_parts):
        return None, 'nombre de notes incohérent'
    inserts = []
    for offset, (old, desired) in enumerate(zip(current, expected_parts)):
        if old == desired:
            continue
        if not safe_insertion(old, desired):
            return None, 'changement de voyelle, déplacement ou suppression de phonème'
        item = notes[start + offset]
        if protect_verified and str(item.get('origin', '')).startswith(
                ('reference_verified', 'manual_correction', 'manual_verified', 'french_context:')):
            return None, 'syllabe vérifiée à modifier'
        added = desired[:-len(old)]
        if start + offset > 0:
            previous = (expected_parts[offset-1] if offset else
                        list(notes[start-1].get('phonemes') or []))
            if previous and previous[-1] == added[0]:
                return None, 'consonne déjà présente sur la note précédente'
        inserts.append((start + offset, old, desired))
    if not inserts:
        return [], 'mot déjà conforme'
    # Vérification de conservation de toute la chaîne phonétique du mot.
    actual = [p for group in expected_parts for p in group]
    rebuilt = [p for group in current for p in group]
    if len(actual) <= len(rebuilt):
        return None, 'aucun phonème ajouté'
    return inserts, 'insertion(s) consonantique(s) validée(s) sur le mot entier'


def classify_changes(notes, changes, words, issues):
    """Sépare corrections automatiquement applicables et propositions à revoir.

    Les ajouts sont refusés si un autre phonème est remplacé ou supprimé
    dans le même mot, afin de conserver l'invariant phonétique global.
    """
    owners = {}
    for w in words:
        for i in range(w['start'], w['end']):
            owners[i] = (w['start'], w['end'])
    ticks = {n.get('tick'):i for i,n in enumerate(notes)}
    groups = {}
    for c in changes:
        i = ticks.get(c['tick'])
        if i is None:
            c['decision'] = 'review'; c['reason'] = 'note introuvable'; continue
        group = owners.get(i, (i,i+1))
        groups.setdefault(group, []).append(c)
    for group, entries in groups.items():
        candidates_ok = all(safe_insertion(c['before'],c['after']) for c in entries)
        # Une consonne transférée depuis la note précédente ne doit pas
        # subsister deux fois si la proposition n'a pas supprimé l'ancienne.
        for c in entries:
            idx=ticks.get(c['tick'])
            if idx is not None and idx > 0 and safe_insertion(c['before'],c['after']):
                added=c['after'][:-len(c['before'])]
                previous=notes[idx-1].get('phonemes') or []
                prev_change=next((x for x in changes if x['tick']==notes[idx-1].get('tick')),None)
                previous_new=prev_change['after'] if prev_change else previous
                if previous_new and added and previous_new[-1]==added[0]:
                    candidates_ok=False
        for c in entries:
            c['decision'] = 'safe' if candidates_ok else 'review'
            if not candidates_ok:
                c['reason'] = 'remplacement, suppression, transposition ou groupe mixte'
            else:
                c['reason'] = 'consonne(s) ajoutée(s) en attaque; phonèmes existants préservés'
    return changes


def align_document(doc, words, protect_verified=True):
    """Retourne les propositions et classe les insertions ancrées au mot entier.

    Sécurité : une proposition de modification de voyelle ou de consonne
    existante reste en review ; une correction déjà validée est une ancre,
    jamais une autorisation de l'écraser.
    """
    notes=doc['notes']
    proposed={};accepted=set();issues=[];events=[];eligible=[];word_safe={}
    for w,items,error in words_on_notes(notes,words):
        if error:
            issues.append({'tick':(w.get('ticks') or [None])[0], 'word':w.get('word'), 'reason':error});continue
        if w.get('uncertain') or w.get('zipf',0)<2.5:
            issues.append({'tick':items[0].get('tick'),'word':w['word'],'reason':'frontière lexicale incertaine'});continue
        if not w.get('ipa'):
            issues.append({'tick':items[0].get('tick'),'word':w['word'],'reason':'IPA non disponible'});continue
        try: parts=align_word(w['word'],w['syllables'],w['ipa'])
        except ValueError as e:
            issues.append({'tick':items[0].get('tick'),'word':w['word'],'reason':str(e)});continue
        # L'IPA d'un mot isolé peut omettre une liaison déjà placée
        # par la phrase précédente. On ne la supprime jamais tacitement.
        first_existing=items[0].get('phonemes') or []
        boundary_consonants={'fr/z','fr/t','fr/n','fr/j'}
        if (first_existing and first_existing[0] in boundary_consonants
                and parts[0] and parts[0][0]!=first_existing[0]
                and w['start']>0):
            issues.append({'tick':items[0].get('tick'),'word':w['word'],
                'reason':'attaque existante potentiellement issue d’une liaison ou d’un enchaînement; vérification nécessaire'})
            continue
        anchored,reason=anchored_word_insertions(notes,w,parts,protect_verified)
        if anchored is not None:
            word_safe[(w['start'],w['end'])]={i for i,_,_ in anchored}
            # Si la séquence est déjà identique, elle reste candidat
            # aux règles de liaison grammaticale inter-mots.
        elif any(n.get('phonemes') for n in items):
            issues.append({'tick':items[0].get('tick'),'word':w['word'],
                           'reason':reason+'; proposition conservée pour review'})
        for k,ph in enumerate(parts):
            proposed[w['start']+k]=list(ph)
            accepted.add(w['start']+k)
        eligible.append(w)
    # Les liaisons sont des événements distincts, et ne deviennent « safe »
    # que si la vérification globale ne voit aucune suppression.
    events+=apply_liaisons(eligible,notes,proposed,accepted)
    out=copy.deepcopy(doc);changes=[]
    owners={i:(w['start'],w['end']) for w in words for i in range(w['start'],w['end'])}
    for i,ph in sorted(proposed.items()):
        old=list(notes[i].get('phonemes') or [])
        if old!=ph:
            owner=owners.get(i,(i,i+1))
            safe=(i in word_safe.get(owner,set()) and safe_insertion(old,ph))
            # Une liaison peut être vérifiée comme insertion uniquement
            # si le mot est déjà conforme et que l'on ne modifie rien d'autre.
            if not safe and safe_insertion(old,ph):
                group_words=[w for w in eligible if w['start']<=i<w['end']]
                if group_words:
                    w=group_words[0]
                    expected=word_safe.get((w['start'],w['end']))
                    if expected is not None and all(
                        (j==i or proposed.get(j,list(notes[j].get('phonemes') or [])) == list(notes[j].get('phonemes') or []))
                        for j in range(w['start'],w['end'])):
                        safe=True
            # Respecter les syllabes vérifiées et l'interdiction des doublons.
            if protect_verified and str(notes[i].get('origin','')).startswith(
                ('reference_verified','manual_correction','manual_verified','french_context:')):
                safe=False
            if safe and i>0 and ph[:-len(old)] and list(notes[i-1].get('phonemes') or [])[-1:] == ph[:1]:
                safe=False
            c={'tick':notes[i].get('tick'),'syllable':notes[i].get('syllable'),
               'before':old,'after':ph,'origin':'word_ipa_align',
               'decision':'safe' if safe else 'review',
               'reason':'insertion sans perte, vérifiée dans le mot' if safe else
               'changement mixte, syllabe protégée ou frontière à vérifier'}
            changes.append(c)
            out['notes'][i]['phonemes']=ph
            out['notes'][i]['origin']='word_ipa_align_proposed'
    return out,changes,issues,events


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=Path('/output/partition/full'))
    parser.add_argument('--words',type=Path,help='Diagnostic french_words.json à analyser')
    parser.add_argument('--apply',action='store_true',help='Appliquer les insertions sans perte vérifiées au niveau du mot (avec sauvegarde)')
    parser.add_argument('--replace-verified',action='store_true',help='Autoriser écrasement des corrections déjà validées (déconseillé)')
    args=parser.parse_args()
    source=args.words or args.work/'french_words.json'
    data=json.loads(source.read_text(encoding='utf-8'))
    rows=[];summary={}
    for part,words in data['parts'].items():
        path=args.work/f'{part}.review.json'
        if not path.exists():continue
        doc=json.loads(path.read_text(encoding='utf-8'))
        out,changes,issues,events=align_document(doc,words,not args.replace_verified)
        safe = [c for c in changes if c.get('decision') == 'safe']
        review = [c for c in changes if c.get('decision') != 'safe']
        print(f'{part}: {len(safe)} corrections sûres, {len(review)} à revoir, '
              f'{len(events)} liaisons détectées, {len(issues)} anomalies')
        summary[part]={'safe':len(safe),'review':len(review),
                       'liaisons':len(events),'issues':len(issues)}
        rows += [{'part':part,'kind':'change',**x} for x in changes]
        rows += [{'part':part,'kind':'issue',**x} for x in issues]
        rows += [{'part':part,'kind':'liaison',**x} for x in events]
        if args.apply and safe:
            saved = copy.deepcopy(doc)
            index_by_tick = {n.get('tick'):i for i,n in enumerate(doc['notes'])}
            for c in safe:
                i=index_by_tick[c['tick']]
                saved['notes'][i]['phonemes']=c['after']
                saved['notes'][i]['origin']='word_ipa_align_safe'
            stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            shutil.copy2(path,path.with_name(path.name+'.before_align_'+stamp))
            path.write_text(json.dumps(saved,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    cols=['part','kind','tick','word','syllable','before','after','rule','phones','reason','origin','decision']
    report=args.work/'french_alignment_report.csv'
    with report.open('w',newline='',encoding='utf-8') as f:
        wr=csv.DictWriter(f,fieldnames=cols,delimiter=';');wr.writeheader()
        for x in rows:
            wr.writerow({k:json.dumps(x.get(k,''),ensure_ascii=False) if isinstance(x.get(k),list) else x.get(k,'') for k in cols})
    print('Rapport :',report)
    print('Corrections sûres appliquées (si présentes).' if args.apply else 'Simulation seulement : --apply pour les insertions sûres.')

if __name__=='__main__':main()

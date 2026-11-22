#!/usr/bin/env python3
"""rg2sing 0.8: reconstruire des mots à partir de syllabes musicales.

Analyse uniquement: n'altère JAMAIS les notes, les phonèmes, ni les .review.json.
Fonctionne localement avec wordfreq (français) et, facultativement, espeak-ng.
Les reconstructions et leur confiance sont enregistrées pour validation.
"""
from __future__ import annotations
import argparse, csv, json, re, shutil, subprocess, sys, unicodedata
from pathlib import Path

PARTS=('Soprani','Alti','Tenors','Basses','Soprani_divisi')
TRAILING=re.compile(r'[\.,;:!?…]+$')
APOSTROPHE=re.compile(r'[\u2019\u02bc]')


def text_of(note):
    return APOSTROPHE.sub("'",str(note.get('syllable','')).strip())


def clean(text):
    return TRAILING.sub('',text).casefold()


def score_candidate(syllables, frequency):
    word=clean(''.join(syllables))
    if not word or word=='+': return None
    # Un assemblage grammaticalement impossible (contenant plusieurs apostrophes)
    # ne doit pas passer pour un mot.
    if word.count("'")>1: return None
    z=frequency(word)
    if z<=0: return None
    # Coût de création d'un mot: sans ce coût, le découpage en syllabes
    # individuellement courantes l'emporterait artificiellement.
    return z-6.0


def segment_indices(notes, frequency, max_syllables=6):
    """DP avec meilleures et deuxièmes meilleures solutions par position.

    N'autorise pas le passage d'une pause, d'un signe '+', ni d'une ponctuation
    forte. Un mot peut commencer en début de mesure sans contrainte arbitraire.
    """
    n=len(notes)
    if not n:return []
    best=[None]*(n+1)
    best[n]=(0.0,[])
    for i in range(n-1,-1,-1):
        candidates=[]
        spans=[]
        for j in range(i+1,min(n,i+max_syllables)+1):
            if j>i+1:
                previous,current=notes[j-2],notes[j-1]
                if text_of(previous).endswith(('.', '!', '?', ';', ':')):break
                if 'end_tick' in previous and 'tick' in current and current['tick']>previous['end_tick']:break
                if text_of(current)[:1].isupper() and text_of(previous) and not text_of(previous).endswith("'"):
                    # Majuscule au milieu d'une phrase : frontière probable.
                    break
            s=[text_of(x) for x in notes[i:j]]
            if any(not x or x=='+' for x in s):break
            cand_score=score_candidate(s,frequency)
            if cand_score is None:continue
            if best[j] is None:continue
            raw=''.join(s)
            # Ne pas fusionner une syllabe terminée par une ponctuation.
            if any(TRAILING.search(x) for x in s[:-1]):continue
            # Pénaliser fortement les mots inconnus au lieu de les jeter,
            # mais ici seuls les candidats lexicaux sont retenus.
            total=cand_score+best[j][0]
            candidates.append((total,[{'start':i,'end':j,'word':clean(raw),'zipf':cand_score+6.0},*best[j][1]]))
            spans.append((j,total))
        if not candidates:
            # Fallback explicite: syllabe isolée sans preuve lexicale.
            if best[i+1] is None:best[i+1]=(0.0,[])
            best[i]=(-9.0+best[i+1][0], [{'start':i,'end':i+1,'word':clean(text_of(notes[i])),'zipf':0.0,'uncertain':'absent du lexique'},*best[i+1][1]])
        else:
            best[i]=max(candidates,key=lambda x:x[0])
    return best[0][1]


def no_cross_context(note):
    """Les + et les syllabes sans texte signalent une prolongation, pas un mot."""
    return text_of(note) in ('','+')


def split_runs(notes):
    groups=[]; run=[]; start=0
    for i,n in enumerate(notes):
        if no_cross_context(n):
            if run:groups.append((start,run));run=[]
            continue
        if run:
            prev=run[-1]
            if ('end_tick' in prev and 'tick' in n and n['tick']>prev['end_tick']) or text_of(prev).endswith(('.', '!', '?', ';', ':')):
                groups.append((start,run));run=[]
        if not run:start=i
        run.append(n)
    if run:groups.append((start,run))
    return groups


def split_orthographic_candidates(parts, frequency):
    """Le tiret de Rosegarden est une CONTINUATION, non une graphie lexicale.

    Les corpus statistiques segmentent parfois un pseudo-mot « lou-an-ge »
    en plusieurs mots courants et lui donnent un score artificiellement élevé.
    Un mot soudé attesté a donc PRIORITÉ. Le véritable composé « porte-clé »
    reste possible quand « porteclé » est absent du lexique.

    Returns (graphie retenue, candidats, ambiguïté non tranchée).
    """
    plain = clean(''.join(parts))
    if len(parts) == 1:
        return plain, [plain], False
    hyphen = clean('-'.join(parts))
    candidates = [plain, hyphen]
    f_plain = frequency(plain)
    f_hyphen = frequency(hyphen)
    if f_plain >= 2.0:
        # Ne pas considérer des traits musicaux comme des preuves d'un composé.
        return plain, candidates, False
    if f_plain <= 0 and f_hyphen >= 2.0:
        return hyphen, candidates, False
    if f_plain > 0 and f_hyphen <= 0:
        return plain, candidates, f_plain < 2.0
    if f_plain <= 0 and f_hyphen <= 0:
        return plain, candidates, True
    # Rares cas réellement ambigus : ne pas imposer une graphie.
    return plain, candidates, True


def explicit_reconstruct(notes, frequency):
    """Regroupement déterministe quand l'import fournit word_continues.

    Une pause, un mélisme ou un changement de groupe coupe toujours le mot.
    On ne devine PAS la graphie composée en l'absence de preuve lexicale.
    """
    out=[]; start=None; pending=[]
    def flush(incomplete=False):
        nonlocal pending,start
        if not pending:return
        raw=[text_of(n) for n in pending]
        chosen,candidates,ambiguous=split_orthographic_candidates(raw,frequency)
        obj={'start':start,'end':start+len(pending),'word':chosen,
             'syllables':raw,'ticks':[n.get('tick') for n in pending],
             'zipf':frequency(chosen),'candidates':candidates,
             'source':'rosegarden_hyphens'}
        if incomplete:obj['uncertain']='mot interrompu après un trait d’union'
        elif ambiguous:obj['uncertain']='orthographe composée ambiguë'
        out.append(obj);pending=[];start=None
    for i,n in enumerate(notes):
        label=text_of(n)
        if no_cross_context(n):
            flush(incomplete=bool(pending and pending[-1].get('word_continues')))
            continue
        if pending:
            prev=pending[-1]
            pause=('end_tick' in prev and 'tick' in n and n['tick']>prev['end_tick'])
            if pause:
                flush(incomplete=bool(prev.get('word_continues')))
            elif not prev.get('word_continues',False):
                flush()
        if not pending:start=i
        pending.append(n)
        if not n.get('word_continues',False):flush()
    flush(incomplete=bool(pending and pending[-1].get('word_continues')))
    return out


def reconstruct(notes,frequency,max_syllables=6):
    # Les exports récents contiennent la propriété sur toutes les notes.
    # Les anciens restent compatibles avec le regroupement lexical heuristique.
    if notes and all('word_continues' in n for n in notes):
        return explicit_reconstruct(notes,frequency)
    out=[]
    for start,run in split_runs(notes):
        for word in segment_indices(run,frequency,max_syllables):
            b=start+word['start'];e=start+word['end']
            out.append({**word,'start':b,'end':e,
                        'syllables':[text_of(n) for n in notes[b:e]],
                        'ticks':[n.get('tick') for n in notes[b:e]],
                        'source':'heuristic_no_hyphens'})
    return out


def espeak_ipa(word,engine):
    if not engine:return None
    try:
        p=subprocess.run([engine,'-q','-v','fr','--ipa',word],capture_output=True,text=True,timeout=10,check=True)
    except (subprocess.SubprocessError, OSError):return None
    return ' '.join(p.stdout.split())


def analyze(work,out,frequency,engine,max_syllables=6):
    rows=[];results={}
    for part in PARTS:
        path=work/(part+'.review.json')
        if not path.exists():continue
        notes=json.loads(path.read_text(encoding='utf-8'))['notes']
        words=reconstruct(notes,frequency,max_syllables)
        results[part]=[]
        for w in words:
            ipa=espeak_ipa(w['word'],engine)
            # 0.8 n'essaye pas de convertir de force une transcription en phonèmes
            # alignés. Exige des vérifications de nombre de noyaux et du e chanté.
            risk=[]
            if w.get('uncertain') or w['zipf']<2.5:risk.append('frontière lexicale à vérifier')
            if len(w['syllables'])>1:risk.append('alignement IPA/notes non encore validé')
            if not ipa:risk.append('IPA indisponible')
            item={**w,'ipa':ipa,'risk':risk,'phonemes_existing':[n.get('phonemes',[]) for n in notes[w['start']:w['end']]]}
            results[part].append(item)
            rows.append({'part':part,'tick':w['ticks'][0],'word':w['word'],
                         'syllables':' | '.join(w['syllables']), 'ipa':ipa or '',
                         'zipf':f"{w['zipf']:.2f}", 'risk':'; '.join(risk)})
        print(f'{part}: {len(words)} mots candidats, {sum(bool(w["risk"]) for w in results[part])} à examiner')
    out.mkdir(parents=True,exist_ok=True)
    with (out/'french_words_report.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['part','tick','word','syllables','ipa','zipf','risk'],delimiter=';')
        writer.writeheader();writer.writerows(rows)
    (out/'french_words.json').write_text(json.dumps({'schema':'rg2sing-word-analysis-v0.8','parts':results},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Rapports :',out/'french_words_report.csv',',',out/'french_words.json')
    print('AUCUNE modification des phonèmes ou du rendu : analyse seule.')
    return results


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.epilog = 'Reconstruire les mots français et produire des rapports sans modifier les phonèmes.'
    p.add_argument('--work',type=Path,default=Path('/output/partition/full'))
    p.add_argument('--output',type=Path,default=None)
    p.add_argument('--max-syllables',type=int,default=6)
    p.add_argument('--no-espeak',action='store_true')
    args=p.parse_args(argv)
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        p.error('Installer wordfreq dans le conteneur : /opt/venv/bin/pip install wordfreq (puis ajouter au Dockerfile)')
    engine=None if args.no_espeak else (shutil.which('espeak-ng') or shutil.which('espeak'))
    if not engine and not args.no_espeak:
        print('Avertissement : espeak-ng non trouvé; analyse lexicale sans IPA',file=sys.stderr)
    def frequency(w):return zipf_frequency(w,'fr',wordlist='best')
    analyze(args.work,args.output or args.work,frequency,engine,args.max_syllables)

if __name__=='__main__':main()

#!/usr/bin/env python3
"""Propose localement des phonèmes pour les syllabes manquantes d'un lexique.

ATTENTION : espeak traite une syllabe isolée; liaison et e chanté à contrôler.
N'écrase aucune entrée déjà renseignée. Vérifie chaque code contre la banque UFR.
"""
import argparse,csv,json,re,shutil,subprocess
from pathlib import Path

# Correspondances phonétiques indicatives, pas un moteur G2P contextuel.
from french_phonemes import IPA, ORDER

def phones_from_ipa(s,available):
    s=s.replace('ˈ','').replace('ˌ','').replace('ː','').replace('‿','').replace('͡','')
    s=re.sub(r'[\s.\-\u0361]', '', s)
    out=[];unhandled=[];idx=0
    while idx<len(s):
        if s[idx] in "'\"(),?!;:":idx+=1;continue
        part=next((token for token in ORDER if s.startswith(token,idx)),None)
        if part is None:
            unhandled.append(s[idx]);idx+=1
        else:
            value=IPA[part]
            if value not in available:unhandled.append(f'{part}->{value} absent')
            else:out.append(value)
            idx+=len(part)
    return out,unhandled


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.epilog = 'Proposer une transcription locale eSpeak-NG pour les syllabes du lexique ; --lexicon et --apply.'
    p.add_argument('--lexicon',default='/output/partition/full/lexicon.json')
    p.add_argument('--root',default='/models/UFR-V1.0/UFR-V1.0')
    p.add_argument('--report',default='/output/partition/full/espeak_suggestions.csv')
    p.add_argument('--apply',action='store_true',help='Insérer les propositions reconnues dans le lexique (à vérifier)')
    args=p.parse_args()
    engine=shutil.which('espeak-ng') or shutil.which('espeak')
    if not engine:p.error('Installer localement espeak-ng dans le conteneur (ou fournir espeak)')
    lexpath=Path(args.lexicon)
    lex=json.loads(lexpath.read_text(encoding='utf8'))
    available=set(json.loads((Path(args.root)/'0_CORE/dsacoustic/millefeuille_v001.phonemes.json').read_text()))
    records=[];n=0
    for word,original in lex.items():
        if original:continue
        proc=subprocess.run([engine,'-q','-v','fr','--ipa',word],capture_output=True,text=True,check=True)
        ipa=proc.stdout.strip()
        phones,issues=phones_from_ipa(ipa,available)
        good=bool(phones) and not issues
        records.append({'syllabe':word,'ipa_espeak':ipa,'proposition':' '.join(phones) if good else '',
                        'incertitude':'; '.join(issues) if issues else 'prononciation hors contexte, vérifier'})
        if args.apply and good:
            lex[word]=phones;n+=1
    out=Path(args.report);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['syllabe','ipa_espeak','proposition','incertitude'])
        w.writeheader();w.writerows(records)
    if args.apply:
        lexpath.write_text(json.dumps(lex,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(f'{len(records)} syllabes analysées; {sum(bool(x["proposition"]) for x in records)} propositions disponibles; {n} ajoutées au lexique')
    print(f'Rapport : {out}')

if __name__=='__main__':main()

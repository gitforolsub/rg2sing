#!/usr/bin/env python3
"""Diagnostic local des durées réellement allouées aux phonèmes par dsdur.

Lit uniquement les JSON de chunks déjà générés et les .review.json actuels.
Ne charge aucun modèle, n'altère aucun WAV, et signale les caches obsolètes.
"""
import argparse,csv,json,re
from pathlib import Path

PARTS=('Soprani','Alti','Tenors','Basses','Soprani_divisi')

def inspect(work,part,syllable='',chunk_notes=20):
    review=json.loads((work/f'{part}.review.json').read_text(encoding='utf-8'))
    notes=review['notes']
    directory=work/'chunks'/part
    if not directory.exists():
        raise FileNotFoundError(f'Aucun segment existant dans {directory}')
    output=[];stale=[]
    indexes=sorted(set(int(p.name.split('_',1)[0]) for p in directory.glob('*.json') if re.match(r'^\d+_',p.name)))
    for index in indexes:
        files=sorted(directory.glob(f'{index:03}_*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        if len(files)>1:
            stale.append(f'{part} segment {index:03}: plusieurs caches; dernier pris par date de modification')
        d=json.loads(files[0].read_text(encoding='utf-8'))
        groups=d.get('groups',[])
        phones=d.get('phonemes',[])
        current=notes[index*chunk_notes:(index+1)*chunk_notes]
        note_groups=[g for g in groups if g!=['SP']]
        if len(note_groups)!=len(current) or any(g!=n.get('phonemes') for g,n in zip(note_groups,current)):
            stale.append(f'{part} segment {index:03}: phonèmes JSON différents des .review.json actuels; résultat IGNORÉ')
            continue
        k=0;j=0
        for g in groups:
            batch=phones[k:k+len(g)];k+=len(g)
            if g==['SP']:continue
            n=current[j];j+=1
            if syllable and syllable.casefold() not in n.get('syllable','').casefold():
                continue
            for ph in batch:
                output.append({'part':part,'tick':n['tick'],'syllable':n.get('syllable',''),
                    'phoneme':ph['phoneme'], 'allocated_ms':round(1000*ph['frames']*d['hop_size']/d['sample_rate'],1),
                    'predicted_frames':round(ph.get('predicted',0),2), 'chunk':index})
    return output,stale

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.epilog = 'Inspecter les phonèmes et leurs durées dans les segments déjà préparés.'
    p.add_argument('--work',type=Path,default=Path('/output/partition/full'))
    p.add_argument('--part',choices=PARTS,default='Tenors')
    p.add_argument('--syllable',default='',help='Filtre de texte, ex. Christ, humble')
    p.add_argument('--chunk-notes',type=int,default=20,help='Doit correspondre à --chunk-notes du rendu')
    p.add_argument('--output',type=Path,help='CSV, défaut <work>/<part>_timing.csv')
    a=p.parse_args()
    rows,warnings=inspect(a.work,a.part,a.syllable,a.chunk_notes)
    out=a.output or a.work/f'{a.part}_timing.csv'
    with out.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['part','tick','syllable','phoneme','allocated_ms','predicted_frames','chunk'],delimiter=';')
        writer.writeheader();writer.writerows(rows)
    for msg in warnings:print('ATTENTION:',msg)
    print(len(rows),'phonèmes examinés; rapport:',out)
    for r in rows[:50]:
        print(f"tick {r['tick']:>7} {r['syllable']:<13} {r['phoneme']:<8} {r['allocated_ms']:>6.1f} ms")
    if not rows:print('Aucun segment valable pour ce filtre. Vérifier les avertissements / le cache.')

if __name__=='__main__':main()

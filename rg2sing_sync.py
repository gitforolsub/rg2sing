#!/usr/bin/env python3
"""Rosegarden -> score et revues SATB + divisi, alignement des paroles.

Fonctionne localement, n'utilise aucune ressource réseau.
Conserve les transcriptions validées des revues précédentes, si présentes.
"""
import argparse,collections,json,re,shutil
from pathlib import Path
from rg2sing import parse,seconds,validate
from export_ustx import segment_notes
from rg2sing_staves import split_staff_model
from rg2sing_lyrics import align_lyrics, resolve_lyric_contractions

SR,HOP=44100,512
PARTS=('Soprani','Alti','Tenors','Basses')
EXTRA_SYLLABLES={
 'dans la nuit':['dans','la','nuit'],
 'cette nuit':['cet','te','nuit'],
 'dans le ciel':['dans','le','ciel'],
 'de la nuit':['de','la','nuit'],
 'des agnelles':['des','a','gnelles'],
 'et chamelles':['et','cha','melles'],
 'des fidèles':['des','fi','dèles'],
 'fraternel':['fra','ter','nel'],
 'à noël':['à','No','ël'],
 'eternel':['é','ter','nel'],
 'éternel':['é','ter','nel'],
}
EXTRA_PHONEMES={
 'dans':['fr/d','fr/en'],'la':['fr/l','fr/ah'],
 'nuit':['fr/n','fr/uy','fr/ih'], 'cet':['fr/s','fr/ae'],
 'te':['fr/t','fr/ee'],'le':['fr/l','fr/ee'],
 'ciel':['fr/s','fr/y','fr/ae','fr/l'],
 'de':['fr/d','fr/ee'], 'des':['fr/d','fr/eh'],
 'a':['fr/ah'],'gnelles':['fr/n','fr/y','fr/ae','fr/l'],
 'et':['fr/eh'],'cha':['fr/sh','fr/ah'],
 'melles':['fr/m','fr/ae','fr/l'],
 'fi':['fr/f','fr/ih'],'dèles':['fr/d','fr/ae','fr/l'],
 'fra':['fr/f','fr/r','fr/ah'],'ter':['fr/t','fr/ae','fr/r'],
 'nel':['fr/n','fr/ae','fr/l'],
 'à':['fr/ah'],'no':['fr/n','fr/oo'],
 'ël':['fr/ae','fr/l'],'é':['fr/eh'],
}
from french_phonemes import VOWELS

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,thing):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(thing,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def old_index(path):
 if not path.exists():return {}
 return {(int(n['tick']),int(n['midi'])):n for n in read(path).get('notes',[])}

def frame(t,tempo):return round(seconds(t,tempo)*SR/HOP)

def new_note(n,tempo,syllable=None):
 return {'tick':n['tick'],'end_tick':n['end'],
         'start_frame':frame(n['tick'],tempo),'end_frame':frame(n['end'],tempo),
         'midi':n['pitch'],'syllable':syllable if syllable is not None else (n['lyric'] or ''),
         'phonemes':[], 'origin':'missing',
         'word_continues':bool(n.get('word_continues',False))}

def apply_old(row,old,lex):
 existing=old.get((row['tick'],row['midi']))
 if existing and existing.get('phonemes') and existing.get('syllable')==row['syllable']:
  row['phonemes']=existing['phonemes'][:]
  row['origin']=existing.get('origin','previous_review')
 else:
  phones=lex.get(row['syllable'].casefold(),[])
  if phones:
   row['phonemes']=phones[:]
   row['origin']='lexicon_proposed'
 return row

def annotation_regions(score):
 """Find a parenthesis on a soprano lyric event, bounded by next soprano onset.

 The lyric event itself contains the main sung syllable and editorial male text.
 Returns the original passage's onsets; never infers notes from missing data.
 """
 sop=segment_notes(score,'Soprani')
 lyrical=sorted({n['tick'] for n in sop if n['lyric'] not in (None,'','+')})
 events=collections.defaultdict(list)
 for seg in score['segments']:
  if seg['part']!='Soprani':continue
  for ev in seg['events']:
   if ev['type']=='text' and ev['properties'].get('type')=='lyric':
    raw=ev['properties'].get('text','')
    match=re.search(r'\(([^()]*)\)',raw)
    if match:events[ev['tick']].append((match.group(1).strip(),raw))
 regions=[]
 for start,values in sorted(events.items()):
  uniq=list(dict.fromkeys(values))
  if len(uniq)!=1:
   raise ValueError(f'Plusieurs annotations contradictoires au tick {start}: {uniq}')
  lyric,whole=uniq[0]
  following=next((t for t in lyrical if t>start),None)
  if following is None:raise ValueError(f'Annotation à {start} sans note suivante')
  key=lyric.casefold()
  syllables=EXTRA_SYLLABLES.get(key)
  if not syllables:
   raise ValueError(f'Annotation non reconnue tick {start}: {lyric!r}; ajouter son découpage à EXTRA_SYLLABLES')
  regions.append((start,following,lyric,syllables))
 return regions

def build(score,work,lex,old,strict=True):
 tempo=score['tempo']
 sop=segment_notes(score,'Soprani')
 primary=[];divisi=[];chord_info=[]
 by_start=collections.defaultdict(list)
 for n in sop:by_start[n['tick']].append(n)
 for t,notes in sorted(by_start.items()):
  pitches=sorted({x['pitch'] for x in notes},reverse=True)
  top=next(x for x in notes if x['pitch']==pitches[0])
  row=apply_old(new_note(top,tempo),old['Soprani'],lex)
  primary.append(row)
  if len(pitches)>1:
   chord_info.append({'tick':t,'pitches':pitches,'syllable':row['syllable']})
   for pitch in pitches[1:]:
    n=next(x for x in notes if x['pitch']==pitch)
    copy=apply_old(new_note(n,tempo,syllable=row['syllable']),old['Soprani_divisi'],lex)
    if not copy['phonemes'] and row['phonemes']:
     copy['phonemes']=row['phonemes'][:];copy['origin']='soprano_divisi_proposed'
    divisi.append(copy)
 def doc(part,rows):
  return {'schema':'rg2sing-phoneme-review-v0.4','sample_rate':SR,'hop_size':HOP,
          'part':part,'end_tick':max(x['end_tick'] for x in rows), 'notes':rows,
          'instructions':'Annotations masculines venant des parenthèses; revoir les propositions. Divisi : une note par hauteur supplémentaire seulement.'}
 write(work/'Soprani.review.json',doc('Soprani',primary))
 if divisi:write(work/'Soprani_divisi.review.json',doc('Soprani_divisi',divisi))
 regions=annotation_regions(score)
 bytick={r['tick']:r for r in primary}
 soprano_sorted=sorted(primary,key=lambda r:r['tick'])
 extras=[]
 lyric_diagnostics={}
 reference_by_part={}
 for part in PARTS[1:]:
  raw=segment_notes(score,part)
  seen=collections.defaultdict(set)
  for n in raw:seen[n['tick']].add(n['pitch'])
  crowded={t:sorted(v) for t,v in seen.items() if len(v)>1}
  if crowded:raise ValueError(f'{part} contient des divisi à traiter : {crowded}')
  rows=[];j=0
  own_lyrics = any(n.get('lyric') not in (None, '') for n in raw)
  if own_lyrics:
   for n in raw:
    r=apply_old(new_note(n,tempo),old[part],lex)
    rows.append(r)
   lyric_diagnostics[part]={'source':part, 'method':'own_lyrics',
                            'notes':len(rows)}
  else:
   reference_part = ('Soprani' if part=='Alti' or (part=='Tenors' and not reference_by_part.get('Tenors')) else 'Tenors')
   reference = (soprano_sorted if reference_part=='Soprani'
                else reference_by_part.get('Tenors',[]))
   if not reference:
    raise ValueError(f'{part}: paroles de {reference_part} non disponibles')
   ref_syllables=[r for r in reference if r.get('syllable') not in ('','+')]
   assignments,info=align_lyrics(ref_syllables,raw)
   contractions,info=resolve_lyric_contractions(ref_syllables,raw,assignments,info)
   info['source']=reference_part
   info['method']='sequential'
   info['unassigned_lyrics_details']=[
       {'tick':ref_syllables[i]['tick'],'syllable':ref_syllables[i]['syllable']}
       for i in info['unassigned_lyrics']]
   lyric_diagnostics[part]=info
   if info['max_tick_offset']>3840:
    raise ValueError(f'{part}: attribution trop éloignée ({info["max_tick_offset"]} ticks); vérifier la partition')
   for idx,n in enumerate(raw):
    r=new_note(n,tempo)
    source=assignments[idx]
    if idx in contractions:
     contraction=contractions[idx]
     r['syllable']=contraction['syllable']
     r['word_continues']=contraction['word_continues']
     r['phonemes']=[]
     r['origin']='contracted_syllables_pending'
    elif source is not None:
     ref=ref_syllables[source]
     r['syllable']=ref['syllable']
     r['word_continues']=ref.get('word_continues',False)
     r['phonemes']=ref['phonemes'][:]
     r['origin']=f'{reference_part.lower()}_sequential_proposed'
    else:
     r['syllable']='+'
     r['word_continues']=False
     r['origin']='melisma_pending'
    apply_old(r,old[part],lex)
    rows.append(r)
  if part=='Tenors':
   reference_by_part['Tenors']=rows
  for start,stop,lyric,syllables in regions:
   targets=[r for r in rows if start<r['tick']<stop]
   if part in ('Tenors','Basses'):
    if len(targets)!=len(syllables):
     raise ValueError(f'{part}: tick={start}, parenthèse {lyric!r} = {len(syllables)} syllabes mais {len(targets)} notes ({[x["tick"] for x in targets]})')
    for r,syll in zip(targets,syllables):
     r['syllable']=syll
     r['phonemes']=list(lex.get(syll.casefold()) or EXTRA_PHONEMES.get(syll.casefold(),[]))
     r['origin']='parenthesis_aligned_proposed' if r['phonemes'] else 'missing'
     extras.append({'part':part,'tick':r['tick'],'syllable':syll,'annotation':lyric})
   elif targets:
    extras.append({'part':part,'tick':start,'info':f'{len(targets)} additional note(s) but no parenthesized words assigned'})
  for r in rows:
   previous=old[part].get((r['tick'],r['midi']))
   if previous and previous.get('origin','').startswith('manual') and previous.get('syllable')==r['syllable']:
    r['phonemes']=previous['phonemes'][:];r['origin']=previous['origin']
  write(work/f'{part}.review.json',doc(part,rows))
 if lyric_diagnostics: write(work/'syllable_alignment.json',lyric_diagnostics)
 return chord_info,regions,extras

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('rg',type=Path,help='Fichier Rosegarden .rg local')
 ap.add_argument('--output-dir',type=Path,default=Path('/output/partition'))
 ap.add_argument('--seed',type=Path,default=None,help='JSON phonétique de référence des premières mesures')
 ap.add_argument('--force',action='store_true',help='Autoriser la mise à jour des fichiers de révision (sauvegarde automatique)')
 ap.add_argument('--layout',choices=['auto','satb-2staves','satb-4staves'],default='auto')
 ap.add_argument('--upper-staff',help='Nom de la portée supérieure du fichier .rg')
 ap.add_argument('--lower-staff',help='Nom de la portée inférieure du fichier .rg')
 a=ap.parse_args()
 model,staff_diag=split_staff_model(parse(a.rg),layout=a.layout,upper_staff=a.upper_staff,lower_staff=a.lower_staff)
 model['staff_layout']=staff_diag['layout']
 scorepath=a.output_dir/'score.json';work=a.output_dir/'full'
 paths=[scorepath]+[work/f'{p}.review.json' for p in PARTS]
 if (scorepath.exists() or any(p.exists() for p in paths)) and not a.force:
  ap.error('Données existantes : ajouter --force (sauvegardes .bak)')
 old={p:old_index(work/f'{p}.review.json') for p in PARTS+('Soprani_divisi',)}
 if a.seed and a.seed.exists():
  oldseed=old_index(a.seed)
  for k,n in oldseed.items():
   old['Soprani'].setdefault(k,n)
 lex=read(work/'lexicon.json') if (work/'lexicon.json').exists() else {}
 if a.force:
  for p in [*paths,work/'Soprani_divisi.review.json']:
   if p.exists():shutil.copy2(p,p.with_suffix(p.suffix+'.bak'))
 a.output_dir.mkdir(parents=True,exist_ok=True)
 write(scorepath,model)
 chord_info,regions,extras=build(model,work,lex,old)
 write(work/'rg_alignment_diagnostics.json',{
  'staff_split':staff_diag,
  'chords':chord_info,
  'parentheses':[{'tick':t,'until':stop,'text':text,'syllables':syll} for t,stop,text,syll in regions],
  'male_assignments':extras})
 for p in PARTS+('Soprani_divisi',):
  path=work/f'{p}.review.json'
  if path.exists():
   rows=read(path)['notes']; missing=[r for r in rows if not r['phonemes']]
   print(f'{p:16}: {len(rows)} notes, {len(missing)} sans phonèmes')
 print(f'Accords divisi : {len(chord_info)}; annotations parenthèses : {len(regions)}')
 print('Répartition des portées :',staff_diag['staff_mapping'])
 print('Anacrouse décalée de',staff_diag['negative_tick_shift'],'ticks')
 print('Score :',scorepath,'\nDiagnostic :',work/'rg_alignment_diagnostics.json')
 print('Aucun modèle acoustique exécuté : utiliser chorale_full.py render après vérification des revues.')

if __name__=='__main__':main()

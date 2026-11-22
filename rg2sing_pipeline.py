#!/usr/bin/env python3
"""Pipeline rg2sing 0.9.5 : .rg -> revues -> rendu SATB et divisi -> mixage.

Les données restent locales. Une commande produit les étapes successives ;
les fichiers de travail existants sont sauvegardés et les validations
phonétiques incomplètes provoquent un arrêt explicite avant calcul GPU.
"""
import argparse,json,subprocess,sys
from pathlib import Path

SCRIPT=Path(__file__).resolve().parent
DEFAULT_WORK=Path('/output/partition')

def run(argv):
 print('+', ' '.join(map(str,argv)),flush=True)
 subprocess.run(list(map(str,argv)),check=True)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.epilog = 'Point d’entrée : importer une partition .rg, phonétiser, synthétiser et mixer. Exemple : rg2sing_pipeline.py --source-file /input/piece.rg --output-dir /output/tests/piece --layout auto --prepare-only --bootstrap-espeak'
 p.add_argument('--version',action='version',version='rg2sing 0.9.5')
 p.add_argument('rg',nargs='?',type=Path,help='Partition .rg (syntaxe historique)')
 p.add_argument('--source-file',type=Path,help='Nouvelle partition Rosegarden à tester')
 p.add_argument('--layout',choices=['auto','satb-2staves','satb-4staves'],default='auto')
 p.add_argument('--upper-staff',help='Nom exact de la portée supérieure')
 p.add_argument('--lower-staff',help='Nom exact de la portée inférieure')
 p.add_argument('--bootstrap-espeak',action='store_true',help='Proposer localement les phonèmes manquants, sans dictionnaire précédent')
 p.add_argument('--output-dir',type=Path,default=DEFAULT_WORK)
 p.add_argument('--settings',type=Path,default=SCRIPT/'singers.json')
 p.add_argument('--seed',type=Path,default=None)
 p.add_argument('--all',action='store_true',help='Exécuter préparation, analyses, synthèse et mixage (comportement par défaut)')
 p.add_argument('--prepare-only',action='store_true',help='Préparer la partition sans calculer les WAV')
 p.add_argument('--render-only',action='store_true',help='Réutiliser les revues déjà préparées')
 p.add_argument('--force',action='store_true',help='Autoriser la mise à jour des revues avec sauvegardes .bak')
 p.add_argument('--no-mix',action='store_true')
 p.add_argument('--resume',action='store_true')
 p.add_argument('--skip-word-analysis',action='store_true',help='Ne pas reconstruire les mots / produire le diagnostic v0.8')
 p.add_argument('--phoneme-align',action='store_true',help='Simuler le nouvel alignement phonétique v0.8.4 (sans modifier les revues)')
 p.add_argument('--apply-phoneme-align',action='store_true',help='Appliquer uniquement les insertions consonantiques sûres v0.8.4')
 p.add_argument('--skip-french-phonetics',action='store_true',help='Ne pas appliquer les règles contextuelles (diagnostic non exécuté)')
 p.add_argument('--parts',nargs='+',default=['Soprani','Alti','Tenors','Basses','Soprani_divisi'],
                choices=['Soprani','Alti','Tenors','Basses','Soprani_divisi'])
 args=p.parse_args()
 if args.all and (args.prepare_only or args.render_only):
  p.error('--all ne peut pas être combiné avec --prepare-only ou --render-only')
 if args.prepare_only and args.render_only:
  p.error('--prepare-only et --render-only sont incompatibles')
 if args.rg is not None and args.source_file is not None:
  p.error('Utiliser soit un argument .rg, soit --source-file, pas les deux')
 source=args.source_file or args.rg
 if source is None:
  p.error('Indiquer une partition .rg ou --source-file fichier.rg')
 if not source.is_file():
  p.error(f'Fichier source introuvable : {source}')
 # Ne jamais mélanger par défaut les données d'une nouvelle œuvre avec /output/partition.
 if args.source_file and args.output_dir==DEFAULT_WORK:
  import re
  slug=re.sub(r'[^A-Za-z0-9_.-]+','_',source.stem).strip('._') or 'composition'
  args.output_dir=Path('/output/tests')/slug
 print(f'rg2sing 0.9.5\nSource : {source}\nSortie : {args.output_dir}\nRevues : {args.output_dir / "full"}\nMode : {args.layout}',flush=True)
 if args.bootstrap_espeak and args.render_only:
  p.error('--bootstrap-espeak est réservé à la préparation initiale')
 if not args.render_only:
  cmd=[sys.executable,SCRIPT/'rg2sing_sync.py',source,'--output-dir',args.output_dir]
  cmd+=['--layout',args.layout]
  if args.upper_staff:cmd+=['--upper-staff',args.upper_staff]
  if args.lower_staff:cmd+=['--lower-staff',args.lower_staff]
  if args.seed:cmd+=['--seed',args.seed]
  if args.force:cmd+=['--force']
  run(cmd)
  if args.bootstrap_espeak:
   run([sys.executable,SCRIPT/'rg2sing_bootstrap.py','--work',args.output_dir/'full'])
 if not args.skip_french_phonetics:
  run([sys.executable,SCRIPT/'french_singing.py','--work',args.output_dir/'full','--apply'])
 if not args.skip_word_analysis:
  run([sys.executable,SCRIPT/'french_words.py','--work',args.output_dir/'full'])
 if args.phoneme_align or args.apply_phoneme_align:
  if args.skip_word_analysis:
   p.error('--phoneme-align exige la génération du diagnostic lexical')
  cmd=[sys.executable,SCRIPT/'french_align.py','--work',args.output_dir/'full']
  if args.apply_phoneme_align:
   if args.resume:p.error('--resume est incompatible avec --apply-phoneme-align : WAV possiblement obsolètes')
   cmd+=['--apply']
  run(cmd)
 if args.prepare_only:return
 if not args.settings.is_file():p.error('Fichier chanteurs manquant : '+str(args.settings))
 settings=json.loads(args.settings.read_text(encoding='utf-8'))
 for part in args.parts:
  review_path=args.output_dir/'full'/f'{part}.review.json'
  if not review_path.is_file():
   print(f'[{part}] absent de la partition : rendu ignoré',flush=True)
   continue
  spec=settings.get(part)
  if not spec:raise ValueError(f'Chanteur non configuré pour {part} dans {args.settings}')
  cmd=[sys.executable,SCRIPT/'chorale_full.py','render','--work',args.output_dir/'full',
       '--part',part,'--singer',spec['singer'],'--vocoder',spec.get('vocoder','nsf'),
       '--steps',str(spec.get('steps',20)),'--depth',str(spec.get('depth',0.6)),
       '--allow-proposals']
  if spec.get('speaker'):cmd+=['--speaker',spec['speaker']]
  if args.resume:cmd+=['--resume']
  run(cmd)
 if not args.no_mix and {'Soprani','Alti','Tenors','Basses'}.issubset(set(args.parts)):
  run([sys.executable,SCRIPT/'chorale_full.py','mix','--work',args.output_dir/'full'])
 else:print('Mixage non demandé (ou pupitres incomplets).')

if __name__=='__main__':main()

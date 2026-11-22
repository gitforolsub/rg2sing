# rg2sing 0.9.5 — distribution consolidée

Logiciel expérimental de synthèse chorale SATB, intégralement **local**. Archives sans `singers.json` : conserve ta configuration existante.

## Installer

Décompresser les fichiers Python dans `/scripts`. Les fichiers `.py` ont un mode Unix 0755 **dans le ZIP** ; avec sshfs/FUSE la restitution des permissions dépend aussi du montage et de `unzip`.

Les scripts Python servant d'outils ont l'option `-h` / `--help`. Les modules Python (`rg2sing_lyrics.py`, `french_phonemes.py`, etc.) ne sont pas des exécutables. Les fichiers `test_*.py` sont destinés à `unittest`.

Ce paquet inclut tous les scripts actuels hors `mix.py` (ancienne interface remplacée par `chorale_full.py mix`). Ne pas supprimer arbitrairement d'anciens fichiers du volume si d'autres workflows y font appel.

## Préparer une nouvelle partition (depuis zéro)

À refaire dans **chaque nouveau shell du conteneur** :

```bash
SOURCE='/input/nouvelle-partition.rg'
WORK='/output/tests/nouvelle-partition'
FULL="$WORK/full"

rg2sing_pipeline.py --source-file "$SOURCE" --output-dir "$WORK" \
  --layout auto --prepare-only --bootstrap-espeak
chorale_full.py status --work "$FULL"
```

`--layout auto` doit être vérifié sur les notations atypiques. Préciser `--layout satb-2staves` ou `satb-4staves` si nécessaire. Choisir un **nouveau WORK** pour chaque essai indépendant. Si tu veux effacer ce WORK, vérifier explicitement le chemin avant `rm -rf -- "$WORK"`.

## Écouter et comparer

```bash
SOURCE='/input/nouvelle-partition.rg'
WORK='/output/tests/nouvelle-partition'
FULL="$WORK/full"

french_liaisons.py --work "$FULL"        # simulation
french_liaisons.py --work "$FULL" --apply
chorale_full.py status --work "$FULL"
rg2sing_pipeline.py --source-file "$SOURCE" --output-dir "$WORK" \
  --layout auto --render-only --resume
```

Le mixage est normalement `$FULL/chorale_satb.mp3`, à condition que `ffmpeg` soit installé. Les WAV par pupitre sont dans le même répertoire. `--resume` réutilise les segments identifiés comme inchangés. Conserver une copie du MP3 avant comparaison. **Ne pas utiliser `--prepare-only --force` pour réécouter des retouches manuelles : cela pourrait écraser les revues.**

## Commandes principales

| Programme | Utilité |
|---|---|
| `rg2sing_pipeline.py` | Orchestration de l'ensemble, `--version`, `--source-file`, `--output-dir`, `--prepare-only`, `--render-only`, `--all` |
| `rg2sing_sync.py` | Interprétation du fichier Rosegarden et préparation des pupitres |
| `rg2sing_bootstrap.py` | Proposition phonétique eSpeak-NG sur les mots reconstruits |
| `chorale_full.py` | Préparation et suivi des revues, rendu ONNX, mixage |
| `french_singing.py` | Corrections françaises contextuelles utilisées pendant la préparation |
| `french_liaisons.py` | Simulation / application explicite des liaisons et silences |
| `french_words.py` | Diagnostic des mots regroupés |
| `french_align.py` | Diagnostic / application prudente de l'alignement des phonèmes |
| `suggest_espeak.py` | Suggestions pour le lexique, hors workflow habituel |
| `phoneme_timing.py` | Diagnostic des durées phonétiques |
| `test_all_voices.py` | Comparaison de banques et de speakers |
| `rg2sing.py`, `export_ustx.py` | Import bas niveau et export OpenUtau |
| `prepare_singing.py`, `render_millefeuille_duration.py`, `millefeuille_*.py` | Fonctions de durée, pitch et rendu bas niveau |
| `rg2sing_lyrics.py`, `rg2sing_staves.py`, `french_phonemes.py`, `french_lexical_context.py` | Modules importés, non destinés à être lancés directement |

## Nouvelle liaison « permet ainsi »

Pour une diction chorale soignée, la liaison facultative en /t/ est désormais proposée après **permet** devant un mot à attaque vocalique, sans silence. Elle est vérifiée par les mêmes contrôles que les autres liaisons : syllabes distinctes, attaque vocalique, absence de consonne déjà présente, protection des révisions manuelles. Cela ne signifie pas que cette liaison est obligatoire dans toute diction parlée.

## Tests sans GPU

```bash
cd /scripts
python3 -m unittest discover -p 'test_*.py' -q
```

## Conteneur Docker

Prévoir au Dockerfile :

```dockerfile
ENV PATH="/scripts:/opt/venv/bin:${PATH}"
ENV PYTHONPATH=/scripts
ENV LANG=C.UTF-8
```

L'inférence et les phonétiseurs fonctionnent sans réseau. Les modèles et dépendances sont préparés lors de la construction de l'image.

# rg2sing 0.9.3 — homographes contextuels et divisi facultatif

Correctif incrémental destiné à la distribution consolidée 0.8.9 + correctifs 0.9.0, 0.9.1 et 0.9.2.

## Fichiers à remplacer dans /scripts
- `rg2sing_bootstrap.py` — sélection lexicale sûre avant acceptation d'eSpeak.
- `rg2sing_pipeline.py` — version 0.9.3, saute les parties absentes.
- `french_lexical_context.py` — nouveau module réutilisable pour des homographes.
- `test_french_lexical_context.py` et `test_lexical_bootstrap.py` — tests.

**Aucun `singers.json`, aucun fichier de partition, aucune modification des modèles.**

## Comportement
- `au Fils` ou `un fils` : /fis/, soit `fr/f fr/ih fr/s`, même si eSpeak propose /fil/.
- `des fils` / `deux grands fils` : ambiguïté non levée automatiquement. Elle reste dans le diagnostic : le programme ne devine pas s'il s'agit de descendants ou de fils textiles.
- N'écrase pas les corrections manuelles (`manual*`, `reference_verified*`).
- Peut corriger une ancienne attribution `espeak_word_proposed` dans un fichier `.review.json` existant.
- Ignore `Soprani_divisi` au rendu si son `.review.json` n'existe pas.

Il s'agit d'un premier résolveur **prudent**, et non d'un analyseur sémantique général du français.

## Application sans recommencer la préparation
Dans le conteneur :

```bash
WORK=/output/tests/louange-v092
FULL="$WORK/full"
rg2sing_pipeline.py --version
python3 -m unittest test_french_lexical_context test_lexical_bootstrap -v
rg2sing_bootstrap.py --work "$FULL"
chorale_full.py status --work "$FULL"
```

Pour revoir la proposition `Fils` :

```bash
python3 - "$FULL" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
for p in ('Soprani','Alti','Tenors','Basses'):
    notes=json.loads((root/f'{p}.review.json').read_text())['notes']
    print(p, [(n['tick'],n.get('phonemes'),n.get('origin')) for n in notes if n.get('syllable','').casefold()=='fils'])
PY
```

La ré-exécution de bootstrap ne modifie pas les WAV existants. Pour regénérer le rendu en réutilisant les morceaux non modifiés :

```bash
rg2sing_pipeline.py --source-file /input/louange-2portees-propre-corrigé-DB-revu.rg \
  --output-dir "$WORK" --layout satb-2staves --render-only --resume
```

Les clés SHA-256 des segments changés invalident automatiquement leur cache. Le mixage est reconstruit à la fin. La partition et les données restent locales.

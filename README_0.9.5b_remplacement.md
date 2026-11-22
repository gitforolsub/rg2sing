# rg2sing 0.9.5b — remplacement complet des fichiers

Ces fichiers s'installent par extraction du ZIP **sur l'hôte**, puis copie directe dans `/scripts` du conteneur. Aucun `unzip` n'est requis dans le conteneur.

Remplacer `rg2sing_sync.py` et `rg2sing_lyrics.py` après sauvegarde locale. Copier les deux tests `test_lyrics_contractions.py` et `test_sync_contraction_integration.py` dans `/scripts`. Aucun `singers.json`, aucune partition ni aucun enregistrement n'est inclus.

La base de `rg2sing_sync.py` est celle du miroir GitHub au commit `2116707740e8c4061b6f6a4cbd9c6b17dbd2619d`, branche main (22 novembre 2026). Le code installé déclaré par l'utilisateur conserve le bloc d'alignement d'origine; des adaptations locales ailleurs dans ce fichier ne sont pas couvertes et seraient écrasées par un remplacement entier.

## Validation

```bash
SOURCE='/input/psaume23-corrigé-DB.rg'
WORK='/output/tests/psaume23-095b-complet'
FULL="$WORK/full"

python3 -m py_compile /scripts/rg2sing_sync.py /scripts/rg2sing_lyrics.py
PYTHONPATH=/scripts python3 -m unittest -v test_lyrics_contractions test_sync_contraction_integration test_rg2sing_lyrics test_voice_lyrics_sources
python3 /scripts/rg2sing_sync.py "$SOURCE" --output-dir "$WORK" --layout auto
python3 - "$FULL" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);a=json.loads((p/'syllable_alignment.json').read_text())['Alti'];r=json.loads((p/'Alti.review.json').read_text())['notes']
print('Contractions :',a.get('contracted_lyrics'))
print('Syllabes sans note :',a.get('unassigned_lyrics_details'))
print([(n['tick'],n['syllable']) for n in r if n['tick'] in (77760,80640)])
PY
```

Attendu : contraction `sible` à 77760 et `De` à 80640. Les phonèmes de `sible` ne sont **pas copiés** depuis `si` : ils devront être régénérés par la phonétisation habituelle.

## Limites

La contraction n'est effectuée que pour des syllabes explicitement reliées par `word_continues`, temporellement contiguës et couvertes par la note cible. Aucune altération de la hauteur, du tempo, des reprises ou du divisi. Le test complet de la partition réelle reste à exécuter dans le conteneur.

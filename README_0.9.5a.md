# rg2sing — correctif 0.9.5a : sources de paroles SATB

Correctif incrémental pour la base rg2sing 0.9.5 (ne touche pas à singers.json).

Dans une partition à quatre portées :
- Soprani : paroles locales si présentes ;
- Alti : paroles locales si présentes, sinon paroles Soprani ;
- Tenors : paroles locales si présentes, sinon paroles Soprani ;
- Basses : paroles locales si présentes, sinon paroles Tenors (lesquelles peuvent elles-mêmes provenir des sopranos quand aucun texte ténor n'existe).

Une source locale n'est jamais remplacée par une autre. En l'absence de paroles locales,
l'alignement se fait dans l'ordre des syllabes (pas seulement à tick égal).
L'outil consigne les correspondances, les prolongations et les syllabes laissées
sans note dans `full/syllable_alignment.json`.

**Attention** : sur `psaume23-corrigé-DB.rg`, l'alignement Soprani→Alti laisse
une syllabe `ble` (tick 79680) non affectée. Ce cas est volontairement conservé
dans le diagnostic : ne pas considérer une préparation automatique comme validée
sans vérifier cette discordance musicale.

Installation : extraire `rg2sing_sync.py` dans `/scripts`, sans supprimer les autres scripts.
Les modifications des paroles nécessitent une **nouvelle préparation à partir du .rg** :
```
SOURCE='/input/psaume23-corrigé-DB.rg'
WORK='/output/tests/psaume23-sourcefix'
FULL="$WORK/full"
rg2sing_pipeline.py --source-file "$SOURCE" --output-dir "$WORK" --layout auto --prepare-only --bootstrap-espeak
chorale_full.py status --work "$FULL"
cat "$FULL/syllable_alignment.json"
```
Les fichiers de travail existants ne sont pas touchés ; ne pas lancer `--render-only`
sur l'ancien répertoire pour tester ce changement d'alignement.

Tests : `PYTHONPATH=/scripts python3 /scripts/test_voice_lyrics_sources.py -v`.

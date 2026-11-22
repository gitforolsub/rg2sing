# rg2sing — essai de superposition de chanteurs

Expérience non intrusive de mélange de deux ou trois rendus de **la même voix musicale** par plusieurs **chanteurs différents**. La durée et l'origine temporelle (t=0) des WAV doivent correspondre. Le script ne calcule aucun nouveau chant et ne modifie pas les fichiers de révision. Installation : déposer `rg2sing_choir_layers.py` dans `/scripts` (permission 0755 incluse dans le ZIP). Aide : `rg2sing_choir_layers.py -h`.

Dans le conteneur (toutes les commandes redéfinissent les chemins) :

```bash
SOURCE='/input/louange-2portees-propre-corrigé-DB-revu.rg'
WORK='/output/tests/louange-v092'
FULL="$WORK/full"
LAYER="$FULL/choir_layers"
mkdir -p "$LAYER/tiger" "$LAYER/mimosa" "$LAYER/hibya"
cp "$FULL/Tenors.review.json" "$LAYER/mimosa/"
cp "$FULL/Tenors.review.json" "$LAYER/hibya/"
cp "$FULL/Tenors.review.json" "$LAYER/tiger/"
```

Effectuer ensuite les deux rendus avec `chorale_full.py render --work "$LAYER/felix" --part Tenors --singer NOM_CHANTEUR --speaker NOM_SPEAKER --vocoder nsf --steps 20 --depth 0.6 --allow-proposals` en remplaçant NOM_CHANTEUR et NOM_SPEAKER par une combinaison connue et compatible. Faire de même pour `$LAYER/autre` avec une autre voix. Pour la référence, on peut simplement utiliser `$FULL/Tenors.wav` et ne rendre que l'autre voix.

Comparer le solo, puis le duo :

```bash
rg2sing_choir_layers.py \
 --voice "$FULL/Tenors.wav" 0.55 -0.30 0 \
 --voice "$LAYER/autre/Tenors.wav" 0.45 0.30 17 \
 --output "$LAYER/duo_tenors.wav" --mp3
```

La première voix est à gauche de 30 %, la seconde à droite de 30 % avec 17 ms de retard ; le retard est volontairement petit et ne change pas la structure musicale. Ne pas retarder de plusieurs dizaines de ms dans les passages rythmiquement rapides. Tester aussi 0 ms si le retard produit un écho. Le mix ne remplace pas les quatre voix SATB : il épaissit **un pupitre à la fois**. Ne pas réutiliser les noms de répertoires d'un chanteur pour un autre ; le paramètre `--resume` et les caches sont séparés.

La réverbération, les variations d'expression et la création d'un mix SATB complet peuvent être ajoutées lors des expériences suivantes. La fusion de deux WAV strictement identiques ne donne pas deux chanteurs ; elle ne fait qu'augmenter le niveau ou provoquer du filtrage si on les décale.

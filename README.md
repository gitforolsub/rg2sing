# Test contrôlé des vocodeurs Millefeuille

Cette archive **incrémentale** contient `render_millefeuille_duration.py` (ajout de
`--features-in` et `--features-out`), `rg2sing_vocoder_bench.py` et
`test_vocoder_bench.py`. Aucun `singers.json`.

À installer dans `/scripts` du conteneur, en remplaçant seulement le renderer.
Les autres scripts rg2sing 0.9.5 restent inchangés.

## Test rapide

```bash
WORK=/output/tests/louange-v092
FULL="$WORK/full"
python3 /scripts/test_vocoder_bench.py -v
rg2sing_vocoder_bench.py --work "$FULL" --part Tenors --start-tick 24000 --notes 14 --dry-run
rg2sing_vocoder_bench.py --work "$FULL" --part Tenors --start-tick 24000 --notes 14
```

Les sorties se trouvent dans `"$FULL/vocoder_bench/Tenors_24000/"`.
Lire `ecoute_enchainee.wav`, les WAV individuels et `comparaison.csv`.

Les vocodeurs doivent tous posséder des paramètres compatibles (vérification
stricte héritée du renderer). Si l'un ne correspond pas, le programme s'arrête
sans prétendre que la comparaison est valide. Le premier vocodeur produit un
unique spectrogramme et une courbe f0 ; tous les suivants relisent les mêmes
valeurs depuis un `.npz` (sans pickle). Aucun accès réseau.

Ce test **ne change pas de modèle acoustique**. Si les trois timbres restent
semblables, il faut envisager une nouvelle banque/modèle avant d'introduire
des imperfections d'intonation aléatoires.

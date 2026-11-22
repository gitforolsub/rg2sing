# rg2sing — banc d'essai de naturel 0.9.6 (prototype)

## But

Comparer un même extrait d'un pupitre en faisant varier **un seul paramètre à la fois**. Les phonèmes, la hauteur, la durée globale, la voix et le vocodeur restent inchangés (sauf lorsque la variante indique explicitement le contraire). Aucune connexion réseau.

## Installation

Décompresser les deux fichiers Python dans `/scripts` sans modifier `singers.json`. Chaque `.py` est archivé en mode Unix 0755.

## Commandes autonomes après redémarrage du conteneur

```bash
SOURCE='/input/louange-2portees-propre-corrigé-DB-revu.rg'
WORK='/output/tests/louange-v092'
FULL="$WORK/full"

rg2sing_naturalness_bench.py --work "$FULL" --part Tenors --start-tick 0 --notes 14 --dry-run
rg2sing_naturalness_bench.py --work "$FULL" --part Tenors --start-tick 0 --notes 14
```

Pour une autre partition, modifier `SOURCE` et `WORK` et vérifier que `FULL` contient la revue du pupitre choisi. Le banc ne lit pas `SOURCE`, qui reste indiqué pour la cohérence des procédures.

## Résultats

Sous `FULL/naturalness/Tenors_0/` :

- `01_reference.wav` : plafonds de consonnes 100 ms, glide 55 ms, finale 65 ms, diffusion 20 pas.
- `02_consonnes_courtes.wav` : plafonds 65 / 55 / 45 ms.
- `03_consonnes_souples.wav` : plafonds 140 / 55 / 90 ms.
- `04_glides_courts.wav` : plafonds 100 / 30 / 65 ms.
- `05_diffusion_40.wav` : 40 pas, autres paramètres identiques à la référence.
- `ecoute_enchainee.wav` : cinq extraits à volume RMS approximativement égal, séparés par des silences.
- `comparaison.csv` : durées, niveau RMS, crête, pourcentage de voyelles, durée des consonnes nasales et semi-voyelles.
- fichiers `.json` des durées et `.log` de rendu, pour diagnostic.

Le test porte sur un seul pupitre et non sur la polyphonie. La qualité du timbre dépend aussi de la banque vocale et du vocodeur, que ce premier protocole conserve constants.

`--resume` est réservé à une relance à données inchangées ; en cas de modification des phonèmes de la revue ou des modèles, supprimer l'ancien répertoire d'essai ou choisir un autre `--output-dir`.

## Tests et aide

```bash
python3 /scripts/test_naturalness_bench.py -v
rg2sing_naturalness_bench.py -h
```

Le benchmark ne modifie ni le score Rosegarden, ni les revues, ni `singers.json`, ni les WAV existants des pupitres. Les fichiers sont créés dans un dossier d'essai séparé.

**Limites** : ce premier banc n'évalue pas dspitch (flat pitch pour rester reproductible). Il n'implémente pas encore un entraînement des modèles ou une simulation réaliste de choristes multiples. Le contrôle des paramètres acoustiques est expérimental et doit être évalué à l'écoute.

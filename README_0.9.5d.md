# rg2sing 0.9.5d — Attribution SATB par ordre des pistes

Correctif Rosegarden **sans modification de singers.json**.

## Contenu

- `rg2sing_staves.py` : nouvelle option `force_satb=False` dans `split_staff_model` ; quand vraie, les quatre `track_id` contenant des notes sont triés numériquement et affectés à Soprani, Alti, Tenors et Basses. Les noms de segments, notamment `Acoustic Grand Piano`, ne sont pas utilisés pour décider de la voix.
- `rg2sing_sync.py` : option CLI `--force-satb` ; conserve les corrections 0.9.5b et la détection des vraies paroles (marqueur `+` exclu).
- `test_force_satb.py` : six tests, notamment pistes non contiguës, multiples segments, contrôle du nombre de pistes, absence de changement sans l'option.

`--force` continue à désigner **l'autorisation de remplacer des revues existantes** ; `--force-satb` ne l'implique pas.

## Installation

Extraire sur l'hôte puis remplacer **uniquement** les deux fichiers `rg2sing_staves.py` et `rg2sing_sync.py` dans `/scripts`. Copier également `test_force_satb.py`. Préserver les autres modules, spécialement `rg2sing_lyrics.py`, et la configuration `singers.json`.

## Essai complet (redéfinir ces variables à chaque shell)

```bash
SOURCE='/input/nouvelle-partition.rg'
WORK='/output/tests/nouvelle-partition-095d'
FULL="$WORK/full"

python3 /scripts/rg2sing_sync.py "$SOURCE" --output-dir "$WORK" --force-satb
python3 -m json.tool "$FULL/rg_alignment_diagnostics.json"
python3 -m json.tool "$FULL/syllable_alignment.json"
```

## Tests

```bash
SOURCE='/input/nouvelle-partition.rg'
WORK='/output/tests/nouvelle-partition-095d'
FULL="$WORK/full"
cd /scripts
python3 -m unittest -v test_force_satb test_staves_aliases test_rg2sing_staves
python3 -m unittest discover -p 'test_*.py' -q
python3 rg2sing_sync.py -h
```

## Limites et sécurité

L'option `--force-satb` est intentionnelle : l'ordre croissant des **identifiants Rosegarden** est présumé correspondre à S/A/T/B. Cela n'est pas déduit des hauteurs de notes. Le diagnostic JSON indique `forced_satb: true`, `track_count: 4` et l'affectation exacte de chaque `track_id`.

Le mode refuse une partition ayant moins ou plus de quatre pistes avec des notes, ainsi que sa combinaison avec `--layout satb-2staves`. Des pistes vides ou sans notes ne comptent pas. Aucune modification aux modules de phonétisation, de rendu, ni à l'importation de formats autres que Rosegarden.

## Correctif de non-régression (0.9.5d-r1)

Conserve le mode explicite `--layout satb-4staves` pour les modèles partiels dont les parties sont déjà nommées (par exemple un seul `Soprani` dans le test de chronologie). Ce mode ne devine aucune voix pour des noms ambigus. L’option `--force-satb` exige toujours exactement quatre pistes contenant des notes. Copier impérativement `test_force_satb.py` dans `/scripts`, en plus des deux scripts complets.

# rg2sing 0.9.4 — liaisons contextuelles

Correctif incrémental **sur la version 0.9.3**, sans `singers.json`.

Fichiers à déposer dans `/scripts` :

- `french_liaisons.py` : nouveau module de décision des liaisons en /z/, /n/, /t/ à partir des frontières de mots reconstruites, de l'attaque phonétique et des silences entre notes ; outil autonome de diagnostic / application.
- `french_singing.py` : appelle le module de liaisons dans le passage habituel des corrections françaises. L'ancienne logique de liaison z par syllabe est supprimée.
- `rg2sing_pipeline.py` : version 0.9.4.
- `test_french_liaisons.py` : tests de non-régression.

Les seules règles automatiquement appliquées sont celles de classes lexicales prudentes :
- /z/ : déterminants pluriels et quelques pronoms (`les`, `des`, `mes`, `tes`, `ses`, `ces`, `nos`, `vos`, `leurs`, `aux`, `deux`, `trois`, `nous`, `vous`, `ils`, `elles`)
- /n/ : `un`, `mon`, `ton`, `son`, `on`, `en`
- /t/ : `soit`, `est`, `sont`, `quand`

Elles ne sont envisagées que devant un phonème vocalique ou une semi-voyelle et **sans silence musical**. Le moteur n'ajoute pas de consonne si elle est déjà présente, et ne modifie pas les phonèmes manuels de la syllabe cible. « et » et quelques exceptions de liaison sont exclus. L'analyse grammaticale est encore partielle : les vrais cas ambigus ou facultatifs ne sont pas couverts.

## Installation

```bash
unzip -o rg2sing_0.9.4_correctif.zip -d /var/data/diffsinger.subilia.info/scripts
```

(adapter le chemin du volume si besoin). Dans le conteneur :

```bash
rg2sing_pipeline.py --version
cd /scripts && python3 -m unittest discover -p 'test_*.py' -v
```

## Application à la composition existante

```bash
WORK=/output/tests/louange-v092
FULL="$WORK/full"
french_liaisons.py --work "$FULL"     # simulation et rapport
french_liaisons.py --work "$FULL" --apply
```

Le rapport est `french_liaisons_report.csv`. Des sauvegardes datées `.before_liaison_*` sont créées pour toute partie modifiée. La commande est idempotente pour les liaisons déjà présentes.

```bash
rg2sing_pipeline.py \
  --source-file '/input/louange-2portees-propre-corrigé-DB-revu.rg' \
  --output-dir "$WORK" --layout satb-2staves --render-only --resume
```

Ne **pas** relancer `--prepare-only --force`. Les anciens WAV sont préservés jusqu'à l'écriture des nouveaux ; le moteur reprend les segments non modifiés si la clé de cache les identifie correctement. Pour une comparaison fiable, sauvegarder d'abord le MP3 antérieur.

## Validation locale

90 tests Python réussis sur la distribution 0.8.9 plus les correctifs 0.9.0 à 0.9.4. Aucun test CUDA complet n'a été exécuté ici. Tout s'exécute localement, sans service réseau.

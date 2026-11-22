# rg2sing 0.9.0 — reconstructions lexicales et partition prioritaire

Correctif **incrémental pour l'installation 0.8.9**. Copier les fichiers `.py` de cette archive dans `/scripts` (en écrasant les noms identiques). **Aucun `singers.json`**, aucun autre script à effacer.

## Changements

- `french_words.py` : les tirets musicaux `Lou- | an- | ge` ne concurrencent plus artificiellement la forme lexicale attestée `louange`. Si la forme soudée présente une fréquence française suffisante, elle prime sur les variantes comportant des tirets de syllabation, même si la fréquence artificielle de ces variantes est élevée. Le vrai mot composé `porte-clé` reste sélectionnable quand `porteclé` n'est pas lexicalement attesté. Les cas réellement incertains restent signalés.
- `french_align.py` : le digramme français `ui` associé à `fr/uh fr/ih` en sortie eSpeak se convertit en `fr/uy fr/ih`, sans ajouter de noyau vocalique. Tests sur `lui` et `puissance`. Les autres voyelles ne sont pas modifiées.
- **Respect de la partition :** `vi | e`, qui représente deux notes pour « vie » prononcé sur une syllabe, reste un refus explicite. Le programme **n'ajoute pas** de voyelle pour masquer cette erreur de notation : la partition doit être corrigée dans Rosegarden. Une éventuelle diérèse voulue aurait besoin d'une confirmation musicale explicite.
- `rg2sing_bootstrap.py` : affiche séparément le nombre de notes vides et marqueurs `+` restant sans phonèmes ; cela ne constitue pas une correction automatique du mélisme.
- `rg2sing_pipeline.py --version` : `0.9.0`.

## Vérification

```bash
rg2sing_pipeline.py --version
cd /scripts
python3 -m unittest discover -p 'test_*.py' -v
```

Sur la distribution consolidée 0.8.9 avec ce correctif, **67 tests unitaires réussis** en environnement de développement (tests sans GPU ni eSpeak). L'extraction de la véritable partition « Louange » a également été testée : 150/147/147/144 notes S/A/T/B. Le rendu CUDA et l'amorçage par eSpeak dans votre conteneur restent à tester.

## Rejouer la préparation contextuelle sans effacer les fichiers existants

```bash
WORK='/output/tests/louange-2portees-propre-corrig_-DB-db'
rg2sing_bootstrap.py --work "$WORK/full"
chorale_full.py status --work "$WORK/full"
```

Pour un essai **strictement ab ovo**, conserver les anciens résultats en renommant le dossier (ou le supprimer volontairement), puis :

```bash
rg2sing_pipeline.py \
    --source-file '/input/louange-2portees-propre-corrigé-DB-db.rg' \
    --layout satb-2staves \
    --prepare-only \
    --bootstrap-espeak
```

Il est prévu que d'autres erreurs subsistent : `vi | e` nécessite la correction de la partition, les notes sans texte/`+` doivent être vérifiées comme mélismes et certaines reconstructions demandent encore une analyse musicale/phonétique. Ne pas lancer le rendu tant que les notes manquantes n'ont pas été comprises.

Toute la chaîne s'exécute en local ; les compositions ne sont pas transmises à des services en ligne.

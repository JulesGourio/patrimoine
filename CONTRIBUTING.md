# Contribuer à Patrimoine

Merci de t'y intéresser. Le projet est jeune comme projet partagé : les contributions qui l'ouvrent à d'autres
banques, courtiers et pays comptent le plus.

## Avant de commencer

- Ouvre une *issue* pour discuter d'un gros changement avant de l'écrire.
- **Ne mets jamais de données personnelles** dans une issue, une PR ou un test : relevés réels, IBAN, soldes,
  noms, jetons. Anonymise ou invente des données de test.
- Aucun secret dans le code, `.env` ou la base : tout passe par `patrimoine/vault.py`.

## Mettre en place

```bash
uv sync
uv run pytest        # doit passer avant toute PR
```

## Règles du code

- Montants en **centimes entiers** ; quantités de titres en réel.
- Un virement entre comptes de l'utilisateur est `interne` (ni dépense ni revenu).
- Le moteur (`patrimoine/`) ne doit importer ni Streamlit, ni `mcp`, ni Plotly, ni keyring, ni matplotlib au
  chargement : `tests/test_portable.py` le vérifie. Un nouvel outil se déclare une fois avec `@tool` dans
  `patrimoine/api.py`.
- **Jamais d'ordre de bourse passé par le code ou par l'IA** : on prépare, l'utilisateur exécute.
- Tout code qui touche l'argent, les secrets, la synchro ou la base a besoin de tests.
- Commits clairs, une idée par PR. Code en anglais de préférence, textes affichés en français (ou via
  l'internationalisation quand elle existera).

## Ajouter une banque ou un courtier

Chaque établissement vit dans `patrimoine/sources/`. Un bon point de départ est l'import CSV, qui n'exige ni accès
API ni secret :

1. Écris un parseur qui transforme le fichier en opérations `(date, libellé, montant en centimes, compte)`
   (voir `patrimoine/sources/cmb_parse.py` et `cmb_csv.py` comme modèles).
2. Branche-le dans `patrimoine/imports.py` et la commande de `patrimoine/cli.py`.
3. Ajoute des tests avec un **faux** fichier d'exemple dans `tests/`.
4. Ajoute la ligne du tableau « Sources prises en charge » du README.

Une interface de connecteurs plus propre est prévue : voir `docs/GENERALISATION.md`, tes retours sont bienvenus.

## Pull request

Décris le changement, la manière de le vérifier, et coche la liste du modèle de PR. Les tests (`.github/workflows/tests.yml`)
doivent être verts.

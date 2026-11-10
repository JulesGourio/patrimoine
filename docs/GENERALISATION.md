# Ouvrir Patrimoine à d'autres utilisateurs

L'outil a été écrit pour une seule personne. Ce document liste ce qui reste à rendre configurable, du plus utile
au moins urgent. Chaque point est un bon sujet de PR ; ouvre une issue avant de te lancer.

## 1. Comptes et établissements (le plus important)

Les comptes sont codés en dur (`patrimoine/db.py`, liste `ACCOUNTS` : `cmb_courant`, `cmb_livret_a`, `tr_cto`,
`tr_pea`, `peg_airbus`…) et ces identifiants sont référencés dans `sync.py`, `portfolio.py`, `queries.py`, `api.py`,
`analytics.py`, `imports.py`, `app_pages/accueil.py` et `app_pages/fiscalite.py`.

À faire : une configuration des comptes de l'utilisateur (table ou fichier `data/comptes.toml` créé par
`patrimoine init`), plutôt qu'une liste fixe ; remplacer chaque identifiant en dur par une recherche par type
(`courant`, `livret`, `cto`, `pea`, `peg`…).

## 2. Interface de connecteurs

Aujourd'hui `patrimoine/sources/` mélange des parseurs (`cmb_parse`, `tr_parse`, `amundi`) et des clients
(`enable_banking`, `trade_republic`). À faire : un contrat commun, par exemple un connecteur qui expose
`fetch_transactions()`, `fetch_positions()` et `balance()`, déclaré dans un registre. Premiers candidats :

- un **import CSV générique** configurable (colonnes, séparateur, format de date) : couvre presque toutes les banques ;
- d'autres banques via **Enable Banking** (même API que la CMB) ;
- d'autres courtiers (Boursorama, Degiro, Interactive Brokers, Fortuneo…) par export de fichier.

## 3. Règles de catégories et libellés

`patrimoine/categories.py` contient des motifs liés à l'historique du premier utilisateur (lieux, commerces,
libellés de virements propres à ses comptes). `sources/cmb_parse.py` contient la liste des libellés de virements
internes. À faire : un jeu de règles par défaut neutre + un fichier de règles utilisateur ; détecter les virements
internes à partir des comptes configurés, plutôt que par libellés écrits à la main.

## 4. Lignes de portefeuille et indices de référence

`briefing.py` (`BENCH`), `radar.py` et `queries.py` (`TER`) contiennent les ISIN du premier utilisateur avec leur
indice de référence, levier et frais. À faire : déduire l'indice de référence et le TER des fonds détenus (ou les
saisir dans un fichier utilisateur), et ne plus citer de titre précis.

## 5. Valeurs en dur liées à une personne

- `patrimoine/cloud.py` : dépôt GitHub par défaut (`PATRIMOINE_GITHUB_REPO` permet de le changer).
- Consignes d'analyse (`scripts/analyse.md`, `scripts/analyse_cloud.md`) et description du serveur MCP
  (`patrimoine/api.py`) : mentionnent le prénom et les lignes de l'utilisateur ; les passer en gabarits remplis
  depuis le profil.
- Docstrings et commentaires qui disent « Jules » : remplacer par « l'utilisateur ».
- Package Android `fr.julesgourio.patrimoine` : à renommer avec un identifiant neutre (le changement de
  `applicationId` impose de réinstaller l'appli ; à faire avec le dépôt propre).
- Tests qui utilisent le prénom et le nom du premier utilisateur (`tests/test_alerts_cmb.py`) et son dépôt
  (`tests/test_cloud.py`).

## 6. Internationalisation et fiscalité

L'interface et les messages sont en français, la fiscalité est celle de la France (PEA, CTO, flat tax, PEG).
À faire : textes dans des fichiers de langue, et fiscalité en modules par pays.

## 7. Dépôt propre

Avant d'annoncer publiquement le dépôt, créer un nouveau dépôt sans historique (l'historique actuel contient une
ancienne clé de signature Android et des données propres à l'auteur). Ne pas publier l'historique actuel.

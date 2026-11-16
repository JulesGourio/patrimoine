# Ouvrir Patrimoine à d'autres utilisateurs

L'outil a été écrit pour une seule personne. Ce document liste ce qui reste à rendre configurable, du plus utile
au moins urgent. Chaque point est un bon sujet de PR ; ouvre une issue avant de te lancer.

## 1. Comptes et établissements

Fait : le moteur cherche les comptes par type (`kind` de la table `accounts` : `courant`, `livret`, `especes`, `cto`,
`pea`, `peg`, `prepaye`) avec `db.accounts_of_kind`, `db.main_account` (le compte du type qui a le plus d'opérations)
et `db.used_accounts` ; plus aucun identifiant en dur dans `portfolio`, `queries`, `analytics`, `api`,
`accueil_ecran`, `mobile`. Les libellés d'affichage viennent de `queries.account_labels` (libellés historiques pour
les ids du premier utilisateur, sinon le nom du compte) et les groupes de l'accueil du type (`queries.KIND_GROUPS`).
Un compte se crée avec `uv run patrimoine comptes --ajouter ID --nom NOM --type courant [--etablissement X]`
(`imports.creer_compte`, `mobile.create_account`), puis l'import CSV générique peut le cibler.

Reste : `db.ACCOUNTS` sème encore les sept comptes du premier utilisateur dans toute base neuve (ils restent vides
et sont ignorés par `main_account` / `used_accounts`), et les connecteurs (`sources/tr_parse.py`, `cmb_parse.py`,
`cmb_csv.py`, `amundi.py`, `sync.py` pour leurs imports) produisent ces identifiants. Semer seulement les comptes des
connecteurs que l'utilisateur active, et nommer les comptes du connecteur dans un réglage, reste à faire.

## 2. Interface de connecteurs

Aujourd'hui `patrimoine/sources/` mélange des parseurs (`cmb_parse`, `tr_parse`, `amundi`) et des clients
(`enable_banking`, `trade_republic`). À faire : un contrat commun, par exemple un connecteur qui expose
`fetch_transactions()`, `fetch_positions()` et `balance()`, déclaré dans un registre. Premiers candidats :

- un **import CSV générique** configurable (colonnes, séparateur, format de date) : couvre presque toutes les banques ;
- d'autres banques via **Enable Banking** (même API que la CMB) ;
- d'autres courtiers (Boursorama, Degiro, Interactive Brokers, Fortuneo…) par export de fichier.

## 3. Règles de catégories et libellés

Fait : `patrimoine/categories.py` ne contient plus que des commerces, enseignes et mots génériques. Les règles
propres à un utilisateur sont dans la base (`category_rules`, origine `utilisateur`) : une règle `defaut` qui
disparaît du code est basculée en `utilisateur` par `db.init` (jamais supprimée). Les virements internes sont
détectés par des libellés génériques (LIVRET, COMPTE COURANT, VIREMENT INTERNE, TRADE REPUBLIC), le nom du
propriétaire (`meta.owner`), les noms des comptes configurés et la liste `meta.libelles_internes`, remplie au
premier passage depuis l'historique (contreparties des lignes `interne`). Reste : un fichier de règles
utilisateur importable/exportable.

## 4. Lignes de portefeuille et indices de référence

`briefing.py` (`BENCH`) et `queries.py` (`TER`) contiennent les ISIN du premier utilisateur avec leur
indice de référence, levier et frais. À faire : déduire l'indice de référence et le TER des fonds détenus (ou les
saisir dans un fichier utilisateur), et ne plus citer de titre précis.

## 5. Valeurs en dur liées à une personne

- `patrimoine/cloud.py` : le dépôt GitHub par défaut reste celui de l'auteur (`PATRIMOINE_GITHUB_REPO` permet de
  le changer, documenté dans le README) pour ne pas casser son installation. À faire : défaut vide et erreur
  claire quand rien n'est configuré, une fois l'installation de l'auteur migrée.
- Fait : consignes d'analyse, description MCP, docstrings et tests ne citent plus le prénom ni le nom. Les noms de proches
  et libellés internes personnels ont quitté `categories.py` et `cmb_parse.py` (migration vers la base de
  l'utilisateur). `scripts/analyse.md` cite encore des lignes en exemple (profil via
  `CLAUDE.local.md`) ; la routine cloud n'a pas accès au profil.
- Package Android `fr.julesgourio.patrimoine` : à renommer avec un identifiant neutre (le changement de
  `applicationId` impose de réinstaller l'appli ; à faire avec le dépôt propre).

## 6. Internationalisation et fiscalité

L'interface et les messages sont en français, la fiscalité est celle de la France (PEA, CTO, flat tax, PEG).
À faire : textes dans des fichiers de langue, et fiscalité en modules par pays.

## 7. Dépôt propre

Avant d'annoncer publiquement le dépôt, créer un nouveau dépôt sans historique (l'historique actuel contient une
ancienne clé de signature Android et des données propres à l'auteur). Ne pas publier l'historique actuel.

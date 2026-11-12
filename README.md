# Patrimoine

Application Android de suivi **local** de tes dépenses, de ton portefeuille et de ton patrimoine total, avec analyses
de marché, alertes et rapports. Le moteur Python tourne sur le téléphone : une base SQLite, des secrets dans
l'Android Keystore, aucun serveur à héberger.

> *English summary: a local-first Android personal finance app, whose Python engine runs on the phone (spending, brokerage portfolio, net worth, alerts,
> AI-assisted market analysis through an MCP server). Documentation is in French for now; contributions and
> translations are welcome.*

**Statut : en cours d'ouverture.** L'outil est né comme projet personnel. Il fonctionne bien avec les sources
ci-dessous, mais plusieurs réglages propres à son premier utilisateur sont encore dans le code
(voir [`docs/GENERALISATION.md`](docs/GENERALISATION.md)). Attends-toi à devoir adapter un peu si tu n'es pas
client des mêmes établissements. C'est précisément là que ton aide est la bienvenue.

## Ce que ça fait

- **Dépenses et revenus** : import des comptes bancaires, catégories automatiques (règles par motif, règles
  perso, correction à la main), virements internes écartés, remboursements déduits.
- **Portefeuille** : positions, prix de revient (PMP, frais inclus), performance (TWR, TRI) contre des indices,
  risques (levier, devise, concentration, simulation de baisse), fiscalité et frais.
- **Patrimoine total** : tous les comptes, avant et après impôts latents, projection (Monte-Carlo).
- **Alertes et rapports** : baisses de X % et seuils configurables, notifications téléphone (ntfy) et mail,
  analyse de marché quotidienne et bilan hebdomadaire.
- **Investisseurs suivis** : déclarations 13F des fonds américains, opérations des élus du Congrès (STOCK Act),
  déclarations rapides (Form 4, 13D/13G), ETF d'ARK.
- **Serveur MCP** : tes données exposées à Claude (ou un autre client MCP) pour analyser et préparer des ordres.
  **Aucun ordre n'est jamais passé** : l'outil prépare, tu exécutes chez ton courtier.
- **Appli Android** : l'interface de l'outil ; le moteur Python tourne sur le téléphone ([`android/README.md`](android/README.md)).

## Sources prises en charge aujourd'hui

| Source | Contenu | Méthode |
|---|---|---|
| CMB (Crédit Mutuel de Bretagne) | Compte courant | API DSP2 via [Enable Banking](https://enablebanking.com) ; livrets par exports CSV ou soldes saisis |
| Trade Republic | Compte-titres, PEA, espèces, carte | [`pytr`](https://github.com/pytr-org/pytr) (API non officielle) |
| Amundi | PEG d'entreprise | Relevés PDF `AVO*.pdf` |
| Yahoo Finance | Cours, fondamentaux | `yfinance` |
| SEC EDGAR, Chambre et Sénat US | 13F, Form 4, élus | Données publiques |

D'autres banques et courtiers sont prévus : voir [`docs/GENERALISATION.md`](docs/GENERALISATION.md) et
[`CONTRIBUTING.md`](CONTRIBUTING.md) pour savoir comment en ajouter une.

## Avertissements

- **Ce n'est pas un conseil en investissement.** Les analyses, idées et alertes sont des aides à la réflexion ; tu
  restes seul responsable de tes décisions. Les logiciels et données peuvent être faux ou en retard.
- **Trade Republic n'a pas d'API publique.** `pytr` est non officiel et peut casser ou contrevenir aux conditions
  d'utilisation du courtier. Utilisation à tes risques.
- Les accès bancaires passent par un agrégateur agréé (DSP2) et durent 180 jours avant renouvellement.
- Ce dépôt ne contient aucune donnée personnelle ; la tienne reste dans `data/` (ignoré par git) et dans le
  gestionnaire d'identifiants de ton système.

## Installation

L'appli se construit et s'installe depuis [`android/README.md`](android/README.md). Ce qui suit prépare le dépôt sur
PC, pour développer et lancer les tests.

Il te faut [`uv`](https://docs.astral.sh/uv/) et Python 3.11 ou plus.

```bash
git clone https://github.com/JulesGourio/patrimoine.git
cd patrimoine
uv sync
uv run patrimoine init                 # crée data/patrimoine.db
uv run patrimoine secret set tr_pin    # les secrets vont dans le gestionnaire d'identifiants du système
uv run pytest                          # vérifie que tout est en ordre
```

Optionnel, variables d'environnement (ou fichier `.env`, ignoré par git) :

| Variable | Rôle |
|---|---|
| `PATRIMOINE_DATA_DIR` | Dossier de la base (par défaut `data/`) |
| `PATRIMOINE_EMAIL` | Adresse Gmail des mails (à défaut, le secret `smtp_email`) |
| `PATRIMOINE_CONTACT` | Contact joint aux requêtes vers la SEC et le Congrès (la SEC en demande un) |
| `PATRIMOINE_GITHUB_REPO` | Dépôt `propriétaire/nom` utilisé par les routines cloud (voir plus bas) |

## Commandes

```bash
uv run patrimoine tr sync        # Trade Republic : télécharge (confirmation dans l'appli si besoin) et importe
uv run patrimoine cmb connect    # (re)donne l'accès aux comptes CMB via Enable Banking (tous les 180 jours)
uv run patrimoine cmb-csv ~/Downloads   # historique CMB depuis les exports CSV du site
uv run patrimoine peg ~/Downloads       # relevés Amundi du PEG
uv run patrimoine solde <compte> <montant>   # solde d'un compte non exposé par la banque
uv run patrimoine historique     # cours, valorisation quotidienne, plus-values et fiscalité
uv run patrimoine sync           # tout synchroniser, alertes comprises
uv run patrimoine --help         # la liste complète
```

## Principes

- **Une seule base SQLite** (`data/patrimoine.db`, hors git). Montants en centimes entiers, quantités en réel.
- **Chaque mouvement a un flux** (`patrimoine/categories.py`) : dépense, revenu, ou `interne` (virement entre tes
  propres comptes : de l'épargne déplacée, ni dépensée ni gagnée).
- **Aucun secret dans un fichier** : `patrimoine/vault.py` (keyring sur le PC, Android Keystore sur le téléphone).
- **Aucun ordre de bourse automatique.**
- **Le moteur est portable** : `patrimoine/api.py` ne dépend ni de Streamlit, ni de Plotly, ni de keyring au
  chargement (vérifié par `tests/test_portable.py`), pour tourner aussi sur le téléphone.

## Structure

```
patrimoine/      moteur : base, sources/ (une par établissement), analyses, alertes, API d'outils
android/         appli Android (Kotlin, Jetpack Compose, Chaquopy) : écrans et synchro
scripts/         consignes des analyses de marché, déploiement
tests/           pytest
docs/            généralisation, exemples
```

## Analyses de marché et MCP

`.mcp.json` déclare le serveur MCP local `patrimoine`. Avec [Claude Code](https://claude.com/claude-code) ouvert
dans ce dossier, Claude lit tes comptes via ces outils. Les consignes d'analyse sont dans `scripts/analyse.md`
(local) et `scripts/analyse_cloud.md` (routines cloud). Pour adapter l'esprit des analyses à ton profil, copie
[`docs/profil-exemple.md`](docs/profil-exemple.md) en `CLAUDE.local.md` (ignoré par git) et remplis-le.

## Contribuer

Lis [`CONTRIBUTING.md`](CONTRIBUTING.md). Pour une faille de sécurité, [`SECURITY.md`](SECURITY.md).
Licence : [MIT](LICENSE).

## Feuille de route

Fait : socle, Trade Republic, historique, CMB, patrimoine total, serveur MCP, alertes, synchro
planifiée, suivi des investisseurs et des élus, déclarations rapides, appli Android.
En cours : appli Android autonome (moteur complet sur le téléphone).
**Prochain chantier : ouverture à d'autres utilisateurs** — comptes et règles configurables au lieu d'être en dur,
interface de connecteurs (banques, courtiers), import CSV générique, traduction. Détail dans
[`docs/GENERALISATION.md`](docs/GENERALISATION.md).

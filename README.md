# Patrimoine

Suivi local des dépenses, du portefeuille et du patrimoine de Jules, avec analyses et alertes.

## Comptes suivis

| Id | Établissement | Contenu | Source |
|---|---|---|---|
| `cmb_courant` | CMB | Compte courant (salaire) | API bancaire DSP2 (étape 4) |
| `cmb_livret_jeune`, `cmb_livret_a` | CMB | Livrets | API bancaire DSP2 |
| `tr_especes` | Trade Republic | Espèces, carte (1 % Saveback) | pytr (étape 2) |
| `tr_cto`, `tr_pea` | Trade Republic | Actions, ETF | pytr |
| `peg_airbus` | Airbus | 109,4 actions Airbus, disponibles (déblocage anticipé) | Manuel × cours AIR.PA |

## Installation

```bash
uv sync
uv run patrimoine init              # crée data/patrimoine.db
uv run patrimoine secret set tr_pin # secrets dans le gestionnaire d'identifiants Windows
uv run pytest
```

## Principes

- **Une seule base SQLite** (`data/patrimoine.db`, hors git). Montants en centimes entiers.
- **Chaque mouvement a un flux** (`patrimoine/categories.py`) : une dépense carte Trade Republic est une
  `depense` comme une dépense CMB ; un virement CMB → Trade Republic ou vers un livret est `interne`
  (de l'épargne déplacée, pas dépensée) ; le Saveback est un flux à part.
- **Catégories** seulement pour les dépenses et revenus : règles par motif (le plus long l'emporte),
  règles perso en base (`origin = utilisateur`), et correction à la main par ligne (`category_override`).
- **Aucun secret dans un fichier** : keyring (`patrimoine/vault.py`).
- **Aucun ordre de bourse automatique** : Claude prépare, Jules exécute dans l'appli Trade Republic.

## Commandes

```bash
uv run patrimoine tr sync        # télécharge Trade Republic (confirmation dans l'appli si la session a expiré) et importe
uv run patrimoine tr import      # réimporte le dernier téléchargement sans appeler Trade Republic
uv run patrimoine historique     # cours, valorisation jour par jour, plus-values et fiscalité
uv run patrimoine cmb connect    # (re)donne accès aux comptes CMB via Enable Banking (tous les 180 jours)
uv run streamlit run streamlit_app.py   # tableau de bord
```

## Limites connues

- Trade Republic ne donne plus d'historique de cours : cours Yahoo, turbos valorisés au prix des ordres.
- Le PEG est valorisé à sa quantité actuelle sur tout l'historique (dates d'acquisition inconnues).
- La CMB ne partage que le compte courant (DSP2) : le Livret CMB suit les virements vus sur le courant à partir
  du solde saisi (`patrimoine solde cmb_livret_a …`), le Livret Jeune reste au solde saisi. Resaisir après les intérêts.
- Le prix de revient Trade Republic ignore les divisions d'actions : on recalcule le nôtre (PMP, frais inclus).

## Feuille de route

1. Socle : base, comptes, catégories, secrets, tests. ✅
2. Trade Republic en lecture (pytr) : timeline, positions, import idempotent, tests sur réponses réelles. ✅
3. Historique : cours Yahoo (meilleure cotation par ISIN, contrôlée contre les prix des ordres), valorisation
   quotidienne, PMP, plus-values, report des moins-values, PFU estimé. ✅
4. CMB : API DSP2 via un agrégateur (Enable Banking), sinon import CSV/OFX.
5. Patrimoine net : tous comptes + PEG.
6. Serveur MCP local pour les analyses de Claude.
7. Dashboard Streamlit : Patrimoine, Dépenses (reclassement en place), Portefeuille, Fiscalité. ✅ (Alertes à venir)
8. Alertes (ntfy + mail), budgets, rapport hebdo, suivi fiscal (plus-values, PFU, dividendes).
9. Synchronisation planifiée (tâche Windows).

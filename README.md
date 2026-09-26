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

## Feuille de route

1. Socle : base, comptes, catégories, secrets, tests. ✅
2. Trade Republic en lecture (pytr) : timeline, positions, import idempotent, tests sur réponses réelles.
3. Historique : valorisation quotidienne reconstruite, contrôlée contre la valeur actuelle.
4. CMB : API DSP2 via un agrégateur (Enable Banking), sinon import CSV/OFX.
5. Patrimoine net : tous comptes + PEG.
6. Serveur MCP local pour les analyses de Claude.
7. Dashboard Streamlit : Patrimoine, Dépenses, Portefeuille, Alertes.
8. Alertes (ntfy + mail), budgets, rapport hebdo, suivi fiscal (plus-values, PFU, dividendes).
9. Synchronisation planifiée (tâche Windows).

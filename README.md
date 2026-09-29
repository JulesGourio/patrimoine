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
- PEG : reconstitué depuis les relevés Amundi (`uv run patrimoine peg ~/Downloads` pour les nouveaux AVO*.pdf).
  L'ESOP n'a que des valeurs : converti en équivalent actions Airbus, coût de souscription estimé.
- La CMB ne partage que le compte courant (DSP2) : le Livret CMB suit les virements vus sur le courant à partir
  du solde saisi (`patrimoine solde cmb_livret_a …`), le Livret Jeune reste au solde saisi. Resaisir après les intérêts.
- Le prix de revient Trade Republic ignore les divisions d'actions : on recalcule le nôtre (PMP, frais inclus).

## Feuille de route

1. Socle : base, comptes, catégories, secrets, tests. ✅
2. Trade Republic en lecture (pytr) : timeline, positions, import idempotent. ✅
3. Historique : cours Yahoo contrôlés contre les ordres, valorisation quotidienne, PMP, fiscalité. ✅
4. CMB via Enable Banking (compte courant) + livrets saisis. ✅
5. Patrimoine total : tous comptes + PEG. ✅
6. Serveur MCP local `patrimoine` pour les analyses de Claude. ✅
7. Dashboard : Patrimoine, Dépenses (filtres au clic), Portefeuille (TWR, TRI, indices), Fiscalité, Suivi, Réglages. ✅
8. Alertes (ntfy + mail Gmail), budgets, rapport hebdo rédigé par Claude, ordres préparés. ✅
9. Synchronisation planifiée (tâches Windows, 7 h 30 et dimanche 18 h). ✅

10. Investisseurs : fonds (13F) et élus du Congrès américain (STOCK Act), classement par performance, un seul
    récapitulatif quotidien. ✅

Idées suivantes : alertes sur les achats d'élus/fonds touchant mes lignes, projection patrimoniale, crypto,
OCR des déclarations papier, suivi des frais et de l'impôt de l'année en cours.

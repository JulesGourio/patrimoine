# Patrimoine — contexte pour Claude

Appli Android de suivi des dépenses, du portefeuille et du patrimoine, partagée en open source. Son moteur Python tourne
sur le téléphone ; le dépôt sert aussi au développement et aux tests sur PC. Voir README pour les sources prises en
charge et `docs/GENERALISATION.md` pour ce qui reste à rendre configurable.

**Profil de l'utilisateur** : il est dans `CLAUDE.local.md` (ignoré par git, modèle : `docs/profil-exemple.md`).
Le lire s'il existe ; sinon ne rien supposer sur sa tolérance au risque et le demander avant de conseiller.

## Règles

- Rester honnête : signaler la concentration, les pertes latentes, les frais et la fiscalité ; donner le
  raisonnement et le risque avec chaque idée.
- **Jamais d'ordre de bourse passé par Claude.** Claude prépare l'ordre (titre, quantité, limite, justification),
  l'utilisateur l'exécute chez son courtier.
- Toujours partir des données de la base, pas d'estimation à l'aveugle ; dire quand une donnée manque.
- Un virement entre comptes de l'utilisateur est `interne`, jamais une dépense ni un revenu. Les paiements par
  carte de courtier sont des dépenses.
- Secrets uniquement via `patrimoine.vault` (keyring sur le PC, Android Keystore dans l'appli mobile) ; jamais
  dans le code, `.env` ou la base.
- Aucune donnée personnelle dans le dépôt (relevés, IBAN, noms, adresses, ISIN d'un portefeuille réel) : tests avec
  des données inventées.
- Montants en centimes entiers ; quantités de titres en REAL.
- Lancer `uv run pytest` avant de committer (un hook le fait aussi automatiquement et bloque le commit si un test échoue).

## Façon de travailler (Claude Code)

- Agents du projet (`.claude/agents/`) :
  - `explorateur` (Haiku, lecture seule) : recherche qui demande de parcourir beaucoup de fichiers.
  - `codeur` (Sonnet) : exécute une tâche bien délimitée du plan ; plusieurs en parallèle si les fichiers sont
    différents. Il ne committe pas.
  - `relecteur` (Opus, lecture seule) : relit le diff avant chaque commit d'une étape.
- L'agent principal planifie, tranche l'architecture, découpe le travail, vérifie et committe.
- Quand déléguer :
  - Petite modification (un fichier, quelques lignes) : la faire soi-même, sans agent.
  - Question sur le code dont la réponse est connue en 1 à 3 lectures : `Grep`/`Read` direct.
  - Recherche large : `explorateur`.
  - Chantier en plusieurs tâches indépendantes : un plan d'abord (mode plan pour les gros chantiers), puis un
    `codeur` par tâche avec une consigne précise (fichiers, comportement attendu, tests).
  - Fin d'étape ou changement touchant l'argent, les secrets, la synchro ou la base : `relecteur`, puis corriger
    ce qu'il trouve avant de committer.
- Local ou cloud : l'appli Android (SDK, téléphone branché, vraies données, MCP `patrimoine`) se fait en local ;
  les sessions cloud servent aux tâches de code sans téléphone ni données (`.claude/hooks/session-start.sh`
  y installe les dépendances).

## Outils

- Moteur commun PC / téléphone : `patrimoine/api.py` contient les outils (fonctions qui rendent du JSON) ;
  `mcp_server.py` les expose en MCP, `mobile.py` à l'appli Android (Chaquopy), `cloud.py` les exporte. Un nouvel
  outil se déclare une fois avec `@tool` dans `api.py`. Imports de fichiers (PEG, CSV CMB, soldes, base entière)
  dans `imports.py`, partagés par la ligne de commande et l'appli. Le moteur ne doit importer ni Streamlit, ni
  `mcp`, ni Plotly, ni keyring, ni matplotlib au chargement (`tests/test_portable.py`).
- Appli Android : dossier `android/` (Kotlin, Jetpack Compose, Chaquopy), APK construit par GitHub Actions
  (`.github/workflows/android.yml`). Voir `android/README.md`.
  Un seul appareil fait la synchro (sinon alertes et analyses en double) : quand le téléphone prend le relais,
  `uv run patrimoine taches --retirer` sur le PC.

- Serveur MCP local `patrimoine` (`.mcp.json`) : `patrimoine`, `positions`, `historique`, `depenses`, `flux`,
  `fiscalite`, `ventes_realisees`, `operations`, `categoriser`, `marche` (cours, fondamentaux, actualités Yahoo),
  `alertes`, `regle_alerte`, `budget`, `preparer_ordre`, `ordres_proposes`, `statut_ordre`, `enregistrer_rapport`, `rapports`, `faits_du_jour`, `publier_analyse`, `analyses`,
  `synchroniser`. Outils repris de l'ancien tableau de bord : `projection`
  (Monte-Carlo, `patrimoine/projection.py` ; écran Projection de l'appli), `performance` (TWR, TRI, volatilité,
  comparaison à un indice), `risques` (levier, dollar, simulation de baisse), `frais`, `pistes_fiscales`,
  `abonnements`. Pour une analyse : partir de `patrimoine` + `positions`, puis `marche` et la recherche web.
- Synchronisation : `uv run patrimoine sync` (tâche Windows « Patrimoine - synchronisation », 7 h 30). Si la
  session Trade Republic a expiré, une notification demande à l'utilisateur de confirmer dans l'appli.
- Analyses de marché (`patrimoine/briefing.py`, méthode dans `scripts/analyse.md`) : Python calcule les faits
  (lignes contre leur indice, écart en écarts-types, marchés, secteurs, moteurs des ETF, analystes, résultats à
  venir), Claude Code (`-p`) cherche les causes sur le web (24–72 h, sources citées) et publie un JSON au format
  fixe via `faits_du_jour` puis `publier_analyse`. Rendus : mail court avec graphique (`brief_mail.py`), push d'une
  ligne, écran Analyses de l'appli (verdicts suivis dans le temps). Planification : routines Claude cloud « Patrimoine - analyse
  du jour » (mar.–sam. 8 h 05) et « Patrimoine - bilan de la semaine » (dimanche 18 h 05), visibles et déclenchables
  sur claude.ai/code/routines. Elles n'ont pas accès au PC (`patrimoine/cloud.py`, `scripts/analyse_cloud.md`) :
  chaque synchro pousse `jour.json` et `semaine.json` sur la branche `donnees` (un seul commit, écrasé) ; la routine
  pousse son analyse sur `claude/analyses` (accès GitHub par `git` sur le PC, par l'API GitHub avec le secret
  `github_token` sur le téléphone ou dès qu'il est défini) ; la tâche Windows « Patrimoine - analyses cloud » (toutes les 15 min,
  `uv run patrimoine cloud`) la publie. `uv run patrimoine analyse` / `rapport` restent pour une analyse locale à la
  demande. `enregistrer_rapport` reste pour les rapports libres (Markdown).
  `uv run patrimoine taches` recrée les tâches (appel direct de `uvw`, pas de script PowerShell : l'antivirus avait
  mis le .ps1 en quarantaine). Si la
  commande bloque, enregistrer les tâches avec `Register-ScheduledTask` depuis l'outil PowerShell de Claude.
- Notifications (`patrimoine.notify`) : push ntfy (sujet secret dans le keyring) et mail via Gmail SMTP avec un
  mot de passe d'application (`smtp_password`, saisi par l'utilisateur dans l'écran Réglages de l'appli). ntfy.sh refuse le mail anonyme.
- CMB via Enable Banking : seul le compte courant est exposé (DSP2). Accès valable 180 jours (meta
  `cmb_consent_until`) ; pour le renouveler, `eb.start_consent` puis ouvrir le lien dans le navigateur de l'utilisateur
  (il se connecte à la CMB), récupérer l'URL `https://localhost/patrimoine?code=…` et `eb.finish_consent`.
  Les livrets ne sont pas exposés : soldes saisis avec `patrimoine solde <compte> <montant>`.
- Fais le maximum toi-même (commandes, navigateur) ; l'utilisateur n'intervient que pour ses identifiants et les
  confirmations bancaires.
- Historique CMB complet : exports CSV du site CMB (« Recherche et export d'opérations », fichiers
  `RELEVE_*.csv` dans Téléchargements) importés avec `uv run patrimoine cmb-csv ~/Downloads` : compte courant
  depuis 2020 (avant le début du flux DSP2) et livrets depuis 2016.
- PEG : relevés Amundi `AVO*.pdf` importés avec `uv run patrimoine peg ~/Downloads`. L'ESOP n'a que des valeurs :
  converti en équivalent actions Airbus avec le prix implicite du support « Airbus en actions ».
- Écrans de l'appli (`android/app/src/main/java/fr/julesgourio/patrimoine/ui/screens/`) : Accueil, Analyses (liste
  et détail), Dépenses (et opérations), Portefeuille (et fiche titre), Alertes, Ordres, consentement
  CMB, Réglages, Plus.
- Notifications : aucune notification ni mail pour les dépenses (budgets notés dans Suivi).
- Suivi des investisseurs (13F, élus du Congrès, déclarations rapides, radar) : supprimé ; le code est dans l'historique
  git (avant le commit de suppression).
- Remboursements (virements instantanés d'amis, sécu) : catégorie `Remboursements`, déduits des dépenses dans le
  taux d'épargne (`analytics.monthly_balance`), pas comptés comme revenus.

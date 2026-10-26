# Patrimoine — contexte pour Claude

Appli locale de Jules : dépenses (CMB + carte Trade Republic), portefeuille (Trade Republic CTO et PEA),
PEG Airbus (109,4 actions, disponibles), patrimoine total, alertes, rapports. Voir README pour les comptes
et la feuille de route.

## Profil investisseur

- Recherche la performance, tolère le risque, horizon long. Ne pas proposer de profil prudent par défaut.
- Rester honnête : signaler la concentration (Airbus via le PEG + éventuellement en direct), les pertes
  latentes, les frais et la fiscalité ; donner le raisonnement et le risque avec chaque idée.
- Tout type d'actif possible (actions, ETF, et plus tard crypto ou autres).
- Rapports : hebdomadaire + à la demande. Alertes : baisses de X % et seuils configurables, sur téléphone
  (ntfy) et mail.

## Règles

- **Jamais d'ordre de bourse passé par Claude.** L'API Trade Republic n'est pas officielle : Claude
  prépare l'ordre (titre, quantité, limite, justification), Jules l'exécute.
- Toujours partir des données de la base, pas d'estimation à l'aveugle ; dire quand une donnée manque.
- Un virement entre comptes de Jules est `interne`, jamais une dépense ni un revenu. Les paiements carte
  Trade Republic sont des dépenses.
- Secrets uniquement via `patrimoine.vault` (keyring) ; jamais dans le code, `.env` ou la base.
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

- Serveur MCP local `patrimoine` (`.mcp.json`) : `patrimoine`, `positions`, `historique`, `depenses`, `flux`,
  `fiscalite`, `ventes_realisees`, `operations`, `categoriser`, `marche` (cours, fondamentaux, actualités Yahoo),
  `alertes`, `regle_alerte`, `budget`, `preparer_ordre`, `ordres_proposes`, `enregistrer_rapport`, `rapports`, `faits_du_jour`, `publier_analyse`, `analyses`,
  `synchroniser`, et pour les investisseurs connus (13F) `investisseurs`, `investisseur`,
  `consensus_investisseurs`, `recoupement_investisseurs`, `suivre_investisseur`, `nouveautes` (fil des déclarations
  rapides, élus, 13F et fraîcheur des sources), `positions_actuelles` (13F mis à jour), `dirigeants`, et pour les élus du Congrès
  américain (STOCK Act) `elus`, `elu`, `achats_elus`, `suivre_elu` ; `radar` (idées « quoi regarder » : élus,
  fonds, tendance, analystes, exposition via mes ETF) et `performance_fonds` (rendement de la copie des 13F). Pour une analyse : partir de `patrimoine` + `positions`, puis `marche` et la recherche web.
- Tableau de bord : `pat` (raccourci `~/.local/bin/pat.cmd`) ou `uv run patrimoine app` : le lance s'il ne tourne pas et ouvre
  le navigateur (http://localhost:8501).
- Synchronisation : `uv run patrimoine sync` (tâche Windows « Patrimoine - synchronisation », 7 h 30). Si la
  session Trade Republic a expiré, une notification demande à Jules de confirmer dans l'appli.
- Analyses de marché (`patrimoine/briefing.py`, méthode dans `scripts/analyse.md`) : Python calcule les faits
  (lignes contre leur indice, écart en écarts-types, marchés, secteurs, moteurs des ETF, analystes, résultats à
  venir), Claude Code (`-p`) cherche les causes sur le web (24–72 h, sources citées) et publie un JSON au format
  fixe via `faits_du_jour` puis `publier_analyse`. Rendus : mail court avec graphique (`brief_mail.py`), push d'une
  ligne, page Analyses (verdicts suivis dans le temps). Planification : routines Claude cloud « Patrimoine - analyse
  du jour » (mar.–sam. 8 h 05) et « Patrimoine - bilan de la semaine » (dimanche 18 h 05), visibles et déclenchables
  sur claude.ai/code/routines. Elles n'ont pas accès au PC (`patrimoine/cloud.py`, `scripts/analyse_cloud.md`) :
  chaque synchro pousse `jour.json` et `semaine.json` sur la branche `donnees` (un seul commit, écrasé) ; la routine
  pousse son analyse sur `claude/analyses` ; la tâche Windows « Patrimoine - analyses cloud » (toutes les 15 min,
  `uv run patrimoine cloud`) la publie. `uv run patrimoine analyse` / `rapport` et le bouton « Nouvelle analyse »
  restent pour une analyse locale à la demande. `enregistrer_rapport` reste pour les rapports libres (Markdown).
  `uv run patrimoine taches` recrée les tâches (appel direct de `uvw`, pas de script PowerShell : l'antivirus avait
  mis le .ps1 en quarantaine). Si la
  commande bloque, enregistrer les tâches avec `Register-ScheduledTask` depuis l'outil PowerShell de Claude.
- Notifications (`patrimoine.notify`) : push ntfy (sujet secret dans le keyring) et mail via Gmail SMTP avec un
  mot de passe d'application (`smtp_password`, saisi par Jules dans la page Réglages). ntfy.sh refuse le mail anonyme.
- CMB via Enable Banking : seul le compte courant est exposé (DSP2). Accès valable 180 jours (meta
  `cmb_consent_until`) ; pour le renouveler, `eb.start_consent` puis ouvrir le lien dans le navigateur de Jules
  (il se connecte à la CMB), récupérer l'URL `https://localhost/patrimoine?code=…` et `eb.finish_consent`.
  Les livrets ne sont pas exposés : soldes saisis avec `patrimoine solde <compte> <montant>`.
- Fais le maximum toi-même (commandes, navigateur) ; Jules n'intervient que pour ses identifiants et les
  confirmations bancaires.
- Historique CMB complet : exports CSV du site CMB (« Recherche et export d'opérations », fichiers
  `RELEVE_*.csv` dans Téléchargements) importés avec `uv run patrimoine cmb-csv ~/Downloads` : compte courant
  depuis 2020 (avant le début du flux DSP2) et livrets depuis 2016.
- PEG : relevés Amundi `AVO*.pdf` importés avec `uv run patrimoine peg ~/Downloads`. L'ESOP n'a que des valeurs :
  converti en équivalent actions Airbus avec le prix implicite du support « Airbus en actions ».
- 13F : EDGAR (SEC), vérifié une fois par jour pendant la synchronisation. Liste par défaut dans
  `patrimoine/sources/sec13f.py` (`INVESTORS`).
- Élus américains : déclarations officielles (Chambre : index `{année}FD.zip` + PDF ; Sénat : efdsearch via
  curl_cffi, qui imite Chrome pour passer le filtre anti-robot), `patrimoine/sources/congress.py`, analyses dans
  `patrimoine/politicians.py`. Sélection automatique chaque jour (`politicians.auto_follow`) : Pelosi + élus actifs
  battant le S&P 500 de 5 points ; les choix manuels de Jules (meta `congress_follow_manual`) priment.
- Déclarations rapides (`patrimoine/sources/ownership.py`, analyses dans `patrimoine/fresh.py`), chaque jour :
  Form 4 et 13D/13G des fonds suivis (XML EDGAR), ETF d'ARK (CSV quotidiens, historique stocké à partir du
  29/09/2026), opérations des dirigeants des titres surveillés (`fresh.watchlist`, page EDGAR `own-disp`, une
  requête par société ; achats P et ventes S seulement, plans salariés écartés). `fresh.current_positions` : 13F
  mis à jour par ces déclarations. Un 13F-NT renvoie vers un autre déclarant (table `investor_aliases`, ex.
  Pershing Square Inc. depuis mi-2026). Scion (Burry) ne dépose plus : désactivé.
- Dates d'élus impossibles (opération après la déclaration) : `congress.fix_date` (année corrigée ou date vide).
- Radar (`patrimoine/radar.py`) recalculé chaque jour ; fonds 13F sous-performants désactivés (`investors.active`).
- Pages : Patrimoine (total avant impôts + après impôts latents, « Cette semaine »), Dépenses (« À retenir »,
  salaires, recherche), Portefeuille (Risques : levier, dollar, concentration, simulation de baisse),
  Analyses (séance ou semaine, verdicts, sources, rapports libres), Projection (Monte-Carlo), Fiscalité et frais (année en cours, TER dans `queries.TER`), Investisseurs (Nouveautés,
  Radar, Fonds avec positions estimées, Élus ; fiche par titre), Suivi, Réglages.
- Parseur PDF de la Chambre corrigé pour les sauts de page ; après une correction du parseur,
  `congress.reparse_house(con)` réanalyse les rapports suspects (`all_reports=True` pour tout).
- Notifications : un seul récapitulatif « Suivi des investisseurs » par jour (13F + opérations des élus suivis et
  grosses opérations des autres). Aucune notification ni mail pour les dépenses (budgets notés dans Suivi).
- Remboursements (virements instantanés d'amis, sécu) : catégorie `Remboursements`, déduits des dépenses dans le
  taux d'épargne (`analytics.monthly_balance`), pas comptés comme revenus.

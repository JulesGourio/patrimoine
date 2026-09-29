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
- Lancer `uv run pytest` avant de committer.

## Outils

- Serveur MCP local `patrimoine` (`.mcp.json`) : `patrimoine`, `positions`, `historique`, `depenses`, `flux`,
  `fiscalite`, `ventes_realisees`, `operations`, `categoriser`, `marche` (cours, fondamentaux, actualités Yahoo),
  `alertes`, `regle_alerte`, `budget`, `preparer_ordre`, `ordres_proposes`, `enregistrer_rapport`, `rapports`,
  `synchroniser`, et pour les investisseurs connus (13F) `investisseurs`, `investisseur`,
  `consensus_investisseurs`, `recoupement_investisseurs`, `suivre_investisseur`, et pour les élus du Congrès
  américain (STOCK Act) `elus`, `elu`, `achats_elus`, `suivre_elu` ; `radar` (idées « quoi regarder » : élus,
  fonds, tendance, analystes, exposition via mes ETF) et `performance_fonds` (rendement de la copie des 13F). Pour une analyse : partir de `patrimoine` + `positions`, puis `marche` et la recherche web.
- Synchronisation : `uv run patrimoine sync` (tâche Windows « Patrimoine - synchronisation », 7 h 30). Si la
  session Trade Republic a expiré, une notification demande à Jules de confirmer dans l'appli.
- Rapport hebdo : tâche « Patrimoine - rapport hebdo » (dimanche 18 h) qui lance Claude Code en mode `-p` avec
  `scripts/rapport_hebdo.md` (`uv run patrimoine rapport`). `uv run patrimoine taches` recrée les tâches
  (appel direct de `uvw`, pas de script PowerShell : l'antivirus avait mis le .ps1 en quarantaine). Si la
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
- Radar (`patrimoine/radar.py`) recalculé chaque jour ; fonds 13F sous-performants désactivés (`investors.active`).
- Pages : Patrimoine (total avant impôts + après impôts latents, « Cette semaine »), Dépenses (« À retenir »,
  salaires, recherche), Portefeuille (Risques : levier, dollar, concentration, simulation de baisse),
  Projection (Monte-Carlo), Fiscalité et frais (année en cours, TER dans `queries.TER`), Investisseurs (Radar,
  Fonds, Élus ; fiche par titre), Suivi, Réglages.
- Parseur PDF de la Chambre corrigé pour les sauts de page ; après une correction du parseur,
  `congress.reparse_house(con)` réanalyse les rapports suspects (`all_reports=True` pour tout).
- Notifications : un seul récapitulatif « Suivi des investisseurs » par jour (13F + opérations des élus suivis et
  grosses opérations des autres). Aucune notification ni mail pour les dépenses (budgets notés dans Suivi).
- Remboursements (virements instantanés d'amis, sécu) : catégorie `Remboursements`, déduits des dépenses dans le
  taux d'épargne (`analytics.monthly_balance`), pas comptés comme revenus.

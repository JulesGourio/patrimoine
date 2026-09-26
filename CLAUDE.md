# Patrimoine — contexte pour Claude

Appli locale de Jules : dépenses (CMB + carte Trade Republic), portefeuille (Trade Republic CTO et PEA),
PEG Airbus (109,4 actions, disponibles), patrimoine net, alertes, rapports. Voir README pour les comptes
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
  `synchroniser`. Pour une analyse : partir de `patrimoine` + `positions`, puis `marche` et la recherche web.
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

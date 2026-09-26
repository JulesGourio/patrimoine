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

# Sécurité

Cet outil manipule des données financières et des accès bancaires. Merci de signaler toute faille de manière responsable.

## Signaler une vulnérabilité

**N'ouvre pas d'issue publique.** Utilise l'onglet *Security* → *Report a vulnerability* du dépôt GitHub
(signalement privé). Indique ce que tu as trouvé, comment le reproduire et l'impact. On répond dès que possible.

## Ce qui est considéré comme critique

- Fuite de secrets (PIN, jetons, mots de passe d'application, clés privées) dans le code, les journaux, la base, ou
  une sauvegarde.
- Exécution de code ou lecture de fichiers via un relevé importé (PDF, CSV, XML).
- Contournement de la règle « aucun ordre passé automatiquement ».

## Bonnes pratiques pour les utilisateurs

- Les secrets restent dans le gestionnaire d'identifiants du système, jamais dans un fichier ni dans `.env`.
- `data/` (base, clés Enable Banking) est ignoré par git : ne le publie jamais.
- Garde ta clé de signature Android hors du dépôt (voir `android/README.md`).
- Si tu penses avoir poussé un secret, révoque-le tout de suite : l'effacer de l'historique ne suffit pas.

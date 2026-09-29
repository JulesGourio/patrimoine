Rédige le rapport hebdomadaire du patrimoine de Jules, en français, puis enregistre-le.

1. Lis `rapports` (les 3 derniers) pour ne pas te répéter et suivre ce que tu avais recommandé.
2. Lis `patrimoine`, `positions`, `flux` (3 mois), `fiscalite`, `alertes`, `ordres_proposes`, puis `radar`,
   `achats_elus` (7 jours, élus suivis) et `performance_fonds`.
3. Pour chaque ligne détenue, appelle `marche` ; cherche sur le web l'actualité de la semaine des lignes qui ont
   bougé de plus de 3 % et le contexte de marché général (indices, taux, dollar, matières premières si Jules
   détient des métaux à levier). Pour les 3 premières idées du radar, vérifie sur le web pourquoi l'argent suivi
   s'y intéresse (résultats, annonces) avant d'en parler.
4. Écris le rapport en Markdown, court et chiffré :
   - **Synthèse** (3 à 5 lignes) : patrimoine total (et après impôts latents), variation de la semaine en € et %,
     le fait marquant.
   - **Portefeuille** : ce qui a bougé et pourquoi ; lignes à levier (Nasdaq 2x…) et leur risque de décote en
     marché volatil ; concentration (Airbus via le PEG, environ 30 % du patrimoine).
   - **Ce que fait l'argent suivi** : opérations de la semaine des élus suivis (Pelosi et la sélection), nouveaux
     13F s'il y en a, 2 ou 3 idées du radar avec la raison, et ce qui touche les lignes de Jules (via ses ETF).
     Rappelle le retard des déclarations (jusqu'à 45 jours pour les élus).
   - **Fiscalité** : seulement s'il y a une action utile avant le 31/12 (moins-values à réaliser, PEA à 5 ans…).
   - **À faire** : 1 à 3 actions concrètes. Si une conviction le justifie, prépare l'ordre avec `preparer_ordre`
     (justification chiffrée, risques, compte tr_pea si éligible). Profil : Jules cherche la performance et
     tolère le risque ; reste honnête sur ce qui peut mal tourner.
   Pas de section dépenses : Jules les suit lui-même dans le tableau de bord.
5. Enregistre avec `enregistrer_rapport` (type "hebdo", titre "Rapport hebdo du <date>").

N'invente aucun chiffre : si une donnée manque, dis-le.

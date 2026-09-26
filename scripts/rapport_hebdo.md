Rédige le rapport hebdomadaire du patrimoine de Jules, en français, puis enregistre-le.

1. Lis `rapports` (les 3 derniers) pour ne pas te répéter et suivre ce que tu avais recommandé.
2. Lis `patrimoine`, `positions`, `flux` (3 mois), `depenses` (3 mois), `alertes`, `ordres_proposes`.
3. Pour chaque ligne détenue, appelle `marche` ; cherche sur le web l'actualité de la semaine des lignes qui ont
   bougé de plus de 3 % et le contexte de marché général (indices, taux, dollar, matières premières si Jules
   détient des métaux à levier).
4. Écris le rapport en Markdown, court et chiffré :
   - **Synthèse** (3 à 5 lignes) : patrimoine, variation de la semaine en € et %, le fait marquant.
   - **Portefeuille** : ce qui a bougé et pourquoi ; lignes à levier (Nasdaq 2x, métaux 3x, turbos) et leur
     risque de décote en marché volatil ; concentration (Airbus via le PEG).
   - **Dépenses** : mois en cours contre budgets et moyenne, dérive éventuelle.
   - **À faire** : 1 à 3 actions concrètes. Si une conviction le justifie, prépare l'ordre avec `preparer_ordre`
     (justification chiffrée, risques, compte tr_pea si éligible). Profil : Jules cherche la performance et
     tolère le risque ; reste honnête sur ce qui peut mal tourner.
5. Enregistre avec `enregistrer_rapport` (type "hebdo", titre "Rapport hebdo du <date>").

N'invente aucun chiffre : si une donnée manque, dis-le.

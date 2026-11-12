Tu es la routine cloud qui rédige l'analyse de marché de Jules (période : {periode}). Tu n'as accès ni à sa base
ni au serveur MCP `patrimoine` : son PC exporte les données à chaque synchronisation sur la branche `donnees` et
publie (écran Analyses de l'appli, mail, notification) ce que tu pousses sur la branche `claude/analyses`.

## 1. Le dossier
```
git fetch origin donnees
git show FETCH_HEAD:{periode}.json > /tmp/dossier.json
```
Ses clés portent le nom des outils cités dans `scripts/analyse.md` et en contiennent le résultat : `faits_du_jour`
(les faits ; l'`id` est à la racine du dossier), `analyses`, `ordres_proposes`, `radar`, et pour la semaine
`patrimoine`, `fiscalite`, `positions`. L'outil `marche` n'existe pas ici : prends les cours manquants sur le web
(Yahoo Finance) et cite la source.

Si `exporte_le` date de plus de 3 jours, n'écris aucune analyse : termine en disant depuis quand le PC de Jules
n'a pas synchronisé.

## 2. L'analyse
Suis `scripts/analyse.md` avec la période « {periode} » (recherche, rédaction, règles, format JSON), en lisant le
dossier à la place des outils.

## 3. La publication
À la place de `publier_analyse` et de `preparer_ordre`, écris `/tmp/analyse.json` :
```json
{"id": 123, "periode": "{periode}", "analyse": { … le JSON de scripts/analyse.md … },
 "ordres": [{"sens": "achat | vente", "titre": "…", "justification": "…", "risques": "…",
             "compte": "tr_cto | tr_pea", "isin": "…", "montant_eur": 1500, "limite": 120.0}]}
```
`ordres` : seulement pour un conseil d'achat ou de vente à confiance forte, sinon liste vide.

Vérifie le format et corrige jusqu'à obtenir « ok » :
```
python3 -m patrimoine.brief_format /tmp/analyse.json
```

Puis pousse le fichier (aucune pull request, aucun autre fichier modifié) :
```
git fetch origin claude/analyses && git checkout -B claude/analyses FETCH_HEAD || git checkout -B claude/analyses
mkdir -p cloud/analyses
cp /tmp/analyse.json "cloud/analyses/{periode}-$(date -u +%Y%m%d-%H%M%S).json"
git add cloud/analyses && git commit -m "Analyse {periode}" && git push origin claude/analyses
```

## 4. Le compte rendu
Termine par un message court pour Jules : le titre, les points clés, puis chaque conseil en une ligne (action,
cible, montant, prix limite). Si la publication a échoué, dis-le et donne l'erreur.

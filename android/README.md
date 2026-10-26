# Patrimoine sur Android

L'appli fait tourner le moteur Python du dépôt (`patrimoine/`) directement sur le téléphone, grâce à Chaquopy.
Il n'y a ni serveur ni PC à garder allumé. Le PC continue de fonctionner comme avant.

## Installer

1. Ouvre GitHub → **Actions** → **Android**, prends le dernier passage vert, puis télécharge l'artefact
   `patrimoine-apk`. C'est un zip qui contient `app-debug.apk`.
2. Sur le Pixel, ouvre l'APK et autorise l'installation depuis cette source la première fois.
3. Les versions suivantes s'installent par-dessus la précédente, sans perdre les données. Toutes les versions
   sont signées avec la même clé, `app/patrimoine.keystore`.

## Premier lancement

1. **Base** : copie `data/patrimoine.db` du PC sur le téléphone (Drive, câble…), puis va dans Réglages →
   « Importer une base ». Tout l'historique arrive d'un coup : CMB depuis 2016, PEG, 13F, élus, analyses.
2. **Secrets** : dans Réglages, saisis le téléphone et le PIN Trade Republic, puis le jeton GitHub. Saisis
   aussi le mot de passe d'application Gmail si tu veux les mails.
   - Le jeton GitHub sert aux analyses des routines Claude. Prends un jeton « fine-grained » limité au dépôt
     `patrimoine`, avec l'autorisation « Contents : lecture et écriture ».
   - Les secrets sont chiffrés par l'Android Keystore.
3. **Trade Republic** : appuie sur « Se connecter », puis confirme dans l'appli Trade Republic.
4. **CMB** : appuie sur « Installer la clé » (le fichier `.pem` de `data/enablebanking/` sur le PC), puis sur
   « Renouveler l'accès ». Tu te connectes à la CMB dans l'appli, qui récupère toute seule le code de retour.

La synchro tourne ensuite chaque matin vers 7 h 30 : Trade Republic, CMB, cours, investisseurs et alertes.
L'appli récupère aussi les analyses Claude toutes les heures. Les alertes arrivent en notifications du
téléphone. L'appli se verrouille par empreinte ou par code après 5 minutes en arrière-plan.

## PC et téléphone

- Chaque appareil a sa propre base. Le téléphone peut devenir la base principale : Réglages → « Enregistrer
  une copie » produit un fichier à rapporter sur le PC si besoin.
- Les deux appareils écrivent dans le même dépôt GitHub : l'export pour les routines et la lecture des
  analyses. Une analyse publiée sur un appareil ne l'est pas sur l'autre, puisque chaque base garde sa liste.

## Construire en local

Il faut le SDK Android (Android Studio), Java 17 et Python 3.13 sur le PC. Ensuite :

```bash
cd android
./gradlew assembleDebug          # Windows : gradlew.bat assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Le moteur est recopié depuis `../patrimoine` à chaque construction ; il n'est jamais dupliqué dans git. Les
modules réservés au PC restent en dehors : `ui.py` (Streamlit), `mcp_server.py` et `tasks.py` (tâches Windows).

## Organisation

- `engine/` : démarrage de Python et appels JSON (`Engine`), coffre de secrets (`SecretStore`, Keystore),
  notifications (`Notifier`), fichiers choisis (`Files`).
- `work/` : synchro quotidienne et analyses en arrière-plan (WorkManager).
- `ui/` : écrans Compose. Chaque écran appelle un outil de `patrimoine/api.py` ou un écran de
  `patrimoine/mobile.py` par son nom (`rememberCall("positions")`).

Règle inchangée : l'appli ne passe jamais d'ordre. Les ordres préparés s'affichent, puis Jules les exécute
lui-même dans Trade Republic et note qu'ils sont passés.

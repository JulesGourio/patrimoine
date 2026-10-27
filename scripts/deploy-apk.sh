#!/usr/bin/env bash
# Usage: deploy-apk.sh [workflow=android.yml] [artifact=patrimoine-apk] [package=fr.julesgourio.patrimoine] [apk=app-debug.apk]
# Attend le build CI du dernier commit poussé, télécharge l'APK et l'installe via adb. Dépôt courant.
set -euo pipefail
WF=${1:-android.yml}; ART=${2:-patrimoine-apk}; PKG=${3:-fr.julesgourio.patrimoine}; APK=${4:-app-debug.apk}
ADB=${ADB:-$HOME/android-tools/platform-tools/adb.exe}
SHA=$(git rev-parse HEAD)
git status --porcelain | grep -q . && { echo "Modifications non committées : committe d'abord."; exit 1; }
git push -q 2>/dev/null || true
for _ in $(seq 30); do
  RUN=$(gh run list --workflow "$WF" --commit "$SHA" --limit 1 --json databaseId -q '.[0].databaseId' 2>/dev/null || true)
  [ -n "$RUN" ] && break; sleep 5
done
[ -n "${RUN:-}" ] || { echo "Aucun build trouvé pour $SHA"; exit 1; }
gh run watch "$RUN" --exit-status >/dev/null || { echo "Build en échec : gh run view $RUN --log-failed"; exit 1; }
D=$(mktemp -d); gh run download "$RUN" -n "$ART" -D "$D"
"$ADB" start-server >/dev/null 2>&1
"$ADB" devices | grep -qw device || { echo "Aucun appareil : active le débogage sans fil (adb connect IP:port) ou branche l'USB. APK : $D/$APK"; exit 2; }
"$ADB" install -r "$D/$APK"
echo "Installé : $PKG"

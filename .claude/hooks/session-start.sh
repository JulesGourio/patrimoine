#!/bin/bash
# Sessions Claude Code cloud : installe les dépendances pour que `uv run pytest` marche.
# Rien à faire en local (le .venv de Jules existe déjà).
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"
uv sync

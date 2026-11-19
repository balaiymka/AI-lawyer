#!/bin/sh
# Выкладка кода на сервер и перезапуск: scripts/deploy.sh
# Копирует проект в ~/zhkh на сервере (без .env, data/, node_modules), пересобирает и перезапускает контейнеры.
# Секреты живут только на сервере в ~/zhkh/.env и этим скриптом не трогаются.
set -eu
HOST="${DEPLOY_HOST:-zhkh_ai_lawyer@94.131.95.171}"
KEY="${DEPLOY_KEY:-$HOME/.ssh/yc_zhkh}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

rsync -az --delete -e "ssh -i $KEY" \
  --exclude .git --exclude .env --exclude '.env.*' --exclude data/ --exclude node_modules/ \
  --exclude .venv/ --exclude .next/ --exclude .next-demo/ --exclude __pycache__/ --exclude '*.pyc' \
  --exclude .pytest_cache/ --exclude tsconfig.tsbuildinfo --exclude infra/prod/snapshots/ --exclude infra/prod/.env \
  --exclude .claude/ --exclude docs/ \
  "$ROOT/" "$HOST:zhkh/"

ssh -i "$KEY" "$HOST" 'cd ~/zhkh/infra/prod && docker compose up -d --build && docker image prune -f >/dev/null && docker compose ps'

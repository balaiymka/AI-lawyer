#!/bin/sh
# Демо для ментора: продакшен-сборка сайта на :3001 + публичная ссылка через Cloudflare Tunnel.
# Нужно, чтобы уже работали Qdrant (data/qdrant_server/run.sh) и API (:8000).
#   scripts/demo.sh build   — собрать (после изменений во фронтенде)
#   scripts/demo.sh web     — запустить сайт на :3001
#   scripts/demo.sh tunnel  — открыть публичную ссылку (печатается https://….trycloudflare.com)
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/.env.demo"
export DEMO_PASSWORD="${DEMO_PASSWORD:-}" NEXT_DIST_DIR=.next-demo NEXT_PUBLIC_API_URL=/backend
cd "$ROOT/apps/web"
case "$1" in
  build) npx next build ;;
  web) exec caffeinate -i npx next start -p 3001 ;;  # caffeinate: Mac не засыпает, пока идёт демо
  tunnel) exec caffeinate -i "$ROOT/data/tools/cloudflared" tunnel --no-autoupdate --url http://localhost:3001 ;;
  *) echo "usage: $0 build|web|tunnel"; exit 1 ;;
esac

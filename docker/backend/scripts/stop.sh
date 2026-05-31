#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

GREEN='\033[0;32m'; NC='\033[0m'
log() { echo -e "${GREEN}[INFO]${NC}  $*"; }

log "停止后端服务 ..."
cd "$DOCKER_DIR"
docker compose down

log "服务已停止"
echo ""
echo "重新启动: bash $SCRIPT_DIR/deploy.sh"
echo "仅重启:   cd $DOCKER_DIR && docker compose up -d"

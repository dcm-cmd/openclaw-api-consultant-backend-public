#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/home/ubuntu/openclaw-api-consultant}"

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

if [ ! -f "$DEPLOY_DIR/docker-compose.yml" ]; then
    err "未找到 $DEPLOY_DIR/docker-compose.yml，部署目录不存在或未初始化"
fi

log "停止 OpenClaw Gateway ..."
cd "$DEPLOY_DIR"
docker compose down

log "服务已停止"
echo ""
echo "重新启动:"
echo "  cd $DEPLOY_DIR && docker compose up -d"
echo ""
echo "清理部署目录（慎用）:"
echo "  rm -rf $DEPLOY_DIR"

#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/home/ubuntu/openclaw-api-consultant}"

cd "$DEPLOY_DIR"
docker compose restart openclaw-gateway
echo ""
docker compose ps
echo ""
sleep 3
curl -fsS "http://127.0.0.1:18889/healthz"

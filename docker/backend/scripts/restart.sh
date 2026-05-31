#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$DOCKER_DIR"
docker compose restart backend
docker compose ps

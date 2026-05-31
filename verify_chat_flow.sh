#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo ".env not found in $ROOT_DIR" >&2
  exit 1
fi

POSTGRES_PASSWORD="$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)"
BACKEND_PORT="$(grep '^BACKEND_PORT=' .env | cut -d= -f2-)"
BACKEND_PORT="${BACKEND_PORT:-8000}"

echo "== health =="
curl -fsS "http://127.0.0.1:${BACKEND_PORT}/health"
printf '\n\n'

echo "== ensure test user =="
docker exec ${DB_CONTAINER:-openclaw-api-consultant-db} \
  psql -U postgres -d openclaw_consultant \
  -c "ALTER USER postgres WITH PASSWORD '${POSTGRES_PASSWORD}'; \
      INSERT INTO users (tenant_id, id, email, status, plan) \
      VALUES ('tenant-demo', 'user-demo', 'demo@example.local', 'active', 'free') \
      ON CONFLICT (tenant_id, id) DO NOTHING;"
printf '\n'

TOKEN="$(docker exec ${BACKEND_CONTAINER:-openclaw-api-consultant-backend} python -c "from app.core.auth import create_token; print(create_token('user-demo','tenant-demo'))")"
REQ_ID="req-demo-$(date +%s)"

echo "== chat stream =="
curl -sN \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\":\"conv-demo-001\",\"message\":\"你好，请回复收到\",\"client_request_id\":\"${REQ_ID}\"}" \
  "http://127.0.0.1:${BACKEND_PORT}/api/chat/stream"
printf '\n\n'

echo "== stored messages =="
curl -fsS \
  -H "Authorization: Bearer ${TOKEN}" \
  "http://127.0.0.1:${BACKEND_PORT}/api/conversations/conv-demo-001/messages"
printf '\n'
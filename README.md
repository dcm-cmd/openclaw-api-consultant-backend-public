# OpenClaw API Consultant Backend

AI-powered API consultation backend — FastAPI + OpenClaw Gateway + PostgreSQL.

## Architecture

```
Client (ProChat SSE)
  → Backend (FastAPI, JWT auth)
    → OpenClaw Gateway (Agent hooks + session management)
      → Docker Sandbox (read + exec tools)
        → /data (business knowledge, ro)
        → /scripts (query scripts, ro)
        → PostgREST → PostgreSQL
```

## Deployment Modes

| Mode | Config | Environment | Isolation |
|------|--------|-------------|-----------|
| **Sandbox** | `config/openclaw.sandbox.json` | Linux native Docker | Docker container isolation |
| **No Sandbox** | `config/openclaw.nosandbox.json` | Windows/Mac Docker Desktop | `workspaceOnly` + AGENTS.md |

```bash
bash config/deploy.sh <sandbox|nosandbox> <project-root>/state
```

See [config/README.md](openclaw-workspace-example/config/README.md) for prerequisites.

## Project Structure

```
openclaw-api-consultant-backend/
├── app/
│   ├── api/chat.py               # REST + SSE endpoints
│   ├── core/                     # Config, JWT auth, database
│   ├── models/                   # SQLAlchemy ORM
│   ├── schemas/                  # Pydantic models
│   └── services/                 # OpenClaw integration + DB service
├── openclaw-workspace-example/   # Reference workspace & configs
│   ├── config/                   # sandbox / nosandbox configs
│   ├── workspace/
│   │   ├── data/company/         # Business knowledge (7 files)
│   │   ├── scripts/              # Database query script
│   │   └── skills/               # Agent skills (3 skills)
├── docker/
│   ├── backend/               # Backend Dockerfile + compose
│   └── openclaw-gateway/      # Gateway Dockerfile + compose + state
├── tests/
└── requirements.txt
```

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health check |
| POST | `/api/chat` | JWT | Synchronous chat |
| POST | `/api/chat/stream` | JWT | Streaming chat (SSE, 6 event types) |
| POST | `/api/conversations` | JWT | Create conversation |
| GET | `/api/conversations/{id}/messages` | JWT | Message history |
| DELETE | `/api/conversations/{id}` | JWT | Soft-delete conversation |

### SSE Events

`start`, `delta`, `tool_call`, `tool_call_done`, `done`, `error`

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENCLAW_BASE_URL` | Gateway URL | `http://127.0.0.1:18889` |
| `OPENCLAW_HOOKS_TOKEN` | Hooks API token | (required) |
| `OPENCLAW_GATEWAY_TOKEN` | Gateway tools token | (required) |
| `OPENCLAW_AGENT_ID` | Agent ID | `consultant-main` |
| `JWT_SECRET` | JWT signing secret | `change-me-in-production` |
| `DATABASE_URL` | PostgreSQL connection | `postgresql+asyncpg://...` |

Full list in [docker/backend/.env.example](docker/backend/.env.example).

## Quick Start

```bash
# 1. Configure
cp docker/backend/.env.example .env
# Edit .env with your tokens and secrets

# 2. Deploy
docker compose -f docker/backend/docker-compose.yml up -d

# 3. Verify
curl http://localhost:8000/health
```

## Security

Three-layer defense:

| Layer | Mechanism |
|-------|-----------|
| L1 | `tools.fs.workspaceOnly` (no sandbox) or Docker sandbox isolation (sandbox) |
| L2 | AGENTS.md — restricts file reading, directs to business consultation |
| L3 | Backend output sanitization — detects 80+ internal disclosure patterns |

Features:
- JWT multi-tenant auth (`tenant_id` + `user_id`)
- Client request idempotency
- Output sanitization (no system files, tokens, or internal state leaked)
- Sandbox exec restrict to safe script only

## Testing

See [TEST_PLAN.md](TEST_PLAN.md) for testing procedures.
Latest validation: 12/12 tests passed on Linux sandbox deployment.

## Documentation

- [DEPLOYMENT.md](DEPLOYMENT.md) — Full deployment guide
- [TEST_PLAN_FULL.md](TEST_PLAN_FULL.md) — Complete test plan
- [OPENCLAW_CHAT_SEQUENCE_AND_HANDOFF.md](OPENCLAW_CHAT_SEQUENCE_AND_HANDOFF.md) — Sequence diagram & handoff
- [config/README.md](openclaw-workspace-example/config/README.md) — Config guide

## License

To be determined.

-- OpenClaw API Consultant 数据库初始化脚本
-- PostgreSQL 15+
-- 执行方式：psql -U postgres -d openclaw_consultant -f init.sql

BEGIN;

CREATE TABLE IF NOT EXISTS users (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  external_id TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'deleted')),
  plan TEXT NOT NULL DEFAULT 'free',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS users_tenant_email_uq
  ON users (tenant_id, email)
  WHERE email IS NOT NULL;


CREATE TABLE IF NOT EXISTS conversations (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  agent_id TEXT NOT NULL DEFAULT 'consultant-main',
  title TEXT NOT NULL DEFAULT '新的咨询',
  status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'active', 'rebuilding', 'degraded', 'deleted')),
  openclaw_session_id TEXT,
  session_generation INTEGER NOT NULL DEFAULT 0 CHECK (session_generation >= 0),
  prompt_version TEXT NOT NULL DEFAULT 'v1',
  policy_version TEXT NOT NULL DEFAULT 'policy-v1',
  summary TEXT,
  summary_version INTEGER NOT NULL DEFAULT 0 CHECK (summary_version >= 0),
  last_message_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, user_id) REFERENCES users (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS conversations_user_last_message_idx
  ON conversations (tenant_id, user_id, last_message_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS conversations_active_session_uq
  ON conversations (tenant_id, openclaw_session_id)
  WHERE openclaw_session_id IS NOT NULL;


CREATE TABLE IF NOT EXISTS chat_requests (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  client_request_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('received', 'processing', 'completed', 'failed', 'cancelled')),
  agent_id TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  openclaw_session_id TEXT,
  response_message_id TEXT,
  error_code TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
  stream BOOLEAN NOT NULL DEFAULT FALSE,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id),
  FOREIGN KEY (tenant_id, user_id) REFERENCES users (tenant_id, id),
  UNIQUE (tenant_id, user_id, conversation_id, client_request_id)
);

CREATE INDEX IF NOT EXISTS chat_requests_status_idx
  ON chat_requests (tenant_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS chat_requests_conversation_idx
  ON chat_requests (tenant_id, conversation_id, created_at DESC);


CREATE TABLE IF NOT EXISTS messages (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
  status TEXT NOT NULL CHECK (status IN ('pending', 'streaming', 'completed', 'failed', 'aborted')),
  content TEXT NOT NULL DEFAULT '',
  tool_calls JSONB NOT NULL DEFAULT '[]'::jsonb,
  token_input INTEGER NOT NULL DEFAULT 0 CHECK (token_input >= 0),
  token_output INTEGER NOT NULL DEFAULT 0 CHECK (token_output >= 0),
  error_code TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id),
  FOREIGN KEY (tenant_id, user_id) REFERENCES users (tenant_id, id),
  FOREIGN KEY (tenant_id, request_id) REFERENCES chat_requests (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS messages_conversation_created_idx
  ON messages (tenant_id, conversation_id, created_at ASC);

CREATE INDEX IF NOT EXISTS messages_request_idx
  ON messages (tenant_id, request_id);

CREATE UNIQUE INDEX IF NOT EXISTS messages_user_once_per_request_uq
  ON messages (tenant_id, request_id, role)
  WHERE role = 'user';

CREATE UNIQUE INDEX IF NOT EXISTS messages_assistant_once_per_request_uq
  ON messages (tenant_id, request_id, role)
  WHERE role = 'assistant';

CREATE INDEX IF NOT EXISTS messages_status_idx
  ON messages (tenant_id, status, created_at DESC);


CREATE TABLE IF NOT EXISTS usage_logs (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  model TEXT NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
  output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
  tool_call_count INTEGER NOT NULL DEFAULT 0 CHECK (tool_call_count >= 0),
  tool_calls JSONB NOT NULL DEFAULT '[]'::jsonb,
  latency_ms INTEGER NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
  cost NUMERIC(12, 6) NOT NULL DEFAULT 0 CHECK (cost >= 0),
  error_code TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, user_id) REFERENCES users (tenant_id, id),
  FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id),
  FOREIGN KEY (tenant_id, request_id) REFERENCES chat_requests (tenant_id, id),
  UNIQUE (tenant_id, request_id)
);

CREATE INDEX IF NOT EXISTS usage_logs_user_created_idx
  ON usage_logs (tenant_id, user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS usage_logs_conversation_created_idx
  ON usage_logs (tenant_id, conversation_id, created_at DESC);


CREATE TABLE IF NOT EXISTS audit_logs (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  operator_user_id TEXT,
  conversation_id TEXT,
  request_id TEXT,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, id),
  FOREIGN KEY (tenant_id, operator_user_id) REFERENCES users (tenant_id, id),
  FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id),
  FOREIGN KEY (tenant_id, request_id) REFERENCES chat_requests (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS audit_logs_event_type_idx
  ON audit_logs (tenant_id, event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS audit_logs_conversation_idx
  ON audit_logs (tenant_id, conversation_id, created_at DESC);


CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER conversations_set_updated_at BEFORE UPDATE ON conversations FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER chat_requests_set_updated_at BEFORE UPDATE ON chat_requests FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER messages_set_updated_at BEFORE UPDATE ON messages FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================
-- PostgREST 沙箱数据库查询支持
-- 创建 api schema + anon/web 角色 + 测试表
-- ============================================================
CREATE SCHEMA IF NOT EXISTS api;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'web') THEN
    CREATE ROLE web NOLOGIN;
    GRANT anon TO web;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA api TO anon;
GRANT USAGE ON SCHEMA api TO web;

CREATE TABLE IF NOT EXISTS api.business_metrics (
  id SERIAL PRIMARY KEY,
  metric_name VARCHAR(100) NOT NULL,
  metric_value DECIMAL(12,2) NOT NULL,
  category VARCHAR(50),
  period VARCHAR(20),
  recorded_at TIMESTAMP DEFAULT NOW()
);

GRANT SELECT ON api.business_metrics TO anon;
GRANT SELECT ON api.business_metrics TO web;

-- ============================================================
-- 预置测试用户
-- ============================================================
INSERT INTO users (tenant_id, id, email, status, plan)
VALUES ('tenant-demo', 'user-demo', 'demo@example.local', 'active', 'free')
ON CONFLICT (tenant_id, id) DO NOTHING;

COMMIT;
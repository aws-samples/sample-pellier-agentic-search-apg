-- Migration 013: Back-fill DDL for chat-session tables
--
-- The audit (audit_full_schema.sql) revealed four tables in the
-- `pellier` schema that have no migration source on disk:
--
--   * pellier.conversations    (session_id PK, agent_name, context, ...)
--   * pellier.messages         (id PK, session_id FK, role, content, ...)
--   * pellier.session_metadata (session_id PK, user_preferences, ...)
--   * pellier.tool_uses        (id PK, session_id FK, tool_name, ...)
--
-- They were created by a now-deleted bootstrap path (most likely
-- the earlier seed-database.sh shape, before the boutique catalog
-- consolidation). The tables are currently empty (0 rows) but the
-- shape is preserved here so a fresh-cluster bootstrap can recreate
-- them deterministically.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS for all four tables.
-- Existing live tables (verified via the audit probe) match this
-- DDL exactly — running this on the live cluster is a no-op.
--
-- Run with:
--   PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" \
--     -U "$DB_USER" -d "$DB_NAME" \
--     -f scripts/migrations/013_chat_session_tables.sql

\set ON_ERROR_STOP on

BEGIN;

CREATE SCHEMA IF NOT EXISTS pellier;

-- conversations: one row per chat session.
CREATE TABLE IF NOT EXISTS pellier.conversations (
    session_id   VARCHAR PRIMARY KEY,
    agent_name   VARCHAR,
    context      JSONB DEFAULT '{}'::jsonb,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata     JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_conversations_created_at
    ON pellier.conversations (created_at);

-- messages: one row per turn in a conversation.
CREATE TABLE IF NOT EXISTS pellier.messages (
    id           SERIAL PRIMARY KEY,
    session_id   VARCHAR NOT NULL
                 REFERENCES pellier.conversations(session_id)
                 ON DELETE CASCADE,
    role         VARCHAR NOT NULL,        -- 'user' | 'assistant' | 'system'
    content      TEXT NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata     JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id
    ON pellier.messages (session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at
    ON pellier.messages (created_at);

-- session_metadata: per-session context that doesn't fit on conversations.
CREATE TABLE IF NOT EXISTS pellier.session_metadata (
    session_id        VARCHAR PRIMARY KEY
                      REFERENCES pellier.conversations(session_id)
                      ON DELETE CASCADE,
    user_preferences  JSONB DEFAULT '{}'::jsonb,
    context_data      JSONB DEFAULT '{}'::jsonb,
    last_activity     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- tool_uses: per-tool-call telemetry within a session.
-- Distinct from public.tool_audit (which is the canonical write-tool
-- ledger for Cedar-gated mutations); tool_uses captures all tool calls
-- including reads. Useful for /atelier/sessions replay.
CREATE TABLE IF NOT EXISTS pellier.tool_uses (
    id           SERIAL PRIMARY KEY,
    session_id   VARCHAR NOT NULL
                 REFERENCES pellier.conversations(session_id)
                 ON DELETE CASCADE,
    tool_name    VARCHAR NOT NULL,
    tool_input   JSONB,
    tool_output  JSONB,
    "timestamp"  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tool_uses_session_id
    ON pellier.tool_uses (session_id);
CREATE INDEX IF NOT EXISTS idx_tool_uses_timestamp
    ON pellier.tool_uses ("timestamp");

DO $$
DECLARE
    n INTEGER;
BEGIN
    SELECT COUNT(*) INTO n
      FROM information_schema.tables
     WHERE table_schema='pellier'
       AND table_name IN ('conversations','messages','session_metadata','tool_uses');
    RAISE NOTICE 'Chat-session tables in pellier: % (expected 4)', n;
END $$;

COMMIT;

-- ============================================================
-- ARIADNE CAPTURE PARTY — MISSION CONTROL TAVERN SCHEMA
-- PostgreSQL schema for the premium dashboard
-- ============================================================

-- Enable UUID extension if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- CORE TABLES
-- ============================================================

-- Quests / Tasks
CREATE TABLE IF NOT EXISTS tavern_quests (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    quest_id            TEXT UNIQUE NOT NULL,           -- e.g. "quest-001"
    objective           TEXT NOT NULL,
    target_hero         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'backlog' CHECK (status IN ('backlog','todo','in_progress','review','done')),
    est_minutes         INTEGER,
    base_xp             INTEGER,
    est_pwin_delta      NUMERIC(5,2),
    actual_minutes      INTEGER,
    xp_earned           INTEGER,
    pwin_delta_realized NUMERIC(5,2),
    evidence            TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

-- Hero Activity Log
CREATE TABLE IF NOT EXISTS tavern_hero_activity (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hero            TEXT NOT NULL,
    action_type     TEXT NOT NULL,                      -- 'quest_started', 'quest_completed', 'delegation', 'skill_forge', etc.
    quest_id        TEXT,
    description     TEXT,
    xp_gained       INTEGER,
    pwin_impact     NUMERIC(5,2),
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- pWin History (for trends and charts)
CREATE TABLE IF NOT EXISTS tavern_pwin_history (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recorded_at     TIMESTAMPTZ DEFAULT NOW(),
    pwin_value      NUMERIC(5,2) NOT NULL,
    notes           TEXT
);

-- Agent Logs (detailed action log)
CREATE TABLE IF NOT EXISTS tavern_agent_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hero            TEXT NOT NULL,
    timestamp       TIMESTAMPTZ DEFAULT NOW(),
    task            TEXT,
    model_used      TEXT,
    status          TEXT CHECK (status IN ('success','failure','in_progress')),
    duration_ms     INTEGER,
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    metadata        JSONB
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_quests_status ON tavern_quests(status);
CREATE INDEX IF NOT EXISTS idx_quests_hero ON tavern_quests(target_hero);
CREATE INDEX IF NOT EXISTS idx_activity_hero ON tavern_hero_activity(hero);
CREATE INDEX IF NOT EXISTS idx_logs_hero ON tavern_agent_logs(hero);
CREATE INDEX IF NOT EXISTS idx_pwin_recorded ON tavern_pwin_history(recorded_at);

-- ============================================================
-- VIEWS (for dashboard convenience)
-- ============================================================

CREATE OR REPLACE VIEW tavern_dashboard_metrics AS
SELECT
    (SELECT COUNT(*) FROM tavern_quests WHERE status = 'in_progress') AS active_quests,
    (SELECT COUNT(*) FROM tavern_quests WHERE status = 'done') AS completed_quests,
    (SELECT COUNT(DISTINCT hero) FROM tavern_hero_activity) AS active_heroes,
    (SELECT pwin_value FROM tavern_pwin_history ORDER BY recorded_at DESC LIMIT 1) AS current_pwin,
    (SELECT SUM(xp_earned) FROM tavern_quests) AS total_xp_earned;
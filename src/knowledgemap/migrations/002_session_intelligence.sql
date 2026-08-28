CREATE TABLE IF NOT EXISTS session_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    client TEXT NOT NULL CHECK (client IN ('claude-code', 'codex')),
    session_id TEXT NOT NULL,
    previous_checkpoint_id TEXT REFERENCES session_checkpoints(checkpoint_id),
    last_message_id TEXT,
    content_hash TEXT NOT NULL,
    provider_mode TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(client, session_id, checkpoint_id, content_hash)
);

CREATE TABLE IF NOT EXISTS task_episodes (
    checkpoint_id TEXT NOT NULL REFERENCES session_checkpoints(checkpoint_id),
    episode_id TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (checkpoint_id, episode_id)
);

CREATE TABLE IF NOT EXISTS task_state_events (
    state_event_id TEXT PRIMARY KEY,
    checkpoint_id TEXT NOT NULL REFERENCES session_checkpoints(checkpoint_id),
    episode_id TEXT NOT NULL,
    field TEXT NOT NULL,
    operation TEXT NOT NULL,
    value TEXT NOT NULL,
    previous_value TEXT,
    evidence_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gap_routes (
    route_id TEXT PRIMARY KEY,
    checkpoint_id TEXT NOT NULL REFERENCES session_checkpoints(checkpoint_id),
    unresolved_item_id TEXT NOT NULL,
    route TEXT NOT NULL,
    rationale TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    UNIQUE(checkpoint_id, unresolved_item_id)
);

CREATE TABLE IF NOT EXISTS knowledge_needs (
    knowledge_need_id TEXT PRIMARY KEY,
    checkpoint_id TEXT NOT NULL REFERENCES session_checkpoints(checkpoint_id),
    unresolved_item_id TEXT NOT NULL,
    question TEXT NOT NULL,
    normalized_question TEXT NOT NULL,
    decision_it_changes TEXT NOT NULL,
    current_assumption TEXT,
    knowledge_type TEXT NOT NULL,
    preferred_source_types_json TEXT NOT NULL DEFAULT '[]',
    version_or_time_scope TEXT,
    why_context_is_insufficient TEXT NOT NULL,
    confidence REAL NOT NULL,
    rank_score REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_need_evidence (
    knowledge_need_id TEXT NOT NULL REFERENCES knowledge_needs(knowledge_need_id),
    client TEXT NOT NULL,
    session_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    PRIMARY KEY (knowledge_need_id, client, session_id, message_id)
);

CREATE TABLE IF NOT EXISTS knowledge_need_claims (
    knowledge_need_id TEXT NOT NULL REFERENCES knowledge_needs(knowledge_need_id),
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    attached_at TEXT NOT NULL,
    PRIMARY KEY (knowledge_need_id, claim_id)
);

CREATE TABLE IF NOT EXISTS knowledge_need_feedback (
    feedback_id TEXT PRIMARY KEY,
    knowledge_need_id TEXT NOT NULL REFERENCES knowledge_needs(knowledge_need_id),
    feedback TEXT NOT NULL CHECK (feedback IN ('useful', 'not_useful', 'resolved')),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_session
    ON session_checkpoints(client, session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_needs_status ON knowledge_needs(status, rank_score DESC);
CREATE INDEX IF NOT EXISTS idx_needs_question ON knowledge_needs(normalized_question);

PRAGMA user_version = 2;

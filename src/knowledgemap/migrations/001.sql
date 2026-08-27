CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    canonical_uri TEXT NOT NULL UNIQUE,
    author TEXT,
    publisher TEXT,
    authority_tier TEXT,
    update_policy TEXT,
    tracked_ref TEXT,
    last_checked_at TEXT,
    availability_status TEXT NOT NULL DEFAULT 'available',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    local_blob_path TEXT NOT NULL,
    media_type TEXT NOT NULL,
    locator_json TEXT NOT NULL,
    retrieval_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(source_id, version, content_hash)
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    statement TEXT NOT NULL,
    scope TEXT,
    limitations TEXT,
    review_status TEXT NOT NULL CHECK (review_status IN (
        'pending', 'accepted', 'rejected', 'disputed', 'stale_candidate', 'superseded'
    )),
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewed_by TEXT
);

CREATE TABLE IF NOT EXISTS claim_evidence (
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
    PRIMARY KEY (claim_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS claim_relations (
    from_claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    to_claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    relation TEXT NOT NULL CHECK (relation IN ('supersedes', 'conflicts_with')),
    PRIMARY KEY (from_claim_id, to_claim_id, relation)
);

CREATE TABLE IF NOT EXISTS knowledge_views (
    knowledge_view_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    topic TEXT,
    summary TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    aliases_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS knowledge_view_claims (
    knowledge_view_id TEXT NOT NULL REFERENCES knowledge_views(knowledge_view_id),
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    PRIMARY KEY (knowledge_view_id, claim_id)
);

CREATE TABLE IF NOT EXISTS session_grants (
    grant_id TEXT PRIMARY KEY,
    client TEXT NOT NULL CHECK (client IN ('claude-code', 'codex')),
    session_id TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    revoked_at TEXT,
    UNIQUE(client, session_id, granted_at)
);

CREATE TABLE IF NOT EXISTS session_analyses (
    analysis_id TEXT PRIMARY KEY,
    grant_id TEXT NOT NULL REFERENCES session_grants(grant_id),
    goal TEXT NOT NULL,
    existing_knowledge_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id TEXT PRIMARY KEY,
    analysis_id TEXT NOT NULL REFERENCES session_analyses(analysis_id),
    knowledge_question TEXT NOT NULL,
    why_needed TEXT NOT NULL,
    preferred_source_types_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (status IN ('pending', 'dismissed', 'resolved'))
);

CREATE TABLE IF NOT EXISTS review_items (
    review_item_id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    proposed_action TEXT,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    actor TEXT NOT NULL,
    client TEXT NOT NULL,
    event_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS update_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS update_results (
    result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES update_runs(run_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    status TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(
    claim_id UNINDEXED,
    statement,
    title,
    tags,
    aliases,
    tokenize = 'unicode61'
);

PRAGMA user_version = 1;

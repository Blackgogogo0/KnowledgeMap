# KnowledgeMap Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first MCP knowledge service that analyzes explicitly authorized Claude Code/Codex sessions, imports user-selected text sources, reviews and retrieves evidence-backed claims, and tracks source updates without silently replacing knowledge.

**Architecture:** A Python modular monolith stores metadata and FTS indexes in SQLite while keeping immutable evidence blobs on disk by SHA-256. Client-specific session readers, source adapters, an OpenAI-compatible analysis provider, review workflow, updater, and MCP transport communicate through typed service interfaces; only accepted claims enter default retrieval.

**Tech Stack:** Python 3.12+, uv, SQLite/FTS5, Pydantic 2, pydantic-settings, HTTPX, Trafilatura, MCP Python SDK 2.x, pytest, pytest-asyncio, respx.

**Spec:** `docs/superpowers/specs/2026-08-27-knowledge-map-phase-1-design.md`

## Global Constraints

- Operation is local-first; runtime data defaults to `~/.local/share/knowledgemap` and tests always use temporary directories.
- Session discovery may read metadata only; body reads require an explicit active grant.
- AI output may create pending recommendations or claims, never accepted claims.
- Evidence blobs and claim versions are immutable; updates append versions and audited transitions.
- Default retrieval returns accepted claims only and uses SQLite FTS5/BM25.
- PDF, OCR, image, chart, and visually structured document ingestion are excluded.
- Imported repository content is data only; KnowledgeMap never executes repository code or installs its dependencies.
- GitHub evidence uses commit SHA, path, and line locator; mutable branch URLs are convenience links only.
- MCP SDK must stay on the stable 2.x line: `mcp>=2,<3`.
- No task may add vector search, real-time search, social monitoring, GraphRAG, multi-tenancy, or a web UI.

---

## Planned File Structure

```text
pyproject.toml                         dependency and tool configuration
README.md                              install, run, client setup, security boundaries
src/knowledgemap/__init__.py           package version
src/knowledgemap/config.py             environment and filesystem settings
src/knowledgemap/db.py                 SQLite connection and transaction helpers
src/knowledgemap/migrations/001.sql    schema, constraints, indexes, FTS tables
src/knowledgemap/models.py             shared enums and Pydantic contracts
src/knowledgemap/errors.py             stable domain error codes
src/knowledgemap/audit.py              append-only audit recording
src/knowledgemap/evidence.py           content-addressed immutable blob store
src/knowledgemap/repository.py         source, evidence, claim, review repositories
src/knowledgemap/sessions/base.py      session reader protocol and normalized messages
src/knowledgemap/sessions/claude.py    Claude Code JSONL adapter
src/knowledgemap/sessions/codex.py     Codex rollout JSONL adapter
src/knowledgemap/sessions/service.py   discovery, grant, revoke, authorized read
src/knowledgemap/analyzer/base.py      analyzer protocol
src/knowledgemap/analyzer/openai.py    OpenAI-compatible structured analysis adapter
src/knowledgemap/analyzer/service.py   session recommendation and claim extraction flows
src/knowledgemap/sources/base.py       source adapter protocol
src/knowledgemap/sources/local.py      Markdown/plain-text file ingestion
src/knowledgemap/sources/web.py        HTML retrieval and main-text extraction
src/knowledgemap/sources/github.py     GitHub docs import, diff, and pinned locators
src/knowledgemap/ingest.py             snapshot-first ingestion orchestration
src/knowledgemap/review.py             review state machine and audited decisions
src/knowledgemap/search.py             FTS indexing, search, and evidence tracing
src/knowledgemap/update.py             due-source checks and change proposals
src/knowledgemap/mcp_server.py         MCPServer and typed tool definitions
src/knowledgemap/__main__.py           stdio server entry point
tests/fixtures/sessions/               synthetic Claude/Codex JSONL fixtures
tests/fixtures/sources/                synthetic Markdown/HTML/GitHub snapshots
tests/unit/                             focused domain tests
tests/integration/                      cross-module and MCP contract tests
tests/retrieval/fixture.json            labeled Recall@5 regression set
```

### Task 1: Project Foundation and Persistent Schema

**Files:**
- Create: `pyproject.toml`
- Create: `src/knowledgemap/__init__.py`
- Create: `src/knowledgemap/config.py`
- Create: `src/knowledgemap/db.py`
- Create: `src/knowledgemap/migrations/001.sql`
- Create: `src/knowledgemap/models.py`
- Create: `src/knowledgemap/errors.py`
- Test: `tests/unit/test_db.py`
- Test: `tests/unit/test_models.py`

**Interfaces:**
- Produces: `Settings`, `Database.connect()`, `Database.transaction()`, `Database.migrate()`, shared enums, IDs, input/output contracts, and `KnowledgeMapError(code, message, details)`.
- Consumes: none.

- [ ] **Step 1: Write failing schema and model tests**

```python
def test_migrate_creates_claim_and_fts_tables(tmp_path):
    db = Database(tmp_path / "knowledge.db")
    db.migrate()
    names = {r[0] for r in db.connect().execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
    )}
    assert {"sources", "evidence", "claims", "claim_evidence", "claims_fts"} <= names

def test_claim_status_rejects_unknown_value():
    with pytest.raises(ValueError):
        ClaimStatus("published")
```

- [ ] **Step 2: Run the tests and verify missing-package failures**

Run: `uv run pytest tests/unit/test_db.py tests/unit/test_models.py -v`
Expected: FAIL because `knowledgemap.db` and `knowledgemap.models` do not exist.

- [ ] **Step 3: Add the package configuration and dependencies**

```toml
[project]
name = "knowledgemap"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "httpx>=0.28,<1",
  "mcp>=2,<3",
  "pydantic>=2,<3",
  "pydantic-settings>=2,<3",
  "trafilatura>=2,<3",
]

[dependency-groups]
dev = ["pytest>=8,<10", "pytest-asyncio>=0.25,<2", "respx>=0.22,<1"]

[project.scripts]
knowledgemap = "knowledgemap.__main__:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 4: Implement settings, errors, database helpers, and migration**

`Settings` must resolve `data_dir`, `database_path`, `evidence_dir`, Claude/Codex session roots, analyzer URL/model/key, and update interval. `001.sql` must create sources, evidence, claims, claim-evidence links, knowledge views, session grants, analyses, recommendations, review items, audit events, update runs, and external version tables. Enable foreign keys and WAL on every connection. Create an FTS5 external-content table over accepted claim text, title, tags, and aliases.

```python
class Database:
    def __init__(self, path: Path): self.path = path
    def connect(self) -> sqlite3.Connection: raise NotImplementedError
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]: raise NotImplementedError
    def migrate(self) -> None: raise NotImplementedError
```

- [ ] **Step 5: Run foundation checks**

Run: `uv run pytest tests/unit/test_db.py tests/unit/test_models.py -v`
Expected: PASS.
Run: `uv run python -m compileall src`
Expected: exit 0.

- [ ] **Step 6: Commit the foundation**

```bash
git add pyproject.toml uv.lock src/knowledgemap tests/unit/test_db.py tests/unit/test_models.py
git commit -m "feat: establish KnowledgeMap storage foundation"
```

### Task 2: Immutable Evidence, Claims, and Audit Repositories

**Files:**
- Create: `src/knowledgemap/audit.py`
- Create: `src/knowledgemap/evidence.py`
- Create: `src/knowledgemap/repository.py`
- Test: `tests/unit/test_evidence.py`
- Test: `tests/unit/test_repository.py`

**Interfaces:**
- Consumes: `Database`, `SourceRecord`, `EvidenceRecord`, `ClaimRecord`, `ClaimStatus`, `KnowledgeMapError`.
- Produces: `EvidenceStore.put(data: bytes) -> StoredBlob`, `EvidenceStore.read(hash: str) -> bytes`, `SourceRepository`, `EvidenceRepository`, `ClaimRepository`, `AuditLog.append(event: AuditEvent) -> None`.

- [ ] **Step 1: Write failing immutability and transition tests**

```python
def test_same_content_reuses_blob_and_never_overwrites(tmp_path):
    store = EvidenceStore(tmp_path)
    first = store.put(b"alpha")
    second = store.put(b"alpha")
    assert first.content_hash == second.content_hash
    assert store.read(first.content_hash) == b"alpha"

def test_claim_update_creates_new_version(db):
    claims = ClaimRepository(db)
    v1 = claims.create_pending("The API uses OAuth.", ["ev-1"])
    v2 = claims.propose_replacement(v1.claim_id, "The API uses OAuth 2.1.", ["ev-2"])
    assert v1.claim_id != v2.claim_id
    assert claims.get(v1.claim_id).statement == "The API uses OAuth."
```

- [ ] **Step 2: Run tests and verify failures**

Run: `uv run pytest tests/unit/test_evidence.py tests/unit/test_repository.py -v`
Expected: FAIL because repository classes do not exist.

- [ ] **Step 3: Implement content-addressed evidence storage**

Store blobs at `<evidence_dir>/<hash[0:2]>/<hash>` using exclusive creation. Validate the SHA-256 again on read and raise `EVIDENCE_INTEGRITY_ERROR` on mismatch. Store only relative blob paths in SQLite.

```python
@dataclass(frozen=True)
class StoredBlob:
    content_hash: str
    relative_path: str
    size: int
```

- [ ] **Step 4: Implement repositories and append-only audit events**

Repository write methods must run in explicit transactions. Claim repository methods may insert versions and relationships but must not update statement or evidence fields. Audit each state change with actor, client, event type, target ID, before JSON, and after JSON.

- [ ] **Step 5: Run repository tests**

Run: `uv run pytest tests/unit/test_evidence.py tests/unit/test_repository.py -v`
Expected: PASS, including corrupted-blob and invalid-transition cases.

- [ ] **Step 6: Commit evidence persistence**

```bash
git add src/knowledgemap/audit.py src/knowledgemap/evidence.py src/knowledgemap/repository.py tests/unit/test_evidence.py tests/unit/test_repository.py
git commit -m "feat: preserve immutable evidence and claim versions"
```

### Task 3: Claude Code and Codex Session Authorization

**Files:**
- Create: `src/knowledgemap/sessions/__init__.py`
- Create: `src/knowledgemap/sessions/base.py`
- Create: `src/knowledgemap/sessions/claude.py`
- Create: `src/knowledgemap/sessions/codex.py`
- Create: `src/knowledgemap/sessions/service.py`
- Create: `tests/fixtures/sessions/claude.jsonl`
- Create: `tests/fixtures/sessions/codex.jsonl`
- Test: `tests/unit/test_sessions.py`

**Interfaces:**
- Consumes: `Settings`, `Database`, `AuditLog`, `KnowledgeMapError`.
- Produces: `SessionReader.list_metadata()`, `SessionReader.read_messages(session_id)`, `SessionService.list(client, project, since)`, `SessionService.grant_and_read(client, session_id, confirm_read=True)`, `SessionService.revoke(client, session_id)`.

- [ ] **Step 1: Create synthetic JSONL fixtures and failing adapter tests**

```python
def test_list_does_not_parse_message_body(claude_reader, monkeypatch):
    monkeypatch.setattr(claude_reader, "_parse_messages", Mock(side_effect=AssertionError))
    rows = claude_reader.list_metadata()
    assert rows[0].client == "claude-code"

def test_read_requires_active_grant(session_service):
    with pytest.raises(KnowledgeMapError, match="SESSION_NOT_AUTHORIZED"):
        session_service.read("codex", "session-1")
```

Fixtures must contain only invented project paths and messages. Claude fixtures use top-level user/assistant JSONL records; Codex fixtures use `session_meta` and `response_item` records. Tool outputs and reasoning records must be present in fixtures and excluded from normalized messages.

- [ ] **Step 2: Run session tests and verify failure**

Run: `uv run pytest tests/unit/test_sessions.py -v`
Expected: FAIL because session adapters do not exist.

- [ ] **Step 3: Implement the normalized session protocol**

```python
class SessionReader(Protocol):
    client: Literal["claude-code", "codex"]
    def list_metadata(self, project: str | None, since: datetime | None) -> list[SessionMetadata]:
        raise NotImplementedError
    def read_messages(self, session_id: str) -> list[SessionMessage]:
        raise NotImplementedError
```

Resolve session IDs through discovered paths, reject path traversal, cap a single session body at a configured byte limit, and normalize only user/assistant text. Metadata listing may stat files and read the minimal metadata record; it must not concatenate message bodies.

- [ ] **Step 4: Implement grant, read, and revoke semantics**

`grant_and_read` must reject `confirm_read=False`, hash the exact authorized body snapshot, insert a grant, audit it, and return normalized messages. `revoke` sets `revoked_at` and audits the transition. A new explicit grant is required after revocation.

- [ ] **Step 5: Run authorization tests**

Run: `uv run pytest tests/unit/test_sessions.py -v`
Expected: PASS for both clients, revoked access, oversized sessions, malformed lines, and traversal attempts.

- [ ] **Step 6: Commit session adapters**

```bash
git add src/knowledgemap/sessions tests/fixtures/sessions tests/unit/test_sessions.py
git commit -m "feat: read explicitly authorized agent sessions"
```

### Task 4: Structured AI Analysis and Recommendations

**Files:**
- Create: `src/knowledgemap/analyzer/__init__.py`
- Create: `src/knowledgemap/analyzer/base.py`
- Create: `src/knowledgemap/analyzer/openai.py`
- Create: `src/knowledgemap/analyzer/service.py`
- Test: `tests/unit/test_analyzer.py`
- Test: `tests/integration/test_session_analysis.py`

**Interfaces:**
- Consumes: authorized `SessionMessage` lists, `Settings`, `SessionService`, recommendation repository.
- Produces: `Analyzer.analyze_session(messages) -> SessionAnalysisDraft`, `Analyzer.extract_claims(document) -> list[ClaimDraft]`, `AnalysisService.analyze_authorized_session(client, session_id, confirm_read) -> SessionAnalysisResult`.

- [ ] **Step 1: Write failing structured-output and authorization tests**

```python
@pytest.mark.asyncio
async def test_analyzer_rejects_invalid_json(respx_mock, analyzer):
    respx_mock.post("http://llm.test/v1/chat/completions").respond(json={
        "choices": [{"message": {"content": "not-json"}}]
    })
    with pytest.raises(KnowledgeMapError, match="ANALYZER_INVALID_OUTPUT"):
        await analyzer.analyze_session([SessionMessage(role="user", text="Learn OAuth")])

@pytest.mark.asyncio
async def test_session_analysis_only_creates_recommendations(service, granted_session):
    result = await service.analyze_authorized_session(granted_session)
    assert result.recommendations
    assert service.claims.count() == 0
```

- [ ] **Step 2: Run analyzer tests and verify failure**

Run: `uv run pytest tests/unit/test_analyzer.py tests/integration/test_session_analysis.py -v`
Expected: FAIL because analyzer classes do not exist.

- [ ] **Step 3: Implement the analyzer protocol and OpenAI-compatible adapter**

Send `POST {base_url}/v1/chat/completions` with the configured model and request a JSON object. Validate returned content with Pydantic. Do not log prompts, session bodies, API keys, or raw source contents. Bound retries to two transient attempts and apply connect/read timeouts.

```python
class Analyzer(Protocol):
    async def analyze_session(self, messages: list[SessionMessage]) -> SessionAnalysisDraft:
        raise NotImplementedError
    async def extract_claims(self, document: ExtractableDocument) -> list[ClaimDraft]:
        raise NotImplementedError
```

- [ ] **Step 4: Implement the session analysis service**

The prompt must ask for the session goal, already-present knowledge, a minimal list of decision-relevant knowledge questions, why each is needed, and preferred source types. Persist analysis provenance and recommendations. Never call `ClaimRepository.create_pending` in this flow.

- [ ] **Step 5: Run analyzer tests**

Run: `uv run pytest tests/unit/test_analyzer.py tests/integration/test_session_analysis.py -v`
Expected: PASS for valid output, invalid JSON, timeout, revoked grant, and recommendation persistence.

- [ ] **Step 6: Commit structured analysis**

```bash
git add src/knowledgemap/analyzer tests/unit/test_analyzer.py tests/integration/test_session_analysis.py
git commit -m "feat: recommend knowledge from authorized sessions"
```

### Task 5: Snapshot-First Text and Web Ingestion

**Files:**
- Create: `src/knowledgemap/sources/__init__.py`
- Create: `src/knowledgemap/sources/base.py`
- Create: `src/knowledgemap/sources/local.py`
- Create: `src/knowledgemap/sources/web.py`
- Create: `src/knowledgemap/ingest.py`
- Create: `tests/fixtures/sources/article.md`
- Create: `tests/fixtures/sources/article.html`
- Test: `tests/unit/test_sources.py`
- Test: `tests/integration/test_ingest.py`

**Interfaces:**
- Consumes: `EvidenceStore`, repositories, `Analyzer.extract_claims`, HTTPX client.
- Produces: `SourceAdapter.fetch(request) -> FetchedSource`, `IngestService.import_source(request) -> ImportResult`.

- [ ] **Step 1: Write failing source-boundary tests**

```python
@pytest.mark.asyncio
async def test_markdown_is_snapshotted_before_claim_extraction(ingest, analyzer, markdown_path):
    result = await ingest.import_source(ImportRequest(uri=str(markdown_path), source_type="paper"))
    assert ingest.evidence_store.read(result.evidence.content_hash)
    assert analyzer.extract_call_happened_after_blob_write
    assert all(c.review_status == ClaimStatus.PENDING for c in result.claims)

@pytest.mark.asyncio
async def test_pdf_is_rejected(ingest, tmp_path):
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-1.7")
    with pytest.raises(KnowledgeMapError, match="UNSUPPORTED_VISUAL_DOCUMENT"):
        await ingest.import_source(ImportRequest(uri=str(path), source_type="paper"))
```

- [ ] **Step 2: Run ingestion tests and verify failure**

Run: `uv run pytest tests/unit/test_sources.py tests/integration/test_ingest.py -v`
Expected: FAIL because source adapters and ingestion service do not exist.

- [ ] **Step 3: Implement safe local and web adapters**

Local adapter accepts UTF-8 Markdown and plain text only, rejects symlinks escaping an explicitly supplied allowed root, and enforces a byte limit. Web adapter accepts `http` and `https`, rejects loopback/private/link-local targets after DNS resolution, limits redirects and response size, records final URL and ETag/Last-Modified, and extracts main text with Trafilatura while retaining raw HTML as evidence.

- [ ] **Step 4: Implement snapshot-first orchestration**

Create/update the source identity, store the raw bytes, insert the evidence row, and only then call the analyzer. Each claim draft must contain at least one locator into the extracted text and an evidence ID. On analyzer failure, retain evidence and create an error record but no claim.

- [ ] **Step 5: Run ingestion tests**

Run: `uv run pytest tests/unit/test_sources.py tests/integration/test_ingest.py -v`
Expected: PASS for Markdown, HTML, duplicate content, redirect metadata, SSRF rejection, oversized content, PDF rejection, and analyzer failure.

- [ ] **Step 6: Commit ingestion**

```bash
git add src/knowledgemap/sources src/knowledgemap/ingest.py tests/fixtures/sources tests/unit/test_sources.py tests/integration/test_ingest.py
git commit -m "feat: ingest text sources behind a review gate"
```

### Task 6: Review State Machine, FTS Retrieval, and Evidence Trace

**Files:**
- Create: `src/knowledgemap/review.py`
- Create: `src/knowledgemap/search.py`
- Create: `tests/retrieval/fixture.json`
- Test: `tests/unit/test_review.py`
- Test: `tests/unit/test_search.py`
- Test: `tests/integration/test_review_search_trace.py`

**Interfaces:**
- Consumes: claim/evidence repositories, audit log, SQLite FTS5.
- Produces: `ReviewService.list()`, `ReviewService.decide()`, `SearchService.search()`, `SearchService.trace()`.

- [ ] **Step 1: Write failing review and search tests**

```python
def test_pending_claim_is_not_searchable(search, pending_claim):
    assert search.search(SearchQuery(query="OAuth")) == []

def test_accept_indexes_claim_and_trace_reads_original(review, search, pending_claim):
    review.decide(pending_claim.claim_id, ReviewAction.ACCEPT, actor="user", client="test")
    hit = search.search(SearchQuery(query="OAuth", top_k=5))[0]
    trace = search.trace(hit.claim_id)
    assert hit.review_status == ClaimStatus.ACCEPTED
    assert trace.content_hash and trace.locator
```

- [ ] **Step 2: Run review/search tests and verify failure**

Run: `uv run pytest tests/unit/test_review.py tests/unit/test_search.py tests/integration/test_review_search_trace.py -v`
Expected: FAIL because services do not exist.

- [ ] **Step 3: Implement the four review actions**

Support exactly `accept`, `reject`, `downgrade-to-disputed`, and `research-more`. `research-more` leaves the claim pending and records a note. Accepting a replacement and its supersession relationship must occur in one transaction. Every decision writes an audit event.

- [ ] **Step 4: Implement FTS projection and search**

Index accepted claim statement, knowledge-view title, tags, and aliases. Escape user queries into safe FTS expressions; support exact phrase, required/excluded term, source type, date, scope, and status filters. Return a normalized positive score, stable tie-breaking, claim ID, evidence IDs, source metadata, and review status.

- [ ] **Step 5: Implement evidence tracing and regression fixture**

`trace` re-reads and verifies the evidence blob, resolves its locator, and returns original excerpt plus stable/local pointers. Build a fixture with at least 20 invented claims and 10 labeled queries covering exact terms, aliases, exclusions, and disputed claims. The test must assert Recall@5 >= 0.90 and evidence-hit rate == 1.0.

- [ ] **Step 6: Run retrieval tests**

Run: `uv run pytest tests/unit/test_review.py tests/unit/test_search.py tests/integration/test_review_search_trace.py -v`
Expected: PASS.
Run: `uv run pytest tests/integration/test_review_search_trace.py -k retrieval_regression -v`
Expected: Recall@5 >= 0.90 and every hit traceable.

- [ ] **Step 7: Commit review and retrieval**

```bash
git add src/knowledgemap/review.py src/knowledgemap/search.py tests/unit/test_review.py tests/unit/test_search.py tests/integration/test_review_search_trace.py tests/retrieval/fixture.json
git commit -m "feat: review and retrieve traceable claims"
```

### Task 7: GitHub Docs Import and Commit-Aware Updates

**Files:**
- Create: `src/knowledgemap/sources/github.py`
- Create: `tests/fixtures/sources/github/commit-a.json`
- Create: `tests/fixtures/sources/github/commit-b.json`
- Test: `tests/unit/test_github_source.py`
- Test: `tests/integration/test_github_update.py`

**Interfaces:**
- Consumes: source/evidence/claim repositories, `EvidenceStore`, `Analyzer`, HTTPX client.
- Produces: `GitHubSourceAdapter.resolve_ref()`, `fetch_manifest()`, `fetch_files()`, `compare()`, `stable_url()`, and update proposals.

- [ ] **Step 1: Write failing import-mode and stable-link tests**

```python
def test_docs_only_filters_manifest(github_adapter):
    paths = github_adapter.select_paths(
        ["README.md", "docs/auth.md", "src/app.py", "vendor/lib.js"],
        mode="docs-only",
    )
    assert paths == ["README.md", "docs/auth.md"]

def test_stable_url_is_commit_pinned(github_adapter):
    assert github_adapter.stable_url("o", "r", "abc123", "docs/a.md", 4, 9) == (
        "https://github.com/o/r/blob/abc123/docs/a.md#L4-L9"
    )
```

- [ ] **Step 2: Run GitHub tests and verify failure**

Run: `uv run pytest tests/unit/test_github_source.py tests/integration/test_github_update.py -v`
Expected: FAIL because the GitHub adapter does not exist.

- [ ] **Step 3: Implement GitHub API access and import modes**

Use GitHub REST endpoints through HTTPX with optional `KNOWLEDGEMAP_GITHUB_TOKEN`. Resolve the tracked ref to a commit, retrieve the recursive tree, then fetch only selected UTF-8 text blobs. Implement `docs-only`, `selected-paths`, and `whole-repo`; apply default exclusions and byte/file-count limits in every mode.

- [ ] **Step 4: Implement commit-aware diff and impact proposals**

Compare old/new manifests by path and blob SHA. Classify added, modified, deleted, and same-hash renamed files. Preserve old evidence. Modified/deleted evidence creates `stale_candidate` proposals for dependent claims; contradictory analyzer output creates `disputed` proposals. None of these transitions is applied before review.

- [ ] **Step 5: Implement discontinuity handling**

Represent force-push/no-common-ancestor, default-branch change, archived repository, not-found repository, and authorization failure as distinct update results. Keep the last accepted snapshot. Never run checked-out code.

- [ ] **Step 6: Run GitHub tests**

Run: `uv run pytest tests/unit/test_github_source.py tests/integration/test_github_update.py -v`
Expected: PASS for all three modes, unchanged commit, modification, deletion, rename, conflict, force-push, archived, and unavailable cases.

- [ ] **Step 7: Commit GitHub support**

```bash
git add src/knowledgemap/sources/github.py tests/fixtures/sources/github tests/unit/test_github_source.py tests/integration/test_github_update.py
git commit -m "feat: track GitHub knowledge by commit"
```

### Task 8: Manual and Weekly Update Orchestration

**Files:**
- Create: `src/knowledgemap/update.py`
- Test: `tests/unit/test_update.py`
- Test: `tests/integration/test_weekly_update.py`

**Interfaces:**
- Consumes: source adapters, ingestion service, repositories, review service.
- Produces: `UpdateService.check_source(source_id)`, `UpdateService.check_due(now)`, `UpdateResult`, per-source error isolation.

- [ ] **Step 1: Write failing due-date and isolation tests**

```python
@pytest.mark.asyncio
async def test_weekly_check_only_runs_due_sources(update_service, sources):
    result = await update_service.check_due(datetime(2026, 8, 27, tzinfo=UTC))
    assert result.checked_ids == [sources.due.source_id]

@pytest.mark.asyncio
async def test_one_failure_does_not_block_other_sources(update_service):
    result = await update_service.check_due(NOW)
    assert result.failed_count == 1
    assert result.succeeded_count == 1
```

- [ ] **Step 2: Run update tests and verify failure**

Run: `uv run pytest tests/unit/test_update.py tests/integration/test_weekly_update.py -v`
Expected: FAIL because `UpdateService` does not exist.

- [ ] **Step 3: Implement update scheduling as an idempotent command**

Do not add a daemon. `check_due(now)` queries sources whose policy is due and processes them independently; the OS or client can invoke this command weekly. Use ETag/Last-Modified for web sources and commit SHA for GitHub. An unchanged source only updates `last_checked_at`.

- [ ] **Step 4: Implement update results and stale behavior**

Store one update run and one per-source result with `unchanged`, `changed`, `failed`, or `source_unavailable`. A failure keeps previous accepted evidence active and sets source freshness metadata. Changed content creates snapshots, pending claims, and review proposals.

- [ ] **Step 5: Run update tests**

Run: `uv run pytest tests/unit/test_update.py tests/integration/test_weekly_update.py -v`
Expected: PASS, including repeat invocation without duplicate snapshots or review items.

- [ ] **Step 6: Commit update orchestration**

```bash
git add src/knowledgemap/update.py tests/unit/test_update.py tests/integration/test_weekly_update.py
git commit -m "feat: check subscribed sources for reviewed updates"
```

### Task 9: MCP Tool Surface

**Files:**
- Create: `src/knowledgemap/mcp_server.py`
- Create: `src/knowledgemap/__main__.py`
- Test: `tests/integration/test_mcp_contract.py`

**Interfaces:**
- Consumes: all application services from Tasks 3-8.
- Produces: MCP tools `session_list`, `session_analyze`, `session_revoke`, `source_import`, `source_update`, `review_list`, `review_decide`, `knowledge_search`, `knowledge_trace`, and `knowledge_status` over stdio.

- [ ] **Step 1: Write failing MCP discovery and contract tests**

```python
@pytest.mark.asyncio
async def test_server_exposes_exact_phase_one_tools(mcp_client):
    tools = {tool.name for tool in await mcp_client.list_tools()}
    assert tools == {
        "session_list", "session_analyze", "session_revoke", "source_import",
        "source_update", "review_list", "review_decide", "knowledge_search",
        "knowledge_trace", "knowledge_status",
    }

@pytest.mark.asyncio
async def test_search_defaults_to_accepted(mcp_client):
    result = await mcp_client.call_tool("knowledge_search", {"query": "OAuth", "top_k": 5})
    assert all(item["review_status"] == "accepted" for item in result.structured_content["hits"])
```

- [ ] **Step 2: Run MCP contract tests and verify failure**

Run: `uv run pytest tests/integration/test_mcp_contract.py -v`
Expected: FAIL because the server entry point does not exist.

- [ ] **Step 3: Build the MCPServer and lifespan dependencies**

Use `from mcp.server import MCPServer` from MCP Python SDK 2.x. Create database, repositories, adapters, HTTP client, analyzer, and services once in the server lifespan. Tool functions accept Pydantic request models and return Pydantic result models. Convert `KnowledgeMapError` to stable structured tool errors without stack traces or secrets.

- [ ] **Step 4: Implement the ten tool wrappers**

Each tool delegates to exactly one application service. `session_analyze` requires `confirm_read=True`; `source_import` never accepts a review status; `review_decide` accepts only the four review actions; `knowledge_trace` verifies the evidence blob before returning; `knowledge_status` reports source freshness, pending reviews, index counts, and recent errors.

- [ ] **Step 5: Run MCP tests and a stdio smoke test**

Run: `uv run pytest tests/integration/test_mcp_contract.py -v`
Expected: PASS.
Run: `uv run knowledgemap --help`
Expected: exit 0 and show `serve`, `migrate`, and `check-updates` commands.
Run: `uv run mcp dev src/knowledgemap/mcp_server.py`
Expected: server initializes and lists all ten tools without import or migration errors.

- [ ] **Step 6: Commit the MCP surface**

```bash
git add src/knowledgemap/mcp_server.py src/knowledgemap/__main__.py tests/integration/test_mcp_contract.py
git commit -m "feat: expose KnowledgeMap through MCP"
```

### Task 10: Client Configuration, End-to-End Acceptance, and Documentation

**Files:**
- Create: `README.md`
- Create: `docs/claude-code.md`
- Create: `docs/codex.md`
- Create: `tests/integration/test_end_to_end.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: installed `knowledgemap` command and all MCP tools.
- Produces: reproducible local setup for Claude Code and Codex, full acceptance coverage, documented evidence-citation behavior.

- [ ] **Step 1: Write the failing end-to-end acceptance test**

```python
@pytest.mark.asyncio
async def test_session_to_recommendation_and_source_to_cited_answer(app):
    sessions = app.session_list(client="codex")
    analysis = await app.session_analyze(
        client="codex", session_id=sessions[0].session_id, confirm_read=True
    )
    assert analysis.recommendations

    imported = await app.source_import(uri=app.fixture_uri("article.md"), source_type="paper")
    app.review_decide(imported.claims[0].claim_id, "accept", actor="user", client="test")
    hit = app.knowledge_search("OAuth", top_k=5).hits[0]
    trace = app.knowledge_trace(hit.claim_id)
    assert trace.content_hash and trace.locator and trace.original_excerpt
```

- [ ] **Step 2: Run the acceptance test and verify any missing integration**

Run: `uv run pytest tests/integration/test_end_to_end.py -v`
Expected before documentation/config completion: FAIL on the first missing wiring or output field; no test may be skipped.

- [ ] **Step 3: Document installation and runtime configuration**

README must show `uv sync`, `uv run knowledgemap migrate`, analyzer environment variables, optional GitHub token, data directory, evidence backup requirements, and update invocation. It must state that session bodies leave the machine only when the configured analyzer endpoint is remote, and that PDF/visual ingestion is unsupported.

- [ ] **Step 4: Document Claude Code and Codex MCP configuration**

Provide copy-paste stdio configurations that launch `uv run --directory /Users/example/KnowledgeMap knowledgemap serve`, with a sentence telling users to replace that example directory with their checkout path. Document the client instruction: search KnowledgeMap first, call `knowledge_trace` for every used claim, cite stable evidence, label disputed/stale results, and say `unverified` when trace fails. Tests generate real temporary paths.

- [ ] **Step 5: Complete the end-to-end fixture and run the full suite**

Run: `uv run pytest -v`
Expected: all unit, integration, fault, GitHub update, MCP contract, and retrieval regression tests PASS.
Run: `uv run python -m compileall src`
Expected: exit 0.
Run: `git diff --check`
Expected: no output.

- [ ] **Step 6: Perform client smoke tests**

In Claude Code and Codex separately, register the local stdio server, list tools, call `knowledge_status`, call `knowledge_search` against the acceptance fixture, and call `knowledge_trace` on the hit. Record the client version, command, and observed result in `docs/claude-code.md` and `docs/codex.md`; do not record session content or credentials.

- [ ] **Step 7: Commit the completed Phase 1 MVP**

```bash
git add README.md docs/claude-code.md docs/codex.md pyproject.toml tests/integration/test_end_to_end.py
git commit -m "docs: complete KnowledgeMap phase one handoff"
```

## Final Verification Gate

Before declaring Phase 1 complete, run these commands from a clean checkout:

```bash
uv sync --frozen
uv run pytest -v
uv run python -m compileall src
uv run knowledgemap migrate
uv run knowledgemap check-updates --dry-run
git diff --check
git status --short
```

Required evidence:

- dependency installation succeeds from `uv.lock`;
- every test passes with no skips;
- compilation exits 0;
- migration is idempotent;
- dry-run update performs no state transition;
- working tree is clean;
- manual Claude Code and Codex MCP smoke-test results are recorded without sensitive content.

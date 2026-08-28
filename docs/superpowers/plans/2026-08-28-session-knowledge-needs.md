# Session Knowledge Needs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace full-session recommendation generation with incremental task-state extraction, explicit gap routing, structured Knowledge Needs, and client-assisted Codex/Claude Code submission while retaining local Ollama analysis.

**Architecture:** Add a Session Intelligence domain alongside the existing analyzer. Both client-assisted submissions and local Ollama produce the same typed pipeline output; a transactional service validates provenance, merges checkpoint deltas, deduplicates needs, searches accepted claims, and exposes results through MCP.

**Tech Stack:** Python 3.12+, Pydantic 2, SQLite/FTS5, HTTPX/Ollama OpenAI-compatible endpoint, MCP Python SDK 2.x, pytest, pytest-asyncio, respx.

**Spec:** `docs/superpowers/specs/2026-08-28-session-knowledge-needs-spec.md`

## Global Constraints

- No external LLM API support; local analyzer URLs must resolve to loopback hosts.
- Client-assisted mode persists structured results and bounded evidence excerpts, not full transcripts.
- Session reads require an active explicit grant.
- Only `search_knowledge_map` and `check_freshness` routes may create Knowledge Needs.
- Session analysis cannot create or accept claims.
- No external search, PDF visual processing, embedding requirement, or user labeling workflow.
- Existing source ingestion, review, FTS retrieval, evidence trace, and update semantics remain compatible.

---

## Planned File Structure

```text
src/knowledgemap/migrations/002_session_intelligence.sql  checkpoint/state/route/need schema
src/knowledgemap/session_intelligence/models.py           domain contracts and enums
src/knowledgemap/session_intelligence/filter.py           normalization, redaction, excerpts
src/knowledgemap/session_intelligence/state.py            delta validation and snapshot merge
src/knowledgemap/session_intelligence/router.py           route invariants
src/knowledgemap/session_intelligence/needs.py            composition, dedupe, ranking
src/knowledgemap/session_intelligence/repository.py       transactional persistence
src/knowledgemap/session_intelligence/service.py          prepare/submit/get/resolve orchestration
src/knowledgemap/analyzer/base.py                         staged local analyzer protocol
src/knowledgemap/analyzer/openai.py                       Ollama-only staged prompts
src/knowledgemap/mcp_server.py                            five new MCP tools
tests/fixtures/session_intelligence/                      invented client submissions
tests/unit/test_session_*.py                              domain tests
tests/integration/test_session_intelligence.py            storage and resolution flow
tests/integration/test_mcp_session_intelligence.py        MCP contracts
```

### Task 1: Domain Models and Migration

**Files:**
- Create: `src/knowledgemap/migrations/002_session_intelligence.sql`
- Create: `src/knowledgemap/session_intelligence/__init__.py`
- Create: `src/knowledgemap/session_intelligence/models.py`
- Modify: `src/knowledgemap/db.py`
- Test: `tests/unit/test_session_models.py`
- Test: `tests/unit/test_db.py`

**Interfaces:**
- Produces: `GapRoute`, `KnowledgeNeedStatus`, `TaskStateDelta`, `TaskStateSnapshot`, `GapRouteDecision`, `KnowledgeNeedDraft`, `SessionInsightSubmission`.
- Produces tables: `session_checkpoints`, `task_episodes`, `task_state_events`, `gap_routes`, `knowledge_needs`, `knowledge_need_evidence`, `knowledge_need_claims`, `knowledge_need_feedback`.

- [ ] Write model tests proving enum rejection, evidence requirement, confidence bounds, and `search_knowledge_map/check_freshness` route-to-need invariants.
- [ ] Run `uv run pytest tests/unit/test_session_models.py -v`; expect import failure.
- [ ] Implement the exact Pydantic contracts from the spec, using discriminated enums and `model_validator` for cross-field invariants.
- [ ] Write migration tests starting from a migrated v1 database containing an existing recommendation; assert migration reaches `PRAGMA user_version = 2` and preserves that row.
- [ ] Implement migration 002 with foreign keys, uniqueness on `(client, session_id, checkpoint_id, content_hash)`, and indexes on need status, session, and normalized question.
- [ ] Run `uv run pytest tests/unit/test_session_models.py tests/unit/test_db.py -v`; expect PASS.
- [ ] Commit with `git commit -m "feat: define session intelligence domain"`.

### Task 2: Filtering, Redaction, and Task-State Merge

**Files:**
- Create: `src/knowledgemap/session_intelligence/filter.py`
- Create: `src/knowledgemap/session_intelligence/state.py`
- Test: `tests/unit/test_session_filter.py`
- Test: `tests/unit/test_session_state.py`

**Interfaces:**
- Produces: `normalize_events(messages, after_message_id) -> list[AnalysisEvent]`.
- Produces: `redact_excerpt(text, max_chars=500) -> str`.
- Produces: `merge_state(previous: TaskStateSnapshot | None, deltas: list[TaskStateDelta]) -> TaskStateSnapshot`.

- [ ] Write failing tests excluding reasoning/system/binary output, collapsing repeated confirmations, preserving user decisions and failures, redacting bearer tokens/private keys/password assignments, and enforcing 500-character excerpts.
- [ ] Implement deterministic filtering; do not use LLM inference in this module.
- [ ] Write failing state tests for add/replace/remove operations, missing evidence, replacement of unknown fields, and episode boundary creation.
- [ ] Implement immutable delta application; every replacement/removal must reference an existing field and evidence pointer.
- [ ] Run `uv run pytest tests/unit/test_session_filter.py tests/unit/test_session_state.py -v`; expect PASS.
- [ ] Commit with `git commit -m "feat: filter sessions into auditable task state"`.

### Task 3: Gap Routing and Knowledge Need Construction

**Files:**
- Create: `src/knowledgemap/session_intelligence/router.py`
- Create: `src/knowledgemap/session_intelligence/needs.py`
- Create: `tests/fixtures/session_intelligence/routing_cases.json`
- Test: `tests/unit/test_gap_router.py`
- Test: `tests/unit/test_knowledge_needs.py`

**Interfaces:**
- Produces: `validate_routes(unresolved, routes) -> list[GapRouteDecision]`.
- Produces: `build_needs(routes, drafts) -> list[KnowledgeNeedDraft]`.
- Produces: `dedupe_needs(existing, incoming) -> DedupeResult` and `rank_need(need) -> float`.

- [ ] Encode all seven routing examples from the acceptance document as fixture-driven tests.
- [ ] Implement validation requiring exactly one route per unresolved item and forbidding needs for non-knowledge routes.
- [ ] Write tests limiting aspect decomposition to five, requiring decision impact/context insufficiency/evidence, retaining evidence from merged duplicates, and distinguishing version scopes.
- [ ] Implement deterministic canonicalization plus analyzer-supplied `same_decision_purpose`; never merge solely on cosine/vector similarity.
- [ ] Implement the documented weighted ranking using configuration constants whose total equals 1.0.
- [ ] Run `uv run pytest tests/unit/test_gap_router.py tests/unit/test_knowledge_needs.py -v`; expect PASS.
- [ ] Commit with `git commit -m "feat: route gaps into decision-relevant knowledge needs"`.

### Task 4: Transactional Repository and Checkpoint Semantics

**Files:**
- Create: `src/knowledgemap/session_intelligence/repository.py`
- Test: `tests/unit/test_session_intelligence_repository.py`

**Interfaces:**
- Produces: `SessionIntelligenceRepository.commit_submission(submission, snapshot) -> AnalysisRecord`.
- Produces: `get_latest_state(client, session_id)`, `list_needs(filters)`, `attach_resolution(need_id, hits)`, `record_feedback(need_id, feedback)`.

- [ ] Write failing tests for atomic submission, exact retry idempotency, checkpoint conflict, audit-history retention, evidence accumulation after dedupe, and feedback not changing claim state.
- [ ] Implement all writes in one database transaction; insert active-run pointers separately from immutable analysis history.
- [ ] Reject `previous_checkpoint_id` that is not the active checkpoint with `CHECKPOINT_CONFLICT`.
- [ ] Ensure rollback after any invalid route or evidence leaves row counts unchanged.
- [ ] Run `uv run pytest tests/unit/test_session_intelligence_repository.py -v`; expect PASS.
- [ ] Commit with `git commit -m "feat: persist incremental session checkpoints atomically"`.

### Task 5: Local Ollama Staged Analyzer

**Files:**
- Modify: `src/knowledgemap/config.py`
- Modify: `src/knowledgemap/analyzer/base.py`
- Modify: `src/knowledgemap/analyzer/openai.py`
- Test: `tests/unit/test_analyzer.py`

**Interfaces:**
- Produces: `extract_state(events, previous_state)`, `route_gaps(state)`, `compose_needs(state, routes)`.
- Keeps: `extract_claims(document)` unchanged for source ingestion.

- [ ] Write failing configuration tests accepting `127.0.0.1`, `localhost`, and `::1`, while rejecting non-loopback analyzer hosts.
- [ ] Write three independent structured-response tests verifying state extraction, routing, and need composition prompts/output schemas.
- [ ] Replace the single full-session prompt with staged requests; pass only filtered incremental events plus the bounded prior state.
- [ ] Keep bounded retry and all-or-nothing schema validation; tag provider mode as `local_ollama`.
- [ ] Retain deprecated `analyze_session` as an adapter over the staged methods for one release.
- [ ] Run `uv run pytest tests/unit/test_analyzer.py -v`; expect PASS.
- [ ] Commit with `git commit -m "feat: analyze session gaps through local Ollama stages"`.

### Task 6: Unified Session Intelligence Service

**Files:**
- Create: `src/knowledgemap/session_intelligence/service.py`
- Modify: `src/knowledgemap/analyzer/service.py`
- Modify: `src/knowledgemap/mcp_server.py`
- Test: `tests/integration/test_session_intelligence.py`

**Interfaces:**
- Produces: `prepare_local(client, session_id, confirm_read)`, `submit(submission)`, `get_analysis(...)`, `list_needs(...)`, `resolve_need(need_id)`.
- Consumes: `SessionService`, staged analyzer, `SessionIntelligenceRepository`, `SearchService`.

- [ ] Write an end-to-end local test: grant → filter incremental events → staged analysis → commit checkpoint → list needs.
- [ ] Write a client-assisted test that submits without reading Session body and verifies only bounded evidence excerpts are persisted.
- [ ] Implement `prepare_local` using active grants and the last message/checkpoint pointer.
- [ ] Implement `submit` with schema validation, state merge, routing invariants, dedupe/rank, and atomic persistence.
- [ ] Implement `resolve_need`: accepted hit → resolved; stale/disputed-only hit → needs_refresh; no hit → open.
- [ ] Make legacy `AnalysisService.analyze_authorized_session` delegate to this service and include deprecation metadata.
- [ ] Run `uv run pytest tests/integration/test_session_intelligence.py tests/integration/test_session_analysis.py -v`; expect PASS.
- [ ] Commit with `git commit -m "feat: orchestrate session knowledge need analysis"`.

### Task 7: MCP Contracts and Status

**Files:**
- Modify: `src/knowledgemap/mcp_server.py`
- Modify: `tests/integration/test_mcp_contract.py`
- Create: `tests/integration/test_mcp_session_intelligence.py`

**Interfaces:**
- Adds MCP tools: `session_analysis_prepare`, `session_analysis_submit`, `session_analysis_get`, `knowledge_need_list`, `knowledge_need_resolve`.
- Extends: `knowledge_status`.

- [ ] Write contract tests for success/error envelopes, typed submission, empty needs, resolution evidence, idempotency, and `CHECKPOINT_CONFLICT`.
- [ ] Register the five tools with structured output and no hidden Session reads in `session_analysis_submit`.
- [ ] Extend `knowledge_status` with `open_knowledge_needs`, `needs_refresh`, `latest_checkpoint_at`, and `analyzer_mode`.
- [ ] Assert old MCP tools and response keys remain compatible.
- [ ] Run `uv run pytest tests/integration/test_mcp_contract.py tests/integration/test_mcp_session_intelligence.py -v`; expect PASS.
- [ ] Commit with `git commit -m "feat: expose session intelligence over MCP"`.

### Task 8: Documentation and Release Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/codex.md`
- Modify: `docs/claude-code.md`
- Modify: `docs/user-guide.zh-CN.md`
- Modify: `tests/integration/test_end_to_end.py`

**Interfaces:**
- Documents client-assisted and local Ollama workflows, privacy boundaries, deprecation, and troubleshooting.

- [ ] Add copy-pasteable Codex and Claude Code instructions that ask the client to generate the specified structured submission and call `session_analysis_submit`.
- [ ] Add the authorized Ollama workflow, open/needs-refresh/resolved meanings, and examples of evidence-backed resolution.
- [ ] Add an end-to-end test for one synthetic Codex submission and one synthetic Claude Code submission; assert neither persists full transcript text.
- [ ] Run `uv run pytest -q`; expect all tests PASS.
- [ ] Run `uv run python -m compileall src`; expect exit 0.
- [ ] Run `uv build`; expect wheel and sdist build successfully.
- [ ] Scan `rg -n "TBD|TODO|external analyzer|full.session" README.md docs src`; resolve any user-facing contradiction introduced by this change.
- [ ] Commit with `git commit -m "docs: publish session knowledge need workflows"`.

## Self-review Traceability

| Requirement group | Implemented by |
|---|---|
| Shared schema and provenance | Tasks 1, 4 |
| Filtering and state segmentation | Task 2 |
| Gap classification and need generation | Task 3 |
| Incremental/idempotent processing | Tasks 4, 6 |
| Local Ollama only | Task 5 |
| Codex/Claude Code direct submission | Tasks 6, 7 |
| Evidence-backed KnowledgeMap resolution | Task 6 |
| Privacy, compatibility, release criteria | Tasks 7, 8 |


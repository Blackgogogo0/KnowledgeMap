# KnowledgeMap Phase 1 Design

Date: 2026-08-27
Status: Draft for final user review

## 1. Purpose

KnowledgeMap is a local-first, evidence-backed knowledge layer for Claude Code and Codex. It analyzes explicitly authorized local sessions to recommend missing knowledge, imports user-selected sources through a review gate, retrieves approved claims quickly, tracks source changes, and returns traceable evidence with AI answers.

Phase 1 is intentionally narrow. It does not provide real-time web search, social-media monitoring, automated external discovery, GraphRAG, team tenancy, or enterprise connector synchronization.

## 2. Goals

- Read user-selected Claude Code and Codex sessions from their local history stores.
- Derive goals, knowledge questions, and source recommendations from authorized sessions.
- Import user-specified papers, PDFs, web documentation, technical blogs, and GitHub content.
- Preserve immutable source snapshots and precise evidence pointers.
- Let AI propose claims while reserving publication decisions for the user.
- Provide fast local retrieval through SQLite FTS5/BM25.
- Track subscribed sources manually or weekly without silently replacing knowledge.
- Expose a common local MCP interface to Claude Code and Codex.
- Return source, version, and locator information whenever an AI answer uses KnowledgeMap.

## 3. Non-goals

- Real-time search, news, social media, or sentiment monitoring.
- SurfSense, Onyx, or similar connector platforms.
- Automatic discovery or automatic publication of external knowledge.
- A mandatory embedding or vector-database dependency.
- Full knowledge graphs, GraphRAG, or code knowledge graphs.
- Team collaboration, multi-tenancy, SSO, or source-system ACL synchronization.
- A complex web or mobile interface.

## 4. Architecture

Phase 1 uses a local modular monolith:

```text
Session Reader Adapters ----> Session Analyzer ----> Recommendations
                                                       |
User Sources -------------> Evidence Store ----------> Claim Extractor
                                                       |
Source Updater -----------> Change Analyzer ---------> Review Queue
                                                       |
                                               User Review Gate
                                                       |
                                                SQLite + FTS5
                                                       |
                                                 Local MCP Server
                                                       |
                                             Claude Code / Codex
```

Modules have narrow responsibilities:

- **Session Reader Adapters:** Discover session metadata and read only explicitly authorized session bodies.
- **Session Analyzer:** Produce goals, knowledge questions, and recommendations; it cannot create published claims.
- **Source Ingestor:** Resolve user-provided files or URLs and create immutable evidence snapshots.
- **Evidence Store:** Store original content by content hash, separate from mutable summaries and indexes.
- **Claim Extractor:** Propose atomic claims with scope, limitations, and evidence pointers.
- **Review Queue:** Hold proposed claims and state transitions until the user decides.
- **Source Updater:** Check tracked sources manually or weekly and preserve source-version history.
- **FTS Retriever:** Index approved claims and aliases through SQLite FTS5/BM25.
- **MCP Server:** Provide one stable interface for Claude Code and Codex.

Embedding search is an optional later retrieval channel. The data model and MCP contracts must allow it to be added without changing evidence or review semantics.

## 5. Trust Boundaries

### 5.1 Session authorization

- Session discovery returns metadata such as client, project, title, and timestamp without reading the body.
- The user selects a session before KnowledgeMap reads its body.
- Access is read-only. KnowledgeMap never changes or deletes client history.
- Analysis records the client, session ID, grant time, content hash, and analysis ID.
- Revocation prevents future analysis reads. Existing derived recommendations remain auditable but are not formal knowledge.

### 5.2 Publication authorization

- Session analysis creates recommendations only.
- Source ingestion and updates create pending claims only.
- AI is a proposer, not a publishing authority.
- Only an explicit user review decision can make a claim `accepted`.

### 5.3 Evidence integrity

- Original evidence snapshots are immutable and content-addressed.
- Summaries and knowledge views may be regenerated.
- Existing claims are never silently edited or overwritten.
- Missing original evidence prevents a claim from being cited as verified.

## 6. Data Model

### 6.1 Source

Represents a continuing source identity.

- `source_id`
- `type`: `paper`, `pdf`, `web_documentation`, `technical_blog`, `github`
- `canonical_uri`
- `author`
- `publisher`
- `authority_tier`
- `update_policy`
- `tracked_ref`, when applicable
- `last_checked_at`
- `availability_status`

### 6.2 EvidenceSnapshot

Represents an immutable retrieved version.

- `evidence_id`
- `source_id`
- `version`
- `content_hash`
- `retrieved_at`
- `local_blob_path`
- `media_type`
- `locator`: page, section, paragraph, path, line, or equivalent
- retrieval metadata needed to reproduce or audit the snapshot

### 6.3 Claim

The atomic unit of reviewed knowledge.

- `claim_id`
- `statement`
- `evidence_ids`
- `scope`
- `limitations`
- `review_status`
- `supersedes`
- `conflicts_with`
- `created_at`
- `reviewed_at`
- `reviewed_by`

Claim states are:

- `pending`
- `accepted`
- `rejected`
- `disputed`
- `stale_candidate`
- `superseded`

`stale_candidate` means that supporting source material changed or disappeared; it does not assert that the claim is false.

### 6.4 KnowledgeView

A rebuildable retrieval view over claims.

- `knowledge_view_id`
- `title`
- `topic`
- `claim_ids`
- `summary`
- `tags`
- `aliases`
- FTS projection

### 6.5 SessionGrant and SessionAnalysis

- client: `claude-code` or `codex`
- session ID and optional project identity
- grant and revocation timestamps
- body content hash
- analysis ID
- extracted goal and knowledge questions

### 6.6 Recommendation

- `analysis_id`
- `knowledge_question`
- `why_needed`
- `preferred_source_types`
- `status`: `pending`, `dismissed`, or `resolved`

A recommendation never automatically becomes a claim.

## 7. Core Workflows

### 7.1 Session analysis

1. List session metadata through a client-specific reader.
2. Obtain explicit selection and record a grant.
3. Read a body snapshot and compute its hash.
4. Extract the user's goal, existing knowledge, and the smallest useful set of knowledge questions.
5. Produce source-type recommendations.
6. Store recommendations separately from formal knowledge.

### 7.2 Source import

1. Receive a user-specified file or URL and source type.
2. Retrieve and preserve the original content before synthesis.
3. Record source metadata, version, retrieval time, hash, and locators.
4. Extract candidate claims with evidence pointers, applicability, and limitations.
5. Place claims in the review queue.
6. On acceptance, publish claims and update FTS indexes.

Parsing failure preserves the raw input when available and creates an actionable error record. It does not publish partial claims.

### 7.3 Retrieval and answer generation

1. Claude Code or Codex calls `knowledge_search` before relying on external or model-only knowledge.
2. The retriever searches accepted claims using BM25, aliases, scope, source type, time, and status filters.
3. The client calls `knowledge_trace` for claims used in an answer.
4. The answer cites the original source, version, and precise locator.
5. Disputed or stale knowledge is clearly labeled when explicitly requested.
6. A hit whose original evidence cannot be read is returned as unverified and must not be cited as verified.

## 8. Source Updates

Sources support manual checks and a weekly schedule. An update never publishes knowledge automatically.

1. Resolve the current source version.
2. If it is unchanged, update `last_checked_at` only.
3. If it changed, preserve a new evidence snapshot.
4. Compare versions and identify affected evidence and claims.
5. Propose new claims or claim-state transitions.
6. Send all semantic changes through the review queue.
7. Keep the last accepted version usable when a check fails, while marking the source stale or unavailable.

## 9. GitHub Source Handling

A GitHub source separates a mutable tracking target from immutable evidence:

```text
Tracking target: owner/repository + branch or tag
Evidence target: commit SHA + file path + line range
```

AI citations use commit-pinned URLs. A current-branch URL may also be returned for convenience, but it is not the stable evidence pointer.

### 9.1 Import modes

- `docs-only` (default): README, `docs`, ADRs, changelog, and release notes.
- `selected-paths`: paths or globs selected by the user.
- `whole-repo`: documentation and source text, without a code knowledge graph.

Dependencies, build artifacts, binaries, generated files, secret files, and oversized data are excluded by default. Imported repository content is treated strictly as data; KnowledgeMap never installs dependencies or executes repository code.

### 9.2 Update behavior

- Compare the previous commit SHA with the tracked ref's current SHA.
- Do nothing beyond recording the check when the SHA is unchanged.
- Process only added, modified, deleted, or renamed relevant files.
- Treat same-hash renames as locator migrations.
- Preserve deleted evidence and propose `stale_candidate` for dependent claims.
- Preserve both sides of contradictory updates and propose `disputed`.
- Warn on force-pushes, default-branch changes, archival, deletion, or authorization failure.
- Never delete local evidence because a remote repository became unavailable.

## 10. MCP Contract

### `session_list`

Inputs: client, project filter, time range.  
Outputs: session metadata safe to show before body authorization.

### `session_analyze`

Inputs: client, session ID, explicit authorization.  
Outputs: goal, knowledge questions, recommendations, and analysis provenance.

### `source_import`

Inputs: file or URL, source type, and GitHub import options when applicable.  
Outputs: source record, evidence snapshot, and pending claims.

GitHub options include `github_mode`, `tracked_ref`, `include_paths`, and `exclude_paths`.

### `source_update`

Inputs: source ID or all due sources.  
Outputs: old and new versions, changed files or sections, affected claims, and proposed transitions.

### `review_list`

Inputs: item type and status filters.  
Outputs: pending claims and transitions with evidence.

### `review_decide`

Inputs: claim ID or transition ID, decision, and optional note.  
Outputs: audited state change.

Valid review actions are `accept`, `reject`, `downgrade-to-disputed`, and `research-more`. Superseding a claim is represented as acceptance of a replacement plus an explicit supersession relationship.

### `knowledge_search`

Inputs: query, scope, source types, statuses, and `top_k`.  
Outputs: ranked claims with claim and evidence IDs. Only accepted claims are included by default.

### `knowledge_trace`

Input: claim ID.  
Output: source identity, evidence version, original excerpt, locator, local pointer, and stable external pointer when available.

### `knowledge_status`

Outputs: source, index, review, update, and error status, with optional filters.

All state-changing tools record actor, client, timestamp, and before/after state.

## 11. Error Handling

- A failed source does not block unrelated imports or updates.
- A failed update retains the last accepted evidence and marks the source stale.
- Missing evidence blocks verified citation.
- Revoked session access blocks further body reads.
- Parser and extractor failures create retryable error records without publishing claims.
- External access failure is distinguished from unchanged content.
- Force-pushes and version discontinuities require explicit review.

## 12. Verification and Acceptance

Phase 1 is accepted when:

- One explicitly authorized Claude Code session and one Codex session can be listed and analyzed.
- Session analysis produces recommendations but cannot create accepted claims.
- PDF, web page, and GitHub Markdown imports work end to end.
- Every accepted claim traces to readable original evidence.
- GitHub citations contain commit SHA, file path, and locator.
- Source updates preserve old versions and create reviewable diffs.
- BM25 retrieval provides interactive local response times on the target personal corpus.
- Claude Code and Codex can call the same MCP server.
- Answers cite evidence on a hit and state that evidence is unavailable when it cannot be verified.
- Revoked session grants prevent subsequent body analysis.
- Failure of one source does not block other work.

Testing includes:

- unit tests for parsers, hashing, locators, state transitions, and authorization;
- MCP contract tests for valid inputs, outputs, and structured errors;
- integration tests for session-to-recommendation and source-to-review-to-search-to-trace flows;
- a retrieval regression fixture measuring Recall@5 and evidence-hit rate;
- fault tests for unavailable sources, changed pages, parser failures, missing evidence, and revoked grants;
- GitHub update fixtures covering modifications, deletion, rename, conflicting changes, and force-push detection.

## 13. Security and Privacy

- Local-first operation is the default.
- Session readers are read-only and require explicit grants.
- Tokens and credentials are never stored in evidence content.
- Imported GitHub code is never executed.
- Secrets and sensitive file patterns are excluded by default.
- Evidence and audit logs preserve provenance without broadening source access permissions.

## 14. Deferred Decisions

- Embedding model and vector index selection.
- Real-time search and Info Agent integration.
- Social-media and sentiment collection.
- External connector frameworks such as SurfSense or Onyx.
- Team authorization and remote synchronization.
- GraphRAG and code knowledge graphs.
- Rich review and knowledge-browsing UI.

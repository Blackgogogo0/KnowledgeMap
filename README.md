# KnowledgeMap

KnowledgeMap is a local-first, evidence-backed knowledge service for Claude Code
and Codex. Phase 1 analyzes explicitly authorized sessions, imports user-selected
text sources, puts AI-extracted claims behind human review, retrieves accepted
claims with SQLite FTS5/BM25, and returns verifiable evidence traces.

## Phase 1 boundaries

- Supported inputs: UTF-8 Markdown/plain text, technical HTML pages, and GitHub
  repository text at a pinned commit.
- PDF and visual-document ingestion are intentionally unsupported.
- Search uses SQLite FTS5/BM25. No embedding model or vector database is used.
- AI output creates recommendations or pending claims; it never creates accepted
  knowledge.
- GitHub updates preserve old evidence and create review proposals before any
  accepted claim changes.

## Install and initialize

Requires Python 3.12+, `uv`, and an OpenAI-compatible analyzer. The default is
local Ollama at `http://127.0.0.1:11434/v1` with `qwen3.5:0.8b`.

```bash
uv sync
uv run knowledgemap migrate
uv run knowledgemap --help
```

Configuration uses `KNOWLEDGEMAP_` environment variables:

```bash
export KNOWLEDGEMAP_DATA_DIR="$HOME/.local/share/knowledgemap"
export KNOWLEDGEMAP_ANALYZER_BASE_URL="http://127.0.0.1:11434/v1"
export KNOWLEDGEMAP_ANALYZER_MODEL="qwen3.5:0.8b"
export KNOWLEDGEMAP_LOCAL_SOURCE_ROOT="/path/to/approved/documents"
# Optional for private repositories or higher GitHub API limits:
export KNOWLEDGEMAP_GITHUB_TOKEN="..."
```

If `KNOWLEDGEMAP_ANALYZER_BASE_URL` points to a remote endpoint, authorized
session bodies and extracted source text leave the machine for analysis. With a
local Ollama endpoint they remain local.

## Run

```bash
# MCP over stdio
uv run knowledgemap serve

# Idempotent manual invocation; schedule this weekly with the OS/client if wanted
uv run knowledgemap check-updates
```

There is no background daemon. Back up both `knowledge.db` and the complete
`evidence/` directory together. The database contains provenance and review
state; the evidence directory contains immutable original bytes. Losing either
breaks auditability.

Client setup:

- [中文使用手册](docs/user-guide.zh-CN.md)
- [Claude Code](docs/claude-code.md)
- [Codex](docs/codex.md)

## Expected agent behavior

Instruct the client to search KnowledgeMap before answering. For every Claim it
uses, it should call `knowledge_trace`, cite the stable source locator and
content hash, label disputed/stale proposals, and say `unverified` if evidence
verification fails. Pending claims are not searchable by default.

## Development

```bash
uv run pytest -v
uv run python -m compileall src
```

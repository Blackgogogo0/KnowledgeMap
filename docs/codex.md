# Codex configuration

Codex MCP configuration lives in `~/.codex/config.toml`, or in a trusted
project's `.codex/config.toml`. This follows the
[official Codex MCP documentation](https://developers.openai.com/codex/mcp/).

Replace `/Users/example/KnowledgeMap` with the absolute path to your checkout:

```toml
[mcp_servers.KnowledgeMap]
command = "uv"
args = ["run", "--directory", "/Users/example/KnowledgeMap", "knowledgemap", "serve"]
cwd = "/Users/example/KnowledgeMap"
```

Alternatively:

```bash
codex mcp add KnowledgeMap -- \
  uv run --directory /Users/example/KnowledgeMap knowledgemap serve
```

Use `/mcp` in Codex to confirm that the KnowledgeMap tools are available.

Add this to the relevant `AGENTS.md`:

> Search KnowledgeMap before answering. For each used claim, call
> `knowledge_trace` and cite its stable evidence locator and content hash. Label
> disputed or stale material. If trace verification fails, say `unverified`.

For the current task, prefer client-assisted analysis:

> Analyze this Codex task locally. Remove confirmations, repeated attempts and
> raw tool output; preserve goals, constraints, decisions, assumptions,
> unresolved items and evidence pointers. Route every unresolved item to one of
> `ask_user`, `search_knowledge_map`, `check_freshness`, `inspect_local`,
> `execute_or_test`, or `ignore`. Create Knowledge Needs only for the two
> knowledge routes, then call `session_analysis_submit`.

This path does not give KnowledgeMap the full transcript. For local Ollama
analysis of a stored Codex session, first call `session_list`, then explicitly
authorize `session_analysis_prepare` with `confirm_read=true`.

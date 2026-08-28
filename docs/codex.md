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

Use `/mcp` in Codex to confirm that all ten KnowledgeMap tools are available.

Add this to the relevant `AGENTS.md`:

> Search KnowledgeMap before answering. For each used claim, call
> `knowledge_trace` and cite its stable evidence locator and content hash. Label
> disputed or stale material. If trace verification fails, say `unverified`.

Session bodies are accessed only after `session_analyze` receives
`confirm_read=true`. If the configured analyzer endpoint is remote, that
authorized content is sent to the remote analyzer.

# Claude Code configuration

Replace `/Users/example/KnowledgeMap` with the absolute path to your checkout.

```bash
claude mcp add --transport stdio KnowledgeMap -- \
  uv run --directory /Users/example/KnowledgeMap knowledgemap serve
```

Equivalent project `.mcp.json`:

```json
{
  "mcpServers": {
    "KnowledgeMap": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/example/KnowledgeMap",
        "knowledgemap",
        "serve"
      ]
    }
  }
}
```

Add this project instruction:

> Search KnowledgeMap before answering. For each used claim, call
> `knowledge_trace` and cite its stable evidence locator and content hash. Label
> disputed or stale material. If trace verification fails, say `unverified`.

`session_analyze` reads a session body only when `confirm_read=true`. Revoking a
grant prevents later analysis until a new explicit grant is created.

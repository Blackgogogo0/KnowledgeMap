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

For client-assisted analysis, instruct Claude Code:

> Analyze the current task locally and submit a `SessionInsightSubmission` with
> task-state deltas, exactly one route per unresolved item, Knowledge Needs only
> for `search_knowledge_map` or `check_freshness`, and bounded message evidence.
> Call `session_analysis_submit`; do not send the full transcript.

Alternatively, `session_analysis_prepare` uses local Ollama after
`confirm_read=true`. Revoking a grant prevents later server-side analysis until
a new explicit grant is created.

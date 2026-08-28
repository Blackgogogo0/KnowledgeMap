# KnowledgeMap 中文使用手册

KnowledgeMap 是一个面向 AI 编程助手的本地优先知识服务。它把“AI 给出的说法”与“能够复核的原始证据”分开管理，让 Codex、Claude Code 等客户端在回答问题前先检索经过审核的知识，并在回答中返回证据位置。

当前版本为 Phase 1，适合个人开发者、小型技术团队和需要维护可信技术资料的 AI Agent 项目。

## 1. KnowledgeMap 解决什么问题

一般的 AI 对话存在几个常见问题：

- 回答可能来自模型记忆，无法确认依据；
- 文档和 GitHub 仓库发生变化后，旧结论可能继续被使用；
- AI 自动整理的内容可能未经人工确认；
- 不同客户端之间难以共享同一套可信知识。

KnowledgeMap 使用以下流程解决这些问题：

```text
用户授权或指定资料
        ↓
保存不可变证据快照
        ↓
AI 提取知识建议或候选 Claim
        ↓
人工审核
        ↓
进入可检索知识库
        ↓
AI 搜索 Claim，并追踪到原始证据
```

这里的 **Claim** 是一条可以独立审核和引用的知识陈述。只有状态为 `accepted` 的 Claim 才会进入默认搜索结果。

## 2. 当前能力与边界

### 可以直接使用

- 发现 Claude Code 和 Codex 的本地 Session 元数据；
- 由 Codex/Claude Code 在客户端过滤 Session，并提交结构化知识需求；
- 经用户明确授权后使用本地 Ollama 增量分析指定 Session；
- 导入 UTF-8 Markdown、纯文本和公开技术网页；
- 先保存原始证据，再让 AI 提取候选 Claim；
- 人工执行接受、拒绝、降级为争议或继续研究；
- 使用 SQLite FTS5/BM25 进行本地全文检索；
- 从搜索结果追踪到内容哈希、原始摘录和稳定来源位置；
- 通过 MCP 向 Codex 和 Claude Code 暴露统一工具。

### 技术预览

代码库已经包含 GitHub commit 固定链接、仓库文本过滤、manifest diff、rename 检测、更新编排和 stale/disputed 审核提案等组件。当前 MCP 的 `source_import` 尚未提供完整的 GitHub 仓库订阅参数，内置更新 checker 也尚未在默认应用中注册。这部分目前更适合二次开发，不应视为完整的终端用户工作流。

### 暂不支持

- PDF 和需要视觉理解的文档；
- 图片、扫描件、音频和视频内容；
- 向量数据库和 embedding 检索；
- 无人审核的自动知识发布；
- 常驻后台更新 daemon。

## 3. 系统要求

- macOS、Linux，或可运行 Python 和 stdio MCP 的环境；
- Python 3.12 或更高版本；
- [uv](https://docs.astral.sh/uv/)；
- 本地 Ollama；Codex/Claude Code 客户端辅助模式不要求额外模型服务。

默认配置使用本地 Ollama：

```text
地址：http://127.0.0.1:11434/v1
模型：qwen3.5:0.8b
```

安装并确认模型：

```bash
ollama pull qwen3.5:0.8b
ollama list
```

Phase 1 不需要 embedding 模型。

## 4. 安装

克隆项目并安装依赖：

```bash
git clone https://github.com/OWNER/KnowledgeMap.git
cd KnowledgeMap
uv sync
uv run knowledgemap migrate
```

如果仓库是私有的，请先配置 GitHub SSH 或 GitHub CLI 登录权限。

确认命令可用：

```bash
uv run knowledgemap --help
```

正常情况下会看到：

```text
serve
migrate
check-updates
```

## 5. 配置

KnowledgeMap 使用以 `KNOWLEDGEMAP_` 开头的环境变量：

```bash
export KNOWLEDGEMAP_DATA_DIR="$HOME/.local/share/knowledgemap"
export KNOWLEDGEMAP_ANALYZER_BASE_URL="http://127.0.0.1:11434/v1"
export KNOWLEDGEMAP_ANALYZER_MODEL="qwen3.5:0.8b"
export KNOWLEDGEMAP_LOCAL_SOURCE_ROOT="/absolute/path/to/approved-documents"
```

可选配置：

```bash
export KNOWLEDGEMAP_GITHUB_TOKEN="..."
export KNOWLEDGEMAP_UPDATE_INTERVAL_DAYS="7"
```

`KNOWLEDGEMAP_LOCAL_SOURCE_ROOT` 是本地文件导入的安全边界。位于该目录之外的文件，以及通过符号链接逃逸到目录外的文件，会被拒绝。

分析器地址只允许 `localhost`、`127.0.0.1` 或 `::1`，不支持外部模型 API。

## 6. 接入 Codex

把示例目录替换为本机项目的绝对路径：

```bash
codex mcp add KnowledgeMap -- \
  uv run --directory /absolute/path/to/KnowledgeMap knowledgemap serve
```

也可以编辑 `~/.codex/config.toml`：

```toml
[mcp_servers.KnowledgeMap]
command = "uv"
args = ["run", "--directory", "/absolute/path/to/KnowledgeMap", "knowledgemap", "serve"]
cwd = "/absolute/path/to/KnowledgeMap"
```

重启 Codex 或新建任务，然后使用 `/mcp` 确认 `KnowledgeMap` 已启用。

建议在项目的 `AGENTS.md` 中加入：

> 回答问题前优先搜索 KnowledgeMap。使用任何 Claim 时都调用 `knowledge_trace`，引用稳定证据位置和内容哈希。争议或过期候选必须明确标注；证据验证失败时标记为 `unverified`。

更完整的配置见 [Codex 配置说明](codex.md)。

## 7. 接入 Claude Code

```bash
claude mcp add --transport stdio KnowledgeMap -- \
  uv run --directory /absolute/path/to/KnowledgeMap knowledgemap serve
```

也可以在项目 `.mcp.json` 中配置：

```json
{
  "mcpServers": {
    "KnowledgeMap": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/KnowledgeMap",
        "knowledgemap",
        "serve"
      ]
    }
  }
}
```

更完整的配置见 [Claude Code 配置说明](claude-code.md)。

## 8. MCP 工具

除原有工具外，Session Intelligence 新增以下工具：

| 工具 | 用途 |
|---|---|
| `session_list` | 只列出 Session 元数据，不读取正文 |
| `session_analyze` | 经确认后读取指定 Session，并生成知识推荐 |
| `session_revoke` | 撤销指定 Session 的读取授权 |
| `source_import` | 导入本地文本或网页，并创建 pending Claim |
| `source_update` | 请求检查单个来源；需要已注册对应 checker |
| `review_list` | 列出待审核项目 |
| `review_decide` | 接受、拒绝、降级或要求继续研究 |
| `knowledge_search` | 默认搜索 accepted Claim |
| `knowledge_trace` | 校验证据并返回原始摘录和来源位置 |
| `knowledge_status` | 查看来源、Claim、索引和错误统计 |
| `session_analysis_prepare` | 授权后使用本地 Ollama 做增量分析 |
| `session_analysis_submit` | 接收 Codex/Claude Code 自身生成的结构化分析 |
| `session_analysis_get` | 读取最新任务状态和 checkpoint |
| `knowledge_need_list` | 列出 open、needs_refresh 或 resolved 知识需求 |
| `knowledge_need_resolve` | 用 accepted Claim 解析知识需求并返回证据关联 |

## 9. 推荐使用流程

### 9.1 查看状态

对 Codex 或 Claude Code 说：

> 调用 KnowledgeMap 的 `knowledge_status`，告诉我当前有多少来源、已接受 Claim 和待审核项目。

### 9.2 分析当前 Session（推荐）

对 Codex 或 Claude Code 说：

> 使用你当前已有的 Session 上下文，过滤寒暄、重复确认和原始工具长输出；整理任务状态，将每个未决项路由为询问用户、检索知识、检查时效、检查本地、执行测试或忽略。只有检索知识和检查时效可以产生 Knowledge Need。调用 `session_analysis_submit`，不要提交完整 Session。

随后查看需求：

> 调用 `knowledge_need_list` 列出当前 Session 的 open 知识需求，并说明每项会影响什么决策。

这种方式使用 Codex/Claude Code 自身模型能力，KnowledgeMap 只保存结构化状态和最多 500 字符的必要证据片段。

### 9.3 使用本地 Ollama 分析历史 Session

先列出元数据：

> 使用 `session_list` 列出当前项目最近的 Codex Session，不要读取正文。

选定 Session 后再明确授权：

> 使用 `session_analysis_prepare` 分析 Session `<session-id>`，我确认允许读取正文，`confirm_read=true`。只生成知识需求，不要创建 accepted Claim。

授权与 Session 内容快照绑定。如果 Session 后续发生变化，需要重新授权。调用 `session_revoke` 后，旧授权立即失效。

旧 `session_analyze` 暂时保留，但已标记 deprecated。

### 9.4 导入资料

本地 Markdown 示例：

> 使用 `source_import` 导入 `/absolute/path/to/approved-documents/oauth.md`，`source_type` 为 `official-doc`。

网页示例：

> 使用 `source_import` 导入 `https://example.org/technical-guide`，`source_type` 为 `technical-blog`。

网页抓取会拒绝私网、loopback、link-local 和不安全重定向目标，以降低 SSRF 风险。PDF 会返回不支持错误。

导入完成后，AI 提取的 Claim 状态是 `pending`，不会立即进入默认搜索。

### 9.5 人工审核

查看候选内容：

> 调用 `review_list` 列出 pending Claim，并逐条展示陈述和证据 ID。

支持四种决定：

| action | 含义 |
|---|---|
| `accept` | 接受并加入默认检索索引 |
| `reject` | 拒绝，不进入默认检索 |
| `downgrade-to-disputed` | 标记为存在争议 |
| `research-more` | 保持 pending，并记录需要补充研究的说明 |

审核示例：

> 对 Claim `<claim-id>` 执行 `accept`，actor 为我的名字，client 为 `codex`。

### 9.6 检索和引用证据

> 在 KnowledgeMap 中搜索“OAuth PKCE”，返回最多 5 条 accepted Claim。对准备使用的每条 Claim 调用 `knowledge_trace`，再根据证据回答。

一个可靠回答至少应包含：

- Claim 陈述；
- Claim ID；
- Evidence ID；
- SHA-256 内容哈希；
- 原始摘录；
- 稳定 URL 或本地证据位置；
- 适用范围和不确定性说明。

推荐回答格式：

```text
结论：……

证据：
- Claim: <claim-id>
- Evidence: <evidence-id>
- Source: <stable-url-or-local-pointer>
- Content hash: <sha256>
- Excerpt: “……”
```

## 10. 检索语法

KnowledgeMap 使用 SQLite FTS5/BM25，不使用 embedding。支持普通词、精确短语和排除词：

```text
OAuth PKCE
"semantic versioning"
OAuth -legacy
```

默认只返回 `accepted` 状态。相同分数使用稳定的 Claim ID 排序，便于重复测试和审计。

## 11. 更新与版本变化

KnowledgeMap 不会静默覆盖旧证据：

- 新内容保存为新的不可变快照；
- GitHub 证据 URL 固定到 commit SHA；
- 修改或删除可能产生 `stale_candidate` 审核提案；
- 新证据与旧 Claim 冲突时可产生 `disputed` 提案；
- 在人工确认之前，既有 accepted Claim 不会被自动改写。

系统没有常驻 daemon。可以由操作系统或客户端按周执行：

```bash
uv run knowledgemap check-updates
```

注意：默认 MCP 应用目前没有注册完整的 Web/GitHub update checker。该命令的调度和故障隔离框架已经可用，但生产更新来源需要在部署时接入对应 checker。

## 12. 数据、安全与隐私

默认数据目录：

```text
~/.local/share/knowledgemap/
├── knowledge.db
└── evidence/
```

安全原则：

- Session 元数据发现与正文读取分离；
- 正文读取必须明确确认；
- 授权可撤销，并绑定内容哈希；
- 原始证据使用 SHA-256 内容寻址；
- AI 输出不能绕过人工审核进入 accepted；
- 搜索结果可追溯到原始证据；
- API key、Session 正文和原始资料不会写入普通日志。

请同时备份 `knowledge.db` 和完整的 `evidence/` 目录。只备份其中一个会破坏证据链。

不要把真实 API key、私有 Session fixture、知识数据库或 evidence 目录提交到公共 Git 仓库。

## 13. 常见问题

### MCP 中看不到 KnowledgeMap

1. 确认项目绝对路径正确；
2. 运行 `uv sync`；
3. 运行 `uv run knowledgemap --help`；
4. 在终端运行 `codex mcp get KnowledgeMap`；
5. 重启客户端或新建任务。

### Analyzer 无法连接

```bash
ollama list
curl http://127.0.0.1:11434/api/tags
```

检查 `KNOWLEDGEMAP_ANALYZER_BASE_URL` 和模型名称。远程地址会被主动拒绝。

### 本地文件被拒绝

确认文件位于 `KNOWLEDGEMAP_LOCAL_SOURCE_ROOT` 内，并且不是逃逸到目录外的符号链接。当前只接受 UTF-8 Markdown 和纯文本。

### 为什么导入后搜索不到

导入只创建 `pending` Claim。必须先通过 `review_decide(action="accept")` 接受，Claim 才会进入默认索引。

### 为什么 Session 分析被拒绝

`session_analyze` 必须传入 `confirm_read=true`。Session 内容变化或授权撤销后，需要重新授权。

### 证据 trace 失败怎么办

不要继续把该 Claim 当作已验证结论。回答中应标记 `unverified`，然后检查 evidence 目录是否缺失或被修改。

## 14. 面向贡献者

运行测试：

```bash
uv run pytest -v
uv run python -m compileall src
```

项目的核心不变量是：**先保存证据、再调用 AI；先人工审核、再进入检索；先验证 trace、再引用结论。**

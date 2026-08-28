# Session Knowledge Needs Specification

Date: 2026-08-28  
Status: Approved  
Supersedes: Phase 1 中“整段 Session 直接生成 recommendations”的分析设计  
Related: [Use Cases](../../product/2026-08-28-session-knowledge-needs-usecases.md) · [Acceptance Criteria](../../product/2026-08-28-session-knowledge-needs-acceptance.md)

## 1. Objective

KnowledgeMap 从用户明确授权的 Codex 或 Claude Code Session 中识别“为了完成当前任务，仍缺少哪些可由权威资料解决的知识”，而不是对全文做泛化总结。

系统必须区分：

- **需求缺失**：目标、约束或验收标准不清楚，应询问用户。
- **知识缺失**：任务明确，但缺少会影响决策的外部事实或证据，应检索知识库。
- **时效缺失**：已有依据可能过期、存在版本冲突，应检查更新。
- **本地上下文缺失**：答案存在于当前代码、配置或本地文档，应检查本地材料。
- **执行缺失**：知识已足够，只需执行、测试或排障。
- **无动作价值**：寒暄、重复确认、已解决尝试或不影响决策的信息，应忽略。

## 2. Product Scope

### 2.1 Included

- Codex、Claude Code 使用自身模型对本地完整 Session 做过滤和结构化。
- Ollama 作为本地独立分析器，处理授权后的 Session 快照。
- 接收客户端已过滤的结构化分析结果，不要求上传完整 Session。
- 对本地 Session 做增量分析，而不是每次重跑全部历史。
- 按任务阶段切分，维护结构化任务状态。
- 对未决项进行缺口路由，只为真正的知识缺失生成 Knowledge Need。
- 先检索当前 KnowledgeMap；命中时返回 claim、证据、版本与定位信息。
- 未命中时保留为待补充知识需求，不自动接入外部搜索。
- 对重复需求去重，并保留各自的 Session 证据。

### 2.2 Excluded

- 外部 LLM API 分析器。
- 实时 Web 搜索、舆情和社交媒体。
- PDF 视觉解析、OCR、图表理解。
- 要求终端用户标注训练集或领域数据集。
- 从 Session 自动发布正式 claim。
- 因分析失败而默认认定存在知识缺口。

## 3. Analysis Modes

### 3.1 Client-assisted mode（推荐）

Codex 或 Claude Code 读取当前 Session，使用自身模型输出标准 `SessionInsightSubmission`。KnowledgeMap 只接收结构化状态、知识需求和最小证据片段。

优点：不复制完整 Session；能使用客户端已有上下文和模型能力；适合相对封闭、无法作为 HTTP analyzer 调用的模型。

### 3.2 Local Ollama mode

KnowledgeMap 在明确授权后读取本地 Session，由 Ollama 的 OpenAI-compatible endpoint 完成同一分析流水线。该模式不得被描述为外部 API；默认地址仍为本机回环地址。

两个模式输出相同领域模型，进入同一持久化、检索和审计流程。

## 4. Processing Pipeline

```text
Session events
  → normalize and redact
  → detect task episodes
  → extract task-state delta
  → route unresolved items
  → compose knowledge needs
  → deduplicate and rank
  → search KnowledgeMap
  → persist analysis + evidence pointers
```

### 4.1 Normalize and redact

- 输入只允许 user/assistant 文本和允许保留的工具结果摘要。
- 默认排除 reasoning、隐藏系统提示、二进制内容和完整工具原始输出。
- 证据片段必须有限长，并带 `message_id` 或稳定的消息序号。
- 凭据形态文本在提交前用 `[REDACTED]` 替换。

### 4.2 Task episode detection

任务边界由以下事件触发：新目标、目标显著变化、用户明确恢复旧目标、任务完成或放弃。固定 token 窗口只能用于模型上下文限额，不得充当语义分段策略。

每个 episode 维护：

```text
objective
constraints
acceptance_criteria
decisions
known_facts
assumptions
evidence_refs
unresolved_items
blockers
actions_and_outcomes
```

### 4.3 State extraction

分析器只输出相对上一个检查点的 `TaskStateDelta`。删除或替换状态必须引用被替换的字段及输入证据。未经证据支持的推断必须进入 `assumptions`，不得进入 `known_facts`。

### 4.4 Gap routing

每个 `UnresolvedItem` 必须且只能被路由到：

```text
ask_user
search_knowledge_map
check_freshness
inspect_local
execute_or_test
ignore
```

路由到 `search_knowledge_map` 或 `check_freshness` 必须同时满足：

1. 问题会改变当前决策、实现选择或验收结论；
2. 问题需要可验证事实，而不是单纯执行动作；
3. 当前 Session 没有充分证据，或证据可能过期/冲突；
4. 问题可表达为独立、可检索、可引用证据回答的问题。

### 4.5 Knowledge Need composition

```json
{
  "question": "当前版本 MCP SDK 是否支持 structured output？",
  "decision_it_changes": "决定工具返回值是否使用结构化 schema",
  "current_assumption": "可能只支持文本返回",
  "knowledge_type": "capability",
  "preferred_source_types": ["official-doc", "github"],
  "version_or_time_scope": "installed-version",
  "why_context_is_insufficient": "Session 中没有接口或版本证据",
  "session_evidence": [{"message_id": "m42", "excerpt": "..."}],
  "confidence": 0.86
}
```

`knowledge_type` 允许：`concept`、`capability`、`implementation`、`compatibility`、`security`、`evaluation`、`version_change`。

复杂问题最多拆为 5 个方面：原理、实现、边界、版本、验证。不得为了达到数量而拆分。

### 4.6 Deduplication and ranking

- 第一阶段使用规范化文本、关键词和版本范围做确定性候选匹配。
- 第二阶段由分析器判断两个候选是否具有相同决策目的。
- 合并仅合并需求实体，不丢弃原始 Session 证据。
- 排序分数由 `decision_impact`、`urgency`、`evidence_weakness`、`confidence` 组成；不使用用户领域标注训练。

### 4.7 KnowledgeMap resolution

- 默认搜索已接受 claim。
- 命中结果必须返回 claim ID、原文证据定位、来源版本及更新时间。
- 只命中过期或 disputed claim 时，需求状态为 `needs_refresh`，不能视为已解决。
- 未命中时状态为 `open`，供用户后续指定资料或调用信息代理处理。

## 5. Domain Contracts

### 5.1 SessionInsightSubmission

```python
class SessionInsightSubmission(BaseModel):
    client: Literal["codex", "claude-code"]
    session_id: str
    checkpoint_id: str
    previous_checkpoint_id: str | None
    content_hash: str
    episode_deltas: list[TaskStateDelta]
    routes: list[GapRouteDecision]
    knowledge_needs: list[KnowledgeNeedDraft]
```

### 5.2 Provenance requirements

- 每个状态变化、路由决定和 Knowledge Need 至少引用一个 Session evidence pointer。
- `content_hash + checkpoint_id` 对同一 Session 必须幂等。
- 客户端提交不能创建或接受 claim。
- 原始 Session 撤销后禁止新的本地读取；已提交结构化结果保留审计记录，并可由用户单独删除（删除功能不在本次实现范围）。

## 6. MCP Changes

新增：

- `session_analysis_prepare(client, session_id, confirm_read)`：本地 Ollama 模式生成增量分析输入和检查点。
- `session_analysis_submit(submission)`：Codex/Claude Code 提交结构化结果并落库。
- `session_analysis_get(client, session_id, checkpoint_id?)`：读取最新任务状态、路由和知识需求。
- `knowledge_need_list(status?, session_id?, top_k?)`：列出排序后的需求与命中状态。
- `knowledge_need_resolve(knowledge_need_id)`：搜索已接受知识并返回带证据结果。

兼容：

- `session_analyze` 保留一个发布周期，内部映射到本地 Ollama 流程并标记 deprecated。
- 既有 `knowledge_search`、`knowledge_trace`、资料审核和更新工具保持不变。

## 7. Trigger and Incremental Semantics

分析检查点包括：

- 用户确认或否定关键方案；
- 新决策或新阻塞出现；
- 任务完成、暂停或目标切换；
- 用户显式调用分析工具。

同一 `content_hash` 重复提交返回已存在结果。新检查点只处理上一个检查点后的事件，并把状态 delta 合并为最新快照。乱序提交被拒绝为 `CHECKPOINT_CONFLICT`。

## 8. Failure Handling

- 模型输出不符合 schema：返回 `ANALYZER_INVALID_OUTPUT`，不写入部分结果。
- Ollama 不可用：返回 `ANALYZER_UNAVAILABLE`，已有状态不受影响。
- 没有可操作知识需求：分析成功并返回空列表，不视为错误。
- 缺少证据指针：拒绝该提交。
- 客户端与本地分析结果冲突：保留两个 analysis run，以最新明确提交为 active，不静默覆盖审计历史。

## 9. Privacy and Security

- 客户端辅助模式默认只传结构化结果与最小证据片段。
- 本地 Ollama 模式仅允许回环地址，除非未来另行修改规格。
- 日志不得记录 Session 正文、提示词全文、凭据或证据 excerpt。
- 所有 Session 读取继续受已有 grant/revoke 机制约束。

## 10. Product Feedback

用户只需执行 `useful`、`not_useful`、`resolved` 三类轻反馈。反馈用于排序和产品统计，不用于要求用户构建训练集。打开资料、导入来源、引用 claim 等行为可以作为本地隐式信号，但不能改变 claim 的审核状态。


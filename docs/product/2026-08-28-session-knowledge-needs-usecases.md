# Session → Knowledge Need Use Cases

Date: 2026-08-28  
Spec: [Session Knowledge Needs Specification](../superpowers/specs/2026-08-28-session-knowledge-needs-spec.md)

## UC-01：Codex 直接提交分析结果

- **参与者**：用户、Codex、KnowledgeMap
- **前置条件**：KnowledgeMap MCP 已连接；用户正在当前 Session 工作。
- **主流程**：Codex 读取自身上下文，过滤无关内容，生成任务状态、缺口路由和 Knowledge Need；调用 `session_analysis_submit`；KnowledgeMap 校验、去重并检索已有 claim。
- **结果**：用户看到缺少什么知识、为什么需要、影响哪个决策以及当前是否已有证据。
- **例外**：缺少 evidence pointer 或 checkpoint 冲突时拒绝整次提交。

## UC-02：Claude Code 直接提交分析结果

流程与 UC-01 相同，`client=claude-code`。客户端模型无需暴露为 HTTP API，也不需要把完整 Session 交给 KnowledgeMap。

## UC-03：使用本地 Ollama 分析已授权 Session

- **前置条件**：用户已显式授权 Session；Ollama 在回环地址运行。
- **主流程**：调用 `session_analysis_prepare`；KnowledgeMap 读取授权后的新增消息；本地分析器依次抽取状态、路由未决项、生成 Knowledge Need；结果落库。
- **结果**：输出格式与客户端辅助模式一致。
- **例外**：Ollama 不可用时不产生部分分析，也不损坏上一个检查点。

## UC-04：Session 没有知识缺口

- **场景**：用户要求修改颜色、执行已有测试或修复明确的语法错误。
- **期望**：路由为 `execute_or_test` 或 `ignore`；Knowledge Need 列表为空；系统不为了“推荐内容”而制造问题。

## UC-05：需求本身不清楚

- **场景**：用户说“把它做得更专业”，但没有目标用户和验收标准。
- **期望**：路由为 `ask_user`，提出缺少的规格字段；不检索“专业设计最佳实践”来代替澄清。

## UC-06：需要权威知识

- **场景**：任务需要决定特定版本库是否支持某 API，但 Session 中只有模型推测。
- **期望**：生成 `capability` 类型 Knowledge Need，首选官方文档和 GitHub；说明该答案会改变哪个实现决策。

## UC-07：已有知识可能过期

- **场景**：Session 引用了 KnowledgeMap 中旧版本 GitHub 文档。
- **期望**：路由为 `check_freshness`；如果 claim 的来源版本落后，状态为 `needs_refresh`，同时保留旧证据。

## UC-08：答案在本地工程中

- **场景**：问题是当前仓库使用哪个 Python 版本或函数参数是什么。
- **期望**：路由为 `inspect_local`；不创建外部知识需求。

## UC-09：复杂知识需求拆解

- **场景**：需要选择 Session memory 方案。
- **期望**：按决策需要拆为原理、实现约束、评估方法和版本边界，最多 5 项；共享同一决策目的并可独立检索。

## UC-10：重复 Session 需求聚合

- **场景**：多个 Session 都需要确认同一 SDK 能力。
- **期望**：聚合成一个 Knowledge Need，保留多个 Session/episode evidence pointer；已解决后所有关联 Session 可看到结果。

## UC-11：KnowledgeMap 命中并返回证据

- **场景**：生成的知识问题已被 accepted claim 覆盖。
- **期望**：`knowledge_need_resolve` 返回 claim、证据 excerpt、稳定 locator、来源版本和更新时间；Knowledge Need 标记为 `resolved`。

## UC-12：KnowledgeMap 未命中

- **期望**：Knowledge Need 保持 `open`，提供推荐 source type；不伪造答案，也不自动调用外部搜索。用户可随后指定论文、文档、博客或 GitHub 来源。

## UC-13：增量分析

- **场景**：同一 Session 继续产生新消息。
- **期望**：只分析上个 checkpoint 之后的内容；旧决策和证据通过状态快照继承；同一内容重试不会创建重复记录。

## UC-14：用户轻反馈

- **场景**：用户认为推荐无用，或确认知识需求已经解决。
- **期望**：记录 `not_useful` 或 `resolved`，影响排序；不改变任何 claim 的审核状态。


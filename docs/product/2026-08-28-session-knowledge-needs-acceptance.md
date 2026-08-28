# Session → Knowledge Need Acceptance Criteria

Date: 2026-08-28  
Spec: [Session Knowledge Needs Specification](../superpowers/specs/2026-08-28-session-knowledge-needs-spec.md)

## A. Functional acceptance

- **AC-01** Codex 和 Claude Code 均可通过 `session_analysis_submit` 提交相同 schema，且无需配置外部模型 API。
- **AC-02** 本地 Ollama 可在显式授权后完成分析；非回环 analyzer 地址被配置校验拒绝。
- **AC-03** 一个 analysis run 至少保存 episode、状态 delta、route decision、Knowledge Need 和 Session evidence pointer。
- **AC-04** 每个未决项只能有一个 route；route 必须属于规格定义的六种之一。
- **AC-05** `ask_user`、`inspect_local`、`execute_or_test`、`ignore` 不产生 Knowledge Need。
- **AC-06** 没有知识缺口的 Session 返回成功及空 Knowledge Need 列表。
- **AC-07** Knowledge Need 包含 question、decision impact、当前假设、知识类型、来源偏好、版本/时间范围、上下文不足原因、证据和置信度。
- **AC-08** 相同 checkpoint 和 content hash 重试幂等；乱序 checkpoint 返回 `CHECKPOINT_CONFLICT`。
- **AC-09** 增量提交只包含上个 checkpoint 之后的新 evidence pointer，并能生成合并后的最新任务状态。
- **AC-10** 同一决策目的的重复需求可合并，所有原 evidence pointer 仍可追溯。
- **AC-11** accepted claim 命中后返回 claim ID、来源、版本、locator 和 evidence excerpt。
- **AC-12** 仅命中 disputed、stale 或旧版本 claim 时返回 `needs_refresh`，不得标记 resolved。
- **AC-13** 未命中保持 open，不调用外部搜索、不生成无证据答案。
- **AC-14** Session 分析永远不能创建 accepted claim。
- **AC-15** `useful`、`not_useful`、`resolved` 反馈可记录但不改变 claim review status。

## B. Filtering and routing examples

以下固定用例必须通过自动化回归测试：

| 输入事件 | 预期 route | Knowledge Need |
|---|---|---|
| “把按钮改成蓝色并运行测试” | `execute_or_test` | 无 |
| “做得更专业”，无验收说明 | `ask_user` | 无 |
| “项目当前 Python 版本是多少？” | `inspect_local` | 无 |
| 安装依赖时报权限错误 | `execute_or_test` | 无 |
| 模型猜测某 SDK 当前支持某接口 | `search_knowledge_map` | 有，类型 `capability` |
| 引用了旧 commit 的接口说明 | `check_freshness` | 有，类型 `version_change` |
| 重复的“ok/继续/同意” | `ignore` | 无 |

## C. Privacy and safety acceptance

- **AC-16** 未授权的本地 Session 无法被 `prepare` 或旧版 `session_analyze` 读取。
- **AC-17** client-assisted mode 的数据库和应用日志不保存完整 Session 正文。
- **AC-18** reasoning、隐藏系统消息、二进制工具结果不进入分析输入。
- **AC-19** evidence excerpt 有明确长度上限，且常见 token、password、private key 模式在持久化前被替换为 `[REDACTED]`。
- **AC-20** analyzer 输出校验失败时事务回滚，不留下 analysis、route 或 need 的部分记录。

## D. Compatibility and operations acceptance

- **AC-21** 既有 `knowledge_search`、`knowledge_trace`、source import/update 和 review 测试继续通过。
- **AC-22** 旧 `session_analyze` 在一个发布周期内可用，并返回 deprecation 信息。
- **AC-23** schema migration 可从现有 user_version=1 数据库升级，已有 grants、analyses 和 recommendations 不丢失。
- **AC-24** `knowledge_status` 增加 open needs、needs refresh、latest checkpoint 和 analyzer mode 统计。
- **AC-25** Codex 与 Claude Code 使用文档分别给出 client-assisted 示例；用户指南给出 Ollama 示例。

## E. Release gate

发布前必须满足：

```bash
uv run pytest -q
uv run python -m compileall src
uv build
```

全部退出码为 0；MCP contract integration tests 覆盖五个新增工具；使用一个合成 Codex Session 和一个合成 Claude Code Session 完成端到端验收。该验收是产品研发回归，不要求终端用户进行人工标注。


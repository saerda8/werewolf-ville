# Task Plan: Project Governance Completion

创建日期：2026-06-04

## Goal

把 Werewolf Ville 的长期项目治理体系一次性落地，解决长上下文丢需求、bug 反复回归、worker 不敢干活或乱改、频道混乱、缺少恢复入口的问题。

## Scope

本任务属于“项目工具与结构频道”。

允许改动：

- 项目治理文档
- `.planning/` 规划目录
- `AGENTS.md`

不在本任务范围：

- 游戏运行代码
- UI bug 修复
- `personas/` 运行态文件
- 模型配置或 API key

## Phases

### Phase 1: Worker Delegation

Status: complete

- [x] 委派 DeepSeek 实际编辑治理文档。
- [x] 委派 Antigravity 实际编辑频道和流程文档。
- [x] 保留基本边界，但不限制到单文件导致 worker 无法工作。

### Phase 2: Governance Docs

Status: complete

- [x] 建立 `USER_REQUIREMENTS_LEDGER.md`。
- [x] 为稳定需求建立 REQ 编号体系。
- [x] 建立 `BUG_BACKLOG.md` 并补充关联需求、回归测试、关闭门禁字段。
- [x] 建立 `PROJECT_CHANNELS.md`。
- [x] 建立 `DECISIONS.md`。
- [x] 建立 `GAME_ENGINE_SPLIT_PLAN.md`。
- [x] 建立 `PROJECT_INDEX.md`。

### Phase 3: Planning Files

Status: complete

- [x] 建立 `.planning/README.md`。
- [x] 建立本任务的 `task_plan.md`。
- [x] 建立本任务的 `findings.md`。
- [x] 建立本任务的 `progress.md`。

### Phase 4: Validation

Status: complete

- [x] 检查 `git status`，确认没有越界改动。
- [x] 运行 `python -m py_compile agent.py game_engine.py llm.py ui/app.py`。
- [x] 需要时运行 `git diff --stat`。
- [x] 提交治理文档检查点。

## Completion Criteria

- 所有治理文档在 Git 中可追踪。
- 基础 Python 编译检查通过。
- `CURRENT_SPRINT.md` 清楚说明下一步是 `game_engine.py` 第一切片拆分。
- 新会话可从 `PROJECT_INDEX.md` 和 `.planning/` 恢复上下文。

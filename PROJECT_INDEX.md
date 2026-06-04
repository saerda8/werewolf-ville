# Werewolf Ville Project Index

更新时间：2026-06-04

## 作用

这是新会话、新 worker 或长时间中断后的第一入口。不要一上来读完整聊天记录；先按这里的顺序恢复项目上下文。

## 快速恢复顺序

1. 读 [AGENTS.md](AGENTS.md)：确认协作规则、worker 含义、MCP 使用要求、命令规范。
2. 读 [PROJECT_CONTINUITY.md](PROJECT_CONTINUITY.md)：确认项目目标、玩法事实、工程风险、回归门禁。
3. 读 [DECISIONS.md](DECISIONS.md)：确认最近做过哪些治理和架构决策。
4. 读 [CURRENT_SPRINT.md](CURRENT_SPRINT.md)：确认当前正在做什么、哪些事情明确不做。
5. 查看 [.planning/README.md](.planning/README.md) 和活跃 `.planning/<task>/`：恢复短期任务进度。
6. 如果是需求或玩法问题，读 [USER_REQUIREMENTS_LEDGER.md](USER_REQUIREMENTS_LEDGER.md) 和 [ROADMAP.md](ROADMAP.md)。
7. 如果是 bug，读 [BUG_BACKLOG.md](BUG_BACKLOG.md)，不要只靠聊天截图。
8. 如果是 `game_engine.py` 拆分，读 [GAME_ENGINE_SPLIT_PLAN.md](GAME_ENGINE_SPLIT_PLAN.md)。

## Codex 项目线程

Codex `create_thread` 的项目目标使用工作区路径：

```text
G:\Trae-Project\werewolf-ville
```

当前固定线程：

- 项目结构与治理：`019e8322-7e35-71b1-aba5-0148fb57347d`
- 玩法设计：`019e92f1-c30c-7e42-a14c-b695433729bf`
- Bug 修复：`019e92f1-e1b0-7153-9b92-859a70f450d4`

频道使用规则见 [PROJECT_CHANNELS.md](PROJECT_CHANNELS.md)。

## 单一事实来源

| 问题 | 权威文件 |
| --- | --- |
| 用户稳定需求编号 | `USER_REQUIREMENTS_LEDGER.md` |
| 当前玩法与项目事实 | `PROJECT_CONTINUITY.md` |
| 当前任务状态 | `CURRENT_SPRINT.md` |
| Bug 复现、根因、关闭状态 | `BUG_BACKLOG.md` |
| 多频道流程 | `PROJECT_CHANNELS.md` |
| 架构/流程决策历史 | `DECISIONS.md` |
| 大文件拆分计划 | `GAME_ENGINE_SPLIT_PLAN.md` |
| 当前短期任务执行记录 | `.planning/<task>/task_plan.md`、`findings.md`、`progress.md` |

## 开工前固定检查

```powershell
rtk git status --short
python -m py_compile agent.py game_engine.py llm.py ui/app.py
```

涉及 UI 时，必须确保 `http://127.0.0.1:5000/` 跑的是最新代码，并用浏览器实际验证。

## Worker 使用原则

限制不要细到让 coworker 无法干活。推荐做法是：

- 给出任务目标、允许改动的文档或模块范围、禁止碰的运行态文件、验收命令。
- 允许 DeepSeek 和 Antigravity 在范围内实际改文件。
- 主 agent 最后用 `git diff`、测试和浏览器验收兜底。

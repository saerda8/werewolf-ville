# Current Sprint

更新日期：2026-06-04

关联需求：REQ-011 ~ REQ-017（版本与项目治理）。完成时 commit 标注 `(refs REQ-XXX)`。

## Sprint 目标

先完成工程结构治理和 `game_engine.py` 拆分准备，再进入 bug 修复。

## 当前频道

项目工具/结构频道收口中。后续新方向转入玩法设计线程。

## 任务清单

- [x] 初始化 Git 仓库并创建首个基线提交。
- [x] 创建项目连续性文档 `PROJECT_CONTINUITY.md`。
- [x] 建立 `ROADMAP.md`。
- [x] 建立 `BUG_BACKLOG.md`。
- [x] 建立 `CURRENT_SPRINT.md`。
- [x] 建立频道工作流文档与短期任务 `.planning/` 目录规范。
- [x] 汇总 DeepSeek 的 `game_engine.py` 拆分建议并建立 `GAME_ENGINE_SPLIT_PLAN.md`。
- [x] 汇总 Antigravity 的频道/流程建议并落实在 `PROJECT_CHANNELS.md`。
- [x] 写出最终 `game_engine.py` 拆分执行计划与 Worker 协作 SOP。
- [x] 执行低风险拆分切片并提交。

## 本轮不做

- 不直接修 UI 气泡 bug。
- 不直接改投票玩法。
- 不新增银器/夜晚玩法。

原因：先拆结构，再修 bug，避免重复回归。

## 验证要求

每个拆分切片必须通过回归门禁（详见 `PROJECT_CONTINUITY.md §11.1`），至少：

```powershell
python -m py_compile agent.py game_engine.py llm.py ui/app.py
```

根据影响范围运行相关测试：

```powershell
pytest -q tests/test_engine_foundation.py
pytest -q tests/test_vote_flow.py
pytest -q tests/test_ui_bubble_layout.py
```

验收后更新 `BUG_BACKLOG.md` 状态（如有相关 bug）并在 commit 中标注关联 REQ。

## 项目线程状态

- [x] 项目结构与治理线程：`019e8322-7e35-71b1-aba5-0148fb57347d`
- [x] 玩法设计线程：`019e92f1-c30c-7e42-a14c-b695433729bf`
- [x] Bug 修复线程：`019e92f1-e1b0-7153-9b92-859a70f450d4`

Codex 项目目标使用工作区路径 `G:\Trae-Project\werewolf-ville`。后续创建线程不强行传模型名。

## 结构阶段收口结果（2026-06-04）

- [x] 抽离导航与地图纯工具：`engine_navigation.py`
- [x] 抽离警长每日任务构建：`engine_tasks.py`
- [x] 抽离引擎侧气泡计时与摘要：`engine_bubbles.py`
- [x] 抽离黄昏、投票与监狱流程：`engine_dusk.py`
- [x] 每个结构切片独立验证并提交
- [x] 记录后续高风险拆分边界

项目结构阶段完成，已完成一轮 Bug Backlog 收口。后续新方向应转入 **玩法设计线程**，围绕 NPC 行为框架、行动枚举、线索灯泡、主动汇报和交谈规则形成设计文档，不再在本线程混入新玩法讨论。

最终收口回归：`python -m pytest tests -q`，结果 `380 passed`。

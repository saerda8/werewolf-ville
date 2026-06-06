# DeepSeek / Antigravity MCP Worker 使用手册

更新日期：2026-06-07

## 目的

这是 Werewolf Ville 项目换频道后恢复 worker 调用方式的固定手册。新会话不要只靠聊天记忆判断 DeepSeek 或 Antigravity 是否可用；先按本文件确认工具、分配任务、设置文件范围、审查结果。

## 结论

- 非平凡 bug 修复和中等以上开发，先评估并尽量调用 DeepSeek / Antigravity。
- DeepSeek 和 Antigravity 默认视为可用；不要因为“可能碰 personas”直接跳过。
- 如果任务天然会写 `personas/` 运行态，要么换给本地主 agent / Antigravity 做，要么明确允许运行态写入并由主 agent 清理；不能一边让 worker 运行会写入的流程，一边把这些路径设为禁止后再判 worker 失败。

## 换频道后的恢复顺序

1. 读 `PROJECT_INDEX.md`、`AGENTS.md`、`PROJECT_CHANNELS.md`、本文件。
2. 用工具发现确认当前频道是否暴露了专用 MCP：
   - 搜索关键词：`DeepSeek code worker Antigravity code worker start implementation MCP`
   - 如果出现专用工具，优先用：
     - `mcp__deepseek_code_worker.deepseek_start_implementation`
     - `mcp__antigravity_code_worker.antigravity_start_implementation`
   - 如果没有出现专用工具，不要说 MCP 永久不可用；说明“当前频道未暴露专用 MCP”，再用可见的通用子 agent 或本地主 agent 推进。
3. 先做任务拆分，再派 worker；主 agent 同时继续做不重叠的工作。
4. worker 完成后，主 agent 必须审查 `git status`、`git diff`、测试、浏览器表现，再合并结论。

## 什么时候派谁

| 任务类型 | 优先 worker | 原因 |
| --- | --- | --- |
| 后端状态机、投票、夜晚、调度、prompt 契约、测试 | DeepSeek | 适合复杂逻辑和跨模块根因定位 |
| 前端 UI、气泡位置、日志面板、浏览器交互、Socket 同步 | Antigravity | 适合界面和运行态前端细节 |
| 文档整理、流程手册、重复规则合并 | Antigravity 或本地主 agent | 范围低风险，容易审查 |
| 会启动整局游戏、会触发 NPC 记忆写入、会修改 `personas/` 运行态 | 本地主 agent 优先；必要时明确允许 worker 写入后清理 | 避免 forbidden_paths 把 worker 判失败 |

## DeepSeek 调用模板

适合：后端逻辑、测试、根因定位、prompt 契约。

```text
Tool: mcp__deepseek_code_worker.deepseek_start_implementation

cwd: G:\Trae-Project\werewolf-ville
use_case: debug_loop 或 auto
worker_profile: debug_loop 或 implementation
verification_profile: standard
model: deepseek-v4-pro[1m] 或 deepseek-v4-flash
permission_mode: dontAsk / acceptEdits
safety_mode: permissive 或 safe
allowed_dirs:
  - G:\Trae-Project\werewolf-ville
forbidden_paths:
  - 只在任务不会写入时才禁止 personas
  - 只在任务不会写入时才禁止 .pytest_cache
task:
  目标、允许改动范围、禁止改动范围、前置验证、后置验证、验收标准
checks:
  - python -m py_compile <受影响文件>
  - python -m pytest <相关测试> -q -p no:cacheprovider
```

### DeepSeek 派工注意

- 不要把“运行整局游戏、启动真实 NPC 行动循环、写 memory/cognition”的任务交给 DeepSeek 后又禁止 `personas/`。
- 如果只需要 DeepSeek 分析这类问题，改成只读任务：让它读源码、写根因报告或写不触发运行态的单元测试。
- 如果必须让 DeepSeek 跑会写 `personas/` 的验证，就在任务说明中明确“允许运行态写入，主 agent 之后清理”，不要把 `personas/` 放进 forbidden_paths。
- DeepSeek 失败时先看它的输出和 diff；失败不等于没价值，保留可用发现，再缩小任务重派。

## Antigravity 调用模板

适合：前端 UI、气泡、日志面板、浏览器同步、低风险文档/脚本。

```text
Tool: mcp__antigravity_code_worker.antigravity_start_implementation

cwd: G:\Trae-Project\werewolf-ville
model: pro
timeout_ms: 900000
task:
  目标、允许改动文件、禁止改动文件、验收标准、测试命令
```

### Antigravity 派工注意

- UI bug 可以直接给 `ui/templates/index.html`、`tests/test_ui_bubble_layout.py`、`BUG_BACKLOG.md` 等明确范围。
- Antigravity 不只是前端，也可以做文档、Socket、低风险后端拆分。
- Antigravity 产出的前端改动必须由主 agent 用浏览器验证，不只看它的总结。
- 如果 Antigravity 状态查询遇到 usage limit，只说明状态查询受限；已写入工作区的改动仍要按 `git diff` 审查。

## personas/ 策略

`personas/` 既有静态模板，又有运行态记忆。错误策略是：让 worker 跑会写运行态的流程，同时禁止它改 `personas/`，最后把 worker 判失败。

正确策略只有两种：

1. **禁止写入策略**：任务、测试、验证都必须设计成不会触发 NPC 运行态写入。适合静态代码分析、纯单元测试、前端 UI、文档。
2. **允许写入策略**：任务明确允许运行态写入；worker 完成后主 agent 检查并清理 `personas/*/memory.md`、`cognition.md`、`scratch.json`、`memory_index.json` 等脏数据，只保留真正需要的静态修复。

如果不确定，先不要派 DeepSeek 跑运行态；改派 Antigravity 做前端/文档，或主 agent 自己用隔离方式验证。

## 标准派工文本

```text
## Task
目标：<一句话>
改动范围：<允许改的文件或目录>
禁止改动：<不允许改的文件；如果 personas 会被运行态写入，就不要放这里，改写清理策略>
personas 策略：禁止写入 / 允许运行态写入并由主 agent 清理
前置验证：<需要先看的测试或编译>
后置验证：<必须通过的测试或浏览器检查>
验收标准：<可观察结果>
关联需求/BUG：REQ-XXX / BUG-XXX
```

## 主 agent 审查清单

- `git status` 确认 worker 改动范围。
- `git diff` 确认没有无关重构、调试输出、运行态污染。
- `personas/` 如果变脏，逐项判断是运行态还是静态模板；默认清理运行态。
- 受影响 Python 文件通过编译。
- 相关 pytest 通过。
- UI 改动必须重启服务，确认 `http://127.0.0.1:5000/` 是最新版本，并用浏览器检查。
- 修 bug 后更新 `BUG_BACKLOG.md`，必要时更新 `CURRENT_SPRINT.md`。
- 完成后创建可回滚 Git 提交。

## 已知调用记录

这些记录说明项目里已经成功/部分成功调用过两个 worker：

- Antigravity：`ag-c5e0e0ce-02f8-48e4-b25b-6dc9e28ac8bb`，用于把智能体日志从右侧移到底部，产出后由主 agent 审查并提交为 `d67e69f fix: move agent log to bottom panel`。
- Antigravity：`ag-cc018b18-ef8d-4919-85b0-a141c69d8860`，用于日志字号、可拖动、气泡边界等 UI 修复；产出有价值，但需主 agent 修正和浏览器验收。
- DeepSeek：`dsw_mpzw7wd4_oaw9vq`，用于日志面板静态测试/文档支持；因任务设计仍诱发 `personas/` 运行态变化而被 forbidden_paths 判失败。
- DeepSeek：`dsw_mpzx3bzs_e4e4ov`，用于后端日志过滤、思考气泡生命周期、克罗走路抖动分析；同样暴露出 personas 策略设计错误。
- DeepSeek：`dsw_mq2ljczi_85xaqc`，用于黄昏投票与夜晚流程；记录显示模型、参数和检查命令可用，但也出现 forbidden_paths 与 personas 冲突。

本项目的经验结论：MCP 本身不是不可用，主要问题是主 agent 派工范围和 personas 策略没有提前设计好。

# Project Collaboration Preferences

- Before starting any task, first assess whether analysis or implementation can be delegated to available subagents.
- For any non-trivial investigation or code change, begin by planning subagent delegation first, before doing the work locally. Prefer launching clearly scoped tasks to both DeepSeek and Antigravity in parallel whenever their scopes can be separated.
- If only one subagent can be used, or if a task is too small/unsafe/sequential to delegate, state that reason briefly before proceeding locally.
- Do not leave DeepSeek or Antigravity idle on substantial work merely to save coordination effort; use them to save primary-agent context and tokens.
- For work that requires non-trivial investigation or code changes, prefer splitting clearly scoped tasks between DeepSeek and Antigravity.
- Antigravity can own backend investigation and implementation tasks as well as frontend work. When backend work can be divided into independent scopes, distribute it across both CLI workers instead of queueing all backend tasks behind DeepSeek.
- The primary agent remains responsible for task boundaries, reviewing changes, integration, and final verification.
- Prefix ordinary shell commands with `rtk` in this project to reduce terminal output and token use. Use direct commands only for MCP calls, approved Windows management commands, or cases where `rtk` would interfere with the required operation.
- Before delegating a task to DeepSeek, run a Claude Code CLI preflight with the configured native Windows executable and DeepSeek key file. Confirm that the CLI starts successfully before launching the DeepSeek worker.
- On Windows, use the native Claude Code `claude.exe` configured through `CLAUDE_BIN`; do not rely on `claude.ps1`, because the DeepSeek launcher starts Claude Code through Node.js `spawn()`.
- Before delegating a task to Antigravity, run the Antigravity CLI doctor and confirm that the configured `antigravity.exe` reports ready. Use the CLI worker path, not the desktop language-server integration.
- When the user asks to use DeepSeek as a subagent, this always means the Claude Code CLI-driven DeepSeek worker. It does not mean a direct model API call or an in-game NPC model.
- When the use of Antigravity as a subagent is requested, this always means the Antigravity CLI worker. It does not mean the Antigravity desktop language-server integration.
- When the user asks to use the in-app Browser, do not conclude it is unavailable just because no direct `browser` tool appears. First follow the Browser plugin skill and connect through the Node REPL browser-client (`agent.browsers.get("iab")`), then use that in-app browser for localhost navigation, screenshots, and inspection.

---

## Worker 能力矩阵

### DeepSeek（Claude Code CLI）

| 能力 | 胜任级别 | 说明 |
|------|---------|------|
| 后端规则重构（状态机、NPC 调度、投票、银器） | ★★★★★ | 适合深度逻辑推理、多模块导入关系梳理 |
| Prompt 契约分析 & NPC prompt 设计 | ★★★★★ | NPC 对话模板、JSON 行动解析、黑盒信息防护 |
| 复杂 bug 根因定位 | ★★★★★ | 多模块耦合、时序、数据竞争、LLM 并发 |
| 测试编写（pytest） | ★★★★★ | 单元测试、集成测试、模拟 LLM 响应 |
| 大文件拆分（Mixin 提取） | ★★★★☆ | 保持外部 API 不变，逐步提取 |
| 文档编写（技术设计、拆分计划） | ★★★★☆ | 中英文技术文档 |
| 前端 Phaser UI 微调 | ★★☆☆☆ | 不擅长像素级布局和 CSS |
| 浏览器视觉验收 | ★☆☆☆☆ | 不适合运行态视觉验证 |

### Antigravity（CLI Worker）

| 能力 | 胜任级别 | 说明 |
|------|---------|------|
| 前端 UI 布局与微调（Phaser 绘制、CSS、气泡位置、层级） | ★★★★★ | 视觉定位、元素对齐、响应式布局 |
| WebSocket/Socket.IO 协议适配 | ★★★★★ | 前端事件同步、状态报文调试 |
| 后端低风险拆分（纯函数提取、导航、气泡状态、任务系统） | ★★★★☆ | 不涉及深度状态机耦合的模块 |
| 文档整理与重复检测 | ★★★★★ | 文件结构优化、单一事实来源分析 |
| 环境清理脚本（运行态隔离、缓存清理） | ★★★★★ | 跨局清理、日志轮转 |
| 复杂状态机逻辑 | ★★☆☆☆ | 不擅长深度耦合的规则判断 |
| 大模型 prompt 设计 | ★☆☆☆☆ | 不适合 NPC prompt 契约分析 |

---

## Worker 卡住升级流程

当 worker 出现以下情况时，必须**显式**向主 agent 报告，不能静默等待或反复重试：

1. **编译失败**：代码无法通过 `py_compile`，且 5 分钟内不能定位根因。
2. **测试大面积失败**：修改导致相关测试半数以上失败，或同一测试连续 3 次修复仍失败。
3. **超出授权范围**：worker 需要修改未授权的目录（`personas/`、缓存、`game_engine.py` 全部重写）。
4. **循环依赖**：提取的模块与 `game_engine.py` 形成反向 import。
5. **环境故障**：CLI 无法启动、Key 无效、模型服务超时。
6. **任务歧义**：描述不明确，worker 无法确定边界或验收标准。

### 升级报告格式

```text
[卡住报告]
Worker: DeepSeek / Antigravity
任务: <任务简述>
卡住类型: <编号 1-6>
具体现象: <错误信息 / 失败截图 / 日志>
已尝试: <已做的排查步骤及其结果>
需要: <主 agent 需做的具体动作>
```

---

## 产出审查流程

主 agent 审查 worker 产出时，逐项检查以下内容：**不能直接信任 worker 输出**。

### A. 审查步骤

1. **范围检查**：`git diff` 确认只改了授权文件。红线：`personas/` 运行态、缓存、无关模块。
2. **语法检查**：`python -m py_compile <所有受影响文件>` 通过。
3. **回归测试**：运行受影响模块的 pytest，测试结果为 Green。
4. **UI 浏览器验证**（仅前端修改）：`restart.bat` → 浏览器截图确认气泡、层级、布局。
5. **逻辑正确性**：抽查 diff 关键逻辑，确认没有顺手修无关 bug 或引入调试 print。
6. **文档同步**：更新 `BUG_BACKLOG.md` 状态（修复 bug 时）和 `CURRENT_SPRINT.md` 进度（sprint 任务时）。

### B. 产出检查清单

- [ ] 只修改了授权文件（`git diff` 确认），未改 `personas/` 运行态、缓存或无关模块。
- [ ] 新文件已 `git add` 追踪。
- [ ] `python -m py_compile <所有文件>` 通过。
- [ ] **没有**新模块反向 import `game_engine`。
- [ ] 涉及 UI 的改动已通过浏览器截图确认。
- [ ] `git diff` 不含调试 print、注释代码、日志噪声。
- [ ] 相关 pytest 全部 Green。
- [ ] `BUG_BACKLOG.md` 状态已更新（如适用）。
- [ ] `CURRENT_SPRINT.md` 进度已更新（如适用）。

### C. 申请用户介入的检查清单

- [ ] 已在 chat 中清晰陈述阻碍。
- [ ] 已准备好 2-3 个选择项供用户决策。
- [ ] 最新调试事实已记录到 `findings.md` 或 `BUG_BACKLOG.md`。

---

## Worker 任务派发模板

为减少歧义，给 worker 派发任务时建议包含以下字段：

```text
## Task
目标：<一句话说明本次要做什么>
改动范围：<文件列表，用 glob 或具体路径>
禁止改动：<哪些文件不能动，如 personas/*, game_engine.py 全部>
前置验证：<改前需运行的编译/测试命令>
后置验证：<改完后需通过的检查>
验收标准：<可观察或可测的完成条件>
关联 REQ：REQ-XXX（若有相关需求）
```

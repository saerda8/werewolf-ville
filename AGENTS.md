# 项目协作规则

本文件是 `werewolf-ville` 的项目级工作协议，给主 agent、DeepSeek、Antigravity 和其他子 agent 使用。它不是玩法说明，也不是 bug 列表。

---

## 1. 工作总原则

- 每个任务开始前，先读项目结构和相关规则，再做最小必要改动。
- 只修改完成任务必须改的文件；不重排无关代码，不格式化无关文件，不读取 `.env`，除非用户明确要求。
- 如果需要查看大量文件，先说明查看范围。
- 默认只查看与当前任务直接相关的模块，不做全局重构。
- 不把多个不相关目标硬塞进同一条对话。当前任务完成后，如果后续是新方向，转到新线程或对应频道。
- 输出只保留关键结论、修改文件和验证方式。错误只总结关键错误和涉及文件，不贴完整日志，除非用户要求。
- 普通 shell 命令优先使用 `rtk`，减少输出和 token 消耗。MCP 调用、已批准的 Windows 管理命令，或 `rtk` 会干扰结果时，可以直接运行原命令。

---

## 2. 子 Agent 使用规则

- 做任何非平凡任务前，先判断能否交给子 agent。
- 非简单调查或代码修改，要先规划 worker 分配，再自己动手。
- 中等以上工作尽量并行使用可用子 agent，不只限 DeepSeek / Antigravity。
- 不要为了省协调成本让 DeepSeek / Antigravity 闲着。
- 如果任务太小、太危险、必须顺序执行，或不适合委派，可以不派 worker，但要说明原因。
- DeepSeek 指 Claude Code CLI 驱动的 DeepSeek worker，不是游戏内 NPC 模型，也不是直接模型 API。
- Antigravity 指 Antigravity CLI worker，不是桌面版语言服务器。
- Antigravity 不只是前端，也可以做低风险后端、文档和脚本。
- 主 agent 负责拆任务、审查 worker 改动、整合、测试、浏览器验证和最终结论。
- worker 输出和改动默认不可信，必须检查 `git status` 和 `git diff`。

---

## 3. Worker 分工

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
| WebSocket / Socket.IO 协议适配 | ★★★★★ | 前端事件同步、状态报文调试 |
| 后端低风险拆分（纯函数提取、导航、气泡状态、任务系统） | ★★★★☆ | 不涉及深度状态机耦合的模块 |
| 文档整理与重复检测 | ★★★★★ | 文件结构优化、单一事实来源分析 |
| 环境清理脚本（运行态隔离、缓存清理） | ★★★★★ | 跨局清理、日志轮转 |
| 复杂状态机逻辑 | ★★☆☆☆ | 不擅长深度耦合的规则判断 |
| 大模型 prompt 设计 | ★☆☆☆☆ | 不适合 NPC prompt 契约分析 |

---

## 4. Worker 前置检查与禁区

- 派 DeepSeek 前，先确认任务能在允许文件范围内完成，不能把天然需要禁区文件的任务交给它。
- 如果 DeepSeek 因为碰禁区失败，立刻复盘它已有结果，保留可用发现，再派更窄任务，不能让这次 worker 工作白费。
- 派 DeepSeek 前，先做 Claude Code CLI 预检。
- Windows 上 DeepSeek 必须使用原生 `claude.exe`（通过 `CLAUDE_BIN` 配置），不要用 `claude.ps1`，因为 DeepSeek launcher 通过 Node.js `spawn()` 启动 Claude Code。
- 派 Antigravity 前，先跑 Antigravity CLI doctor，确认配置的 `antigravity.exe` 可用。这里使用 CLI worker，不是桌面版语言服务器。
- `personas/` 同时包含静态模板和运行时状态。跑 `Agent` / `WerewolfGameEngine` 测试可能写入 `personas/*/memory.md`、`cognition.md`、`scratch.json`、`memory_index.json`。
- 涉及 `personas/` 时，派 worker 前必须明确策略：允许运行态写入并由主 agent 清理/审查，或者禁止写入并避免运行会触发写入的测试路径。

---

## 5. 浏览器与启动

- 用户说“内置浏览器”时，不要因为没有直接 `browser` 工具就判断不可用。
- 按 Browser plugin skill 的 Node REPL browser-client 方式连接：
  - 从 `C:\Users\XD\.codex\chrome-native-hosts-v2.json` 读取 `browserClientPath`。
  - 在 Node REPL 中导入该 `.mjs` 文件。
  - 调用 `await browserClient.setupBrowserRuntime({globals: globalThis})`。
  - 再调用 `await agent.browsers.get("iab")` 获取内置浏览器。
  - 不要猜 `agent-browser` 这类包名；browser client 是本地 ESM 文件，不是普通 npm 包。
- `restart.bat` 结尾有 `pause`，不能把它当健康检查。
- 启动或重启后，要单独验证 `http://127.0.0.1:5000/` 和端口 5000。
- 每次完成代码修改或修复后，最终回复要报告前端显示的 `版本 X`。
- worker、浏览器连接、重启、测试如果约 30 秒没有有用进展，必须检查状态并说明，不许静默等待。

---

## 6. 上下文与输出纪律

- 长线程不把完整聊天记录当主要记忆。
- 稳定需求读 `USER_REQUIREMENTS_LEDGER.md`。
- 协作规则读 `AGENTS.md`。
- bug 读 `BUG_BACKLOG.md`。
- 聊天原文主要看用户最近 5~10 条，除非用户要求回看更早记录。
- assistant 历史输出只采纳最终结论、确认过的计划和设计，不采纳中间排查噪声、worker 卡住闲聊和原始工具输出摘要。
- 使用 `PROJECT_SKILL_ALLOWLIST.md` 作为本项目默认 skill 子集。除非用户明确要求去 skill 库找，或任务明显超出白名单，否则不要展开无关全局 skill。
- `keep-codex-fast` 原则常开：少输出过程噪声，优先外置项目记忆，不向聊天灌大段日志。它的维护/报告脚本只在 Codex 本地状态需要维护或用户要求时运行。
- `caveman` 可在用户要求简短、上下文压力大或总结 worker / 工具输出时使用。线程变长时，可更积极压缩聊天记录摘要、过程记录、worker 输出和工具结果，只保留可执行事实与决策。不要让压缩影响玩法设计、安全说明和复杂步骤的清晰度。

---

## 7. 不可擅改的项目基石

NPC 行为框架是项目基石：

```text
目标前提 + 观察 + 记忆 -> 思考并计划 -> 行动 -> 记忆沉淀 / 阶段反思
```

未经用户讨论确认，不得擅自修改：

- 观察、思考、计划、行动、记忆、反思链路
- 行动类型体系
- 记忆契约
- 蓝色气泡语义

---

## 8. Worker 卡住升级流程

worker 出现以下情况时，必须显式向主 agent 报告，不能静默等待或反复重试：

1. **编译失败**：代码无法通过 `py_compile`，且 5 分钟内不能定位根因。
2. **测试大面积失败**：修改导致相关测试半数以上失败，或同一测试连续 3 次修复仍失败。
3. **超出授权范围**：worker 需要修改未授权目录，如 `personas/`、缓存，或试图整体重写 `game_engine.py`。
4. **循环依赖**：提取模块与 `game_engine.py` 形成反向 import。
5. **环境故障**：CLI 无法启动、Key 无效、模型服务超时。
6. **任务歧义**：描述不明确，worker 无法确定边界或验收标准。

升级报告格式：

```text
[卡住报告]
Worker: DeepSeek / Antigravity / 其他
任务: <任务简述>
卡住类型: <编号 1-6>
具体现象: <错误信息 / 失败截图 / 日志>
已尝试: <已做的排查步骤及其结果>
需要: <主 agent 需做的具体动作>
```

---

## 9. Worker 产出审查

worker 完成或失败后，主 agent 必须审查，不能直接信任 worker 输出。

审查步骤：

1. **范围检查**：`git diff` 确认只改授权文件。红线：`personas/` 运行态、缓存、无关模块。
2. **语法检查**：`python -m py_compile <所有受影响文件>` 通过。
3. **回归测试**：运行受影响模块的 pytest，测试结果应为 Green。
4. **UI 浏览器验证**：涉及前端改动时，重启服务并用浏览器确认气泡、层级、布局、交互。
5. **逻辑正确性**：抽查关键 diff，确认没有顺手修无关 bug 或引入调试 print。
6. **文档同步**：修 bug 时更新 `BUG_BACKLOG.md`，阶段任务更新 `CURRENT_SPRINT.md`。

检查清单：

- [ ] 只修改授权文件，未改 `personas/` 运行态、缓存或无关模块。
- [ ] 新文件已追踪或明确说明为什么未追踪。
- [ ] `python -m py_compile <所有受影响文件>` 通过。
- [ ] 没有新模块反向 import `game_engine`。
- [ ] 涉及 UI 的改动已通过浏览器截图或实际操作确认。
- [ ] `git diff` 不含调试 print、注释代码、日志噪声。
- [ ] 相关 pytest 全部 Green。
- [ ] 必要文档已同步。

---

## 10. 需要用户介入时

如果需要用户处理权限、环境、账号、API key、外部服务或产品决策，必须清楚说明：

- 当前阻碍是什么。
- 已经尝试了什么。
- 需要用户做什么。
- 如有必要，给 2~3 个选择项。
- 最新调试事实应写入 `findings.md`、`BUG_BACKLOG.md` 或相关项目文档。

---

## 11. Worker 任务派发模板

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

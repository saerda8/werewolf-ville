# 项目决策记录 (DECISIONS.md)

本文件用于记录 **Werewolf Ville** 项目在架构设计、开发流程、协作机制和规则变更上的重大决策。凡是对项目有深远影响的规则修改、工具引入或架构重构，必须在此记录，以便团队及 Worker 保持认知对齐。

---

## 决策历史日志 (Decision History Log)

| 决策 ID | 日期 | 决策标题 | 影响范围 | 状态 | 简述 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DEC-001** | 2026-06-04 | 建立多频道开发工作流 | 项目管理、协作流 | **已执行** | 将长期开发任务解耦为：玩法设计、Bug修复、项目工具与结构三个独立频道。 |
| **DEC-002** | 2026-06-04 | 引入 `.planning/` 目录规范 | 任务追踪、状态恢复 | **已执行** | 为大中型任务引入 `task_plan.md`/`findings.md`/`progress.md` 追踪机制。 |
| **DEC-003** | 2026-06-04 | 规范 Worker 协作与双保底 SOP | 团队协作、审计 | **已执行** | 明确 DeepSeek 与 Antigravity 委派边界，制定审查和用户干预清单。 |
| **DEC-004** | 2026-06-04 | 长期项目状态恢复机制 | 项目连续性 | **已执行** | 规范新会话启动或中断后的状态扫描与信息拉齐 SOP。 |

---

## 决策详情 (Decision Details)

### DEC-001：建立多频道开发工作流
*   **背景**：项目已从原型阶段进入长期迭代。在此之前，玩法设计、样式微调和服务器崩溃等各类杂项混合在一个聊天窗口中，导致上下文膨胀、模型注意力分散、频繁改错和回归。
*   **决策内容**：
    1. 强制将所有工作划分为三大频道：**Gameplay Design (玩法设计)**、**Bug Fixing (Bug 修复)**、**Project Tools/Structure (项目工具与结构)**。
    2. 明确定义每个频道的“入口文件”、“产出”和“准入/准出条件”。具体细则参见 [PROJECT_CHANNELS.md](file:///G:/Trae-Project/werewolf-ville/PROJECT_CHANNELS.md)。
    3. 在 Codex 工具原生支持 Project ID 前，以项目文档形式进行物理隔离与信息同步。

### DEC-002：引入 `.planning/` 目录规范
*   **背景**：大语言模型（LLM）的会话长度有限，容易因为上下文达到上限而重置。当重新开启新会话或交接给新 Agent 时，旧任务的执行细节极易丢失，导致重复定位或方向走偏。
*   **决策内容**：
    1. 在根目录下建立 `.planning/` 文件夹。
    2. 对每个复杂任务，新建对应简称的子文件夹，放置：
       * `task_plan.md`（说明改哪里、不能改哪里、如何回滚）
       * `findings.md`（记录纯客观代码事实、协议格式、堆栈根因）
       * `progress.md`（动态更新任务状态、已测试内容及 TODO 检查清单）
    3. 详细执行规范参见 [.planning/README.md](file:///G:/Trae-Project/werewolf-ville/.planning/README.md)。

### DEC-003：规范 Worker 协作与双保底 SOP
*   **背景**：DeepSeek (Claude Code CLI) 与 Antigravity (CLI Worker) 具有不同的专长。若无协作规范，极易出现任务分发混乱、越权篡改运行态 personas 文件、或因自动化错误反复陷入循环的情况。
*   **决策内容**：
    1. **分工契约**：DeepSeek 负责高逻辑性后端、测试编写；Antigravity 负责前端 UI、样式、Socket 协议和文档治理。
    2. **三步审阅法**：必须进行 `git diff` 越权审查 -> `py_compile` 静态语法检查 -> `pytest` 自动化测试验证。
    3. **用户干预阈值**：一旦遇到 API/环境故障、设计冲突或单步循环超过 3 次，必须立刻挂起并请求用户介入。
    4. 详细 SOP 及检查清单参见 [AGENTS.md](file:///G:/Trae-Project/werewolf-ville/AGENTS.md)。

### DEC-004：长期项目状态恢复机制
*   **背景**：项目长期断开或重开会话后，新进入的 Agent 容易丢失前情提要，盲目读取残留的脏日志或错误文档。
*   **决策内容**：
    1. 新 Agent 进入后，首要任务是**执行基线恢复扫描**，而非直接阅读历史聊天。
    2. 检查顺序为：`PROJECT_CONTINUITY.md` -> `DECISIONS.md` -> `CURRENT_SPRINT.md` -> `.planning/` 活跃任务。
    3. 运行测试套件与浏览器验证确认当前物理环境状态，核对完成后方可开展新工作。

---

## 规则变更流程 (How to Change Rules)

当未来需要修改或废弃某项规则时：
1. **不要直接删除或覆盖历史决策**：在日志表中将对应决策状态置为 `Deprecated` (已废弃) 或 `Superceded by DEC-xxx` (被DEC-xxx替代)。
2. **新增决策条目**：在详情部分新增 `DEC-xxx`，说明新的背景、决策内容以及对旧规则的修改。
3. **通知机制**：在 `CURRENT_SPRINT.md` 中记录本次规则变动，确保下一次 Subagent 或主 Agent 启动时能通过 Sprint 关注到。

---

### DEC-005：真实 Codex 项目线程落地

* **背景**：此前项目只完成了文件化频道，但没有真实 Codex 聊天线程。`create_thread` 工具需要 `projectId`，而列表接口不直接暴露单独的 Project ID。
* **发现**：对本工具而言，项目目标可以使用工作区路径 `G:\Trae-Project\werewolf-ville`。第一次创建时传入显式 model override 导致线程 `systemError`；去掉 model override、使用默认模型后创建成功。
* **决策**：
  1. 固定三个 Codex 项目线程：项目结构与治理、玩法设计、Bug 修复。
  2. 线程 ID 记录在 `PROJECT_CHANNELS.md` 和 `PROJECT_INDEX.md`。
  3. 后续创建项目线程时，优先使用工作区路径作为项目目标，不强行传模型名。
* **状态**：已执行。
# 2026-06-04：第一阶段结构收口完成

- 决定：第一阶段只抽离低风险、已有测试覆盖的职责。
- 已完成：`engine_navigation.py`、`engine_tasks.py`、`engine_bubbles.py`、`engine_dusk.py`。
- 兼容策略：`WerewolfGameEngine` 通过 mixin 保持外部方法入口不变。
- 后续策略：银器、对话、NPC 调度、晨会不继续强拆；在对应 Bug/玩法任务中独立实施。
- 频道规则：结构阶段结束后，具体体验 Bug 转入 Bug 修复线程。

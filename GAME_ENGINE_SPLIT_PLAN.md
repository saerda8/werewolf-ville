# game_engine.py Split Execution Plan

更新时间：2026-06-04

关联需求：本计划执行 `USER_REQUIREMENTS_LEDGER.md` 中的 REQ-012（大文件拆分先于修 bug）、REQ-013（低风险切片逐步拆）、REQ-014（保持 API + 测试）。

## 背景

`game_engine.py` 当前承担了太多职责：状态机、NPC 调度、移动寻路、晨会、气泡、投票、监狱、银器、夜晚、日志、UI 序列化等都集中在同一个文件里。

用户已经明确要求：先拆大文件，再继续大规模修 bug。原因是如果先修 bug 再拆文件，拆分过程容易把已修好的问题重新改坏。

本计划吸收 `docs/deepseek-engine-split-plan.md` 和 `docs/antigravity-project-channels-plan.md` 的建议，但以本文件作为执行入口。

## 原则

1. 保持 `WerewolfGameEngine` 对外 API 不变。
2. 每次只拆一个低风险切片。
3. 每个切片都必须能单独编译、测试、提交。
4. 拆分期间不顺手修体验 bug，除非测试或导入关系必须处理。
5. 新模块不反向 import `game_engine.py`，避免循环依赖。
6. 优先用 mixin 或纯函数迁移，减少大范围调用点改动。
7. 主 agent 必须审查 worker 修改，不直接信任 worker 输出。

## 目标结构

建议逐步形成以下模块：

- `engine_navigation.py`：地图、碰撞、路径、移动、邻近物件。
- `engine_bubbles.py`：聊天气泡、思考/行动气泡、过期和状态序列化。
- `engine_dusk_vote.py`：黄昏讨论入口、NPC 投票、投票结果、监狱流程。
- `engine_tasks.py`：警长每日任务、深挖次数、任务完成判定。
- `engine_silver.py`：银器工具、银饰、银子弹、小刀、银器胜负判定。
- `engine_conversation.py`：警长问话、NPC 对话、深挖、对话中断、对话记录。
- `engine_scheduler.py`：NPC 日程、观察、思考/计划、行动调度、LLM job 轮询。
- `engine_gathering.py`：开局晨会、尸体发现、第一轮发言、散场、安葬流程。

文件名使用 `engine_*.py`，避免和已有模块或未来包名冲突。

## 推荐切片顺序

### Slice 1：抽出导航纯函数和移动辅助

目标：

- 把地图碰撞、路径搜索、邻近可走格等低层函数迁到 `engine_navigation.py`。
- 保留 `WerewolfGameEngine` 中的调用方法名，必要时通过 mixin 暴露。

原因：

- 这部分是很多 bug 的根源，但大多是相对独立的算法和工具函数。
- 先抽出它，可以为后续修“穿墙、绕路、重叠、货架站位”打基础。

验证：

- `python -m py_compile game_engine.py engine_navigation.py`
- `python -m pytest tests/test_engine_foundation.py -x --tb=short -q`

### Slice 2：抽出气泡状态

目标：

- 把气泡创建、过期、清理、状态导出迁到 `engine_bubbles.py`。
- 不改变前端协议字段。

原因：

- 气泡 bug 是当前最高频体验问题之一。
- 先拆清职责，再修“克罗蓝泡、重叠、穿 UI、长条压缩、计时不消失”。

验证：

- `python -m py_compile game_engine.py engine_bubbles.py`
- `python -m pytest tests/test_ui_bubble_layout.py -x --tb=short -q`

### Slice 3：抽出任务系统

目标：

- 把警长每日任务、每日深挖次数、任务完成判定迁到 `engine_tasks.py`。

原因：

- UI 右下角任务、黄昏按钮可用状态、每日深挖次数都依赖它。
- 独立后更容易修“任务放错区域、深挖次数不扣、任务文案错误”。

验证：

- `python -m py_compile game_engine.py engine_tasks.py`
- `python -m pytest tests/test_engine_foundation.py -x --tb=short -q`

### Slice 4：抽出黄昏投票与监狱

目标：

- 把黄昏讨论入口、投票生成、投票历史、玩家最终决定、关押监狱迁到 `engine_dusk_vote.py`。

原因：

- 投票流程需要按“讨论 -> 玩家发言 -> 投票 -> 结果 -> 玩家决定 -> 遗言 -> 关押”重做。
- 独立模块后避免和白天 NPC 调度混杂。

验证：

- `python -m py_compile game_engine.py engine_dusk_vote.py`
- `python -m pytest tests/test_vote_flow.py -x --tb=short -q`

### Slice 5：抽出银器系统

目标：

- 把工具、银饰、银子弹、银刀和银器击杀逻辑迁到 `engine_silver.py`。

原因：

- 银器是中期玩法核心，和每日任务、狼人干扰、线索推理相关。
- 需要独立测试，不应继续埋在主状态机里。

验证：

- `python -m py_compile game_engine.py engine_silver.py`
- `python -m pytest tests/test_engine_foundation.py -x --tb=short -q`

### Slice 6：抽出警长/NPC 对话

目标：

- 把普通交谈、深挖、NPC 主动找警长、对话记录、中断、优先级迁到 `engine_conversation.py`。

原因：

- 当前“警长问话不显示、NPC 不回复、远距离继续聊天、详情无对话历史”都属于对话职责。
- 这个模块风险较高，必须在前面低风险模块拆完后做。

验证：

- `python -m py_compile game_engine.py engine_conversation.py`
- `python -m pytest tests/test_llm_priority.py tests/test_engine_foundation.py -x --tb=short -q`

### Slice 7：抽出 NPC 调度

目标：

- 把 NPC 观察、思考/计划、行动、LLM job 轮询、超时保底迁到 `engine_scheduler.py`。

原因：

- 这是 NPC 智能性的核心，也是最容易牵扯并发和模型超时的区域。
- 必须在对话优先级和气泡系统边界清楚后做。

验证：

- `python -m py_compile game_engine.py engine_scheduler.py`
- `python -m pytest tests/test_llm_priority.py tests/test_prompt_boundaries.py -x --tb=short -q`

### Slice 8：抽出晨会/开局集合

目标：

- 把晨会、克罗开场、第一轮发言、第二轮散场、尸体安葬迁到 `engine_gathering.py`。

原因：

- 晨会逻辑和 UI 表现强耦合，且用户已经多次指出开局节奏、发言顺序、NPC 踩人、克罗台词等问题。
- 这是高风险切片，应最后做。

验证：

- `python -m py_compile game_engine.py engine_gathering.py`
- `python -m pytest tests/test_gathering_timeout.py tests/test_prompt_boundaries.py -x --tb=short -q`

## Worker 分工

每个切片开始前：

1. 主 agent 写清边界、禁止事项和验证命令。
2. DeepSeek 优先负责后端逻辑抽取、测试补充、状态机风险审查。
3. Antigravity 可负责前端协议影响审查、文档同步、简单后端切片或浏览器验证脚本。
4. 主 agent 检查 `git diff`，确认没有越权改动、没有改 `personas/` runtime 文件、没有顺手修无关 bug。

## 每个切片的提交要求

每个切片必须单独提交，提交前运行：

```bash
python -m py_compile agent.py game_engine.py llm.py ui/app.py
```

如果新增模块，还要额外编译新增模块。

推荐提交格式：

```text
refactor(engine): extract navigation helpers
refactor(engine): extract bubble state handling
refactor(engine): extract daily task state
```

## 拆分后再修 bug 的顺序

拆完 Slice 1 和 Slice 2 后，可以优先修这些当前高频问题：

1. 克罗头顶蓝色气泡必须彻底消失。
2. 气泡不能重叠、不能穿 UI、不能被边缘挤成长条。
3. NPC 名字、模型名和地点标签层级正确。
4. NPC 与物件/人交互时停在可交互格，不重叠。
5. 警长对话优先级，NPC 必须及时回复。

拆完 Slice 3 和 Slice 4 后，再修：

1. 右下角任务区域。
2. 每日 3 次深挖。
3. 黄昏讨论、玩家发言、投票结果、关押流程。

拆完 Slice 6 和 Slice 7 后，再修：

1. NPC 长期原地思考。
2. NPC 远距离继续聊天。
3. 模型超时保底日志。
4. NPC 记忆和详情记录。
5. NPC 主动亮灯泡和主动找警长汇报。

## 暂停条件

出现以下情况必须暂停当前切片，先回到 Git 检查点：

1. 语法检查失败且 10 分钟内不能定位。
2. 相关测试大面积失败。
3. 需要同时修改三个以上高耦合模块才能继续。
4. worker 改动超出授权范围。
5. 前端状态协议被改动但没有同步 UI。

## 2026-06-04 第一阶段执行结果

第一阶段低风险结构收口已经完成并提交：

| 模块 | 已抽离职责 | 提交 |
| --- | --- | --- |
| `engine_navigation.py` | 碰撞矩阵、场景矩阵、附近物件、BFS 寻路纯工具 | `1771da9` |
| `engine_tasks.py` | 警长每日任务状态构建 | `8cb5284` |
| `engine_bubbles.py` | 引擎侧气泡计时、过期清理、思考摘要 | `fe5fc1c` |
| `engine_dusk.py` | 黄昏阶段、NPC 投票、投票历史、拘留与监狱 | `743e00f` |

`WerewolfGameEngine` 对外方法名保持不变，通过 mixin 继续暴露原 API。

后续高风险拆分（银器、对话、调度、晨会）不在第一阶段继续强拆。它们应在对应 Bug/玩法任务启动时，以独立切片实施和验证，避免为拆分而拆分。

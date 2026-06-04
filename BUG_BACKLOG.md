# Werewolf Ville Bug Backlog

更新日期：2026-06-05

## 使用规则

所有 bug 都必须记录在这里，不能只留在聊天里。每个 bug 需要包含：

```text
ID:
标题:
频道: [玩法 / Bug 修改 / 项目工具与结构]
严重度: Blocker / Major / Minor / External
关联需求: REQ-XXX（若无则填"无"）
复现步骤:
实际表现:
期望表现:
疑似影响文件:
根因:
修复方案:
验证方式:
回归测试: 说明新增或依赖的测试文件和断言
首次发现: 日期 或 Git 提交（可选）
引入版本: 首次被引入的 Git 提交（可选）
回归频率: 每次必现 / 高概率 / 偶发 / 难以判断
验收状态: Open / In Progress / Fixed / Verified / Deferred / Closed
关闭门禁:
  1. 对应回归测试通过。
  2. `python -m py_compile agent.py game_engine.py llm.py ui/app.py` 通过。
  3. 浏览器端（涉及 UI 时）截图确认修复。
  4. 本记录状态更新为 Closed。
相关提交:
```

## 当前待整理 Bug

### BUG-001：克罗头顶仍可能出现蓝色思考/行动气泡

严重度：Major
关联需求：REQ-100
回归测试：`tests/test_ui_bubble_layout.py`
回归频率：每次必现
状态：Closed
验收状态：Closed

期望：克罗由玩家控制，不显示任何蓝色思考/行动气泡；只在需要时显示白色说话气泡。

验证方式：启动游戏，点击移动克罗，观察克罗头顶不出现蓝色气泡；相关 UI 测试需覆盖。

根因：该条目记录的是结构拆分前的历史体验问题，第一阶段结构收口后 backlog 状态未同步。当前后端 `get_status()` 已清空克罗的思考、行动、路径和运行态字段；前端不为克罗创建 thought bubble，并在渲染层继续抑制遗留节点。

修复方案：无需新增生产代码；以现有后端状态隔离和前端多层抑制为最终修复，补做自动化与浏览器验收后关闭滞后条目。

验证结果（2026-06-05）：
- IAB 开始游戏后点击地图移动克罗，DOM 中 Crow thought bubble 节点数量为 0，可见气泡中不存在克罗蓝色气泡。
- `tests/test_ui_bubble_layout.py` 全部通过。
- `tests/test_engine_foundation.py::test_crow_public_status_never_exposes_blue_bubble_state` 通过。
- `python -m py_compile agent.py game_engine.py llm.py ui/app.py engine_bubbles.py` 通过。

关闭门禁：
- [x] 对应回归测试通过。
- [x] 编译门禁通过。
- [x] IAB 截图与 DOM 检查确认修复。
- [x] 根因与关联需求已记录。

相关提交：`fe5fc1c`（气泡状态结构收口）；本次验证收口提交。

### BUG-002：气泡仍可能重叠、穿透 UI 或在边缘被挤成长条

严重度：Major
关联需求：REQ-105, REQ-107, REQ-108, REQ-109
回归测试：`tests/test_ui_bubble_layout.py`
回归频率：高概率
状态：Closed
验收状态：Closed

期望：气泡层只覆盖游戏区域，不穿右侧 UI；边缘处由容器裁切，不动态挤压；近距离对话时左右分布，不重叠。

验证方式：浏览器截图 + `tests/test_ui_bubble_layout.py`。

根因：该条目记录的是结构拆分前的历史体验问题，现有实现已具备固定气泡宽度、游戏区域裁切、对话左右分布和碰撞避让，但 backlog 状态未随实现与测试同步。

修复方案：无需新增生产代码；保留现有 `#bubble-layer` 边界裁切和气泡碰撞解析逻辑，以自动化测试和 IAB 实际布局验收确认关闭。

验证结果（2026-06-05）：
- IAB 中 `#bubble-layer` 实测边界为 `x=0, width=960, right=960`，停在右侧 UI 前。
- 实际出现的 NPC 白色发言气泡与蓝色行动气泡上下分层显示，未重叠或挤成长条。
- `tests/test_ui_bubble_layout.py` 全部通过。
- `python -m py_compile agent.py game_engine.py llm.py ui/app.py engine_bubbles.py` 通过。

关闭门禁：
- [x] 对应回归测试通过。
- [x] 编译门禁通过。
- [x] IAB 截图与 DOM 边界检查确认修复。
- [x] 根因与关联需求已记录。

相关提交：`fe5fc1c`（气泡状态结构收口）；本次验证收口提交。

### BUG-003：克罗找 NPC 对话时，NPC 回复优先级不稳定

严重度：Major
关联需求：REQ-067, REQ-068, REQ-077
回归测试：`tests/test_llm_priority.py`
回归频率：高概率
状态：Open
验收状态：Open

期望：玩家发起的克罗对话应打断 NPC 后台行为，NPC 优先回复，其他 NPC 不插入。

验证方式：点击右侧交谈/深挖，确认克罗到达后立即开口，NPC 回复期间其他 NPC 不围过来。

### BUG-004：黄昏投票流程缺少玩家发言前置讨论环节

严重度：Major
关联需求：REQ-040, REQ-041
回归测试：`tests/test_vote_flow.py`
回归频率：每次必现
状态：Open
验收状态：Open

期望：黄昏先讨论，NPC 发言后玩家/克罗打字发言，之后才投票。

验证方式：端到端手测 + vote flow 测试。

### BUG-005：新游戏可能残留旧局 persona 运行态记忆

严重度：Major
关联需求：REQ-122
回归测试：需新增跨局隔离测试
回归频率：每次必现
状态：Open
验收状态：Open

期望：新游戏前清空单局运行态，静态角色模板不被覆盖。

验证方式：连续开始两局，确认记忆、对话历史、行动状态不串局。

### BUG-006：林梅和克劳斯仍可能在大学同一房间挤在一起

严重度：Minor
关联需求：REQ-127
回归测试：需新增锚点分配测试
回归频率：偶发
状态：Open
验收状态：Open

期望：林梅使用图书馆/书架锚点，克劳斯使用教室/学生座位锚点。

验证方式：开始游戏散场后观察两人目标与坐标。

### BUG-007：右下角可能出现未要求的杂项日志块

严重度：Minor
关联需求：REQ-086
回归测试：浏览器布局检查
回归频率：每次必现
状态：Open
验收状态：Open

期望：右下角只服务警长任务/关键玩法 UI，不放无需求的长文本日志。

验证方式：浏览器检查右侧布局。

## 已知外部问题

### EXT-001：模型供应商超时、限流或余额不足

严重度：External
关联需求：REQ-073, REQ-118, REQ-119
回归测试：`tests/test_llm_priority.py`
回归频率：偶发
状态：Deferred
验收状态：Deferred

说明：这类问题不一定能通过代码修复。代码侧应保证超时保底、优先级队列和日志清晰。

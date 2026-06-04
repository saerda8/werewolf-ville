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
状态：Closed
验收状态：Closed

期望：玩家发起的克罗对话应打断 NPC 后台行为，NPC 优先回复，其他 NPC 不插入。

验证方式：点击右侧交谈/深挖，确认克罗到达后立即开口，NPC 回复期间其他 NPC 不围过来。

根因：后端只在 `detective_chat()` 真正开始后锁定目标 NPC；克罗移动接近目标期间没有服务端 reservation，目标仍可能被日程调度或 NPC-NPC 对话抢走。

修复方案：新增克罗待对话目标 reservation，`move_detective_to_agent()` 成功规划路径时立即占用目标；NPC 调度、NPC-NPC 对话和 NPC 主动接近均检查该 reservation；手动移动、新局、对话开始/结束时清理 reservation。

验证结果（2026-06-05）：
- 新增 `tests/test_llm_priority.py::test_detective_move_to_agent_reserves_target_from_npc_chat`，覆盖克罗接近目标期间 NPC 不被后台对话抢占。
- `tests/test_llm_priority.py` 通过。
- 全量回归 `python -m pytest tests -q` 通过：349 passed；编译门禁通过。

关闭门禁：
- [x] 对应回归测试通过。
- [x] 编译门禁通过。
- [x] 根因与关联需求已记录。

相关提交：本次批量修复提交。

### BUG-004：黄昏投票流程缺少玩家发言前置讨论环节

严重度：Major
关联需求：REQ-040, REQ-041
回归测试：`tests/test_vote_flow.py`
回归频率：每次必现
状态：Closed
验收状态：Closed

期望：黄昏先讨论，NPC 发言后玩家/克罗打字发言，之后才投票。

验证方式：端到端手测 + vote flow 测试。

根因：`_transition_to_dusk()` 进入黄昏后立即生成 NPC 投票并打开投票 UI，没有讨论状态，也没有克罗发言解锁投票的服务端门禁。

修复方案：黄昏转换先进入 `dusk_discussion_active`，生成 NPC 讨论发言并等待克罗提交发言；新增 `submit_dusk_statement()`，克罗发言后才生成 NPC 投票并打开投票；前端增加黄昏发言面板、HTTP 和 Socket.IO 提交入口，投票面板只在 vote summary active 时显示。

验证结果（2026-06-05）：
- 新增 `tests/test_vote_flow.py::test_transition_to_dusk_starts_discussion_before_votes`。
- 新增 `tests/test_vote_flow.py::test_crow_dusk_statement_unlocks_npc_votes`。
- `tests/test_vote_flow.py` 通过。
- UI 静态回归确认黄昏讨论面板存在、投票按钮文案已调整。
- 全量回归 `python -m pytest tests -q` 通过：349 passed；编译门禁通过。

关闭门禁：
- [x] 对应回归测试通过。
- [x] 编译门禁通过。
- [x] UI DOM 检查确认新版入口存在。
- [x] 根因与关联需求已记录。

相关提交：本次批量修复提交。

### BUG-005：新游戏可能残留旧局 persona 运行态记忆

严重度：Major
关联需求：REQ-122
回归测试：`tests/test_daytime_npc_behavior.py`, `tests/test_gathering_timeout.py`
回归频率：每次必现
状态：Closed
验收状态：Closed

期望：新游戏前清空单局运行态，静态角色模板不被覆盖。

验证方式：连续开始两局，确认记忆、对话历史、行动状态不串局。

根因：该条目记录的是跨局隔离风险；当前实现已经在 `new_game()` 和 `Agent.init_files()` 中清理运行态记忆、临时认知、对话历史、行动状态和 scratch 文件，backlog 状态未同步。

修复方案：不新增生产代码；以现有运行态清理逻辑和跨局隔离回归测试作为关闭依据，修复过程中未写入或保留 `personas/` 运行态文件。

验证结果（2026-06-05）：
- `tests/test_daytime_npc_behavior.py::test_new_game_resets_runtime_memory_and_agent_state` 通过。
- `tests/test_gathering_timeout.py::test_agent_init_files_clears_runtime_state` 通过。
- 全量回归 `python -m pytest tests -q` 通过：349 passed；编译门禁通过。

关闭门禁：
- [x] 对应回归测试通过。
- [x] 编译门禁通过。
- [x] `personas/` 运行态文件未被本次修复污染。
- [x] 根因与关联需求已记录。

相关提交：本次批量修复提交。

### BUG-006：林梅和克劳斯仍可能在大学同一房间挤在一起

严重度：Minor
关联需求：REQ-127
回归测试：`tests/test_engine_foundation.py`
回归频率：偶发
状态：Closed
验收状态：Closed

期望：林梅使用图书馆/书架锚点，克劳斯使用教室/学生座位锚点。

验证方式：开始游戏散场后观察两人目标与坐标。

根因：该条目记录的是大学锚点分配风险；当前角色默认和位置锚点已经将林梅/克劳斯分流，backlog 状态未同步。

修复方案：不新增生产代码；用现有锚点默认和模型对象覆盖测试确认林梅、克劳斯不会落到同一大学房间。

验证结果（2026-06-05）：
- `tests/test_engine_foundation.py::test_mei_lin_and_klaus_have_separate_college_defaults` 通过。
- `tests/test_engine_foundation.py::test_college_role_defaults_override_model_object` 通过。
- 全量回归 `python -m pytest tests -q` 通过：349 passed；编译门禁通过。

关闭门禁：
- [x] 对应回归测试通过。
- [x] 编译门禁通过。
- [x] 根因与关联需求已记录。

相关提交：本次批量修复提交。

### BUG-007：右下角可能出现未要求的杂项日志块

严重度：Minor
关联需求：REQ-086
回归测试：`tests/test_ui_bubble_layout.py`
回归频率：每次必现
状态：Closed
验收状态：Closed

期望：右下角只服务警长任务/关键玩法 UI，不放无需求的长文本日志。

验证方式：浏览器检查右侧布局。

根因：前端模板仍保留底部 agent log 面板、CSS 和日志更新脚本，导致右下角/底部出现未要求的长文本日志区域，并挤占游戏和气泡层空间。

修复方案：移除底部 log panel DOM、CSS、resize 脚本和 `updateLog()` 更新逻辑；保留右侧警长任务面板和关键玩法 UI；游戏容器与气泡层恢复到底部 0。

验证结果（2026-06-05）：
- 新增 `tests/test_ui_bubble_layout.py::test_frontend_does_not_render_agent_log_panel`。
- 新增 `tests/test_ui_bubble_layout.py::test_bottom_right_keeps_tasks_without_extra_log_block`。
- `tests/test_ui_bubble_layout.py` 通过。
- 5000 最新服务 HTTP 验证新版模板：`HasDuskStatement=True`, `HasLogPanel=False`, `GameBottom0=True`。
- IAB Playwright DOM 验证：`hasDuskStatementPanel=true`, `hasLogPanel=false`, `hasTaskPanel=true`, `gameBottom=0px`, `bubbleBottom=0px`。

关闭门禁：
- [x] 对应回归测试通过。
- [x] 编译门禁通过。
- [x] UI DOM 检查确认多余日志块已移除。
- [x] 根因与关联需求已记录。

相关提交：本次批量修复提交。

### BUG-008：首页缺失版本号且智能体日志无法显示

严重度：Major
关联需求：REQ-086, REQ-011
回归测试：`tests/test_ui_bubble_layout.py`
回归频率：每次必现
状态：Closed
验收状态：Closed

期望：首页左上角可见前端版本号。恢复一个明确的智能体日志面板，渲染后端 status.recent_log，但放在右侧边栏底部，不影响游戏区域。

验证方式：运行 `pytest tests/test_ui_bubble_layout.py -q`

根因：BUG-007 修复时将 #log-panel 和 updateLog() 完全移除，导致智能体日志在前端无处呈现。且前端版本号未在界面上体现。

修复方案：
  1. 在首页（#start-overlay）左上角添加前端版本号 div，由 Flask 注入当前 Git 短哈希，最终显示为 `v<commit>`。
  2. 在 #side-panel 底部恢复 #log-panel 面板与 updateLog() 渲染逻辑，只读取后端 status.recent_log 进行显示，不影响左侧游戏区域的 bottom 布局，并对日志文本做 HTML 转义。
  3. 在 tests/test_ui_bubble_layout.py 中更新对应断言。

验证结果（2026-06-05）：
- `tests/test_ui_bubble_layout.py` 全部通过。
- `python -m py_compile ui/app.py` 通过。
- 全量回归 `python -m pytest tests -q` 通过：351 passed。

关闭门禁：
- [x] 对应回归测试通过。
- [x] 编译门禁通过。
- [x] 根因与关联需求已记录。

相关提交：本次修复提交。

### BUG-009：警长案情说明句间缺少可见停顿

严重度：Minor
关联需求：REQ-011
回归测试：`tests/test_gathering_timeout.py`
回归频率：每次必现
状态：Closed
验收状态：Closed

期望：警长克罗案情说明每说完一句后，按 `crow_intro_line_delay_seconds` 出现可见停顿，再显示下一句。

验证方式：自动化测试验证第一句和第二句之间存在空白气泡间隔。

根因：当前实现是“显示一句 -> sleep(delay) -> 直接替换下一句”，只有显示时长，没有清空气泡后的句间停顿。

修复方案：在 Crow 开场说明线程中增加 `_pause_after_intro_line()`，每句显示后先等待配置时长，再清空 Crow 气泡和当前发言，再等待配置时长后发布下一句。

验证结果（2026-06-05）：
- 新增 `tests/test_gathering_timeout.py::test_crow_intro_has_visible_pause_between_lines`。
- `tests/test_gathering_timeout.py::test_crow_intro_line_delay_waits_after_estimated_speech` 通过。
- `tests/test_gathering_timeout.py::test_crow_intro_line_delay_reads_config` 通过。
- 全量回归 `python -m pytest tests -q` 通过：351 passed。

关闭门禁：
- [x] 对应回归测试通过。
- [x] 编译门禁通过。
- [x] 根因与关联需求已记录。

相关提交：本次修复提交。

## 已知外部问题

### EXT-001：模型供应商超时、限流或余额不足

严重度：External
关联需求：REQ-073, REQ-118, REQ-119
回归测试：`tests/test_llm_priority.py`
回归频率：偶发
状态：Deferred
验收状态：Deferred

说明：这类问题不一定能通过代码修复。代码侧应保证超时保底、优先级队列和日志清晰。

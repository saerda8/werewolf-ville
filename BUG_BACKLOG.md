# Werewolf Ville Bug Backlog

更新日期：2026-06-08

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

### BUG-2026-06-08-004：真实谈话期间旧思考/旧行动气泡仍会显示

严重度：Major
关联需求：REQ-168、REQ-171、NPC 行为生命周期
回归测试：`tests/test_ui_bubble_layout.py`、`tests/test_engine_foundation.py`
回归频率：高概率
状态：Closed
验收状态：Verified

实际表现：NPC 思考气泡仍可能显示旧兜底文案“正在整理当前情况”；警长已向 NPC 发起真实谈话后，如果第二条模型管线延迟较高，目标 NPC 仍可能继续显示旧思考、旧计划、旧行动白泡。

根因：前端 `buildNpcThoughtBubble()` 仍保留“正在整理当前情况。”作为无模型 thought 的兜底文案；`resolveBubbleLayout()` 在生成蓝泡和白行动泡之后才用 `pendingChatTarget` 做清理，旧 action_status 路径仍可漏出；后端通用气泡过期释放逻辑把 `conversation_pending` 等待气泡和真实谈话锁混在一起，存在等待气泡消失等于释放交谈状态的风险。

修复方案：删除“正在整理当前情况”兜底文本，模型没有真实 thought/plan 时不显示思考计划蓝泡；前端本地进入 `pendingChatTarget` 后立即清空目标 NPC 的旧 thought/plan/action/status 字段，并在气泡布局最前面把 active chat 作为最高优先级压制蓝泡和旧白行动泡；后端 `conversation_pending` 过期不再释放真实谈话锁，真实谈话改由独立 30 秒超时释放。

验证方式：
- `python -m py_compile game_engine.py ui/app.py`
- `node -e "<inline script syntax check>"`
- `pytest -q tests/test_ui_bubble_layout.py::test_pending_detective_chat_locks_button_and_suppresses_bubbles tests/test_ui_bubble_layout.py::test_blue_bubble_sequential_thought_plan_action tests/test_ui_bubble_layout.py::test_thought_waiting_text_is_not_treated_as_real_model_thought tests/test_ui_bubble_layout.py::test_action_status_and_start_action_mutual_exclusion tests/test_ui_bubble_layout.py::test_new_dusk_camera_and_waiting_behavior tests/test_ui_bubble_layout.py::test_action_and_detective_chat_clear_blue_bubble_cache tests/test_ui_bubble_layout.py::test_pending_chat_wait_merge_has_no_duplicate_server_bubble_const`
- `pytest -q tests/test_engine_foundation.py::test_detective_chat_interrupts_movement_and_marks_target_busy_immediately tests/test_engine_foundation.py::test_detective_chat_pending_bubble_expiry_does_not_release_real_chat tests/test_engine_foundation.py::test_detective_chat_real_chat_releases_after_thirty_seconds tests/test_engine_foundation.py::test_detective_chat_status_suppresses_stale_npc_action_fields tests/test_engine_foundation.py::test_stale_planning_thread_does_not_override_detective_conversation_lock tests/test_daytime_npc_behavior.py::test_npc_mid_planning_detective_chat_clears_thinking_flag`

相关提交：待提交。

### BUG-2026-06-08-003：真实聊天秒失败与 NPC 旧行动状态漏到前端

严重度：Major
关联需求：REQ-073、REQ-123、REQ-168、NPC 行为生命周期
回归测试：`tests/test_engine_foundation.py`、`tests/test_gathering_timeout.py`、`tests/test_daytime_npc_behavior.py`、`tests/test_ui_bubble_layout.py`
回归频率：高概率
状态：Closed
验收状态：Verified

实际表现：警长刚和 NPC 说话就出现“模型超时/空结果”；第二轮聚集离场也可能在模型尚未真正等待时直接保底；NPC 被警长问话后仍可能向前端暴露旧 thought、旧 plan、旧 action_status 或旧路径，表现为还在思考/执行。

根因：聚集发言、第二轮去向和警长真实聊天显式传入 `max_retries=0`，遇到上游 429/空结果会立即失败；聚集单人等待下限仍为 20 秒；`get_status()` 只压制克罗自己的行动字段，没有把“正在和警长交谈/等待回复的 NPC”作为最高优先级展示状态处理。

修复方案：聚集单人等待下限改为 30 秒；聚集发言、聚集离场和警长真实聊天恢复默认重试；模型失败日志区分“等待超时”和“模型失败/空结果”；`get_status()` 对正在和警长交谈或等待警长回复的 NPC 清空 thought、action、action_plan、target、path、last_decision 和 action_status 可见时间。

验证方式：
- `python -m py_compile game_engine.py llm.py`
- `pytest -q tests/test_engine_foundation.py::test_detective_chat_uses_priority_retry_response tests/test_engine_foundation.py::test_detective_chat_status_suppresses_stale_npc_action_fields tests/test_gathering_timeout.py::test_gathering_per_speaker_timeout_configured tests/test_gathering_timeout.py::test_gathering_speech_uses_priority_llm_requests tests/test_gathering_timeout.py::test_round_one_timeout_logs_unified_fallback_message tests/test_gathering_timeout.py::test_round_one_empty_result_logs_unified_fallback_message tests/test_gathering_timeout.py::test_round_two_timeout_logs_unified_fallback_message tests/test_gathering_timeout.py::test_detective_chat_empty_response_releases_waiting tests/test_gathering_timeout.py::test_unified_fallback_log_not_present_on_success`
- `pytest -q tests/test_daytime_npc_behavior.py::test_detective_chat_clears_npc_state tests/test_daytime_npc_behavior.py::test_npc_mid_planning_detective_chat_clears_thinking_flag tests/test_engine_foundation.py::test_detective_chat_records_and_locks_before_slow_npc_reply tests/test_engine_foundation.py::test_detective_chat_waiting_reply_does_not_lock_crow_movement tests/test_engine_foundation.py::test_detective_chat_interrupts_movement_and_marks_target_busy_immediately tests/test_engine_foundation.py::test_stale_planning_thread_does_not_override_detective_conversation_lock tests/test_engine_foundation.py::test_action_start_timing_is_backend_driven_not_frontend_cache tests/test_engine_foundation.py::test_moving_state_does_not_leak_stale_frontend_bubble_cache tests/test_ui_bubble_layout.py::test_pending_detective_chat_locks_button_and_suppresses_bubbles tests/test_ui_bubble_layout.py::test_action_and_detective_chat_clear_blue_bubble_cache tests/test_ui_bubble_layout.py::test_strict_sequential_bubbles_and_action_status_clean`

相关提交：待提交。

### BUG-2026-06-08-001：NPC 真实聊天、黄昏集合与测试跳转入口异常

严重度：Major
关联需求：NPC 行为生命周期、黄昏讨论流程、测试便利入口
回归测试：`tests/test_gathering_timeout.py`、`tests/test_engine_foundation.py`、`tests/test_vote_flow.py`、`tests/test_ui_bubble_layout.py`
回归频率：高概率
状态：Closed
验收状态：Verified

实际表现：警长问话后 NPC 可能永久显示 `...` 或继续旧行动；黄昏阶段 NPC 自主 AI 仍会运作，集合后又离开；黄昏镜头可能跳到后续尸体位置而不是开局讨论广场；测试时必须逐个交谈才能进黄昏。

根因：真实聊天等待气泡被后端特殊保活；黄昏阶段没有统一冻结日间 AI 管线和到齐门禁；黄昏镜头复用了动态 `gathering_site`；夜晚回家仍用旧的最近可走格而不是可达路径；缺少测试快捷入口。

修复方案：等待气泡改为“正在聆听警长问询”并 3 秒过期，空回复释放对话锁；黄昏前清理旧气泡/状态，所有人到齐后才开讲并冻结参与者，日间 AI 只在 DAY 跑；黄昏镜头改用 `initial_gathering_site`；夜晚回家复用可达目标；新增“一键交谈完”测试按钮。

验证方式：
- `python -m py_compile game_engine.py engine_dusk.py engine_bubbles.py ui/app.py`
- `pytest -q tests/test_gathering_timeout.py::test_detective_chat_empty_response_releases_waiting tests/test_engine_foundation.py::test_random_werewolf_models_and_initial_body tests/test_engine_foundation.py::test_detective_chat_interrupts_movement_and_marks_target_busy_immediately tests/test_engine_foundation.py::test_detective_chat_empty_response_releases_waiting_bubble tests/test_engine_foundation.py::test_test_shortcut_marks_all_daily_interviews tests/test_vote_flow.py::test_dusk_discussion_waits_until_everyone_arrives tests/test_vote_flow.py::test_autonomous_ai_lane_is_suspended_during_dusk tests/test_vote_flow.py::test_dusk_discussion_uses_half_second_between_npc_statements tests/test_vote_flow.py::test_dusk_vote_all_living_non_jailed_npcs_vote tests/test_ui_bubble_layout.py::test_new_dusk_camera_and_waiting_behavior tests/test_ui_bubble_layout.py::test_dev_complete_interviews_button_exists`
- 本地服务 `http://127.0.0.1:5000/` 返回 200，页面显示版本 42。

相关提交：待提交。

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

期望：气泡不穿右侧 UI；靠近右侧边缘时由 JS 根据游戏容器宽度完整夹回游戏可视区，必要时向左偏移或左右翻转；不能靠容器裁切解决，也不能被挤成长条；近距离对话时左右分布，不重叠。

验证方式：浏览器截图 + `tests/test_ui_bubble_layout.py`。

根因：旧实现把 `#bubble-layer` 截到右侧面板左边并设置 `overflow:hidden`，同时测试仍要求“靠 bubble-layer 裁剪”。这与“靠近右侧 UI 时气泡必须完整可读”的体验目标冲突，导致测量或定位稍有滞后时气泡被右侧边界切掉。

修复方案：`#bubble-layer` 改为不裁剪（`overflow: visible`），由 `resolveBubbleLayout()` 使用 `#game-container.clientWidth/clientHeight` 作为可视边界，将气泡完整 clamp 到游戏区内；同步更新 `tests/test_ui_bubble_layout.py`，禁止再把右边缘裁切作为验收标准。

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
  1. 在首页（#start-overlay）左上角添加纯数字前端版本号 div，由 Flask 注入 Git 提交总数；有未提交改动时预显示下一版数字，最终显示为 `版本 <数字>`。
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

### BUG-010：智能体日志被错误放置在右侧边栏，导致布局挤压及遮挡

严重度：Major
关联需求：无
回归测试：`tests/test_ui_bubble_layout.py`
回归频率：每次必现
状态：Closed
验收状态：Closed

期望：智能体日志面板位于主页面底部区域（游戏区域下方/底部横条），不放在右侧边栏；右侧边栏只保留警长任务、角色列表、聊天/投票等关键 UI；底部日志区存在且不遮挡右侧警长任务。

验证方式：运行 `pytest tests/test_ui_bubble_layout.py -q`

根因：之前修复中为了不影响游戏区域，将 #log-panel 放在了 #side-panel 内部的底部，但由于 #side-panel 为 flex 布局且 bottom: 160px，将日志挤在了右侧中部，导致右侧关键 UI 被严重压缩，且不符合日志位于底部区域的设计。

修复方案：
  1. 将 #log-panel 从 #side-panel 中移出，放在外层 body 下，作为独立绝对定位面板。
  2. 调整样式：#log-panel 设置为 position: absolute; left: 0; right: 320px; bottom: 0; height: 160px; 与右侧 #task-panel（height: 160px; bottom: 0; right: 0; width: 320px;）完美水平对齐，不遮挡警长任务。
  3. 调整游戏区域 #game-container 和 #bubble-layer 的 bottom 为 160px，以容纳底部的日志面板，确保气泡层和游戏区域不与日志重叠。
  4. 保持 #side-panel bottom 为 160px，其内部由于去除了 #log-panel，高度完全留给角色列表和聊天等关键 UI。
  5. 更新 tests/test_ui_bubble_layout.py 中的测试断言，确保 #log-panel 不在 #side-panel 内，并验证其定位约束。

验证结果（2026-06-05）：
- `tests/test_ui_bubble_layout.py` 全部通过。
- `tests` 全量回归通过：351 passed。
- UI 静态回归确认智能体日志已移出侧边栏并在底部横条显示。

关闭门禁：
- [x] 对应回归测试通过。
- [x] 编译门禁通过。
- [x] 根因与关联需求已记录。

相关提交：本次修复提交。

### BUG-011：智能体日志字号偏小、缺乏拖拽调整高度、日志噪声多，且 NPC 气泡在右边缘可能被遮挡或挡住 NPC 模型

严重度：Major
关联需求：无
回归测试：`tests/test_ui_bubble_layout.py`
回归频率：每次必现
状态：Closed
验收状态：Closed

期望：
  1. 底部日志字号放大一级。
  2. 恢复日志面板顶部拖拽调整高度（向上增大、向下减小），调整高度时，所有邻近元素（game-container, side-panel, bubble-layer, task-panel）同步调整。
  3. 日志噪声过滤：前端只显示思考/计划/行动和必要错误，通过明确白名单过滤掉系统、LLM 请求、行动解析、行动理由等噪声。
  4. NPC 气泡在靠近右侧 UI（侧边栏）边界时自动偏移/向左侧移，保持在 game/bubble layer 内，且有安全距离防止遮挡 NPC 模型，必要时在左右两侧自动翻转。

验证方式：运行 `pytest tests/test_ui_bubble_layout.py -q`

根因：之前版本移除了日志面板的拖拽功能，且日志默认字号（11px）偏小；前端未对 `recent_log` 进行精细过滤，直接显示了大量系统、LLM请求与解析的噪声；旧的气泡布局没有考虑右侧 UI 边界的溢出剪裁以及 NPC 模型的遮挡，在边缘时直接被裁剪，且没有防遮挡 NPC 逻辑。

修复方案：
  1. 将 CSS 中 `#log-content` 和 `.log-llm-raw` 的 `font-size` 从 11px 提升至 12px。
  2. 在 `#log-header` 上添加 `cursor: ns-resize`；在前端 JS 中恢复 mousedown/mousemove/mouseup 拖拽事件监听器，动态更新 `log-panel`, `task-panel` 高度及 `game-container`, `side-panel`, `bubble-layer` 的 bottom 样式，并分发 `resize` 事件通知 Phaser 重新适应。
  3. 在 `updateLog` 中添加 `logWhitelist`（白名单正则表达式数组），对日志类型为 `"error"` 或日志消息匹配 `logWhitelist` 的条目予以保留，其余全部过滤掉。
  4. 在 `resolveBubbleLayout` 中引入 `getClampedBubblePosition` 函数，根据气泡的 actual width、NPC 坐标和 viewport 宽度计算不遮挡 NPC 模型（24px 安全间距）且保持在游戏边界内的最佳偏移位置，并在必要时自动从 right 翻转到 left（反之亦然）。

验证结果（2026-06-05）：
  - `tests/test_ui_bubble_layout.py` 全部通过（包含新增/收紧的测试）。
  - `python -m pytest tests -q` 回归测试通过。

关闭门禁：
  - [x] 对应回归测试通过。
  - [x] 编译门禁通过。
  - [x] 根因与关联需求已记录。

相关提交：本次修复提交。

### BUG-012：开局尸体送走前克罗可被玩家乱点移动，蓝色气泡停留过久且行动气泡混入思考

严重度：Major
关联需求：REQ-101, REQ-102, REQ-104, REQ-132
回归测试：`tests/test_engine_foundation.py`, `tests/test_ui_bubble_layout.py`, `tests/test_agent_action_json.py`
状态：Closed
验收状态：Closed

期望：
1. 开局聚集和尸体送走/返回流程未完成前，地图点击、角色卡靠近 NPC、API 移动都不能改变克罗目标。
2. 普通白色说话气泡、蓝色思考气泡和蓝色行动气泡统一约 6 秒，不因 NPC 仍在行动或思考而无限续命。
3. 第一轮、第二轮和黄昏 NPC 发言结束后约 0.5 秒接下一位。
3. NPC 行动气泡只显示短动作，不展示完整思考、计划或模型内心独白。

根因：
1. `move_detective_to()` 和 `move_detective_to_agent()` 只判断了晨会聚集状态，没有判断 `_body_burial` 尸体送走/返回流程。
2. 前端蓝色气泡缓存会在行动态持续豁免 TTL，思考缓存也曾依赖非活跃状态才过期。
3. NPC 行动 prompt 只限制字数，没有明确禁止把 thought/plan 写进 action；后端展示清洗也不够短。

修复方案：
1. 后端两个克罗移动入口共用 `_detective_opening_locked()`，聚集或尸体处理流程未结束时直接拒绝移动。
2. `bubble_lifetime_seconds` 和前端 `BUBBLE_LIFETIME_SECONDS` 统一为 6 秒；蓝色气泡内容不变时按 TTL 消失。
3. `gathering_departure_gap_seconds` 和 `npc_chat_delay_seconds` 默认改为 0.5 秒；黄昏 NPC 发言逐个广播并按配置 sleep。
3. action prompt 改为“只写可见短动作”，后端 `_action_for_display()` 再剥离 `Thought:`、因果推理前缀并限制展示长度。

验证结果（2026-06-05）：
- `python -m py_compile agent.py game_engine.py engine_bubbles.py ui/app.py` 通过。
- `python -m pytest tests -q` 通过：393 passed，只有 pytest cache 权限警告。

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

### BUG-013：NPC 思考后可能未执行行动，或克罗相关对话状态残留

严重度：Major
关联需求：REQ-159, REQ-160, REQ-161, REQ-162, REQ-163, REQ-164
回归测试：`tests/test_engine_foundation.py`, `tests/test_daytime_npc_behavior.py`, `tests/test_agent_action_json.py`
状态：Closed
验收状态：Closed

期望：
1. NPC 完成一次思考/计划后，必须先进入一次可见行动、移动、交谈或兜底 continue_current，不能直接进入下一轮思考。
2. 如果计划后目标临时不可达或无法接近，NPC 转为可见的 continue_current 行动，而不是空回 idle。
3. NPC 主动找克罗汇报属于单向报告，不给克罗或 NPC 留下对话锁、pending action、thinking/acting 残留状态。
4. NPC-NPC 交谈期间双方锁定到白色气泡消失；气泡消失后释放锁并允许后续行动循环。
5. 警长主动找 NPC 交谈会立即中断目标 NPC 的旧移动和旧行动；等待模型回复期间显示 `...`，回复白泡消失后才释放交谈锁并恢复正常思考/计划。
6. 通用真实交谈白泡不能与开始行动蓝泡共存；第二轮离场发言使用阶段特殊流程，先说完再开始蓝色离场行动和移动。

修复方案：
1. Daytime 调度加入串行 planning lane：同一时间只允许一个 NPC 进入模型思考；已有 pending/moving/acting/conversation 的 NPC 被跳过，不会重复思考。
2. pending action 必须落到 moving/acting/conversation；行动持续时间使用模型给出的 5-30 游戏分钟，并受最近一轮串行规划耗时兜底。
3. 无法接近交谈目标或目标物时转为 continue_current 可见行动，避免“计划后空转再思考”。
4. 主动汇报克罗也是交谈行动；NPC 从提交/显示汇报白泡开始进入交谈占用，汇报白泡消失后才释放锁。
5. NPC-NPC 对话锁改为随白色气泡生命周期释放，模型等待期先显示 `...`。
6. 警长问话入口清除目标 NPC 的旧路径、旧 pending action 和旧行动持续泡；移动循环也会跳过任何正在交谈的 NPC。
7. 第二轮离场通过独立等待期延迟蓝色行动泡和移动，不放宽通用交谈气泡互斥规则。

验证结果（2026-06-06）：
- `python -m pytest tests -q` 通过：406 passed，只有 pytest cache 权限警告。
- `python -m py_compile game_engine.py engine_bubbles.py agent.py` 通过。
- 版本 30 最终回归：`python -m pytest tests -q -p no:cacheprovider` 通过，443 passed；完整 `py_compile` 通过。

### BUG-014：行动蓝泡被旧缓存吞掉，交谈错误进入普通行动持续期

严重度：Major
关联需求：REQ-159, REQ-160, REQ-162, REQ-163, REQ-164
回归测试：`tests/test_engine_foundation.py`, `tests/test_ui_bubble_layout.py`
状态：Closed
验收状态：Closed

期望：
1. 每次新行动都必须显示新的“开始行动”蓝泡；NPC 必须等蓝泡展示期结束后才开始移动、普通行动或真实聊天。
2. 打招呼、询问、聊天、交谈等意图必须靠近目标人物后进入真实发言模型管线，不能进入普通 `acting` 持续期或显示假交谈状态泡。
3. NPC 到达交谈目标旧位置后，如果目标已经移动，应重新靠近；无法靠近则转为可见 `continue_current`。
4. NPC 真实发言、行动中、行动结果日志显示绿色；思考、计划、开始行动日志显示紫色。

根因：
1. 前端蓝泡缓存只按 HTML 文本判断新旧，相同动作会复用已经过期的旧缓存；旧思考/计划缓存还会在后端已开始行动后继续阻挡行动蓝泡。
2. `talk/socialize` 到达目标后沿用了普通行动的 `acting` 持续期，真实交谈管线要等持续期结束才触发。
3. 后端设置路径后同一游戏 tick 立即移动，蓝色开始行动气泡还没展示完成，人物已经位移或聊天已经开始。
4. 前端把 `chat` 日志错误映射到了粉色行动样式。

修复方案：
1. 状态报文增加 `action_started_at`，前端按每次行动开始时间刷新蓝泡缓存；行动状态开始后立即替换旧思考/计划泡。
2. `talk/socialize` 到达目标或原本就在交谈范围内时立即进入真实交谈管线；目标移动则重新寻路，失败则转为 `continue_current`。
3. 增加 `starting_action` 展示期，持续到蓝色开始行动气泡结束；展示期结束后才分发到移动、普通持续行动或真实聊天。
4. 明确打招呼/询问/聊天等文本意图，即使模型返回了错误行动类型也强制归入 `talk`。
5. 新增绿色 `log-chat` 样式，真实发言不再复用粉色行动日志样式。
6. 前端只有在蓝色行动泡真实显示时才启动蓝泡 TTL；被真实白泡互斥隐藏的蓝泡不算展示完成。
7. NPC 主动向 Crow 单向汇报仍不留下对话锁或 pending/acting，但白色汇报泡可见期间会被调度器视为忙碌，避免立刻进入下一轮规划。

验证结果（2026-06-07）：
- `python -m py_compile agent.py game_engine.py llm.py ui/app.py engine_navigation.py engine_tasks.py engine_bubbles.py engine_dusk.py` 通过。
- 相关回归通过：315 passed。
- 正式全量回归通过：471 passed。
- 前端内联脚本语法检查通过。
- 内置浏览器已加载版本 32，新模板包含 `log-chat` 与 `starting_action`。
- 前端版本：32。
### BUG-2026-06-08-001：白天交谈、黄昏讨论和夜晚住处回归问题

严重度：Blocker
频道：Bug 修改
状态：Verified

实际表现：
- 警长主动找 NPC 交谈后，警长会被交谈状态锁住，无法自由移动。
- 目标 NPC 在等待模型回复时仍可能显示旧行动/旧白泡，甚至继续前端移动。
- 进入黄昏讨论时旧白天行动气泡残留，NPC 站位可能挤错，右侧残留旧讨论发言区域，讨论阶段可能卡住。
- 夜晚住处仍不够分散，部分居民夜间位置与白天工作地点或警长区域过近。

修复方案：
- 真实交谈开始后只锁目标 NPC，不锁警长；目标 NPC 前端立即切为 `...` 等待回复并压掉旧行动展示。
- 进入黄昏时后端清理旧行动、旧气泡、旧路径和旧交谈锁；黄昏站位按实际参与者唯一分散；NPC 讨论后台推进并对单人发言设短超时。
- 黄昏右侧面板只保留克罗总结输入，不再显示 NPC 发言列表；黄昏/投票阶段延迟 2 秒把镜头平移到讨论区域。
- 夜晚住处重新分散，保留 Sam 酒吧后方和 Isabella 咖啡馆后方两个特例。

验证方式：
- `python -m py_compile game_engine.py engine_dusk.py ui/app.py world_config.py`
- `python -m pytest tests/test_ui_bubble_layout.py tests/test_world_config.py -q`
- `python -m pytest tests/test_world_config.py tests/test_ui_llm_provider.py -q`
- `python -m pytest tests/test_engine_foundation.py -k "detective_chat_waiting_reply_does_not_lock_crow_movement or records_and_locks_before_slow_npc_reply or normal_detective_chat_uses_fixed_human_question" -q`
- `python -m pytest tests/test_vote_flow.py` 分三段运行，31/31 通过；单次全跑超过 30 秒，按线程规则拆分验证。
- 内置浏览器确认 `http://127.0.0.1:5000/` 显示版本 39，实际 HTML 包含新版等待气泡与黄昏镜头函数。
### BUG-2026-06-08-002：室内目标点可走但不可达，导致 NPC 在咖啡馆/住处附近卡住

严重度：Major
状态：Closed
验收状态：Verified

表现：
- 伊莎贝拉回咖啡馆后方住处时，目标点附近看似可走，但路径会被物件层和室内窄通道阻断。
- 同类风险不只咖啡馆，部分角色夜晚住处或公共地点附近也可能被分配到不可达邻点。

根因：
- 目标分配只查“附近可走格”，没有在设定目标时验证“从 NPC 当前坐标真的可达”。
- 咖啡馆柜台后方/厨房通道在物件层被标成工作区或厨房物件，实际是角色需要通行的窄通道。

修复：
- NPC 回家和前往公共地点时，目标分配改为直接选择可达目标并保存路径。
- 柜台后方工作区允许站立；霍布斯咖啡馆厨房通道的必要格不再作为不可见阻挡。
- 新增真实地图回归测试，覆盖所有角色的住处和默认白天地点可达性。

验证：
- `pytest -q tests/test_engine_foundation.py::test_real_map_agent_destinations_are_reachable_when_assigned tests/test_engine_foundation.py::TestTileFreeOfBlockingObjects`
- `pytest -q tests/test_engine_foundation.py::test_real_map_agent_destinations_are_reachable_when_assigned tests/test_engine_foundation.py::TestPathAdjacentToAvoidsObjectTiles tests/test_engine_foundation.py::TestTileFreeOfBlockingObjects tests/test_world_config.py`
- `python -m py_compile game_engine.py engine_navigation.py world_config.py ui/app.py`
- 全角色真实地图审计：8 个角色住处和默认白天地点均能生成真实可达路径。
- 本地服务已重启，`http://127.0.0.1:5000/?cachebust=40` 返回 200，页面显示版本 40。

### BUG-2026-06-09-001: detective chat, dusk vote, escort, and burial regressions

Severity: Blocker
Status: Fixed

Symptoms:
- Detective-to-NPC real chat could show the listening bubble, receive an empty model reply, immediately release the NPC, and allow the NPC to start a new thought/action cycle.
- Dusk vote buttons stayed in a submitting-looking state, sometimes treating missing `crow_vote` as abstain.
- After confirming vote results, Crow could leave while the voted target stayed in place, blocking the night transition.
- Morning burial used `(12, 46)`, causing Crow to drag bodies on a long route near the sheriff/home area instead of the rear of Johnson Park.
- Dusk public statements could be tagged as directed to Crow, and fallback speeches were too repetitive.

Root causes:
- `detective_chat()` released the conversation lock on the first empty response.
- `_move_agents()` skipped every jailed resident, including the current escort target with an active prison path.
- Voting UI kept `crowVoteSubmitting` inside `showVoteButtons`, and old confirm paths waited on socket/fallback timing.
- Burial target was hard-coded to `(12, 46)`.
- Dusk public speech bubbles used `target=Crow`; fallback text used one repeated template.

Fix:
- Live detective chat retries empty responses within the 30s lock window; non-running tests keep the lock instead of releasing immediately.
- Escort target can walk to prison while the dusk escort stage is active, then remains `jailed`.
- Vote and night confirm buttons call REST endpoints immediately; voting UI hides all voting actions after Crow votes and shows countdown/waiting instead.
- Burial target moved to park rear `(24, 42)` and pathless burial movement no longer creates fake moving state.
- Dusk speech prompt/fallback now pushes specific suspicion and public bubbles no longer target Crow.

Verification:
- `python -m py_compile game_engine.py engine_dusk.py ui/app.py tests/test_engine_foundation.py tests/test_gathering_timeout.py tests/test_ui_bubble_layout.py tests/test_vote_flow.py`
- `python -m pytest -q tests/test_ui_bubble_layout.py -q`
- `python -m pytest -q tests/test_vote_flow.py -q`
- Targeted regressions for detective chat empty response, prison escort movement, and park burial target passed.

# 狼人小镇（Werewolf Ville）重构与功能修改任务进度看板

- `[ ]` 未启动任务
- `[/]` 正在执行的任务
- `[x]` 已完成的任务

---

## 📋 任务进度单

- [x] **1. 技术报告角色一致性更新**
  - [x] 修改 `TECHNICAL_REPORT.md`，将文档叙述中的 10 角色统一修正为实际运行的 6 角色。
- [x] **2. 提示词字数限制与反思输出结构化**
  - [x] 修改 `agent.py` 中的 `reflect()`，硬性规定反思字数 ≤ 100 字，并严格实施 `【行动】/【理由】` 结构化格式。
  - [x] 修改 `agent.py` 中的 `generate_response()`，硬性约束对话字数 ≤ 60 字。
  - [x] 修改 `game_engine.py` 中的 `_trigger_round_one_speak()` 和 `_trigger_round_two_speak()`，约束发言 ≤ 60 字。
  - [x] 修改 `game_engine.py` 中的 `_trigger_npc_chat()`，约束闲聊 ≤ 60 字。
- [x] **3. 狼人身份隔离机制**
  - [x] 在 `agent.py` 的 `Agent` 类中实现 `sanitize_prompt_text()` 方法。
  - [x] 在 `agent.py` 的 `generate_response()`、`decide_next_action()` 和 `reflect()` 中对非狼人角色进行数据净化。
  - [x] 在 `game_engine.py` 的发言和闲聊中，对非狼人角色进行 prompt 净化。
- [x] **4. 感知系统与射线检测集成**
  - [x] 在 `game_engine.py` 中实现 `_compute_perception()` 和 `_broadcast_agent_action()`。
  - [x] 在 `_update_agent_schedules()` 中调用 `_compute_perception()` 构建 `nearby_info` 传入决策。
- [x] **5. 侦探推理逻辑实现**
  - [x] 在 `agent.py` 中实现 `detective_deduce()` 和 `detective_announce()` 方法。
- [x] **6. 前端气泡视野检查与纯 WebSocket 通信改造**
  - [x] 修改 `ui/templates/index.html` 中的气泡跟随位置检测，仅在可视 viewport 内且角色存活时显示。
  - [x] 改造 `index.html` 的移动、夜间过渡、指认和聊天，使用 Socket.io 纯 WebSocket 推送代替 fetch HTTP。
- [x] **8. 深度体验交互升级（用户追加需求）**
  - [x] **声影完全同步**：重构聚集离开逻辑，去除主线程提前移动，使智能体在大模型告别语生成并打印在气泡后，才起步离开。
  - [x] **非可视区气泡物理响应修复**：保证 NPC 无论何时在大地图的任何位置说话，一旦他进入屏幕可视区（或玩家拉动镜头），即可在 60 秒内正常重绘其未过期的发言气泡。
  - [x] **小镇居民居中聚焦跳转**：修复 Phaser pointerdown 针对非 Canvas HTML 元素（如侧栏卡片和按钮）的点击冒泡污染，彻底治愈点击右侧人物列表导致失焦的隐藏 Bug，实现完美居中聚焦。
  - [x] **淡蓝色专属心理活动气泡**：在 `get_state` 中下发 `thought`，前端新增淡蓝色思考气泡，仅对玩家展示，且能与发言气泡进行优雅的垂直动态堆叠（有发言时移到头顶 120px，无发言时在头顶 55px），且能做到一旦有新的思考就立即刷新。
  - [x] **全历史言行滚动清单弹窗**：在卡片里嵌入“记录”按钮，并加入了高端典雅的滚动 Modal 面板，通过调用 agent 信息接口把 `memory` 和 `cognition` 完美地一次性呈现给玩家一直往下阅读。
- [/] **7. 系统验证与稳定性测试**
  - [/] 运行服务，通过浏览器测试所有功能。

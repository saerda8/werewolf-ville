# 狼人小镇（Werewolf Ville）技术重构与修改实施计划

本实施计划详细描述了完成 `REQUIREMENTS.md` 中的所有修改需求，并修复 `TECHNICAL_REVIEW.md` 中提出的致命 Bug、架构缺陷及文档一致性问题的技术步骤。

---

## 需用户评审的事项

> [!NOTE]
> 计划将全面采用 **Socket.io WebSocket 事件**来处理关键动作（如侦探移动、昼夜交替、对话提交、最终指认）。这能通过在后台线程中异步处理 LLM 调用，彻底解决 Flask HTTP 线程阻塞挂起的问题，让界面交互极其流畅。

---

## 待讨论问题

目前没有悬而未决的问题。我们已仔细核对了所有文件路径、API 和需求。

---

## 拟作出的修改

我们将在逻辑分层上修改以下三个核心文件：
1. **前端用户界面** (`ui/templates/index.html`)
2. **智能体与 LLM 提示词逻辑** (`agent.py`)
3. **游戏引擎、感知与动作调度** (`game_engine.py`)

---

### 1. 前端 UI 层

#### [修改] [index.html](file:///G:/Trae-Project/werewolf-ville/ui/templates/index.html)
- **气泡视野与范围检查**：
  - 在 Phaser 的 `update()` 循环中，检测每个 NPC 角色是否在相机可视范围内：
    ```javascript
    const isNPCVisible = cx >= cam.scrollX && cx <= (cam.scrollX + cam.width) && cy >= cam.scrollY && cy <= (cam.scrollY + cam.height);
    ```
  - 如果 NPC 已经死亡、不可见 (`!sprite.visible`) 或超出了可视范围 (`!isNPCVisible`)，则隐藏气泡 (`bubbleEl.style.display = "none"`)。这能彻底保证气泡跟随 NPC 出屏幕，且不会穿透覆盖到右侧面板 (`#side-panel`) 或底部日志面板 (`#log-panel`)。
- **纯 WebSocket 通信改造**：
  - 将侦探移动（点击地图）、进入夜晚 (`enterNight()`)、宣布指认 (`showAnnounce()`) 和发送聊天 (`sendChat()`) 统一改造为 WebSocket 的 `socket.emit(...)` 发送，不再使用阻塞式的 `fetch` 请求。
  - 更新 `socket.on("chat_response")` 监听器，在收到 NPC 的回复后直接渲染，如果失败则弹出错误提示。

---

### 2. 智能体与记忆层

#### [修改] [agent.py](file:///G:/Trae-Project/werewolf-ville/agent.py)
- **字数限制严格约束**：
  - 在 `reflect()`（思考反思 ≤ 100 字）和 `generate_response()`（一对一对话 ≤ 60 字）的系统提示词中加入强力硬性限制，并明确“超出字数限制的输出将被视为无效”。
- **思考/反思输出结构化格式**：
  - 在 `reflect()` 的系统提示词中，规定如果决定行动，必须严格使用以下格式输出：
    ```
    【行动】去[地点名]做什么，目标坐标(x, y)
    【理由】为什么要去
    ```
- **狼人身份信息完全隔离**：
  - 在 `Agent` 类中新增一个强力的 `sanitize_prompt_text(self, text: str) -> str` 方法。如果当前角色不是狼人 (`self.role != "werewolf"`)，则动态将所有读取到的记忆、灵魂、状态等文本中的“狼人”、“狼人案件”等词汇自动替换为“凶手”、“失踪案”、“神秘野兽”等通用词汇。
  - 在 `generate_response()`、`decide_next_action()` 和 `reflect()` 中，为非狼人角色加载上下文时，全部调用该净化方法，确保非狼人角色在任何系统 Prompt 和上下文背景中绝不包含“狼人”二字。
- **侦探自动推理函数**：
  - 在 `Agent` 类中实现 `detective_deduce(self, day: int) -> dict` 方法。当调用时，读取侦探的 `notebook.md` 和 `cognition.md`，请求 LLM 分析小镇上所有存活的居民，并输出一个包含怀疑度百分比、怀疑理由、最可疑对象和案情总结的结构化 JSON。
  - 在 `Agent` 中配套实现 `detective_announce(self, werewolf_guess: str) -> dict` 方法。

---

### 3. 游戏引擎与感知层

#### [修改] [game_engine.py](file:///G:/Trae-Project/werewolf-ville/game_engine.py)
- **NPC 行动与感知系统**：
  - 实现 `_compute_perception(self, agent_name: str) -> str`：
    - 使用射线检测 `self._has_line_of_sight()` 扫描 20 格半径内无墙壁遮挡的其他 NPC。
    - 格式化为可观察动作：如移动中为 `[感知] 你看到 Arthur Burton 正在前往 Hobbs Cafe (77, 21)`；如在原地为 `[感知] 你看到 Arthur Burton 在铁匠铺打铁`。绝不暴露其内心活动。
  - 实现 `_broadcast_agent_action(self, agent_name: str, action_sentence: str)`，用于在日志中记录和向外广播清洁 NPC 的行动描述。
  - 在主调度更新 `_update_agent_schedules()` 中，调用 `self._compute_perception(name)` 生成 `nearby_info` 传入 LLM。
- **狼人信息隔离与发言限制**：
  - 在聚集发言的 `_trigger_round_one_speak()`、`_trigger_round_two_speak()` 和随机闲聊 `_trigger_npc_chat()` 中，对于非狼人 NPC 传入 prompt 之前全部调用 `agent.sanitize_prompt_text()` 进行净化。
  - 在所有发言 prompt 中强调字数必须控制在 60 字以内。

---

### 4. 技术文档

#### [修改] [TECHNICAL_REPORT.md](file:///G:/Trae-Project/werewolf-ville/TECHNICAL_REPORT.md)
- 更新技术报告中的第 1.2、3.1 和 7.1 章节，明确指出在当前版本中实际运行的是 **6 个角色**（5 个 NPC 居民 + 1 个侦探），以消除文档与代码角色的数量偏差。

---

## 验证计划

### 自动化验证
- 启动 Flask Web 服务，确保代码可以成功编译、导入并启动。
- 在浏览器中拖拽侦探、触发交谈和昼夜转换，确认所有 WebSocket (Socket.io) 事件能被正确捕获和处理。

### 手动验证
- 打开 Phaser 界面，拖拽镜头，确认 NPC 出屏幕后气泡会自动消失。
- 查看非狼人角色的反思和记忆文件，确认其中没有任何“狼人”二字（完全被“凶手/失踪”等替代），并且思考格式完全符合结构化 `【行动】/【理由】` 的输出要求。

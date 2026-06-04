# 当前修改需求文档

## 一、气泡跟随 NPC 世界坐标（不再 clamp 屏幕边界）

**现状问题**：气泡在 `index.html` 的 `update()` 中有 `screenX/screenY` 的 clamp 逻辑，限制在 `game-container` 边界内。NPC 走出屏幕后气泡被挤压在屏幕边缘。

**要求**：气泡坐标完全跟随 NPC 世界坐标，不做 clamp。NPC 出屏幕 → 气泡也出屏幕。只有玩家拖动镜头重新看到该 NPC 时，气泡才可见。

**修改点**：
- `ui/templates/index.html`：移除 `update()` 中气泡 clamp 逻辑，`screenX/screenY` 直接等于世界坐标转换后的值

---

## 二、文字字数限制

| 类型 | 限制 |
|------|------|
| 聚集发言 | ≤60 字 |
| 一对一对话 | ≤60 字 |
| 思考/反思/cognition | ≤100 字 |
| 情景解析/环境描述 | ≤100 字 |

**修改点**：
- `game_engine.py`：聚集发言 prompt 中加入字数限制
- `agent.py`：所有 LLM 调用 prompt 中加入对应字数限制

---

## 三、思考/反思输出结构化格式

NPC 在思考过程中如果决定行动，必须按以下格式输出：

```
【行动】去[地点名]做什么，目标坐标(x, y)
【理由】为什么要去
```

纯思考（不涉及行动）只需输出简短文字即可。

**修改点**：
- `agent.py`：`_update_agent_schedules()` 中的 prompt 模板

---

## 四、狼人身份信息隔离

**核心原则**：只有狼人本人知道自己是狼人。其他 NPC 的 prompt 中不能出现任何暗示狼人身份的信息。

**具体规则**：
- 非狼人 NPC 的 system prompt 中角色描述不包含"某人是狼人"
- 非狼人 NPC 不知道游戏有"狼人"这个设定
- 非狼人 NPC 只能从 NPC 发言中推断
- 游戏引擎在给 NPC 构造 prompt 时，不能暴露真实角色

**修改点**：
- `agent.py`：`_build_system_prompt()` 或类似方法，确保非狼人 NPC 的 prompt 中不包含狼人身份信息
- `game_engine.py`：聚集发言时给非狼人 NPC 的 prompt 不包含狼人角色信息

---

## 五、感知系统（20格半径 + 无遮挡）

**核心原则**：
- NPC 只知道他**亲眼看到**的事
- 能看到：其他 NPC 的行动（移动、使用物品等）——即"做了什么"
- 看不到：其他 NPC 的思考、反思、内心动机——即"为什么做"
- 范围：20 格半径内，且中间无遮挡物

**感知输入格式**（传给 LLM 的）：
```
[感知] 你看到 Arthur Burton 从铁匠铺走到了广场 (57, 35)
[感知] 你看到 Isabella Rodriguez 在咖啡馆擦桌子
```

**行动输出格式**（供其他 NPC 感知的）：
```
Arthur Burton 正在前往铁匠铺 (45, 32)
Arthur Burton 在铁匠铺打铁
```

**修改点**：
- `game_engine.py`：新增 `_compute_perception()` 方法，计算每个 NPC 能感知到的其他 NPC 行动
- `game_engine.py`：新增 `_broadcast_agent_action()` 方法，记录 NPC 行动供感知使用
- `agent.py`：`_update_agent_schedules()` 中 LLM 调用时传入感知数据
- 需要实现简单的射线检测（判断两个坐标之间是否有遮挡物）

---

## 六、NPC 行动记录

**不做的事**：
- 不广播 NPC 的思考内容
- 不在非狼人 NPC 的 prompt 中暴露狼人身份
- 不把 `cognition.md` 或 `memory.md` 的内容传给其他 NPC

**要做的事**：
- 记录每个 NPC 当前的行动描述（`current_action` 字段）
- 在感知系统中使用这些行动描述
- 行动描述仅包含"可观察到的行为"，不包含内心活动
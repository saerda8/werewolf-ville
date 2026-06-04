# game_engine.py 拆分计划（增量重构）

> 编写时间：2026-06-04  
> 来源：PROJECT_CONTINUITY.md §7.3 识别 `game_engine.py` 过大（5758 行），明确建议拆分出 6 个模块。本文档将此建议转化为可执行的增量提取计划。

## 1. 现状摘要

| 指标 | 值 |
|------|----|
| 总行数 | 5,758 |
| 方法/函数总数 | 158 |
| 类 | `WerewolfGameEngine`（~5050 行）、`GamePhase`（Enum） |
| 模块级函数 | 11 |
| 直接 import | `agent`, `llm`, `world_config`, `simulation_events`, `night_hunt`, `config_loader`, `utils` |

**核心问题**：`WerewolfGameEngine` 一个类承担了状态机调度、路径/移动、NPC 行动规划、投票/监禁、银器任务、集会/发言管理、对话流、气泡 UI 状态、每日任务构建、序列化等至少 10 项职责。任何单项修改都容易引发回归。

---

## 2. 目标模块及内容定义

参考 PROJECT_CONTINUITY.md §7.3 的建议，细化每个模块的提取范围：

### M1 — `dusk_vote.py`（~350 行）

| 方法 | 行号范围 |
|------|---------|
| `can_start_dusk_discussion` | ~2277 |
| `start_dusk_discussion` | ~2298 |
| `_transition_to_dusk` | ~2310 |
| `_generate_dusk_votes` | ~2326 |
| `_generate_single_dusk_vote` | ~2350 |
| `_resolve_display_name_to_internal` | ~2414 |
| `_is_abstain_vote` | ~2427 |
| `_deterministic_dusk_vote` | ~2432 |
| `jail_vote_target` | ~2475 |
| `_place_in_prison` | ~2531 |
| `_get_prison_cell` | ~2564 |
| `_jailed_final_words` | ~2572 |
| `_build_vote_summary` | ~2590 |
| `_record_vote_history_snapshot` | ~2616 |

### M2 — `silver_objectives.py`（~290 行）

| 方法 | 行号范围 |
|------|---------|
| `acquire_silver_bullet` | ~2734 |
| `acquire_silver_jewelry` | ~2793 |
| `craft_silver_bullet` | ~2874 |
| `_silver_kill_target` | ~2899 |
| `_check_win_after_silver_action` | ~2941 |
| `shoot_silver_bullet` | ~2962 |
| `use_silver_knife` | ~2975 |
| `_maybe_use_silver_knife_at_night` | ~2993 |

### M3 — `tasks.py`（~100 行）

| 方法 | 行号范围 |
|------|---------|
| `_build_daily_tasks` | ~2634 |

### M4 — `conversation_flow.py`（~450 行）

| 方法 | 行号范围 |
|------|---------|
| `detective_chat` | ~? |
| `detective_announce` | ~? |
| `_generate_agent_response` | ~? |
| `_trigger_npc_to_detective_chat` | ~? |
| `_trigger_npc_chat` + `_do_chat` | ~? |
| `_npc_chat_key` | ~? |
| `_clear_conversation_pair` | ~? |
| `_clear_conversation_if_too_far` | ~? |
| `_interrupt_agent_conversation` | ~? |
| `_check_llm_chats` | ~? |
| `_build_npc_context` | ~? |
| `_daily_deep_dive_quota` | ~675 |
| `_reset_daily_deep_dive_quota` | ~684 |
| **依赖的状态变量** | `_detective_chat_active_target`, `_detective_chat_job_id`, `_daily_interviewed`, `_npc_chat_tokens`, `_daily_normal_chats` |

### M5 — `npc_scheduler.py`（~600 行）

| 方法 | 行号范围 |
|------|---------|
| `_generate_daily_plans` | ~3437 |
| `_update_agent_schedules` | ~3472 |
| `_llm_tick` + `_do_reflect` | ~? |
| `_body_status` | ~? |
| **依赖的状态变量** | `llm_threads`, `llm_tick_counter`, `llm_reflect_idx`, `llm_interval`, `agent_paths` |

### M6 — `bubble_state.py`（~80 行）

| 方法 | 行号范围 |
|------|---------|
| `_show_gathering_bubble` | ~925 |
| `_expire_chat_bubbles` | ~951 |
| `chat_bubbles` 管理 | 分散 |
| 气泡过期逻辑（get_status 中） | ~5635–5639 |

### M7 — `navigation.py`（~530 行）（额外提议）

| 方法 | 行号范围 |
|------|---------|
| `_get_emoji` | ~4029 |
| `_find_object_in_spatial_memory` | ~4054 |
| `_reverse_lookup_location` | ~4143 |
| `_is_tile_free_of_blocking_objects` | ~4168 |
| `_navigation_maze` | ~4187 |
| `_find_navigation_path` | ~4207 |
| `_occupied_tiles` | ~4212 |
| `_reachable_component` | ~4221 |
| `_nearest_walkable_tile_in_component` | ~4254 |
| `_nearest_walkable_tile` | ~4273 |
| `_nearest_reachable_path` | ~4297 |
| `_path_adjacent_to` | ~4339 |
| `_best_manual_move_path` | ~4414 |
| `_move_agents` | ~4454 |
| `_action_needs_movement` | ~4546 |
| `_complete_agent_action` | ~? |
| `move_detective_to` | ~? |
| `move_detective_to_agent` | ~? |
| 模块级函数 | `load_collision_maze`, `_apply_collision_overrides`, `_connect_maze_regions`, `bfs_path`, `load_scene_data`, `get_tile_scene`, `get_nearby_objects` |

### M8 — `gathering_flow.py`（~1,250 行）（额外提议）

| 方法 | 行号范围 |
|------|---------|
| `_init_gathering` | ~831 |
| `_begin_gathering_turn` | ~889 |
| `_complete_gathering_turn` | ~904 |
| `_expire_gathering_turn` | ~918 |
| `_gathering_speech_visible_seconds` | ~936 |
| `_crow_intro_line_delay` | ~940 |
| `_gathering_departure_gap_seconds` | ~945 |
| `_departure_delay_seconds` | ~949 |
| `_departure_speech` | ~957 |
| `_departure_object` | ~986 |
| `_limit_gathering_speech` | ~996 |
| `_sanitize_round_one_speech` | ~1026 |
| `_destination_label_zh` | ~1106 |
| `_summarize_thought_for_display` | ~1111 |
| `_start_crow_scene_investigation` | ~1140 |
| `_bury_bodies_after_gathering` | ~1150 |
| `_send_crow_to_burial_target` | ~1193 |
| `_send_crow_to_burial_return` | ~1216 |
| `_update_body_burial_sequence` | ~1242 |
| `_handle_gathering` | ~1294 |
| `_handle_round_one` | ~1369 |
| `_publish_crow_dismissal` | ~1401 |
| `_handle_round_two_plus` | ~1417 |
| `_case_intro_text` | ~1444 |
| `_case_intro_fallback_lines` | ~1452 |
| `_parse_crow_intro_lines` | ~1468 |
| `_balance_crow_intro_lines` | ~1493 |
| `_trigger_crow_case_intro` | ~1530 |
| `_trigger_round_one_speak` | ~1579 |
| `_trigger_round_two_speak` | ~1729 |
| `_normalize_destination` | ~1924 |
| `_set_agent_target` | ~1947 |
| `_resolve_concrete_target_object` | ~2026 |
| `_parse_gathering_json` | ~2054 |

---

## 3. 提取顺序（依赖驱动的增量步骤）

```
顺序  模块              前置依赖              对 engine 其余部分的侵入度
───  ───────────────  ───────────────────  ─────────────────────────
1    navigation.py    无（模块级函数为主）    低（纯函数 + 少量 self 引用）
2    bubble_state.py  navigation（可选）    极低（仅操作 chat_bubbles dict）
3    dusk_vote.py     navigation（寻路）    中（访问 agents, _jailed 等状态）
4    silver_obj.py    dusk_vote（监禁状态）  中（访问 agents, _jailed, day）
5    tasks.py         silver_obj（银器）    低（只读状态，纯 builder）
6    npc_scheduler.py navigation + bubble  高（LLM 线程、agent 循环调度）
7    conversation.py  npc_scheduler        高（深度耦合 agent 和 LLM 调用）
8    gathering_flow.py 以上全部（参考）     最高（涉及几乎所有状态）
```

**核心策略**：每一阶段只移走**一个模块**的方法，保留 `WerewolfGameEngine` 作为入口类不变，提取后的模块以 **Mixin class** 方式被继承，或作为**独立的函数集合**接收 `self` 引用。

### 推荐模式：Mixin class

```python
# dusk_vote.py
class DuskVoteMixin:
    \"\"\"提供 WerewolfGameEngine 的投票/监禁功能\"\"\"
    def can_start_dusk_discussion(self) -> tuple[bool, str]:
        # 使用 self.xxx 访问引擎状态
        ...
    def _generate_dusk_votes(self):
        ...
```

```python
# game_engine.py
from dusk_vote import DuskVoteMixin

class WerewolfGameEngine(DuskVoteMixin, ...):
    ...
```

此模式的优势：
- 编译器/解释器级别的方法可见性无变化
- 增量修改：一次加一个 Mixin，不改调用方
- 可单独对 Mixin 做单元测试（mock engine 状态）

---

## 4. 依赖边界（关键约束）

从 `__init__`（行 526–670）看，以下状态变量是多个模块的共享依赖：

| 状态变量 | 类型 | 被以下模块读取 |
|---------|------|-------------|
| `agents` (dict) | 全局 | 全部 |
| `_jailed` (set) | 游戏状态 | gathering, dusk_vote, silver, tasks, conversation |
| `_daily_interviewed` (set) | 对话追踪 | conversation, tasks |
| `chat_bubbles` (dict) | UI 状态 | bubble_state, gathering, get_status |
| `agent_paths` (dict) | 移动 | navigation, npc_scheduler |
| `bodies` / `clues` (list) | 事件 | gathering, night, silver, get_status |
| `day` / `phase` | 核心状态 | 全部 |
| `_silver_*` (bool) | 银器 | silver, tasks |
| `_dusk_*` | 投票 | dusk_vote |
| `llm_threads` / `llm_*` | LLM 调度 | npc_scheduler |
| `_detective_chat_*` | 对话 | conversation |

**提取约束规则**：
1. **一个模块不应该直接读取另一个模块的内部状态变量**（如 `dusk_vote.py` 不应读 `_silver_bullet_acquired`）
2. 跨模块状态访问必须通过 `self` 或 engine 的公开/半公开属性
3. `get_status()` 留在 engine 主体中，因为它引用所有模块的数据（序列化汇聚点）
4. 核心循环 `_game_loop` / `_day_tick` / `_dusk_tick` / `_night_tick` 留在 engine 主体中，只调用提取后的方法

---

## 5. 每步提取后的测试验证

| 步骤 | 模块 | 需通过的测试 |
|------|------|------------|
| 1 | `navigation.py` | `test_engine_foundation.py`（含地图/路径测试） |
| 2 | `bubble_state.py` | `test_ui_bubble_layout.py` |
| 3 | `dusk_vote.py` | `test_vote_flow.py`, `test_engine_foundation.py`（投票相关） |
| 4 | `silver_objectives.py` | `test_engine_foundation.py`（银器相关） |
| 5 | `tasks.py` | `test_engine_foundation.py`（get_status 测试） |
| 6 | `npc_scheduler.py` | `test_daytime_npc_behavior.py`, `test_engine_foundation.py` |
| 7 | `conversation_flow.py` | `test_engine_foundation.py`（对话相关） |
| 8 | `gathering_flow.py` | `test_gathering_timeout.py`, `test_engine_foundation.py` |

**全局回归**（每步后都跑）：
```bash
python -m pytest tests/test_engine_foundation.py -x --tb=short -q
python -m pytest tests/ -x --tb=short -q --timeout=120
python -m py_compile game_engine.py
```

---

## 6. 回滚检查点机制

### Git 分支策略

```bash
# 每步提取前打 tag
git tag split/pre-{module_name}
# 例如
git tag split/pre-navigation
git tag split/post-navigation  # 提取后验证通过
```

### 检查点条件

在提交前必须满足：
1. `python -m py_compile game_engine.py` 通过
2. 新模块 `python -m py_compile {module}.py` 通过
3. 相关测试全部 `PASSED`
4. 完整的 `pytest tests/ -x --tb=short` 通过（排除已知失败）

### 回滚命令

```bash
# 如果某步提取导致测试失败且 5 分钟内无法修复
git checkout -- game_engine.py
git checkout -- {module}.py  # 如果已创建
# 或者如果已提交
git revert HEAD --no-edit
```

### 快速验证脚本（提取后必跑）

```bash
# === 编译检查 ===
python -m py_compile game_engine.py && echo "[engine ok]" || echo "[engine fail]"
python -m py_compile {new_module}.py && echo "[module ok]" || echo "[module fail]"

# === 最小回归 ===
python -m pytest tests/test_engine_foundation.py -x --tb=short -q

# === 全量测试 ===
python -m pytest tests/ -x --tb=short -q
```

---

## 7. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| Mixin 间命名冲突 | 低 | 中 | 提取前扫描所有方法名，确保无重复 |
| `self._xxx` 在 Mixin 中访问不存在变量 | 中 | 高 | 每步提取后运行全量测试 |
| 循环 import | 低 | 高 | 提取的模块只 import 底层模块（如 `simulation_events`, `night_hunt`），不 import `game_engine` |
| 提取后 engine 文件仍过大 | 高 | 低 | 分 8 步提取，每步减 ~100–500 行 |
| 测试覆盖率不足 | 中 | 中 | `test_engine_foundation.py` 有 ~11 万行测试体量，覆盖大部分路径 |

---

## 8. 建议优先级

**第一阶段（高收益低风险，优先执行）**：
1. `navigation.py` — 纯函数多，测试充分，减 530 行
2. `bubble_state.py` — 极小，减 80 行
3. `dusk_vote.py` — 独立域，减 350 行

**第二阶段（核心玩法逻辑）**：
4. `silver_objectives.py` — 减 290 行
5. `tasks.py` — 减 100 行

**第三阶段（最复杂的调度/对话）**：
6. `npc_scheduler.py` — 减 600 行
7. `conversation_flow.py` — 减 450 行
8. `gathering_flow.py` — 减 1,250 行

全部完成后 `game_engine.py` 剩余约 **2,000–2,500 行**（核心循环、`__init__`、`get_status`、`_log`、`start/stop/new_game`、`_game_loop` / tick 方法、`_broadcast_state`、`_build_shared_spatial_memory`、入口 `active_town_people_rule` 等模块级函数）。

---

## 9. 提取后的架构示意图

```
game_engine.py  (核心调度 + __init__ + get_status + 主循环)
  |-- navigation.py        (Mixin)  地图/路径/移动
  |-- bubble_state.py      (Mixin)  气泡管理
  |-- dusk_vote.py         (Mixin)  投票/监禁
  |-- silver_objectives.py (Mixin)  银器任务
  |-- tasks.py             (Mixin)  每日任务构建
  |-- npc_scheduler.py     (Mixin)  NPC 日程/LLM 调度
  |-- conversation_flow.py (Mixin)  侦探对话/NPC 聊天
  |-- gathering_flow.py    (Mixin)  晨会/发言/埋葬
```

每个模块可使用 `simulation_events`, `night_hunt`, `world_config`, `agent`, `llm` 等底层模块，但不反向依赖 `game_engine`。

---

## 10. 附录：关键方法所在行号备忘（供提取时参照）

```
行号范围      模块归属       当前状态
-------      ----------    --------
1-45         文件头/import  不动
47-500       模块级函数      -> navigation.py (M7)
513-517      GamePhase     不动（可留 engine 或移 config）
526-670      __init__       不动
675-684      深挖配额        -> conversation_flow.py (M4)
692-780      _init_agents   不动（创建 Agent 实例）
781-830      set_socketio/广播 不动
831-1100     集会方法群      -> gathering_flow.py (M8)
1106-1139    工具方法        -> gathering_flow.py (M8)
1140-2069    集会/埋葬/发言  -> gathering_flow.py (M8)
2069-2083    _log           不动
2084-2198    start/stop/new 不动
2198-2265    主循环/tick    不动（仅调用）
2277-2633    投票/监禁       -> dusk_vote.py (M1)
2634-2732    每日任务        -> tasks.py (M3)
2734-3020    银器            -> silver_objectives.py (M2)
3023-3435    夜晚/狼人      不动（或未来拆 night_phase.py）
3437-4028    NPC 调度/LLM   -> npc_scheduler.py (M5)
4029-4550+   导航/移动       -> navigation.py (M7)
4550-5100+   代理动作/对话   -> conversation_flow.py (M4)
5101-5300+   线索/检测       -> conversation_flow.py (M4) 或不动
5301-5501    NPC 聊天        -> conversation_flow.py (M4)
5502-5757    get_status     不动（序列化汇聚点）
```

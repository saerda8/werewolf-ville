# NPC Observation Memory Cognition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade NPC behavior from "visible action text plus simple action memory" to a Stanford Smallville-style loop where observation, thought, plan, action, conversation, and memory all feed future decisions.

**Architecture:** Keep the current three model lanes: decision lane, conversation lane, and memory lane. Add a backend observation buffer with radius-based per-NPC filtering, then use asynchronous memory consolidation to turn observations, thoughts, plans, actions, and conversations into durable event/chat/thought memories.

**Tech Stack:** Python engine and agent modules, existing LLM provider wrapper, pytest, Flask/Socket.IO status payload, existing HTML/JS frontend logs and bubbles.

---

## Source Reference

Original Stanford Smallville / Generative Agents reference project:

```text
G:\generative_agents-main
```

Relevant upstream files:

- `G:\generative_agents-main\reverie\backend_server\persona\persona.py`
- `G:\generative_agents-main\reverie\backend_server\persona\cognitive_modules\perceive.py`
- `G:\generative_agents-main\reverie\backend_server\persona\cognitive_modules\retrieve.py`
- `G:\generative_agents-main\reverie\backend_server\persona\cognitive_modules\plan.py`
- `G:\generative_agents-main\reverie\backend_server\persona\cognitive_modules\reflect.py`
- `G:\generative_agents-main\reverie\backend_server\persona\memory_structures\associative_memory.py`

Upstream loop:

```text
perceive -> retrieve -> plan -> reflect -> execute
```

Key upstream lesson:

- `event`, `chat`, and `thought` are all memory-stream nodes.
- Daily plans are stored as `thought` memories.
- Perceived nearby events are stored as `event` memories.
- Conversations are stored as `chat` memories.
- Reflection creates new `thought` memories with evidence links to prior nodes.
- Planning retrieves relevant events and thoughts before deciding what to do.

## Current Problem

The current Werewolf Ville system is too shallow in two places:

- NPC `thought` and `expected_result/action_plan` mostly behave like UI/log explanation text, not durable thought memory.
- Memory is mostly a chronological action/dialogue list. It records "what happened" but does not consistently record "what the NPC inferred, noticed, or now believes."

User-visible symptoms:

- A thought bubble can show fallback text such as "正在整理当前情况" instead of real model reasoning.
- NPCs can produce illogical action-status text such as "招呼客人" when no customer exists nearby.
- Causal chains are unreliable. Example: "someone discovered I am a werewolf, so I need to kill that person" only works if that fact happened to enter memory.
- Nearby overheard conversations or visible actions are not guaranteed to become future decision context.

## Target Design Contract

### Model Lanes

1. Decision lane: one serial NPC planning model lane.
   - Input: observation packet, relevant memory, identity, current state, day plan, recent action history, constraints.
   - Output: thought, plan, action fields, target, action status, duration, clue hint flags.
   - Thought and plan are meaningful cognitive outputs, but they must stay compact. The model must not write omniscient essays or solve the whole game in one turn.
   - `thought` explains only the current basis and motive: "based on what I can observe/remember right now, why am I doing this?"
   - `plan` is simple and action-shaped: "go to this target point/place/person and do this one thing."

2. Conversation lane: one serial speech model lane.
   - Used only when an action is a real `talk/socialize` behavior.
   - Conversation starts when the speech job is submitted.
   - Conversation action completes only after the white speech bubble expires.

3. Memory lane: one asynchronous memory consolidation model lane.
   - Runs after ordinary action completion, real conversation completion, important observed events, stage transitions, and public world events.
   - It must not block visible action execution or the planning lane.

### Observation Radius

Use radius `10` as the initial rule.

- Visual range: NPC can observe entities/events within Manhattan distance `<= 10`.
- Hearing range: ordinary speech and white speech bubbles are hearable within distance `<= 10`.
- Public events: body discovery, vote result, night death announcement, and public meeting statements are broadcast to eligible NPCs regardless of radius.
- Hidden facts: werewolf identity, true night killer, hidden item owner, and internal model/debug facts are not observable merely because of radius.

### Observation Packet

Observation is a decision-prep packet, not just nearby people.

Each NPC decision packet should include:

- Identity: role-facing identity, profession, stable goals, known faction facts.
- Current self-state: position, location, runtime state, current action, previous action result.
- World state: day, hour, phase, dead list, public clues, public tasks.
- Spatial perception: nearby people, distance, location, runtime state, visible action/speech.
- Object perception: nearby objects, reachable target objects, visible clue objects.
- Event perception: recent observable events from the global observation buffer.
- Memory retrieval: relevant long-term memories, thoughts, conversations.
- Short-term state: `scratch.currently` and current concern.
- Day plan: current day plan and any deviations.
- Recent actions: last actions to avoid repetition.
- Rule constraints: allowed locations, allowed target people, black-box information rules.

### Thought And Plan Length Contract

`thought` and `plan` are useful because they represent the NPC's current mind, but they must be constrained.

`thought`:

- Target length: `60..100` Chinese characters.
- Purpose: explain the immediate motive from the NPC's own limited perspective.
- Must reference only current observation, relevant memory, short-term goal, or recent action result.
- Must not reason with hidden facts the NPC does not know.
- Must not produce long-form global deduction, multi-day strategy, or omniscient analysis.

`plan`:

- Target length: `20..40` Chinese characters.
- Purpose: describe only this next action.
- Format: `去/留在/接近 <目标地点/目标人/目标物>，<做一件事>`。
- The target may be a coordinate internally, but the display text should use a readable place/person/object name when possible.
- Must not include a chain of future steps, broad strategy, or explanation. Explanation belongs in `thought`.

Examples:

- `thought`: `店里现在没有客人，但柜台有些凌乱，我先整理杯盘，免得营业时手忙脚乱。`
- `plan`: `留在咖啡馆，整理杯盘。`
- `thought`: `哈维五金店今天可能需要工具支援，我先确认库存，避免后面缺关键物件。`
- `plan`: `去五金店，检查库存。`
- `thought`: `伊莎贝拉刚才在附近停留，我想确认她昨晚是否看到异常，但不能直接指控她。`
- `plan`: `接近伊莎贝拉，询问昨晚情况。`

### Observation Buffer

Events are recorded when they happen, then filtered per NPC when needed.

Important principle:

```text
event happens -> global observation buffer
NPC needs context -> filter by radius/time/permission
memory lane needs consolidation -> filter by witness and importance
```

Do not scrape UI bubbles as the source of truth. UI bubbles are display; backend events are truth.

### Memory Types

Add typed memory records while preserving existing `memory.md` compatibility.

Recommended node types:

- `event`: observable world/action fact.
- `chat`: conversation transcript or summary.
- `thought`: NPC interpretation, belief, plan, suspicion, or inferred motive.
- `plan`: daily or current plan summary. This may be implemented as `thought` with `subtype="plan"` if a separate type is too heavy.

Required fields:

```python
{
    "id": "mem_000001",
    "type": "event|chat|thought|plan",
    "created_at": 1710000000.0,
    "day": 1,
    "game_hour": 9.5,
    "subject": "Isabella Rodriguez",
    "predicate": "noticed",
    "object": "Arthur Burton",
    "text": "伊莎贝拉注意到亚瑟在咖啡馆门口徘徊。",
    "importance": 1,
    "keywords": ["伊莎贝拉", "亚瑟", "咖啡馆"],
    "evidence": ["obs_000123"],
    "source": "observation|action|conversation|reflection|public_event",
    "visibility": "private|public|witnessed"
}
```

### Action Text Constraint

`action_status` must be grounded in the observation packet.

Bad:

```text
招呼客人
```

when there is no customer/person in the cafe.

Good:

```text
擦拭桌面
整理杯盘
检查咖啡豆
清点账本
```

Prompt rule:

```text
action_status 必须只描述当前真实存在的人、物或事务。不得虚构客人、顾客、镇民、对方或不存在的目标。若周围没有可互动的人，只能写物件/职业相关的短任务。
```

Backend fallback:

If `action_status` mentions a generic person but no visible person exists in the observation packet, replace it with a grounded profession/location-safe status.

Examples:

- Isabella Rodriguez: `整理杯盘`
- Sam Moore: `擦拭吧台`
- Arthur Burton: `检查库存`
- Mei Lin: `整理书架`
- Maria Lopez: `整理货架`
- Jane Moreno: `修剪花枝`
- Klaus Mueller: `整理讲义`

## Expected Files

Create:

- `engine_observation.py`: observation event dataclasses/helpers, radius filtering, event serialization.
- `engine_memory_queue.py`: async memory task queue, memory-lane worker, consolidation result parser.
- `tests/test_engine_observation.py`: observation radius/filtering/public/hidden-event tests.
- `tests/test_memory_consolidation.py`: memory lane parsing, writes, thought/plan persistence tests.

Modify:

- `config.yaml`: add `observation.radius`, `observation.event_ttl_seconds`, and memory-lane config.
- `agent.py`: add typed memory write/read helpers, memory consolidation prompt, grounded `action_status` prompt rules.
- `game_engine.py`: emit observation events, build decision observation packets, enqueue memory tasks after action/conversation/public events.
- `llm.py`: expose or reuse a low-priority memory-lane call path without blocking planning/conversation.
- `engine_bubbles.py`: no behavior change expected, but action-status text validation may call shared helpers if useful.
- `tests/test_engine_foundation.py`: planning packet, action status grounding, memory enqueue integration tests.
- `tests/test_daytime_npc_behavior.py`: NPC action/conversation memory regression tests.
- `tests/test_prompt_boundaries.py`: prompt black-box and anti-fiction constraints.
- `USER_REQUIREMENTS_LEDGER.md`: record stable observation/memory requirements.
- `NPC_BEHAVIOR_LIFECYCLE.md`: update lifecycle to include observation packet and memory lane.
- `CURRENT_SPRINT.md`: track implementation status.

Do not modify:

- `personas/` runtime memory during worker investigation.
- Static persona templates unless the user explicitly asks.

## Task 1: Observation Event Model

**Files:**

- Create: `engine_observation.py`
- Test: `tests/test_engine_observation.py`

- [ ] **Step 1: Write failing tests for radius and permissions**

Add tests:

```python
from engine_observation import ObservationEvent, filter_observable_events


def test_radius_10_includes_visible_event():
    event = ObservationEvent(
        event_id="obs_1",
        event_type="action_start",
        subject="Arthur Burton",
        text="亚瑟开始检查库存。",
        x=5,
        y=5,
        day=1,
        game_hour=9.0,
        timestamp=100.0,
    )

    visible = filter_observable_events(
        events=[event],
        observer_name="Isabella Rodriguez",
        observer_x=12,
        observer_y=8,
        now=110.0,
        radius=10,
    )

    assert [item.event_id for item in visible] == ["obs_1"]


def test_radius_10_excludes_far_private_event():
    event = ObservationEvent(
        event_id="obs_2",
        event_type="speech",
        subject="Sam Moore",
        text="山姆低声说话。",
        x=30,
        y=30,
        day=1,
        game_hour=9.0,
        timestamp=100.0,
    )

    visible = filter_observable_events(
        events=[event],
        observer_name="Isabella Rodriguez",
        observer_x=12,
        observer_y=8,
        now=110.0,
        radius=10,
    )

    assert visible == []


def test_public_event_ignores_radius():
    event = ObservationEvent(
        event_id="obs_3",
        event_type="public_announcement",
        subject="Crow",
        text="克罗宣布黄昏讨论开始。",
        x=99,
        y=99,
        day=1,
        game_hour=18.0,
        timestamp=100.0,
        public=True,
    )

    visible = filter_observable_events(
        events=[event],
        observer_name="Mei Lin",
        observer_x=0,
        observer_y=0,
        now=110.0,
        radius=10,
    )

    assert [item.event_id for item in visible] == ["obs_3"]


def test_hidden_event_requires_explicit_witness():
    event = ObservationEvent(
        event_id="obs_4",
        event_type="hidden_fact",
        subject="Arthur Burton",
        text="亚瑟是狼人。",
        x=5,
        y=5,
        day=1,
        game_hour=9.0,
        timestamp=100.0,
        hidden=True,
        witnesses={"Crow"},
    )

    visible_for_crow = filter_observable_events(
        events=[event],
        observer_name="Crow",
        observer_x=5,
        observer_y=5,
        now=110.0,
        radius=10,
    )
    visible_for_sam = filter_observable_events(
        events=[event],
        observer_name="Sam Moore",
        observer_x=5,
        observer_y=5,
        now=110.0,
        radius=10,
    )

    assert [item.event_id for item in visible_for_crow] == ["obs_4"]
    assert visible_for_sam == []
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_engine_observation.py -q -p no:cacheprovider
```

Expected:

```text
ModuleNotFoundError: No module named 'engine_observation'
```

- [ ] **Step 3: Implement observation model**

Create `engine_observation.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class ObservationEvent:
    event_id: str
    event_type: str
    subject: str
    text: str
    x: int
    y: int
    day: int
    game_hour: float
    timestamp: float
    object: str = ""
    public: bool = False
    hidden: bool = False
    witnesses: set[str] = field(default_factory=set)
    source: str = "world"


def manhattan_distance(x1: int, y1: int, x2: int, y2: int) -> int:
    return abs(int(x1) - int(x2)) + abs(int(y1) - int(y2))


def filter_observable_events(
    events: Iterable[ObservationEvent],
    observer_name: str,
    observer_x: int,
    observer_y: int,
    now: float,
    radius: int = 10,
    ttl_seconds: float = 300.0,
) -> list[ObservationEvent]:
    visible: list[ObservationEvent] = []
    for event in events:
        if now - event.timestamp > ttl_seconds:
            continue
        if event.hidden and observer_name not in event.witnesses:
            continue
        if event.public or observer_name in event.witnesses:
            visible.append(event)
            continue
        if manhattan_distance(observer_x, observer_y, event.x, event.y) <= radius:
            visible.append(event)
    return visible
```

- [ ] **Step 4: Verify tests pass**

Run:

```powershell
python -m pytest tests/test_engine_observation.py -q -p no:cacheprovider
```

Expected:

```text
4 passed
```

## Task 2: Engine Observation Buffer

**Files:**

- Modify: `game_engine.py`
- Test: `tests/test_engine_foundation.py`

- [ ] **Step 1: Write failing tests for buffer append and decision packet**

Add tests:

```python
def test_engine_records_observation_event(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)

    event = engine._record_observation_event(
        event_type="action_start",
        subject="Arthur Burton",
        text="亚瑟开始检查库存。",
        x=5,
        y=5,
        public=False,
    )

    assert event.event_type == "action_start"
    assert engine._observation_events[-1].text == "亚瑟开始检查库存。"


def test_decision_packet_includes_nearby_observed_event(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)
    isabella = engine.agents["Isabella Rodriguez"]
    isabella.x = 6
    isabella.y = 5

    engine._record_observation_event(
        event_type="action_start",
        subject="Arthur Burton",
        text="亚瑟开始检查库存。",
        x=5,
        y=5,
        public=False,
    )

    packet = engine._build_observation_packet("Isabella Rodriguez", isabella)

    assert "亚瑟开始检查库存" in packet["observable_events_text"]
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_engine_records_observation_event tests/test_engine_foundation.py::test_decision_packet_includes_nearby_observed_event -q -p no:cacheprovider
```

Expected:

```text
AttributeError: 'WerewolfGameEngine' object has no attribute '_record_observation_event'
```

- [ ] **Step 3: Implement buffer helpers**

In `game_engine.py`:

- Import `ObservationEvent` and `filter_observable_events`.
- Initialize `self._observation_events = []` and `self._observation_event_id = 1`.
- Add `_record_observation_event(...)`.
- Add `_observable_events_for(name, agent)`.
- Add `_build_observation_packet(name, agent)`.

Required packet keys:

```python
{
    "self_state_text": "...",
    "nearby_people_text": "...",
    "nearby_objects_text": "...",
    "observable_events_text": "...",
    "public_world_text": "...",
}
```

- [ ] **Step 4: Verify focused tests pass**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_engine_records_observation_event tests/test_engine_foundation.py::test_decision_packet_includes_nearby_observed_event -q -p no:cacheprovider
```

Expected:

```text
2 passed
```

## Task 3: Decision Prompt Uses Observation Packet

**Files:**

- Modify: `agent.py`
- Modify: `game_engine.py`
- Test: `tests/test_prompt_boundaries.py`
- Test: `tests/test_engine_foundation.py`

- [ ] **Step 1: Write failing prompt test for no fictional customers**

Add a test that inspects `Agent.decide_next_action` prompt construction by monkeypatching `chat_for_agent`:

```python
def test_action_status_prompt_forbids_fictional_customers(monkeypatch):
    captured = {}

    def fake_chat(agent_name, system_prompt, user_prompt, **kwargs):
        captured["prompt"] = user_prompt
        return '{"action_type":"continue_current","target_location":"Hobbs Cafe","target_object":"counter","target_person":"","action":"整理咖啡馆柜台","action_status":"整理杯盘","thought":"店里没有客人，我先整理柜台。","expected_result":"准备营业","duration_minutes":10,"has_visible_clue_hint":false,"has_detective_hint":false}'

    monkeypatch.setattr("agent.chat_for_agent", fake_chat)

    npc = Agent("Isabella Rodriguez", "villager")
    npc.current_location = "Hobbs Cafe"
    npc.decide_next_action(
        game_hour=9,
        day=1,
        dead_list=[],
        nearby_info="周围10格内没有顾客或其他镇民。",
        scene_info="咖啡馆柜台、桌子、杯盘可见。",
    )

    assert "不得虚构客人" in captured["prompt"]
    assert "周围10格内没有顾客或其他镇民" in captured["prompt"]
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_prompt_boundaries.py::test_action_status_prompt_forbids_fictional_customers -q -p no:cacheprovider
```

Expected:

```text
AssertionError: assert '不得虚构客人' in ...
```

- [ ] **Step 3: Update prompt contract**

In `agent.py`, add explicit instructions:

```text
## 观察包
以下信息是你当前真实能看到、听到、记得的内容。你只能基于这些信息做判断，不得虚构附近不存在的人、顾客、物件或线索。

## 行动持续文案约束
action_status 必须只描述当前真实存在的人、物或事务。不得虚构客人、顾客、镇民、对方或不存在的目标。若周围没有可互动的人，只能写物件/职业相关的短任务。
```

- [ ] **Step 4: Pass observation packet into `decide_next_action`**

In the planning thread in `game_engine.py`, replace ad-hoc nearby strings with the new packet text while preserving existing `nearby_info` and `scene_info` compatibility.

Required behavior:

- `nearby_info` includes nearby people and observable event text.
- `scene_info` includes nearby objects and location facts.
- No hidden facts are included unless the NPC is an allowed witness.

- [ ] **Step 5: Verify prompt tests**

Run:

```powershell
python -m pytest tests/test_prompt_boundaries.py -q -p no:cacheprovider
```

Expected:

```text
all tests pass
```

## Task 4: Ground `action_status`

**Files:**

- Modify: `game_engine.py`
- Test: `tests/test_engine_foundation.py`

- [ ] **Step 1: Write failing tests for generic-person status fallback**

Add:

```python
def test_action_status_drops_customer_when_no_visible_person(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)
    isabella = engine.agents["Isabella Rodriguez"]
    isabella.name = "Isabella Rodriguez"
    isabella.current_location = "Hobbs Cafe"

    text = engine._action_status_text(
        isabella,
        {
            "action_status": "招呼客人",
            "action": "整理咖啡馆",
            "target_location": "Hobbs Cafe",
            "_visible_people": [],
        },
    )

    assert text == "整理杯盘"
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_action_status_drops_customer_when_no_visible_person -q -p no:cacheprovider
```

Expected:

```text
AssertionError: assert '招呼客人' == '整理杯盘'
```

- [ ] **Step 3: Implement grounding helper**

Add helper:

```python
GENERIC_PERSON_STATUS_WORDS = ("客人", "顾客", "镇民", "对方", "访客", "来客")

SAFE_ACTION_STATUS_BY_PERSON = {
    "Isabella Rodriguez": "整理杯盘",
    "Sam Moore": "擦拭吧台",
    "Arthur Burton": "检查库存",
    "Mei Lin": "整理书架",
    "Maria Lopez": "整理货架",
    "Jane Moreno": "修剪花枝",
    "Klaus Mueller": "整理讲义",
}
```

Behavior:

- If `action_status` contains generic-person words and `_visible_people` is empty, return the safe fallback.
- If visible people exist, allow the text.
- Keep existing cleanup rules that remove planning tails and speech prefixes.

- [ ] **Step 4: Verify focused tests pass**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_action_status_drops_customer_when_no_visible_person tests/test_engine_foundation.py::test_action_status_text_prefers_model_status_field -q -p no:cacheprovider
```

Expected:

```text
2 passed
```

## Task 5: Typed Memory Writes

**Files:**

- Modify: `agent.py`
- Test: `tests/test_memory_consolidation.py`

- [ ] **Step 1: Write failing typed memory tests**

Add:

```python
def test_add_typed_memory_updates_index(tmp_path):
    npc = Agent("Arthur Burton", "villager", base_dir=str(tmp_path))

    entry = npc.add_typed_memory(
        memory_type="thought",
        text="亚瑟认为伊莎贝拉可能看到了异常。",
        day=1,
        game_hour=10.5,
        subject="Arthur Burton",
        predicate="suspects",
        object="Isabella Rodriguez",
        importance=7,
        keywords=["亚瑟", "伊莎贝拉", "怀疑"],
        evidence=["obs_1"],
        source="reflection",
    )

    assert entry["type"] == "thought"
    assert entry["importance"] == 7
    assert "伊莎贝拉" in npc.read_memory()
    assert npc.memory_index[-1]["type"] == "thought"
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_memory_consolidation.py::test_add_typed_memory_updates_index -q -p no:cacheprovider
```

Expected:

```text
AttributeError: 'Agent' object has no attribute 'add_typed_memory'
```

- [ ] **Step 3: Implement typed memory helper**

In `agent.py`, add:

```python
def add_typed_memory(
    self,
    memory_type: str,
    text: str,
    day: int,
    game_hour: float = 0,
    subject: str = "",
    predicate: str = "",
    object: str = "",
    importance: int = 5,
    keywords: list[str] | None = None,
    evidence: list[str] | None = None,
    source: str = "manual",
    visibility: str = "private",
) -> dict:
    ...
```

Compatibility requirement:

- Still append readable text to `memory.md`.
- Extend `memory_index.json` with typed fields.
- Clamp importance to `1..10`.
- Do not break existing `add_memory`.

- [ ] **Step 4: Verify tests pass**

Run:

```powershell
python -m pytest tests/test_memory_consolidation.py::test_add_typed_memory_updates_index -q -p no:cacheprovider
```

Expected:

```text
1 passed
```

## Task 6: Memory Consolidation Queue

**Files:**

- Create: `engine_memory_queue.py`
- Modify: `game_engine.py`
- Test: `tests/test_memory_consolidation.py`

- [ ] **Step 1: Write failing queue tests**

Add:

```python
from engine_memory_queue import MemoryTask, MemoryQueue


def test_memory_queue_fifo_by_created_order():
    queue = MemoryQueue()
    queue.enqueue(MemoryTask(task_id="memq_1", agent_name="Arthur Burton", payload={"kind": "action"}))
    queue.enqueue(MemoryTask(task_id="memq_2", agent_name="Isabella Rodriguez", payload={"kind": "chat"}))

    assert queue.pop_next().task_id == "memq_1"
    assert queue.pop_next().task_id == "memq_2"
    assert queue.pop_next() is None
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_memory_consolidation.py::test_memory_queue_fifo_by_created_order -q -p no:cacheprovider
```

Expected:

```text
ModuleNotFoundError: No module named 'engine_memory_queue'
```

- [ ] **Step 3: Implement memory queue primitives**

Create `engine_memory_queue.py`:

```python
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import time


@dataclass
class MemoryTask:
    task_id: str
    agent_name: str
    payload: dict
    created_at: float = field(default_factory=time.time)


class MemoryQueue:
    def __init__(self) -> None:
        self._items: deque[MemoryTask] = deque()

    def enqueue(self, task: MemoryTask) -> None:
        self._items.append(task)

    def pop_next(self) -> MemoryTask | None:
        if not self._items:
            return None
        return self._items.popleft()

    def __len__(self) -> int:
        return len(self._items)
```

- [ ] **Step 4: Verify queue tests pass**

Run:

```powershell
python -m pytest tests/test_memory_consolidation.py::test_memory_queue_fifo_by_created_order -q -p no:cacheprovider
```

Expected:

```text
1 passed
```

## Task 7: Memory Consolidation Model Prompt

**Files:**

- Modify: `agent.py`
- Modify: `engine_memory_queue.py`
- Test: `tests/test_memory_consolidation.py`

- [ ] **Step 1: Write failing parser test**

Add:

```python
def test_parse_memory_consolidation_result():
    raw = """
    {
      "memories": [
        {
          "type": "thought",
          "text": "亚瑟认为伊莎贝拉可能注意到了他的异常。",
          "importance": 8,
          "keywords": ["亚瑟", "伊莎贝拉", "异常"],
          "subject": "Arthur Burton",
          "predicate": "suspects",
          "object": "Isabella Rodriguez"
        }
      ],
      "current_goal": "避免伊莎贝拉继续怀疑自己。"
    }
    """

    parsed = Agent.parse_memory_consolidation_result(raw)

    assert parsed["current_goal"] == "避免伊莎贝拉继续怀疑自己。"
    assert parsed["memories"][0]["type"] == "thought"
    assert parsed["memories"][0]["importance"] == 8
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_memory_consolidation.py::test_parse_memory_consolidation_result -q -p no:cacheprovider
```

Expected:

```text
AttributeError: type object 'Agent' has no attribute 'parse_memory_consolidation_result'
```

- [ ] **Step 3: Add consolidation contract**

Add parser and prompt helper in `agent.py`.

Prompt must include:

```text
你是 NPC 的记忆整理模块。你不会决定下一步行动，只决定哪些内容应沉淀为记忆。
输入包含：本轮观察、NPC 思考、计划、行动、行动结果、对话、旁观事件。
输出 JSON：
{
  "memories": [
    {
      "type": "event|chat|thought|plan",
      "text": "完整中文句子",
      "importance": 1-10,
      "keywords": ["..."],
      "subject": "...",
      "predicate": "...",
      "object": "..."
    }
  ],
  "current_goal": "短期目标；没有则空字符串"
}
```

Rules:

- Do not invent facts that are not in the input.
- Preserve important suspicion, fear, relationship, clue, and identity-risk facts.
- For werewolf-related facts, write them only if this NPC actually knows or witnessed them.
- Routine actions can be low importance or omitted.

- [ ] **Step 4: Verify parser tests pass**

Run:

```powershell
python -m pytest tests/test_memory_consolidation.py::test_parse_memory_consolidation_result -q -p no:cacheprovider
```

Expected:

```text
1 passed
```

## Task 8: Enqueue Memory After Actions

**Files:**

- Modify: `game_engine.py`
- Test: `tests/test_engine_foundation.py`

- [ ] **Step 1: Write failing action-memory enqueue test**

Add:

```python
def test_complete_action_enqueues_memory_task(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    arthur._pending_action = {
        "action_type": "inspect",
        "target_location": "Harvey Oak Supply Store",
        "target_object": "shelf",
        "action": "检查库存",
        "action_status": "检查库存",
        "thought": "需要确认工具是否齐全。",
        "expected_result": "掌握库存情况",
        "duration_minutes": 5,
    }

    engine._complete_agent_action("Arthur Burton", arthur)

    assert len(engine._memory_queue) == 1
    task = engine._memory_queue.pop_next()
    assert task.agent_name == "Arthur Burton"
    assert task.payload["kind"] == "action_completed"
    assert "需要确认工具是否齐全" in task.payload["thought"]
    assert "掌握库存情况" in task.payload["expected_result"]
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_complete_action_enqueues_memory_task -q -p no:cacheprovider
```

Expected:

```text
AttributeError: 'WerewolfGameEngine' object has no attribute '_memory_queue'
```

- [ ] **Step 3: Enqueue memory task**

In `game_engine.py`:

- Initialize `self._memory_queue = MemoryQueue()`.
- Add `_enqueue_memory_task(agent_name, payload)`.
- In `_complete_agent_action`, enqueue after action result is known.
- Keep existing direct `agent.add_memory(...)` during transition so current memory behavior does not regress.

Payload must include:

```python
{
    "kind": "action_completed",
    "observation_before": ...,
    "observation_after": ...,
    "thought": ...,
    "expected_result": ...,
    "action": ...,
    "action_result": ...,
    "visible_events": [...],
}
```

- [ ] **Step 4: Verify action enqueue test**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_complete_action_enqueues_memory_task -q -p no:cacheprovider
```

Expected:

```text
1 passed
```

## Task 9: Enqueue Memory After Conversations

**Files:**

- Modify: `game_engine.py`
- Test: `tests/test_engine_foundation.py`

- [ ] **Step 1: Write failing conversation-memory test**

Add:

```python
def test_npc_chat_completion_enqueues_memory_for_both_participants(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)

    engine._enqueue_conversation_memory(
        speaker="Arthur Burton",
        listener="Isabella Rodriguez",
        transcript=[
            ("Arthur Burton", "我看到五金店门口有人徘徊。"),
            ("Isabella Rodriguez", "这听起来很奇怪。"),
        ],
    )

    tasks = [engine._memory_queue.pop_next(), engine._memory_queue.pop_next()]

    assert {task.agent_name for task in tasks} == {"Arthur Burton", "Isabella Rodriguez"}
    assert all(task.payload["kind"] == "conversation_completed" for task in tasks)
    assert all("五金店门口有人徘徊" in str(task.payload["transcript"]) for task in tasks)
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_npc_chat_completion_enqueues_memory_for_both_participants -q -p no:cacheprovider
```

Expected:

```text
AttributeError: 'WerewolfGameEngine' object has no attribute '_enqueue_conversation_memory'
```

- [ ] **Step 3: Implement conversation memory enqueue**

Add `_enqueue_conversation_memory(...)` and call it when model-backed conversation finishes and transcript is available.

Memory lane should generate:

- `chat` memory: summary/transcript.
- `thought` memory: what this NPC should remember for future planning.
- Optional `current_goal`: if the conversation changes intent.

- [ ] **Step 4: Verify conversation enqueue test**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_npc_chat_completion_enqueues_memory_for_both_participants -q -p no:cacheprovider
```

Expected:

```text
1 passed
```

## Task 10: Memory Lane Worker

**Files:**

- Modify: `game_engine.py`
- Modify: `agent.py`
- Test: `tests/test_memory_consolidation.py`

- [ ] **Step 1: Write failing integration test with fake model**

Add:

```python
def test_memory_lane_writes_thought_memory(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    written = []

    def fake_consolidate(payload):
        return {
            "memories": [
                {
                    "type": "thought",
                    "text": "亚瑟认为伊莎贝拉可能已经注意到他的异常。",
                    "importance": 8,
                    "keywords": ["亚瑟", "伊莎贝拉", "异常"],
                    "subject": "Arthur Burton",
                    "predicate": "suspects",
                    "object": "Isabella Rodriguez",
                }
            ],
            "current_goal": "避免伊莎贝拉继续怀疑自己。",
        }

    monkeypatch.setattr(arthur, "consolidate_memory", fake_consolidate)
    monkeypatch.setattr(arthur, "add_typed_memory", lambda **kwargs: written.append(kwargs) or kwargs)

    engine._enqueue_memory_task("Arthur Burton", {"kind": "action_completed"})
    engine._process_next_memory_task()

    assert written[0]["memory_type"] == "thought"
    assert "伊莎贝拉" in written[0]["text"]
    assert arthur.scratch["currently"] == "避免伊莎贝拉继续怀疑自己。"
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_memory_consolidation.py::test_memory_lane_writes_thought_memory -q -p no:cacheprovider
```

Expected:

```text
AttributeError: 'WerewolfGameEngine' object has no attribute '_process_next_memory_task'
```

- [ ] **Step 3: Implement non-blocking memory worker**

Requirements:

- Only one memory task processes at a time.
- Memory lane uses the same provider config but lower priority than decision and conversation.
- If model fails, keep direct action memory already written and log a non-player-visible error.
- Do not create blue bubbles from memory lane.
- Do not change NPC runtime_state to thinking/planning/acting.

- [ ] **Step 4: Verify integration test**

Run:

```powershell
python -m pytest tests/test_memory_consolidation.py::test_memory_lane_writes_thought_memory -q -p no:cacheprovider
```

Expected:

```text
1 passed
```

## Task 11: Thought And Plan Persistence

**Files:**

- Modify: `game_engine.py`
- Modify: `agent.py`
- Test: `tests/test_memory_consolidation.py`

- [ ] **Step 1: Write failing test that decision thought enters memory task**

Add:

```python
def test_decision_thought_and_plan_are_in_memory_payload(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    arthur._pending_action = {
        "action_type": "continue_current",
        "target_location": "Harvey Oak Supply Store",
        "action": "整理柜台工具",
        "action_status": "检查库存",
        "thought": "我担心今天需要更多工具，所以先确认库存。",
        "expected_result": "确保营业前工具齐全",
        "duration_minutes": 5,
    }

    engine._complete_agent_action("Arthur Burton", arthur)

    task = engine._memory_queue.pop_next()
    assert task.payload["thought"] == "我担心今天需要更多工具，所以先确认库存。"
    assert task.payload["expected_result"] == "确保营业前工具齐全"
```

- [ ] **Step 2: Implement payload preservation**

Ensure pending action keeps:

- `thought`
- `expected_result`
- `action`
- `action_status`
- `target_location`
- `target_object`
- `target_person`
- `duration_minutes`

until memory task payload is created.

- [ ] **Step 3: Verify tests pass**

Run:

```powershell
python -m pytest tests/test_memory_consolidation.py::test_decision_thought_and_plan_are_in_memory_payload -q -p no:cacheprovider
```

Expected:

```text
1 passed
```

## Task 12: Public And Witnessed Events

**Files:**

- Modify: `game_engine.py`
- Test: `tests/test_engine_observation.py`
- Test: `tests/test_game_engine_night_loop.py`
- Test: `tests/test_vote_flow.py`

- [ ] **Step 1: Add event emission tests for public events**

Add tests that public announcements are recorded:

- Body discovery.
- Dusk vote result.
- Night death public announcement.

Expected:

- Eligible NPCs receive public event in observation packet.
- Hidden killer identity is not included.

- [ ] **Step 2: Add witnessed hidden fact test**

Add a test where an NPC directly observes a hidden fact within radius and is added as witness.

Expected:

- The witness can retrieve it.
- Non-witnesses cannot retrieve it, even within radius.

- [ ] **Step 3: Implement event emissions**

Record observation events at these backend moments:

- NPC starts action.
- NPC completes action.
- NPC speech bubble is created.
- NPC conversation completes.
- Detective asks a question.
- NPC answers Crow.
- Body is discovered.
- Clue is discovered or delivered.
- Dusk vote result is announced.
- Night death is publicly announced.

- [ ] **Step 4: Verify public/hidden tests**

Run:

```powershell
python -m pytest tests/test_engine_observation.py tests/test_game_engine_night_loop.py tests/test_vote_flow.py -q -p no:cacheprovider
```

Expected:

```text
all tests pass
```

## Task 13: UI And Log Clarification

**Files:**

- Modify: `ui/templates/index.html`
- Test: `tests/test_ui_bubble_layout.py`

- [ ] **Step 1: Keep waiting-state separate from real thought**

Add or preserve UI test:

```python
def test_thought_waiting_text_is_not_treated_as_real_model_thought():
    html = Path("ui/templates/index.html").read_text(encoding="utf-8")

    assert "正在整理当前情况" not in html or "waiting" in html
    assert "thought_summary || p.thought" in html
```

Expected:

- Waiting text can exist only as transient pending display.
- Logs and memory must use real model `thought`, not waiting text.

- [ ] **Step 2: Ensure logs use the agreed color taxonomy**

Keep current taxonomy:

- Purple: blue-bubble lifecycle content, including thought/plan/action-start.
- Bright green: NPC speech, white bubbles, action duration, action result.
- Gold: system.
- Red: error, kill, raw/debug model output.

- [ ] **Step 3: Verify UI tests**

Run:

```powershell
python -m pytest tests/test_ui_bubble_layout.py -q -p no:cacheprovider
```

Expected:

```text
all tests pass
```

## Task 14: Documentation Sync

**Files:**

- Modify: `USER_REQUIREMENTS_LEDGER.md`
- Modify: `NPC_BEHAVIOR_LIFECYCLE.md`
- Modify: `CURRENT_SPRINT.md`
- Modify: `BUG_BACKLOG.md` if this work is started from a bug report.

- [ ] **Step 1: Add stable requirements**

Record:

- Observation radius is `10`.
- Observation packet feeds decision planning.
- Thought/plan are real cognitive outputs and must be eligible for memory consolidation.
- Memory lane is the third model lane and must not block action/conversation.
- Action-status text must be grounded in visible/known people and objects.

- [ ] **Step 2: Update lifecycle doc**

Add lifecycle:

```text
observation packet -> decision model -> visible thought/plan/action -> action execution
ordinary action -> memory queue
real chat action -> conversation model -> speech bubble -> memory queue
memory queue -> event/chat/thought/plan memory -> future retrieval
```

- [ ] **Step 3: Update sprint status**

Add this plan path and implementation state.

## Task 15: Verification

**Files:**

- No new files.

- [ ] **Step 1: Syntax check**

Run:

```powershell
python -m py_compile agent.py game_engine.py llm.py ui/app.py engine_navigation.py engine_tasks.py engine_bubbles.py engine_dusk.py engine_observation.py engine_memory_queue.py
```

Expected:

```text
no output and exit code 0
```

- [ ] **Step 2: Focused tests**

Run:

```powershell
python -m pytest tests/test_engine_observation.py tests/test_memory_consolidation.py tests/test_prompt_boundaries.py tests/test_engine_foundation.py tests/test_daytime_npc_behavior.py tests/test_ui_bubble_layout.py -q -p no:cacheprovider
```

Expected:

```text
all tests pass
```

- [ ] **Step 3: Full tests**

Run:

```powershell
python -m pytest tests -q -p no:cacheprovider
```

Expected:

```text
all tests pass
```

- [ ] **Step 4: Browser verification**

Restart service and verify:

- NPC thought/plan blue bubble shows real model content or an explicit waiting state.
- Ordinary action white bubble is grounded: no "招呼客人" if no customer/person is nearby.
- Real conversation uses the conversation lane and white speech bubbles.
- Logs keep agreed colors.
- Frontend displays the updated version number.

## Worker Split

Recommended split:

- Worker A: `engine_observation.py`, observation tests, engine buffer helpers.
- Worker B: `agent.py` prompt and typed memory helpers, memory parser tests.
- Worker C: `engine_memory_queue.py`, memory-lane queue and integration tests.
- Worker D: UI/log tests and waiting-state display checks.
- Main agent: integrate `game_engine.py`, review all worker diffs, run full tests, browser verify, update docs.

Worker restrictions:

- Do not modify `personas/`.
- Do not run tests that write runtime persona memory unless explicitly authorized.
- Do not change game rules, role logic, voting, night kill, or silver systems.
- Do not expose hidden facts in player-visible UI or ordinary NPC prompts.

## Acceptance Criteria

- NPC decision prompt always receives a grounded observation packet.
- Observation radius defaults to `10`.
- Nearby speech/action events can enter an NPC's decision context if visible/hearable.
- Hidden facts require witness/public permission before entering observation or memory.
- `thought` and `expected_result/plan` are preserved into memory-lane payloads.
- Memory lane can write typed `event`, `chat`, `thought`, and `plan` memories.
- Conversation completion creates memory tasks for both participants.
- Action completion creates memory tasks including observation, thought, plan, action result, and visible nearby events.
- Action-status text cannot mention nonexistent customers/people.
- Ordinary action execution still does not call the decision model.
- Conversation remains the only action-line model call.
- Memory consolidation does not create blue bubbles or block planning/conversation lanes.
- Existing full pytest suite passes.

## Open Product Decisions

These are implementation knobs, not blockers:

- Whether `plan` should be a separate memory type or `thought` with `subtype="plan"`.
- Whether memory lane should run one global FIFO queue or one per-NPC queue with round-robin fairness.
- Whether ordinary low-importance routine actions should still create typed memory nodes or only update `action_history`.
- Whether overheard speech should store full transcript or model-generated summary only.

## Execution Recommendation

Start with Tasks 1-4 before touching memory consolidation. Those tasks fix the visible illogical behavior and create the observation foundation. Then implement Tasks 5-11 to restore the deeper Smallville-style memory/thought loop.

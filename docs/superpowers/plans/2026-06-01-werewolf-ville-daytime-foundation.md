# Werewolf Ville Daytime Simulation Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stable director-view daytime simulation with randomized runtime roles and models, map-aligned personas, an initial body, body-site gathering, structured clues, and clue delivery.

**Architecture:** Introduce focused rules modules alongside the existing engine. `world_config.py` owns stable map-valid character and location definitions. `simulation_events.py` owns structured bodies and clues. `game_engine.py` orchestrates these modules while retaining the existing Flask and Phaser integration.

**Tech Stack:** Python 3.10, dataclasses, Flask-SocketIO, Phaser 3, pytest

---

## File Structure

- Create `world_config.py`: map-valid landmarks, active residents, model pool, ambient sprite names, fallback routines.
- Create `simulation_events.py`: structured `BodyRecord`, `ClueRecord`, and clue-delivery helpers.
- Create `tests/test_world_config.py`: configuration validation and randomized assignment tests.
- Create `tests/test_simulation_events.py`: body and clue lifecycle tests.
- Create `tests/test_game_engine_foundation.py`: engine-level initialization, gathering, and status serialization tests.
- Modify `config.yaml`: replace fixed per-character model assignment and fixed werewolf character with runtime pools.
- Modify `agent.py`: accept runtime model assignment and runtime role injection; keep base persona neutral.
- Modify `game_engine.py`: use structured config, randomize assignments, spawn initial body, gather at body site, expose bodies and clues.
- Modify `ui/templates/index.html`: render bodies and clue bulbs in director view.
- Modify `create_villagers.py`: generate neutral map-aligned persona definitions.

### Task 1: Add Validated World Configuration

**Files:**
- Create: `world_config.py`
- Create: `tests/test_world_config.py`
- Modify: `config.yaml`

- [ ] **Step 1: Write failing configuration tests**

```python
# tests/test_world_config.py
from world_config import ACTIVE_CHARACTERS, PUBLIC_LANDMARKS, validate_world_config


def test_active_characters_use_map_valid_primary_locations():
    validate_world_config()
    assert len(ACTIVE_CHARACTERS) == 6
    for character in ACTIVE_CHARACTERS.values():
        if character["role"] != "detective":
            assert character["primary_location"] in PUBLIC_LANDMARKS


def test_only_crow_is_detective():
    detectives = [
        name for name, cfg in ACTIVE_CHARACTERS.items()
        if cfg["role"] == "detective"
    ]
    assert detectives == ["Crow"]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_world_config.py -v`

Expected: FAIL because `world_config` does not exist.

- [ ] **Step 3: Add `world_config.py`**

```python
PUBLIC_LANDMARKS = {
    "Hobbs Cafe": {"x": 77, "y": 21},
    "The Rose and Crown Pub": {"x": 57, "y": 22},
    "Oak Hill College": {"x": 118, "y": 41},
    "The Willows Market and Pharmacy": {"x": 84, "y": 47},
    "Harvey Oak Supply Store": {"x": 63, "y": 47},
    "Johnson Park": {"x": 27, "y": 46},
}

ACTIVE_CHARACTERS = {
    "Arthur Burton": {
        "role": "resident",
        "job": "hardware store owner and tool repairer",
        "primary_location": "Harvey Oak Supply Store",
        "home": {"x": 57, "y": 15},
    },
    "Crow": {
        "role": "detective",
        "job": "detective",
        "primary_location": "Johnson Park",
        "home": {"x": 57, "y": 22},
    },
    "Isabella Rodriguez": {
        "role": "resident",
        "job": "cafe owner",
        "primary_location": "Hobbs Cafe",
        "home": {"x": 77, "y": 14},
    },
    "Klaus Mueller": {
        "role": "resident",
        "job": "college lecturer",
        "primary_location": "Oak Hill College",
        "home": {"x": 129, "y": 46},
    },
    "Maria Lopez": {
        "role": "resident",
        "job": "market and pharmacy clerk",
        "primary_location": "The Willows Market and Pharmacy",
        "home": {"x": 124, "y": 54},
    },
    "Sam Moore": {
        "role": "resident",
        "job": "pub owner and bartender",
        "primary_location": "The Rose and Crown Pub",
        "home": {"x": 37, "y": 64},
    },
}

AMBIENT_RESIDENT_SPRITES = [
    "Abigail Chen", "Adam Smith", "Ayesha Khan", "Carlos Gomez",
    "Carmen Ortiz", "Eddy Lin", "Francisco Lopez", "Giorgio Rossi",
    "Hailey Johnson", "Jane Moreno", "Jennifer Moore", "John Lin",
    "Latoya Williams", "Mei Lin", "Rajiv Patel", "Ryan Park",
    "Tamara Taylor", "Tom Moreno", "Wolfgang Schulz", "Yuriko Yamamoto",
]


def validate_world_config():
    assert len(ACTIVE_CHARACTERS) == 6
    assert ACTIVE_CHARACTERS["Crow"]["role"] == "detective"
    for name, character in ACTIVE_CHARACTERS.items():
        if name != "Crow":
            assert character["role"] == "resident"
            assert character["primary_location"] in PUBLIC_LANDMARKS
```

- [ ] **Step 4: Replace fixed configuration with runtime pools**

```yaml
# config.yaml
llm:
  available_models:
    - "GLM-5.1"
    - "Kimi-K2.6"
    - "Qwen3.5-Flash"
    - "Qwen3.6-35B-A3B"
    - "deepseek-v4-flash"
    - "MiMo-V2.5-Pro"

werewolf:
  randomize_each_game: true
  kill_detective_last: true
```

Remove `llm.agent_models` and `werewolf.character`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_world_config.py -v`

Expected: PASS.

### Task 2: Add Runtime Assignment And Neutral Personas

**Files:**
- Modify: `llm.py`
- Modify: `agent.py`
- Modify: `create_villagers.py`
- Create: `tests/test_runtime_roles.py`

- [ ] **Step 1: Write failing role and model assignment tests**

```python
# tests/test_runtime_roles.py
from agent import Agent
from llm import get_model_for_agent, set_runtime_model_assignments


def test_agent_uses_runtime_model_assignment(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.PERSONAS_DIR", str(tmp_path))
    resident = Agent("Arthur Burton", role="villager", model="Model-B")
    assert resident.model == "Model-B"


def test_runtime_werewolf_prompt_is_not_in_neutral_soul(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.PERSONAS_DIR", str(tmp_path))
    resident = Agent("Arthur Burton", role="werewolf", model="Model-A")
    resident.init_files()
    resident.write_soul("# Arthur Burton\nHardware store owner.")
    assert "狼人" not in resident.read_soul()
    assert "隐藏身份" in resident.get_runtime_role_prompt()


def test_llm_layer_uses_runtime_model_assignment():
    set_runtime_model_assignments({"Arthur Burton": "Model-C"})
    assert get_model_for_agent("Arthur Burton") == "Model-C"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_runtime_roles.py -v`

Expected: FAIL because `Agent` does not accept `model`, `write_soul`, or `get_runtime_role_prompt`, and the LLM layer has no runtime assignment registration.

- [ ] **Step 3: Add runtime model registration in the LLM layer**

```python
# llm.py
_RUNTIME_AGENT_MODEL_MAP = {}


def set_runtime_model_assignments(assignments: dict[str, str]):
    _RUNTIME_AGENT_MODEL_MAP.clear()
    _RUNTIME_AGENT_MODEL_MAP.update(assignments)


def get_model_for_agent(agent_name: str) -> str:
    return _RUNTIME_AGENT_MODEL_MAP.get(
        agent_name,
        _AGENT_MODEL_MAP.get(agent_name, _DEFAULT_MODEL),
    )
```

- [ ] **Step 4: Add runtime model and role prompt support**

```python
# agent.py
def __init__(self, name: str, role: str = "villager", model: str = ""):
    self.name = name
    self.role = role
    self.model = model or get_model_for_agent(name)
    ...

def write_soul(self, content: str):
    self._write_md("soul.md", content)

def get_runtime_role_prompt(self) -> str:
    if self.role == "werewolf":
        return (
            "你的隐藏目标：隐藏身份，白天维持正常生活，掩盖异常轨迹。"
            "夜间必须选择目标并完成一次击杀。除非其他居民全部死亡，不得杀害Crow。"
        )
    if self.role == "detective":
        return "你的目标：调查事实线索，找出隐藏的狼人。"
    return (
        "你的目标：优先维持正常生活。发现异常时保留事实线索，"
        "必要时调查，并在Crow询问时如实提供你知道的内容。"
    )
```

Use `self.get_runtime_role_prompt()` inside `generate_response()`, `generate_daily_plan()`, `reflect()`, and `decide_next_action()`.

- [ ] **Step 5: Neutralize generated personas**

In `create_villagers.py`, replace map-invalid occupations and remove fixed werewolf text:

```python
"Arthur_Burton": {
    "job": "五金店老板与工具维修员",
    "location": "Harvey Oak Supply Store",
    "goals": "经营五金店，为居民维修工具，留意小镇异常。",
},
"Maria_Lopez": {
    "job": "市场与药房店员",
    "location": "The Willows Market and Pharmacy",
    "goals": "经营市场与药房柜台，留意顾客带来的消息。",
},
"Sam_Moore": {
    "job": "酒吧老板与调酒师",
    "location": "The Rose and Crown Pub",
    "goals": "经营酒吧，接待客人，留意夜间异常。",
},
```

Remove every fixed reference that says Arthur is the werewolf and remove map-invalid dock, fishing, bakery, forge, and blacksmith-shop facts.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_runtime_roles.py -v`

Expected: PASS.

### Task 3: Add Structured Bodies And Clues

**Files:**
- Create: `simulation_events.py`
- Create: `tests/test_simulation_events.py`

- [ ] **Step 1: Write failing event lifecycle tests**

```python
# tests/test_simulation_events.py
from llm import set_runtime_model_assignments
from simulation_events import BodyRecord, ClueRecord, undelivered_clues_for


def test_clue_remains_pending_until_delivered():
    clue = ClueRecord(
        clue_id="clue-1",
        clue_type="witness",
        summary="Saw someone leave Johnson Park at 23:40.",
        source="Isabella Rodriguez",
        related_person="",
        location="Johnson Park",
        created_day=1,
    )
    assert undelivered_clues_for([clue], "Isabella Rodriguez") == [clue]
    clue.delivered_to_crow = True
    assert undelivered_clues_for([clue], "Isabella Rodriguez") == []


def test_body_serialization_is_ui_ready():
    body = BodyRecord("body-1", "Ayesha Khan", "Johnson Park", 27, 46, 0)
    assert body.to_status()["sprite_key"] == "Ayesha_Khan"
    assert body.to_status()["alive"] is False
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_simulation_events.py -v`

Expected: FAIL because `simulation_events` does not exist.

- [ ] **Step 3: Add structured event dataclasses**

```python
# simulation_events.py
from dataclasses import asdict, dataclass


@dataclass
class BodyRecord:
    body_id: str
    victim_name: str
    location: str
    x: int
    y: int
    created_day: int
    discovered: bool = False

    def to_status(self) -> dict:
        data = asdict(self)
        data["sprite_key"] = self.victim_name.replace(" ", "_")
        data["alive"] = False
        return data


@dataclass
class ClueRecord:
    clue_id: str
    clue_type: str
    summary: str
    source: str
    related_person: str
    location: str
    created_day: int
    delivered_to_crow: bool = False


def undelivered_clues_for(clues: list[ClueRecord], source: str) -> list[ClueRecord]:
    return [
        clue for clue in clues
        if clue.source == source and not clue.delivered_to_crow
    ]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_simulation_events.py -v`

Expected: PASS.

### Task 4: Randomize New-Game Assignments And Spawn Initial Body

**Files:**
- Modify: `game_engine.py`
- Create: `tests/test_game_engine_foundation.py`

- [ ] **Step 1: Write failing engine initialization tests**

```python
# tests/test_game_engine_foundation.py
from game_engine import WerewolfGameEngine


def test_new_game_randomizes_one_resident_werewolf():
    game = WerewolfGameEngine(random_seed=11)
    assert game.werewolf_name in game.resident_names
    assert game.werewolf_name != game.detective_name
    assert sum(a.role == "werewolf" for a in game.agents.values()) == 1


def test_new_game_assigns_six_unique_models():
    game = WerewolfGameEngine(random_seed=11)
    assigned = [a.model for a in game.agents.values()]
    assert len(assigned) == 6
    assert len(set(assigned)) == 6


def test_new_game_has_discovered_initial_body():
    game = WerewolfGameEngine(random_seed=11)
    assert len(game.bodies) == 1
    assert game.bodies[0].discovered is True
    assert game.gathering_site == (game.bodies[0].x, game.bodies[0].y)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_game_engine_foundation.py -v`

Expected: FAIL because the engine has no `random_seed`, `bodies`, `resident_names`, or `gathering_site`.

- [ ] **Step 3: Add runtime initialization**

In `game_engine.py`:

```python
from simulation_events import BodyRecord, ClueRecord, undelivered_clues_for
from world_config import ACTIVE_CHARACTERS, AMBIENT_RESIDENT_SPRITES, PUBLIC_LANDMARKS


def __init__(self, random_seed=None):
    self._rng = random.Random(random_seed)
    self.detective_name = "Crow"
    self.resident_names = [name for name in ACTIVE_CHARACTERS if name != self.detective_name]
    self.werewolf_name = self._rng.choice(self.resident_names)
    self.model_assignments = self._build_model_assignments()
    set_runtime_model_assignments(self.model_assignments)
    self.bodies = []
    self.clues = []
    self.gathering_site = None
    ...

def _build_model_assignments(self) -> dict:
    models = list(CONFIG["llm"]["available_models"])
    names = list(ACTIVE_CHARACTERS)
    self._rng.shuffle(models)
    return dict(zip(names, models))

def _spawn_initial_body(self):
    victim = self._rng.choice(AMBIENT_RESIDENT_SPRITES)
    site = PUBLIC_LANDMARKS["Johnson Park"]
    body = BodyRecord("body-initial", victim, "Johnson Park", site["x"], site["y"], 0, True)
    self.bodies.append(body)
    self.gathering_site = (body.x, body.y)
```

In `_init_agents()`, instantiate each agent with its runtime role and `self.model_assignments[name]`. Call `_spawn_initial_body()` before `_init_gathering()`.

- [ ] **Step 4: Make gathering use `self.gathering_site`**

Replace the fixed gathering position `(57, 35)` with `self.gathering_site` and place each active sprite around the body with a small radius.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_game_engine_foundation.py -v`

Expected: PASS.

### Task 5: Add Clue Bulbs And Crow Delivery

**Files:**
- Modify: `game_engine.py`
- Modify: `ui/templates/index.html`
- Modify: `tests/test_game_engine_foundation.py`

- [ ] **Step 1: Add failing delivery tests**

```python
# tests/test_game_engine_foundation.py
def test_status_exposes_pending_clue_bulb_and_delivery_clears_it():
    game = WerewolfGameEngine(random_seed=11)
    game._add_clue(
        clue_type="witness",
        summary="Saw someone leave Johnson Park late at night.",
        source="Isabella Rodriguez",
        related_person="",
        location="Johnson Park",
    )
    before = game.get_status()
    assert before["personas"]["Isabella Rodriguez"]["has_new_clue"] is True

    result = game.deliver_clues_to_detective("Isabella Rodriguez")
    assert result["delivered_count"] == 1
    after = game.get_status()
    assert after["personas"]["Isabella Rodriguez"]["has_new_clue"] is False
```

- [ ] **Step 2: Run test and verify failure**

Run: `pytest tests/test_game_engine_foundation.py::test_status_exposes_pending_clue_bulb_and_delivery_clears_it -v`

Expected: FAIL because clue helpers do not exist.

- [ ] **Step 3: Add clue helpers and status fields**

```python
# game_engine.py
def _add_clue(self, clue_type, summary, source, related_person, location):
    clue = ClueRecord(
        clue_id=f"clue-{len(self.clues) + 1}",
        clue_type=clue_type,
        summary=summary,
        source=source,
        related_person=related_person,
        location=location,
        created_day=self.day,
    )
    self.clues.append(clue)
    return clue

def deliver_clues_to_detective(self, source):
    pending = undelivered_clues_for(self.clues, source)
    for clue in pending:
        clue.delivered_to_crow = True
        self.agents[self.detective_name].add_notebook_entry(
            f"{source} 提供线索：{clue.summary}", self.day
        )
    return {"delivered_count": len(pending), "clues": [c.summary for c in pending]}
```

In `detective_chat()`, deliver pending clues from the target before returning. In `get_status()`, add:

```python
"has_new_clue": bool(undelivered_clues_for(self.clues, name)),
"pending_clue_count": len(undelivered_clues_for(self.clues, name)),
"thought": getattr(agent, "current_thought", ""),
"true_role": agent.role,
```

Add top-level body serialization:

```python
"bodies": [body.to_status() for body in self.bodies],
"director": {
    "werewolf_name": self.werewolf_name,
    "model_assignments": dict(self.model_assignments),
},
```

- [ ] **Step 4: Render clue bulbs and bodies**

In `ui/templates/index.html`, add:

```javascript
const bodySprites = {};

function renderClueIndicator(name, persona) {
  return persona.has_new_clue
    ? `<span class="clue-indicator" title="有尚未获取的新线索">💡</span>`
    : "";
}
```

Include `renderClueIndicator(name, p)` inside each agent card and refresh it during `updateAgentList()`.

During Phaser `preload()`, load ambient resident sprite assets from the upstream-derived local folder `static/assets/characters/` so any selected body sprite is available. Load body sprites from `state.bodies`, rotate them by `Math.PI / 2`, apply `setTint(0x777777)`, and place them at `body.x * TILE_W`, `body.y * TILE_W`.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_simulation_events.py tests/test_game_engine_foundation.py -v`

Expected: PASS.

### Task 6: Enforce Closed-World Daytime Decisions

**Files:**
- Modify: `agent.py`
- Modify: `game_engine.py`
- Modify: `tests/test_game_engine_foundation.py`

- [ ] **Step 1: Add failing validation tests**

```python
# tests/test_game_engine_foundation.py
def test_unknown_model_location_does_not_become_world_state():
    game = WerewolfGameEngine(random_seed=11)
    normalized = game._normalize_destination("码头")
    assert normalized is None


def test_known_alias_normalizes_to_existing_landmark():
    game = WerewolfGameEngine(random_seed=11)
    assert game._normalize_destination("hardware store") == "Harvey Oak Supply Store"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_game_engine_foundation.py::test_unknown_model_location_does_not_become_world_state tests/test_game_engine_foundation.py::test_known_alias_normalizes_to_existing_landmark -v`

Expected: FAIL because `_normalize_destination` does not exist.

- [ ] **Step 3: Add destination normalization**

```python
# game_engine.py
DESTINATION_ALIASES = {
    "cafe": "Hobbs Cafe",
    "coffee": "Hobbs Cafe",
    "pub": "The Rose and Crown Pub",
    "bar": "The Rose and Crown Pub",
    "college": "Oak Hill College",
    "school": "Oak Hill College",
    "market": "The Willows Market and Pharmacy",
    "pharmacy": "The Willows Market and Pharmacy",
    "hardware": "Harvey Oak Supply Store",
    "supply": "Harvey Oak Supply Store",
    "park": "Johnson Park",
    "home": "home",
}

def _normalize_destination(self, raw_location):
    value = str(raw_location or "").strip().lower()
    if value == "home":
        return "home"
    for landmark in PUBLIC_LANDMARKS:
        if value == landmark.lower():
            return landmark
    for alias, landmark in DESTINATION_ALIASES.items():
        if alias in value:
            return landmark
    return None
```

Use `_normalize_destination()` before mutating target location in gathering and LLM action handling. Invalid free-form destinations trigger a profession fallback action.

- [ ] **Step 4: Restrict model prompt vocabulary**

In `agent.py`, construct legal destinations from `world_config.PUBLIC_LANDMARKS` rather than hard-coded prose. State explicitly that model-created locations and facts will be rejected.

- [ ] **Step 5: Run tests**

Run: `pytest tests -v`

Expected: PASS.

### Task 7: Verify The Daytime Foundation

**Files:**
- Modify: `TASK.md`

- [ ] **Step 1: Compile Python sources**

Run: `python -m py_compile main.py ui/app.py game_engine.py agent.py llm.py world_config.py simulation_events.py`

Expected: exit code `0`.

- [ ] **Step 2: Run automated tests**

Run: `pytest tests -v`

Expected: PASS.

- [ ] **Step 3: Start or restart the service**

Run: `python main.py`

Expected: server listens on `http://127.0.0.1:5000/`.

- [ ] **Step 4: Verify multiple fresh games**

For at least three resets:

- inspect `/api/status`;
- record `werewolf_name` in director view;
- record each persona model;
- confirm exactly one body exists;
- confirm all residents gather near the body and later disperse;
- confirm all executable locations are map-valid.

- [ ] **Step 5: Verify clue delivery manually**

Inject or naturally create one clue for Isabella, confirm her card shows `💡`, move Crow near her, chat once, and confirm the bulb clears and Crow's notebook receives the clue.

- [ ] **Step 6: Update progress board**

Record the completed daytime foundation checks in `TASK.md`. Do not mark night-hunt work complete.

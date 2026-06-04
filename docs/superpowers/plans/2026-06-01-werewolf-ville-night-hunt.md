# Werewolf Ville Physical Night Hunt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace immediate night kill settlement with a five-minute physical hunt that dynamically replans, kills exactly one eligible resident, generates factual clues, and starts the next body-site gathering.

**Architecture:** Add a focused `night_hunt.py` rules module. The existing engine delegates night target scoring, deadline pressure, hunt transitions, and clue generation to a serializable hunt state while continuing to own map movement and WebSocket status broadcasting.

**Tech Stack:** Python 3.10, dataclasses, existing BFS pathfinding, Flask-SocketIO, Phaser 3, pytest

---

## File Structure

- Create `night_hunt.py`: hunt state, target scoring, deadline escalation, witness-based clue generation.
- Create `tests/test_night_hunt.py`: target and clue rules.
- Create `tests/test_game_engine_night_loop.py`: engine night loop and morning gathering tests.
- Modify `game_engine.py`: phase orchestration, resident night routines, physical werewolf movement, kill and withdrawal.
- Modify `agent.py`: text-only legal target selection prompt.
- Modify `config.yaml`: night timing and escalation thresholds.
- Modify `ui/templates/index.html`: director-view hunt status.

### Task 1: Add Night Hunt Rules

**Files:**
- Create: `night_hunt.py`
- Create: `tests/test_night_hunt.py`

- [ ] **Step 1: Write failing target-score tests**

```python
# tests/test_night_hunt.py
from night_hunt import HuntCandidate, choose_forced_target


def test_forced_target_prefers_reachable_low_risk_resident():
    candidates = [
        HuntCandidate("Far Resident", 80, 3, True),
        HuntCandidate("Near Resident", 12, 1, True),
    ]
    assert choose_forced_target(candidates).name == "Near Resident"


def test_unreachable_target_is_not_selected():
    candidates = [
        HuntCandidate("Blocked", 1, 0, False),
        HuntCandidate("Reachable", 30, 2, True),
    ]
    assert choose_forced_target(candidates).name == "Reachable"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/test_night_hunt.py -v`

Expected: FAIL because `night_hunt` does not exist.

- [ ] **Step 3: Add rules module**

```python
# night_hunt.py
from dataclasses import dataclass, field


@dataclass
class HuntCandidate:
    name: str
    path_length: int
    witness_risk: int
    reachable: bool

    @property
    def score(self) -> int:
        return self.path_length + self.witness_risk * 20


@dataclass
class NightHuntState:
    started_at: float
    deadline_at: float
    stage: str = "choosing"
    target_name: str = ""
    target_changes: list[str] = field(default_factory=list)
    witnessed_by: set[str] = field(default_factory=set)
    killed_name: str = ""
    withdrawal_complete: bool = False


def choose_forced_target(candidates: list[HuntCandidate]) -> HuntCandidate | None:
    reachable = [candidate for candidate in candidates if candidate.reachable]
    return min(reachable, key=lambda candidate: candidate.score, default=None)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_night_hunt.py -v`

Expected: PASS.

### Task 2: Start Night Without Immediate Kill

**Files:**
- Modify: `config.yaml`
- Modify: `game_engine.py`
- Create: `tests/test_game_engine_night_loop.py`

- [ ] **Step 1: Write failing transition test**

```python
# tests/test_game_engine_night_loop.py
from game_engine import GamePhase, WerewolfGameEngine


def test_enter_night_starts_hunt_without_immediate_kill():
    game = WerewolfGameEngine(random_seed=11)
    before = list(game.dead_list)
    game._transition_to_night()
    assert game.phase == GamePhase.NIGHT
    assert game.dead_list == before
    assert game.night_hunt.stage == "choosing"
```

- [ ] **Step 2: Run test and verify failure**

Run: `pytest tests/test_game_engine_night_loop.py::test_enter_night_starts_hunt_without_immediate_kill -v`

Expected: FAIL because transition still calls immediate kill settlement.

- [ ] **Step 3: Add timing configuration**

```yaml
night_behavior:
  duration_seconds: 300
  replan_interval_seconds: 20
  deadline_pressure_seconds: 60
  forced_completion_seconds: 20
  night_move_steps_per_tick: 3
```

- [ ] **Step 4: Initialize `NightHuntState`**

In `_transition_to_night()`, remove the direct `_werewolf_kill_night()` call. Initialize a `NightHuntState`, set residents to home or limited legal night routines, and log the transition.

- [ ] **Step 5: Run test**

Run: `pytest tests/test_game_engine_night_loop.py::test_enter_night_starts_hunt_without_immediate_kill -v`

Expected: PASS.

### Task 3: Score Candidates And Replan Dynamically

**Files:**
- Modify: `game_engine.py`
- Modify: `agent.py`
- Modify: `tests/test_game_engine_night_loop.py`

- [ ] **Step 1: Write failing candidate test**

```python
# tests/test_game_engine_night_loop.py
def test_detective_is_excluded_until_other_residents_are_dead():
    game = WerewolfGameEngine(random_seed=11)
    names = [candidate.name for candidate in game._build_hunt_candidates()]
    assert "Crow" not in names
```

- [ ] **Step 2: Run test and verify failure**

Run: `pytest tests/test_game_engine_night_loop.py::test_detective_is_excluded_until_other_residents_are_dead -v`

Expected: FAIL because candidate generation does not exist.

- [ ] **Step 3: Add candidate generation**

Build candidates from alive residents, BFS path length, and nearby potential witnesses. Exclude Crow while another resident remains alive.

- [ ] **Step 4: Add text-only LLM choice**

Update `Agent.werewolf_choose_target()` to receive legal candidates formatted as:

```text
- Isabella Rodriguez: route=23 tiles, witness_risk=1
- Sam Moore: route=58 tiles, witness_risk=3
```

Accept only an exact candidate name. If output is invalid or empty, use `choose_forced_target()`.

- [ ] **Step 5: Add periodic replanning**

During `_night_tick()`, re-evaluate after `replan_interval_seconds`. Record target changes in `NightHuntState.target_changes`. Increase preference for easy targets inside `deadline_pressure_seconds`.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_night_hunt.py tests/test_game_engine_night_loop.py -v`

Expected: PASS.

### Task 4: Move, Kill Once, And Withdraw

**Files:**
- Modify: `game_engine.py`
- Modify: `tests/test_game_engine_night_loop.py`

- [ ] **Step 1: Write failing kill-on-arrival test**

```python
# tests/test_game_engine_night_loop.py
def test_werewolf_kills_target_only_after_reaching_target():
    game = WerewolfGameEngine(random_seed=11)
    game._transition_to_night()
    target = game.resident_names[0]
    if target == game.werewolf_name:
        target = game.resident_names[1]
    game.night_hunt.target_name = target
    wolf = game.agents[game.werewolf_name]
    victim = game.agents[target]
    wolf.x, wolf.y = victim.x, victim.y
    game._advance_night_hunt()
    assert game.night_hunt.killed_name == target
    assert target in game.dead_list
```

- [ ] **Step 2: Run test and verify failure**

Run: `pytest tests/test_game_engine_night_loop.py::test_werewolf_kills_target_only_after_reaching_target -v`

Expected: FAIL because physical hunt advancement does not exist.

- [ ] **Step 3: Add hunt advancement**

In `_advance_night_hunt()`:

1. choose or replan a target;
2. set the werewolf path toward the target;
3. move using `night_move_steps_per_tick`;
4. when adjacent, mark exactly one kill and create a `BodyRecord`;
5. set the wolf target to home;
6. mark withdrawal complete on arrival.

- [ ] **Step 4: Add forced completion**

Inside the last `forced_completion_seconds`, choose the easiest reachable eligible victim. Continue physical movement. If movement still cannot complete before transition, place the victim at the nearest reachable encounter tile, perform the kill there, and record elevated trace clues. Do not silently kill at an unrelated coordinate.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_game_engine_night_loop.py -v`

Expected: PASS.

### Task 5: Generate Factual Clues From Night Events

**Files:**
- Modify: `night_hunt.py`
- Modify: `game_engine.py`
- Modify: `tests/test_night_hunt.py`

- [ ] **Step 1: Write failing clue-generation test**

```python
# tests/test_night_hunt.py
from night_hunt import build_trace_clues


def test_exposed_hunt_generates_more_clues():
    quiet = build_trace_clues(day=1, body_location="Johnson Park", witnesses=[], target_changes=[])
    exposed = build_trace_clues(
        day=1,
        body_location="Johnson Park",
        witnesses=["Isabella Rodriguez", "Sam Moore"],
        target_changes=["Maria Lopez"],
    )
    assert len(exposed) > len(quiet)
```

- [ ] **Step 2: Run test and verify failure**

Run: `pytest tests/test_night_hunt.py::test_exposed_hunt_generates_more_clues -v`

Expected: FAIL because clue generation does not exist.

- [ ] **Step 3: Add trace clue generation**

Generate:

- one body-site clue for every kill;
- one witness clue per code-observed witness;
- one extra disturbed-trail clue when the wolf changes targets or forced completion activates.

All clues must describe engine facts and assign a valid source resident where appropriate.

- [ ] **Step 4: Wire witness capture**

During wolf movement, use code-computed range and line-of-sight checks to add visible residents to `night_hunt.witnessed_by`. Do not ask a model whether it saw something.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_night_hunt.py -v`

Expected: PASS.

### Task 6: Start Morning Body Discovery And Gathering

**Files:**
- Modify: `game_engine.py`
- Modify: `tests/test_game_engine_night_loop.py`

- [ ] **Step 1: Write failing morning-loop test**

```python
# tests/test_game_engine_night_loop.py
def test_next_day_gathers_near_new_body():
    game = WerewolfGameEngine(random_seed=11)
    game._transition_to_night()
    target = next(name for name in game.resident_names if name != game.werewolf_name)
    game._kill_night_target(target, location="Johnson Park", x=27, y=46)
    game._transition_to_day()
    newest = game.bodies[-1]
    assert game.gathering_site == (newest.x, newest.y)
    assert game._gathering_active is True
```

- [ ] **Step 2: Run test and verify failure**

Run: `pytest tests/test_game_engine_night_loop.py::test_next_day_gathers_near_new_body -v`

Expected: FAIL because morning gathering is not wired to the latest body.

- [ ] **Step 3: Add body discovery transition**

At the next morning:

1. mark the newest body discovered;
2. set `gathering_site` to the body coordinate;
3. move living characters to a ring around the body;
4. initialize body-site discussion;
5. include selected factual clues in each speaker's text prompt;
6. disperse after discussion.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_game_engine_night_loop.py -v`

Expected: PASS.

### Task 7: Show Director-View Hunt Status

**Files:**
- Modify: `game_engine.py`
- Modify: `ui/templates/index.html`

- [ ] **Step 1: Serialize hunt state**

Expose:

```python
"night_hunt": {
    "stage": self.night_hunt.stage,
    "target_name": self.night_hunt.target_name,
    "target_changes": list(self.night_hunt.target_changes),
    "witnessed_by": sorted(self.night_hunt.witnessed_by),
    "killed_name": self.night_hunt.killed_name,
    "withdrawal_complete": self.night_hunt.withdrawal_complete,
}
```

Use `None` when there is no active hunt.

- [ ] **Step 2: Render compact hunt details**

In the existing side panel, add a director-only night block showing stage, target, target changes, witnesses, and remaining time. Keep the layout compact and hide it during day.

- [ ] **Step 3: Compile and run tests**

Run: `python -m py_compile main.py ui/app.py game_engine.py agent.py night_hunt.py`

Expected: exit code `0`.

Run: `pytest tests -v`

Expected: PASS.

### Task 8: End-To-End Night Verification

**Files:**
- Modify: `TASK.md`

- [ ] **Step 1: Start a clean game**

Start the server and reset the game. Observe the initial body gathering and daytime dispersal.

- [ ] **Step 2: Enter night**

Confirm:

- residents go home or perform a limited valid night routine;
- the werewolf chooses a legal non-Crow target;
- the wolf moves physically;
- target changes are visible when replanning occurs;
- exactly one eligible resident dies;
- the body appears at the actual kill location;
- trace clues reflect witnesses and hunt difficulty.

- [ ] **Step 3: Observe morning**

Confirm the next day starts by discovering the new body and gathering living characters near it.

- [ ] **Step 4: Verify unattended loop**

Run through at least two nights without moving Crow. Confirm the simulation does not stall and executable locations remain map-valid.

- [ ] **Step 5: Update progress board**

Record night-loop verification in `TASK.md`.


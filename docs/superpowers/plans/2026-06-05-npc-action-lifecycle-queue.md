# NPC Action Lifecycle Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make NPCs think in a serial queue, execute visible timed actions locally, and reserve model calls during execution only for queued speech.

**Architecture:** NPC decisions become plans with a target coordinate, visible action text, and game-time duration. The engine runs one serial planning lane, local movement/action execution, and one serial conversation lane ordered by detective priority then trigger time. Existing action labels stay compatible, but execution semantics are unified as "go to target point, then do one thing."

**Tech Stack:** Python engine and pytest, existing Flask/Socket.IO status payload, existing HTML/JS frontend.

---

## Design Contract

- Daytime should be `600` real seconds mapped to one 24-hour game day.
- One NPC planning lane is serial: only one NPC calls the model for action planning at a time.
- Each planning result must produce one executable action. A new thought/plan is not allowed until the previous action is completed or cancelled.
- Ordinary actions are local after planning: movement, choosing nearby fallback coordinates, duration countdown, action completion, and avoidance do not call the model.
- Each action has a game-time duration. The model may suggest `duration_minutes`, clamped by code to `5..30` game minutes, then raised to at least the most recent full planning cycle duration converted to game minutes, and finally capped at `30`.
- If the planned coordinate equals the NPC's current coordinate, the engine chooses a neighboring tile so every new action visibly moves when possible: left, right, up, down.
- `socialize` and `talk` are treated as one conversation behavior.
- Conversation is a timed action from the moment the speech job is submitted to the model until the white bubble disappears. During this whole period, both participants are busy and protected from third-party insertion.
- Conversation model calls are also serial. Priority is detective conversations first, then first-triggered first-served.
- While waiting for speech text, the white bubble shows `...`.
- If a third NPC reaches an occupied conversation, code cancels that conversation trigger, moves the NPC away from the protected area if possible, logs the avoidance, and completes that action without a new model call.
- Crow is player-controlled and must not receive NPC action logs or blue action bubbles.

## Expected Files

- Modify `config.yaml`: day duration and action/conversation timing knobs.
- Modify `agent.py`: prompt JSON contract, `duration_minutes` parsing, action type compatibility.
- Modify `game_engine.py`: serial planning queue, action duration state, coordinate fallback, conversation queue/state, status payload.
- Modify `engine_bubbles.py`: conversation bubble lifetime interaction if needed.
- Modify `ui/templates/index.html`: display ongoing action/conversation state if backend payload changes.
- Modify focused tests under `tests/`: action JSON, daytime NPC behavior, engine foundation, UI bubble layout if status fields change.
- Modify docs: `NPC_BEHAVIOR_LIFECYCLE.md`, `USER_REQUIREMENTS_LEDGER.md`, and possibly `CURRENT_SPRINT.md`.

## Worker Split

## Integration Guardrails

- `game_engine.py` action/conversation lifecycle has one owner during implementation: the main agent. Workers may inspect or propose tests, but must not independently change `_update_agent_schedules`, `_complete_agent_action`, `_trigger_npc_chat`, detective chat methods, `_pending_action`, `runtime_state`, or `in_conversation_with`.
- The backend must expose one state ownership rule: an NPC is unavailable for planning if it is moving, acting, waiting for speech, in conversation, or locked by detective chat.
- Conversation is represented as an action-level busy state plus a conversation lock. The lock is not released when model text returns; it is released only when the conversation action completes, normally after the white bubble lifetime ends.
- The planning lane must have a single entrance and one active planning marker. Starting a model decision thread must fail/skip if another planning request is active.
- Speech jobs must also have one queue abstraction that covers both NPC-to-NPC speech and NPC/Crow speech. Detective speech jobs sort ahead of normal NPC speech jobs; jobs with the same priority are FIFO.
- If implementation cannot complete the unified speech queue in one safe patch, it must first make existing direct speech calls obey the same busy-state release timing and document the remaining queue work.
- Do not run tests or scripts that write `personas/` during worker tasks. If a test unexpectedly writes `personas/`, stop that worker and clean only those runtime writes.

### Worker A: Backend Lifecycle and Tests

**Ownership:** backend tests and `agent.py` prompt/parser only. `game_engine.py` lifecycle edits are owned by the main agent.

- [x] Add/adjust failing tests for serial planning: if an NPC is acting, it is skipped by the planning lane.
- [x] Add/adjust failing tests for action duration: pending action remains until duration expires; no new decision is requested during that time.
- [x] Add/adjust failing tests for target coordinate fallback: same-coordinate action chooses left/right/up/down when possible.
- [x] Add/adjust failing tests for `duration_minutes` parsing and clamping.
- [x] Implement only parser/prompt changes in `agent.py`; leave `game_engine.py` implementation to the main agent.
- [x] Do not touch `personas/`, cache, runtime memory, or frontend files.

### Worker B: Conversation Queue and Protection Review

**Ownership:** read-only review and test recommendations unless the main agent explicitly hands off a narrow patch after the unified state hooks exist.

- [x] Add/adjust failing tests for serial speech queue: detective-priority first, then FIFO.
- [x] Add/adjust failing tests that conversation starts at speech-job submission, shows `...`, and keeps both parties busy until bubble expiry.
- [x] Add/adjust failing tests that third-party insertion cancels/avoids instead of calling the model.
- [x] Do not directly edit lifecycle methods until the main agent has created stable helper methods for conversation start/completion.
- [x] Do not touch `personas/`, cache, frontend files, or docs.

### Worker C: Frontend/Status Surface

**Ownership:** `ui/templates/index.html`, `engine_bubbles.py`, UI tests only.

- [x] Inspect current status payload and bubble rendering.
- [x] Ensure white status bubbles can display ongoing action text like `正在看书...` without being treated as speech from another NPC.
- [x] Ensure blue action bubbles still show only short action explanations, not internal thought.
- [x] Add/adjust UI layout tests if payload or rendering changes.
- [x] Do not touch `agent.py`, `game_engine.py`, `personas/`, or runtime state.

### Main Agent: Integration

- [x] Resolve any overlap between Worker A and Worker B in `game_engine.py`.
- [x] Ensure `stay` remains accepted as a compatibility alias but internal new behavior uses `continue_current`.
- [x] Ensure ordinary actions do not call the model during execution.
- [x] Ensure speech generation remains the only execution-time model call.
- [x] Update project docs with the stable NPC lifecycle contract.
- [x] Run `python -m py_compile agent.py game_engine.py engine_bubbles.py ui/app.py engine_dusk.py engine_tasks.py engine_navigation.py`.
- [x] Run focused pytest files first, then full `python -m pytest tests -q`.
- [x] Restart service and verify `http://127.0.0.1:5000/`.
- [x] Report frontend version number.

## Acceptance Checks

- Planning model calls are serial and observable in logs.
- An NPC cannot start a second thought/plan while it is moving, acting, waiting for speech, or in conversation.
- Ordinary planned actions visibly move to a target coordinate whenever a neighbor tile is available.
- Ordinary action duration is variable, bounded, and not always 30 game minutes.
- Conversation waits show `...`, then speech, then release only after bubble disappearance.
- A single external model API can run the town without all NPCs blocking at once.
- Crow has no autonomous action log or action bubble.

## Execution Status

Updated 2026-06-05 during implementation:

- Completed: design record saved here, in `NPC_BEHAVIOR_LIFECYCLE.md`, and in `USER_REQUIREMENTS_LEDGER.md` as REQ-159 through REQ-164.
- Completed: `duration_minutes` added to the model action contract and normalized to 5-30 game minutes in `agent.py`.
- Completed: daytime config changed to 600 real seconds.
- Completed: backend helper foundation for a single planning lane, dynamic action duration floor, and left/right/up/down neighbor movement.
- Verified: `python -m py_compile agent.py game_engine.py engine_bubbles.py ui/app.py engine_dusk.py engine_tasks.py engine_navigation.py`.
- Verified: `python -m pytest tests/test_agent_action_json.py tests/test_engine_foundation.py::test_action_duration_uses_planned_minutes_and_planning_cycle_floor tests/test_engine_foundation.py::test_neighbor_action_path_prefers_left_then_right tests/test_engine_foundation.py::test_acting_npc_does_not_request_new_plan_before_duration -q`.
- Completed 2026-06-06: unified speech queue covers model-backed NPC-NPC and Crow-NPC speech jobs; detective jobs have priority over queued ordinary NPC speech jobs.
- Completed 2026-06-06: conversation locks for model-backed conversations remain until white bubbles expire; one-way NPC reports to Crow remain the explicit no-lock exception.

Updated 2026-06-06 during closure:

- [x] Planning lane now advances by `active_agents` order even when the current candidate is in retry or decision-interval cooldown.
- [x] Moving, acting, pending-planning, and conversation states are all skipped by the planning lane, so occupied NPCs do not block the next eligible NPC.
- [x] A pending ordinary action enters an `acting` occupancy period before the NPC can request another thought/plan.
- [x] Ordinary action execution is local: duration countdown and completion do not request a new model decision.
- [x] Ordinary action status is shown with a white `action_status` bubble such as `正在看书...` and persists until the action completes.
- [x] Player-visible logs preserve the thought / plan / action closure by allowing `[行动计划]`, `[开始行动]`, and `[行动结果]`.
- [x] Frontend version display now reads `FRONTEND_VERSION`; current closure version is `23`.
- [x] Blue action bubbles use the short action-start form only: destination plus task. White action-duration bubbles use the task-only form and stay for the action duration.
- [x] Version `24` correction: one NPC can show only one visible bubble at a time. White action-duration bubbles start only after movement/action-start blue bubble has cleared and the NPC is in acting state. `action_status` is not dialogue and does not get a speaker prefix.
- [x] Memory line is now a documented third line: action completion deposits memory without creating visible bubbles.
- [x] Regression after version `24`: related suite `292 passed`; full suite `428 passed`; only pytest cache permission warning remains.
- [x] Version `26` correction: frontend now blocks early `action_status` until the action-start blue bubble has actually ended (`expired === true`) and the NPC is no longer moving. Model decisions now include a dedicated `action_status` field for white action-duration text.
- [x] Regression after version `26`: related suite `365 passed`; full suite `430 passed`; only pytest cache permission warning remains.
- [x] Version `27` correction: fixed stuck `moving` at target with empty path, added a 6-second real-time floor for action-duration bubbles, restored visible one-tile nudge for same-coordinate actions even when a target object is present, and ensured frontend action-status text keeps trailing `...`.
- [x] Regression after version `27`: related suite `368 passed`; full suite `433 passed`; only pytest cache permission warning remains.
- [x] Version `28` correction: existing pending actions that already carry `duration_seconds` are also clamped to the 6-second ordinary-action floor, so injected or stale `duration_seconds: 0` cannot bypass the action occupation window.
- [x] Regression after version `28`: related suite `294 passed`; full suite `435 passed` with `-p no:cacheprovider`.
- [x] Version `29/30` correction: ordinary action duration now counts from `action_status_visible_at` (arrival plus completed action-start blue bubble), not raw arrival time. Generic real speech/conversation bubbles do not coexist with moving/action-start blue bubbles; conversation is the ongoing action. Round-two departure speech is a special gathering flow: white departure speech first, then blue departure action/movement after the white bubble's visible window ends.
- [x] Version `30` correction: round-two departure speech now blocks only that NPC's movement until its visible speech window ends; the next speaker queue still advances after the short gap. Target resolution also performs a final one-tile nudge if it would otherwise leave an NPC on the same tile.
- [x] Regression after action-bubble correction: related suite `290 passed`; full suite `426 passed`; only pytest cache permission warning remains.
- [x] Focused regression currently covered by `tests/test_engine_foundation.py` planning/action lifecycle cases and `tests/test_ui_bubble_layout.py` bubble/log lifecycle cases.
- [x] Model-backed speech jobs now use a single serial queue. Detective jobs use priority `0`; ordinary NPC-NPC speech jobs use priority `1` and FIFO order within the same priority.
- [x] Detective interviews now keep both sides locked until the visible white bubbles expire, matching the conversation-duration contract. One-way reports to Crow still do not create a conversation lock.
- [x] Daytime realtime reflection has been removed from the visible loop. Reflection is now a stage-node/background memory activity and must not create blue thought bubbles without an action.
- [x] Action decision failures and exceptions now fall back into concrete visible `continue_current` actions instead of idle waiting.
- [x] Default ordinary action duration now fills the 30-game-minute cap until a measured planning cycle provides another floor.

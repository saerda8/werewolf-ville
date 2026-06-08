# NPC Behavior Lifecycle

Updated: 2026-06-07

## Macro Goal

Every NPC should feel like a living town resident, not a stationary reasoning node. Daytime behavior must produce visible life: movement, conversation, work, investigation, shopping, object interaction, avoidance, or an explicit continuation of a current task.

## Stable Rules

1. Conversation has higher visible priority than generic idle or in-place behavior. If an NPC plans to talk to another NPC, the target is that NPC, not merely the target location.
2. A successful think/plan cycle must lead to one action. The NPC must not start another think/plan cycle until that action has executed, failed, or completed.
3. If the action is conversation and the model is still generating speech, the white speech bubble must appear immediately with `...`. During that wait, the conversation action is still in progress.
4. A conversation action is not complete when the NPC merely reaches the target. It is complete only after the conversation flow publishes speech, fails, times out, or is explicitly released.
5. In-place actions should still have a visible target whenever possible: an NPC id, object id/name, or coordinate. If no person or object target exists, the engine should try a small local movement before continuing the task, so the NPC does not look frozen.
6. Blue bubbles are limited to three player-facing states: thinking, plan, and action. Reason text should be folded into thinking, not displayed as a separate player-facing label.
7. White speech bubbles and blue thinking/action bubbles share the same visible lifetime target. Current default: about 6 seconds.

## 2026-06-05 Action Duration and Queue Design

The agreed target lifecycle is:

```text
serial planning -> local movement -> timed visible action -> completion -> next eligible planning turn
```

Stable rules:

1. Daytime should use a 10-minute real-time day mapped to 24 game hours.
2. NPC planning is a single serial lane. NPCs are considered in a stable order; if the current NPC is moving, acting, waiting for speech, or in conversation, the scheduler skips it and checks the next NPC.
3. Planning decides the next action target and intent. Ordinary execution should not call the model again.
4. Ordinary action format is "go to target coordinate, then do one thing." Work, observe, inspect, investigate, rest, buy, take, and use are visible action descriptions, not separate execution pipelines.
5. Every ordinary action has a game-time duration. The model may suggest a duration, but code clamps it to 5-30 game minutes and also raises the minimum to the latest full serial planning cycle duration converted into game minutes, capped at 30 game minutes.
6. If a new action target coordinate equals the NPC's current coordinate, the engine should choose a nearby walkable tile so the NPC visibly moves. Priority: left, right, up, down. If no valid tile exists, the NPC may act in place and the result should make that clear.
7. Conversation is also a timed action. Its duration starts when the speech request is submitted to the model and ends when the white speech bubble disappears.
8. While speech is waiting for model output, the white bubble displays `...`. During that wait, both participants are busy and must not start new planning.
9. Conversation speech requests use a serial queue. Detective conversations have highest priority; other conversations are first-triggered first-served.
10. Third-party insertion is resolved by code, not by a new model decision. If a target is already in conversation, the arriving NPC cancels the conversation trigger, moves away from the protected area if possible, records the avoidance result, and completes that action.
11. Hide/avoid is still "go to a target coordinate, then enter a hidden/avoidance state." The target should be planned in the planning step; if missing, code may choose a safe fallback point.

## 2026-06-06 State Cleanup Closure

Stable implementation rules:

1. A completed planning response must create one pending action and that action must enter moving, acting, or conversation before the NPC is eligible for another planning response.
2. If a planned target becomes unavailable, blocked, or unreachable after planning, the NPC falls back into a visible `continue_current` action instead of returning to idle and immediately thinking again.
3. NPC reports to Crow are real conversation actions. When the report speech starts, the source NPC is locked in conversation with Crow until the visible white bubble expires.
4. Player-initiated Crow interviews keep the target NPC locked until the visible white bubbles expire. After the player submits the prompt, Crow/player movement is not blocked by that pending model reply.
5. NPC-to-NPC conversations keep both NPCs locked until the visible speech bubbles expire. The model-waiting phase counts as conversation time and shows `...`.

## 2026-06-06 Planning Lane and Action Occupancy Closure

Stable implementation rules:

1. The serial planning lane is ordered by `active_agents`. If the current candidate is cooling down because of retry or decision interval, the lane advances to the next eligible NPC instead of staying stuck on the same person.
2. Moving, acting, pending-planning, and conversation states all make an NPC unavailable for planning. The scheduler skips those NPCs and gives the model request opportunity to the next eligible NPC.
3. Once a planning response produces a pending ordinary action, that NPC must enter movement or an `acting` occupancy period before it can think again.
4. During an ordinary action, execution is local: the NPC waits out the action duration, shows the white ongoing-status bubble, then completes the action without calling the model again.
5. Existing pending actions that already carry `duration_seconds` still obey the ordinary-action 6-second real-time floor; `duration_seconds: 0` is not a valid way to skip the occupation window.
6. Ongoing ordinary action bubbles use white speech-bubble styling and persist until the action completes, for example `正在看书...` or `正在检查库存...`.
7. Player-facing logs must show the full decision closure: `[行动计划]`, `[开始行动]`, and `[行动结果]` are visible entries, while raw parsing/internal noise remains hidden.
8. Blue action bubbles are only the action-start sentence: destination plus concrete task, such as `前往霍布斯咖啡馆，准备开门营业`. They must not repeat thought, plan, motive, or follow-up observation text.
9. White action-duration bubbles show only the ongoing task, such as `准备开门营业...`, and persist for the real action duration. During this duration the NPC must not show new thought/plan bubbles.
10. Visible bubbles are mutually exclusive for one NPC: thought/plan blue bubble first, then action-start blue bubble, then action-duration white bubble. Moving does not show the white duration bubble.
11. `action_status` is not dialogue. It must never add `某某说：`; only real conversation bubbles add speaker/target prefixes.
12. A third memory line runs after action completion: action results are deposited into memory, but memory writeback must not create visible thought/plan/action bubbles.
13. Frontend version is explicit through `FRONTEND_VERSION`; this closure is version `28`.
14. Frontend action-duration display has a hard gate: even if the backend sends `action_status` early, the white duration bubble is hidden until the action-start blue bubble has actually ended (`expired === true`) and the NPC is no longer visually moving.
15. The model action decision JSON includes `action_status`, a dedicated short text for the white action-duration bubble. `action` drives action start; `action_status` drives action duration. The UI should not derive normal duration text by chopping plan text except as a fallback.
16. A resident in `moving` state whose coordinates already equal the target and whose path is empty must immediately leave `moving`: enter `acting` if a pending action exists, otherwise return to `idle`. This prevents a resident from being skipped forever by the serial planning queue.
17. Action-duration display must have a real-time floor of 6 seconds, even if the model chooses a very short game-time action.
18. If a new action's resolved target coordinate equals the NPC's current coordinate, the engine should pick a nearby walkable tile within one grid step first, including actions with a target object, so repeated local work still looks alive.
19. Ordinary action duration starts when the NPC has reached the target and the action-start blue bubble has ended, meaning the white ongoing-action bubble is allowed to appear. It does not start at raw arrival time.
20. Generic real speech/conversation bubbles must not coexist with a moving/action-start blue bubble. A conversation is itself an ongoing action: it starts when the speech model request is queued and ends only after the visible white reply bubble expires. Round-two departure speech is the special gathering flow: the NPC first shows the white departure speech, then starts the blue departure action and movement after that white bubble's visible window ends.
21. Round-two departure speech is a speaking action. Each NPC must finish its own visible departure speech window before walking away, while the gathering queue may advance to the next speaker after the short configured gap.
22. After target resolution, if a normal action still targets the NPC's current tile, the engine must try a one-tile nudge again before allowing same-tile execution.

## 2026-06-06 Speech Queue Closure

Stable implementation rules:

1. Model-backed speech jobs use one serial queue. A running model call is not interrupted; priority applies to jobs waiting in the queue.
2. Detective/Crow speech jobs use higher priority than ordinary NPC-to-NPC speech jobs. Ordinary NPC-to-NPC speech jobs are FIFO within their priority level.
3. NPC-to-NPC chat, detective interviews, deep-dive replies, and NPC-initiated reports to Crow are all conversation actions. Model-backed speech goes through the speech queue; direct report text still uses the same visible conversation lock and release rule.
4. While waiting for model-backed NPC-to-NPC speech, the initiator white bubble shows `...` and both NPCs stay busy.
5. Conversation locks release on visible bubble expiry, not merely when model text returns.

## 2026-06-06 Visible Loop Correction

Stable implementation rules:

1. Daytime has no continuous realtime reflection loop. NPC visible behavior is driven by the serial action planning lane plus the separate serial speech lane.
2. Reflection is a stage-node activity. It may run when night begins after dusk/voting, but it must not create daytime blue thought bubbles or bypass action planning.
3. If an action decision fails, times out, or throws while parsing, the NPC must enter a concrete visible `continue_current` action instead of returning to idle.
4. The default visible action duration is 30 game minutes, capped by the existing 5-30 minute contract. In a 600-second day this is about 12.5 real seconds.
5. Residual idle thoughts from older reflection paths are cleared before scheduling so they cannot appear as blue bubbles without an action.
6. Background memory/reflection is separate from visible behavior. It may write memory/cognition, but it must not mutate current thought/plan/action display state during daytime.

## 2026-06-07 Action Start and Conversation Regression Closure

Stable implementation rules:

1. Every new action has a distinct `action_started_at`. The frontend must use it to refresh the action-start blue bubble even when the visible action sentence matches a previous action.
2. Once backend state changes from planning to moving/acting, the action-start blue bubble replaces any cached thought/plan bubble immediately.
3. Action execution has a `starting_action` display phase. Movement, ordinary action duration, and model-backed speech requests wait until the blue action-start bubble's visible window ends.
4. `talk/socialize` never uses the ordinary timed `acting` window. On reaching conversation range, it enters `starting_action` first; after the blue action-start bubble ends, it starts the model-backed speech pipeline. While waiting, the white bubble shows `...`.
5. If a conversation target moves before arrival, the initiator re-approaches the target. If approach becomes impossible, the action converts to a visible `continue_current` action instead of showing fake conversation activity.
6. Explicit greeting, asking, chatting, speaking, telling, or reporting text with a target person is normalized to `talk` even if the model returns a non-conversation action type.
7. Player log colors distinguish cognition/start from action output: thought, plan, and action start are purple; real NPC speech, white ongoing-action text, action duration, and action result are green.

## 2026-06-07 Observation, Memory, And Cognition Upgrade

Implementation status: completed and verified. Observation packets now separate 10-tile visible objects from near-hand reachable objects; only reachable objects may ground the current white action-status bubble.

Lifecycle target:

```text
observation packet -> decision model -> visible thought/plan/action -> action execution
ordinary action -> background memory queue
real chat action -> conversation model -> white bubble -> background memory queue
memory queue -> event/chat/thought/plan memory -> future retrieval
```

Stable rules:

1. Observation radius starts at Manhattan distance `10`. Visible actions, ordinary speech, and white speech bubbles inside that radius may enter the observer's decision context. Public events such as body discovery, vote results, night death announcements, and public meeting statements may broadcast beyond radius. Hidden facts do not leak through radius.
2. The observation packet is the required decision-prep bundle. It should include current nearby events, prior relevant memories, current self/action state, goals, action history, public world state, nearby people and objects, visible event history, short-term concerns, day-plan deviations, and black-box information constraints.
3. The system has three model lanes: the decision lane for thought/plan/action, the real conversation lane for actual chat text, and the background memory lane for consolidation. The memory lane must not block visible action, conversation, or planning, and must not create blue bubbles.
4. Real conversation is a sustained action. It starts when the speech model request is submitted and completes only after the resulting white bubble disappears; while waiting, the white bubble may show `...`.
5. `thought` and `plan` are real cognition outputs, not placeholder UI copy. They are eligible for memory consolidation, but must stay short and limited to the NPC's current perspective. `thought` explains immediate motive from observable/remembered context; `plan` describes only the next concrete action.
6. `action_status` must be grounded in the observation packet. It may reference only real visible/known people, objects, places, or professional tasks; it must not invent customers, townspeople, opponents, or targets that are not present or known.

## Regression Checks

- `tests/test_daytime_npc_behavior.py::test_npc_chat_shows_typing_bubble_before_model_returns`
- `tests/test_daytime_npc_behavior.py::test_pending_action_executes_before_next_thought`
- `tests/test_daytime_npc_behavior.py::test_pending_acting_action_can_complete`
- `tests/test_daytime_npc_behavior.py::test_npc_one_way_report_to_crow_releases_state`
- `tests/test_engine_foundation.py::test_planned_action_falls_back_to_visible_action_when_target_cannot_be_reached`
- `tests/test_engine_foundation.py::test_npc_chat_lifecycle_sets_and_releases_in_conversation_with`
- `tests/test_engine_foundation.py::test_planning_turn_advances_when_candidate_on_next_retry_cooldown`
- `tests/test_engine_foundation.py::test_planning_turn_advances_when_candidate_on_interval_cooldown`
- `tests/test_engine_foundation.py::test_moving_npc_is_skipped_in_planning_lane`
- `tests/test_engine_foundation.py::test_acting_npc_is_skipped_in_planning_lane`
- `tests/test_engine_foundation.py::test_pending_planning_state_is_skipped_in_planning_lane`
- `tests/test_engine_foundation.py::test_conversation_state_is_skipped_in_planning_lane`
- `tests/test_engine_foundation.py::test_action_duration_does_not_request_decide_next_action`
- `tests/test_engine_foundation.py::test_ordinary_action_status_bubble_persists_until_action_completes`
- `tests/test_engine_foundation.py::test_player_visible_log_keeps_think_plan_action_closure`
- `tests/test_ui_bubble_layout.py::test_agent_log_whitelist_covers_action_lifecycle`
- `tests/test_ui_bubble_layout.py::test_blue_bubble_sequential_thought_plan_action`
- `tests/test_ui_bubble_layout.py::test_white_bubble_displays_ongoing_action_during_movement_or_action`
- `tests/test_engine_foundation.py::test_action_movement_waits_until_blue_action_bubble_window_ends`
- `tests/test_engine_foundation.py::test_starting_talk_waits_for_blue_action_bubble_before_real_chat`
- `tests/test_engine_foundation.py::test_greeting_text_with_wrong_model_type_uses_real_chat_pipeline`
- `tests/test_daytime_npc_behavior.py::test_npc_report_to_crow_skips_planning_until_bubble_expires`
- `tests/test_ui_bubble_layout.py::test_hidden_blue_action_bubble_does_not_count_as_displayed`
- `tests/test_engine_foundation.py::test_npc_chat_speech_jobs_run_serial_fifo`
- `tests/test_engine_foundation.py::test_speech_queue_runs_detective_priority_before_waiting_npc_job`
- `tests/test_engine_foundation.py::test_day_tick_does_not_run_realtime_reflection`
- `tests/test_engine_foundation.py::test_stage_reflection_only_runs_at_night_start_when_running`
- `tests/test_engine_foundation.py::test_initial_action_duration_defaults_to_full_occupancy`
- `tests/test_engine_foundation.py::test_action_decision_exception_becomes_visible_ongoing_action`
- `tests/test_engine_foundation.py::test_idle_residual_reflection_thought_is_cleared`
- `tests/test_ui_bubble_layout.py`

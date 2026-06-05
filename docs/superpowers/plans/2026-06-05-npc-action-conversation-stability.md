# NPC Action Conversation Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make NPC action execution reliable: planned talk actions must become white speech bubbles after the planning pause, pending speech must show `...` while waiting for the model, timeout fallback speech must be visible in logs, right-edge bubbles must not squeeze, and completed talk/report tasks must stop repeating.

**Architecture:** Treat the NPC pipeline as two explicit stages: planning display, then execution. Talk/report execution should reserve the participants immediately, show a white pending bubble containing `...` while text is being generated, then replace it with model/fallback speech. UI bubble positioning should use stable widths and viewport clamping, not content compression. Completion should clear the short-term task so the next decision does not keep repeating the same report.

**Tech Stack:** Python engine (`game_engine.py`, `agent.py`), pytest regression tests, Phaser/HTML UI in `ui/templates/index.html`, static UI tests in `tests/test_ui_bubble_layout.py`.

---

## File Map

- `game_engine.py`
  - Owns NPC scheduling, planning pause, movement completion, talk/report execution, conversation reservations, chat bubbles, timeout fallback logs, and status payload.
- `agent.py`
  - Owns LLM action prompt contract and action taxonomy; should remove or de-emphasize `stay` as visible action output in favor of `continue_current`.
- `ui/templates/index.html`
  - Owns white/blue bubble rendering, right-edge clamping, typing/pending text display, and log labels.
- `tests/test_engine_foundation.py`
  - Backend contract tests for talk execution, timeout fallback, planning delay, duplicate-task clearing, and Crow reservation.
- `tests/test_ui_bubble_layout.py`
  - Static/DOM contract tests for bubble width, right-panel clamping, typing placeholder, and log rendering.
- `.planning/npc-dialogue-ui-regressions/task_plan.md`
  - Running checklist that records which user-reported regression is fixed and verified.

## Worker Strategy

- DeepSeek gets only backend/test slices that do not require `ui/**`, `personas/**`, runtime logs, or broad rewrites. If a task naturally needs restricted files, do not assign it to DeepSeek.
- Antigravity gets UI-only slices such as bubble layout, DOM contract tests, and visual verification.
- Primary agent owns integration, forbidden-path review, final tests, and restart.

## Task 1: Timeout Fallback Speech Logging

**Files:**
- Modify: `game_engine.py`
- Test: `tests/test_engine_foundation.py`
- Optional UI static test: `tests/test_ui_bubble_layout.py`

- [ ] **Step 1: Add failing backend tests for fallback logs**

Add tests covering:

```python
def test_npc_to_detective_timeout_fallback_logs_visible_message(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    crow = engine.agents["Crow"]
    arthur.x, arthur.y = 10, 10
    crow.x, crow.y = 11, 10
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Crow",
        "action": "向警长报告紧急发现",
        "thought": "必须马上告诉警长。",
        "expected_result": "让警长知道",
    }

    monkeypatch.setattr(arthur, "generate_response", lambda *args, **kwargs: "")

    engine._complete_agent_action("Arthur Burton", arthur)

    messages = [entry["message"] for entry in engine.game_log]
    assert any("模型超时/空结果，使用保底发言" in msg for msg in messages)
    assert engine.chat_bubbles["Arthur Burton"]["target"] == "Crow"
    assert engine.chat_bubbles["Arthur Burton"]["text"]
```

Add a parallel NPC-NPC test where `chat_for_agent` returns empty or times out and the visible fallback plus log are both present.

- [ ] **Step 2: Run red tests**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_npc_to_detective_timeout_fallback_logs_visible_message -q
```

Expected: fail if the log is missing or only invisible system/debug logs exist.

- [ ] **Step 3: Implement visible timeout/fallback log helper**

Add one engine helper:

```python
def _log_visible_model_fallback(self, speaker_name: str, context: str) -> None:
    self._log(
        f"[模型超时/空结果，使用保底发言] {display_name_for_person(speaker_name)} {context}",
        "action",
    )
```

Use it whenever an NPC white-bubble speech falls back because the model response is empty, timed out, or otherwise unusable.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_npc_to_detective_timeout_fallback_logs_visible_message tests/test_engine_foundation.py::test_npc_chat_empty_initiator_reply_uses_visible_fallback -q
```

Expected: pass.

## Task 2: Planning Pause Before Action

**Files:**
- Modify: `game_engine.py`
- Test: `tests/test_engine_foundation.py`

- [ ] **Step 1: Add tests for three-second planning gate**

Add a test that verifies an NPC with a pending talk action remains in planning until `planning_display_seconds` expires and does not call `_trigger_npc_chat` immediately.

```python
def test_talk_action_waits_planning_display_before_execution(monkeypatch):
    engine = _make_engine(monkeypatch)
    monkeypatch.setitem(game_engine.CONFIG["agent"], "planning_display_seconds", 3.0)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 12, 10
    arthur.runtime_state = "planning"
    arthur._action_plan_ready_at = time.time() + 3.0
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "找伊莎贝拉交谈昨晚的脚步声",
        "thought": "她可能听到了声音。",
        "expected_result": "交换信息",
    }
    calls = []
    monkeypatch.setattr(engine, "_trigger_npc_chat", lambda *args: calls.append(args))

    engine._update_agent_schedules()

    assert calls == []
    assert arthur.runtime_state == "planning"
```

- [ ] **Step 2: Implement explicit planning completion state**

In `_update_agent_schedules`, when `runtime_state == "planning"`:

- If `now < _action_plan_ready_at`, skip movement/execution.
- If ready, transition to movement or direct execution.
- Do not let the NPC start a new LLM thought while a pending action is waiting.

- [ ] **Step 3: Verify action starts after delay**

Add a second test setting `_action_plan_ready_at = time.time() - 0.1`, then assert `_trigger_npc_chat` is called.

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_talk_action_waits_planning_display_before_execution -q
```

Expected: pass.

## Task 3: Talk Action Must Immediately Reserve And Show Pending White Bubble

**Files:**
- Modify: `game_engine.py`
- Test: `tests/test_engine_foundation.py`

- [ ] **Step 1: Add tests for pending white bubble**

Add a test that when a talk action reaches target, `chat_bubbles[source]` is set immediately to a pending line before model text returns.

```python
def test_npc_talk_shows_pending_white_bubble_before_model_reply(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 12, 10
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "找伊莎贝拉交谈脚步声",
        "thought": "她在附近。",
        "expected_result": "交换信息",
    }
    started = threading.Event()

    def slow_chat(*args, **kwargs):
        started.set()
        time.sleep(0.2)
        return "你昨晚听到脚步声了吗？"

    monkeypatch.setattr(game_engine, "chat_for_agent", slow_chat)
    monkeypatch.setattr(isabella, "generate_response", lambda *args: "我听到了。")

    engine._complete_agent_action("Arthur Burton", arthur)
    assert started.wait(timeout=1)
    assert engine.chat_bubbles["Arthur Burton"]["target"] == "Isabella Rodriguez"
    assert engine.chat_bubbles["Arthur Burton"]["text"] == "..."
```

- [ ] **Step 2: Implement pending bubble**

Inside `_trigger_npc_chat` and `_trigger_npc_to_detective_chat`, immediately after reservation:

```python
self.chat_bubbles[name1] = {
    "text": "...",
    "target": name2,
    "time": time.time(),
    "pending": True,
}
```

For Crow-directed report, also reserve `detective.in_conversation_with = source_name` before model generation.

- [ ] **Step 3: Verify**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_npc_talk_shows_pending_white_bubble_before_model_reply tests/test_engine_foundation.py::test_talk_decision_starts_chat_when_target_person_adjacent -q
```

Expected: pass.

## Task 4: Crow Conversation Queue And Avoidance

**Files:**
- Modify: `game_engine.py`
- Test: `tests/test_engine_foundation.py`

- [ ] **Step 1: Add tests for one active Crow report**

Add a test where two NPCs both target Crow. The first reserves Crow and shows pending bubble. The second must not speak immediately; it should move away or wait outside radius 1.

```python
def test_second_npc_does_not_interrupt_pending_crow_report(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    sam = engine.agents["Sam Chen"]
    crow = engine.agents["Crow"]
    arthur.x, arthur.y = 10, 10
    sam.x, sam.y = 10, 11
    crow.x, crow.y = 11, 10
    crow.in_conversation_with = "Arthur Burton"

    sam._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Crow",
        "action": "向警长说明情况",
        "thought": "我也想说。",
        "expected_result": "让警长知道",
    }

    engine._complete_agent_action("Sam Chen", sam)

    assert "Sam Chen" not in engine.chat_bubbles or engine.chat_bubbles["Sam Chen"].get("target") != "Crow"
    assert sam._pending_action is None
```

- [ ] **Step 2: Implement reservation and avoidance**

Rules:

- Any pending Crow report/chat reserves Crow immediately.
- Other NPCs targeting Crow must not start white bubble while Crow has `in_conversation_with`.
- If another NPC is within radius 1 of Crow and not the current conversation partner, assign a short avoid/wait movement target outside radius 1 if reachable.

- [ ] **Step 3: Verify**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_second_npc_does_not_interrupt_pending_crow_report -q
```

Expected: pass.

## Task 5: Action Text Should Not Leak Full Dialogue

**Files:**
- Modify: `game_engine.py`
- Modify: `agent.py`
- Test: `tests/test_engine_foundation.py`

- [ ] **Step 1: Add action display tests**

```python
def test_talk_action_display_omits_dialogue_content(monkeypatch):
    engine = _make_engine(monkeypatch)
    display = engine._action_for_display(
        "找伊莎贝拉交谈：你昨晚是不是听到了脚步声？我觉得这很重要"
    )
    assert display in {"找伊莎贝拉交谈", "交谈昨晚脚步声"}
    assert "你昨晚是不是" not in display
```

- [ ] **Step 2: Tighten prompt contract**

In `agent.py`, change action JSON guidance:

- `action`: visible executable intent only.
- Do not include actual spoken sentence in `action`.
- Actual speech is generated by the conversation system.
- Replace `stay` guidance with `continue_current` semantics.

- [ ] **Step 3: Implement display sanitizer**

Extend `_action_for_display`:

- For `talk/socialize`, truncate at colon-like dialogue separators.
- Preserve target and topic.
- Never show quoted direct speech in blue action bubble.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_talk_action_display_omits_dialogue_content -q
```

Expected: pass.

## Task 6: Remove Visible Stay Loop

**Files:**
- Modify: `agent.py`
- Modify: `game_engine.py`
- Test: `tests/test_engine_foundation.py`

- [ ] **Step 1: Add tests for continue_current**

```python
def test_failed_decision_uses_continue_current_not_visible_stay(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    arthur.current_location = "Johnson Park"

    def failed_decision(*args, **kwargs):
        return {"ok": False, "error": "empty_response", "raw_response": ""}

    monkeypatch.setattr(arthur, "decide_next_action", failed_decision)
    engine._update_agent_schedules()

    assert arthur.current_action_type == "continue_current"
    assert "停留" not in arthur.current_action
```

- [ ] **Step 2: Normalize action taxonomy**

Add/normalize `continue_current` in engine labels and agent action type mapping. Keep `stay` as backward-compatible input but convert visible state to `continue_current`.

- [ ] **Step 3: Prevent passive loop**

If the last 2-3 actions were passive `continue_current/observe/rest`, increase priority for a concrete work/social/investigation action based on daily plan and location.

- [ ] **Step 4: Verify**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_failed_decision_uses_continue_current_not_visible_stay -q
```

Expected: pass.

## Task 7: Clear Completed Talk/Report Task

**Files:**
- Modify: `game_engine.py`
- Test: `tests/test_engine_foundation.py`

- [ ] **Step 1: Add test for report completion cleanup**

```python
def test_npc_report_to_crow_clears_repeated_share_information_goal(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    crow = engine.agents["Crow"]
    arthur.x, arthur.y = 10, 10
    crow.x, crow.y = 11, 10
    arthur.current_thought = "我要和警长共享情报"
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Crow",
        "action": "向警长共享情报",
        "thought": "我要和警长共享情报",
        "expected_result": "警长知道情况",
    }
    monkeypatch.setattr(arthur, "generate_response", lambda *args, **kwargs: "警长，我说明完了。")

    engine._complete_agent_action("Arthur Burton", arthur)

    assert arthur._pending_action is None
    assert arthur.current_action == ""
    assert arthur.current_thought == ""
```

- [ ] **Step 2: Implement completion cleanup**

After successful NPC-Crow and NPC-NPC chat completion:

- Clear `_pending_action`, `_last_decision`, `current_action`, `current_action_type`, `current_thought`.
- Add action history entry marking the talk/report as completed.
- Set a short cooldown for the same target/topic.

- [ ] **Step 3: Verify**

Run:

```powershell
python -m pytest tests/test_engine_foundation.py::test_npc_report_to_crow_clears_repeated_share_information_goal -q
```

Expected: pass.

## Task 8: Right-Edge Bubble Squeeze Fix

**Files:**
- Modify: `ui/templates/index.html`
- Test: `tests/test_ui_bubble_layout.py`

- [ ] **Step 1: Add static layout tests for stable bubble width**

```python
def test_speech_bubble_has_stable_width_and_no_edge_compression():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "box-sizing: border-box" in html
    assert "min-width: 180px" in html or "width: 220px" in html
    assert "max-width: 260px" in html
    assert "bubbleEl.style.maxWidth" not in html
```

- [ ] **Step 2: Fix bubble layer dimensions**

Change `#bubble-layer` bottom to use `var(--log-panel-height)` rather than the stale `160px`. Ensure it stays aligned with game container:

```css
#bubble-layer {
  position: absolute;
  top: 0;
  left: 0;
  right: 320px;
  bottom: var(--log-panel-height);
  overflow: visible;
  pointer-events: none;
}
```

- [ ] **Step 3: Fix clamping policy**

Bubble should shift/flip, not shrink. Use measured fixed-width bubble rect and clamp `left/top` inside game area. Remove any dynamic width changes near right edge.

- [ ] **Step 4: Browser verification**

Use in-app browser with a forced status payload or test hook to put an NPC near the right panel and assert:

- bubble `getBoundingClientRect().width >= 160`
- bubble right edge is left of side-panel left edge
- no text column is squeezed below readable width

## Task 9: UI Pending Speech Indicator

**Files:**
- Modify: `ui/templates/index.html`
- Test: `tests/test_ui_bubble_layout.py`

- [ ] **Step 1: Add static tests**

```python
def test_pending_speech_bubble_renders_typing_indicator():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "pending" in html
    assert '"..."' in html or "'...'" in html
```

- [ ] **Step 2: Render pending bubble**

In `bubbleSpeechText`, if payload has `pending: true`, render the speaker/target prefix with only dots as the body:

```text
山姆对伊莎贝拉说：...
```

Do not wait for the model response before creating this bubble. Animation is optional; the stable requirement is that the white bubble appears immediately with `...`.

- [ ] **Step 3: Verify**

Run:

```powershell
python -m pytest tests/test_ui_bubble_layout.py::test_pending_speech_bubble_renders_typing_indicator -q
```

Expected: pass.

## Task 10: Regression Matrix And Restart

**Files:**
- Modify: `.planning/npc-dialogue-ui-regressions/task_plan.md`

- [ ] **Step 1: Update checklist**

Add rows for:

- Timeout fallback speech logs.
- Three-second planning pause.
- Talk action pending white bubble.
- Crow report reservation and avoidance.
- Action text does not include full dialogue.
- Continue-current replacing visible stay loop.
- Completed talk/report cleanup.
- Right-edge bubble squeeze.

- [ ] **Step 2: Run full targeted regression**

Run:

```powershell
python -m py_compile game_engine.py agent.py ui/app.py
python -m pytest tests/test_engine_foundation.py::test_talk_decision_starts_chat_when_target_person_adjacent tests/test_engine_foundation.py::test_npc_chat_distance_two_keeps_one_gap_and_still_shows_bubbles tests/test_engine_foundation.py::test_talk_decision_to_crow_speaks_directly_when_adjacent tests/test_ui_bubble_layout.py -q
```

Expected: all pass.

- [ ] **Step 3: Restart and health check**

Run restart through hidden process, then independently check:

```powershell
Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue
Invoke-WebRequest -Uri "http://127.0.0.1:5000/" -UseBasicParsing -TimeoutSec 10
```

Expected: HTTP 200 and new PID.

## Execution Order

1. Task 1: fallback logs.
2. Task 2: planning pause.
3. Task 3: pending white bubble.
4. Task 4: Crow reservation/avoidance.
5. Task 7: completion cleanup.
6. Task 5: action text cleanup.
7. Task 6: remove visible stay loop.
8. Task 8 and Task 9: UI bubble squeeze and pending indicator.
9. Task 10: final regression, checklist, restart.

## Risk Notes

- Do not change the core observe -> think/plan -> act -> memory flow.
- Do not make NPCs report more aggressively to Crow while fixing speech execution.
- Do not let `stay` removal break backwards compatibility; normalize old `stay` to `continue_current`.
- Do not start DeepSeek on tasks requiring `ui/**`, `personas/**`, runtime logs, or broad `game_engine.py` rewrites.
- If a worker reports forbidden-path changes, reject that output and immediately re-scope future worker tasks to a safer slice.

## Open Questions For User Confirmation

- Pending bubble text is confirmed as `...`.
- Visible action wording for talk: default should be `找伊莎贝拉交谈：脚步声` and never include the actual spoken sentence.
- Crow queue behavior: default is second NPC waits or steps away, not auto-queues a visible line.

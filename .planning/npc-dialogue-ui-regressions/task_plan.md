# NPC Dialogue And UI Regression Checklist

Updated: 2026-06-05

Scope: Fix the user-reported regressions around NPC speech/reporting, logs, rule help, and bubble layout. Do not mix these with unrelated gameplay or structure work.

## Fixed Checklist

1. [x] Rules modal explains icons
   - Rule button explains yellow lightbulb: NPC believes it has information worth deep-diving.
   - Rule button explains question mark: NPC model response/error instability marker.
   - Evidence: `tests/test_ui_bubble_layout.py::test_rules_logs_and_bubbles_requirements` and `test_rules_button_handlers_are_global_for_inline_onclick`; served HTML contains the new text.

2. [x] Thought/plan/action text is not duplicated
   - Thought can contain reasoning and plan.
   - Action bubble/log shows concise execution intent, not repeated thought text.
   - Evidence: `tests/test_engine_foundation.py::test_visible_action_omits_reasoning_prefix`.

3. [x] Logs use normal font and explicit labels
   - No italic styling for thought/action/log body.
   - Each visible log row shows a label such as 思考, 计划, 行动, 对话, 错误.
   - Evidence: `tests/test_ui_bubble_layout.py::test_rules_logs_and_bubbles_requirements`; in-app browser computed `#log-content` font style as `normal`.

4. [x] NPC reaches sheriff and immediately speaks
   - If NPC action targets Crow, arrival triggers speech/report automatically.
   - NPC must not stand near Crow and switch back to thinking without saying anything.
   - Evidence: `tests/test_engine_foundation.py::test_talk_decision_to_crow_speaks_directly_when_adjacent`.

5. [x] NPC does not over-report weak information
   - Only urgent/high-value information should trigger active report to Crow.
   - Suspicion, ordinary clues, non-direct evidence, or hunches normally light the right-panel bulb and wait for player deep dive.
   - Evidence: `test_detective_target_not_inferred_for_weak_suspicion_without_target_person` and `test_detective_target_inferred_for_urgent_direct_report_without_target_person`.

6. [x] NPC-NPC conversation preserves one empty tile where possible
   - Left/right conversation prefers one empty tile.
   - Vertical fallback also keeps one empty tile when space allows.
   - Evidence: `test_path_adjacent_to_horizontal_priority_with_blocked_sides` now requires vertical fallback distance 2.

7. [x] Speech bubbles near right-side villager UI are not squeezed
   - Bubble width remains readable.
   - Bubble stays within game/bubble layer or flips/shifts instead of compressing into a thin strip at the side-panel boundary.
   - Evidence: `tests/test_ui_bubble_layout.py::test_bubbles_are_clamped_away_from_right_panel_and_owner_sprite`.

8. [x] NPC-NPC talk action triggers white speech bubbles
   - NPC-NPC talk/socialize actions trigger `_trigger_npc_chat` when the pair is within conversation distance.
   - Conversation distance is 2 for NPC-NPC, so one empty tile between models still counts as close enough.
   - The chat thread uses the same distance-2 threshold and no longer cancels one-gap conversations with the old distance-1 check.
   - Evidence: `test_talk_decision_starts_chat_when_target_person_adjacent` and `test_npc_chat_distance_two_keeps_one_gap_and_still_shows_bubbles`.

9. [x] NPC active reports to sheriff are stricter
   - Ordinary suspicious facts, borrowed tools, weak hunches, and non-urgent leads no longer auto-infer Crow as the target.
   - Active sheriff reports are reserved for explicit clues, important matters, immediate reports, or direct evidence.
   - Evidence: `test_detective_target_not_inferred_for_chinese_weak_tip_without_target_person`, `test_detective_target_not_inferred_for_weak_suspicion_without_target_person`, and `test_detective_target_inferred_for_urgent_direct_report_without_target_person`.

10. [x] Visible stay action removed in favor of continue_current
   - Failed or compatibility `stay` decisions are normalized to `continue_current`.
   - Player-facing action/log text says "继续当前事务" instead of "原地停留".
   - Evidence: `test_failed_action_decision_becomes_continue_current_action`.

## Worker Outcome

- Antigravity completed frontend-oriented changes; output was reviewed and covered by UI tests.
- DeepSeek touched forbidden frontend paths during a backend task and was cancelled. Its output was not trusted as-is; backend fixes were reviewed and integrated locally.
- For the NPC-NPC follow-up, DeepSeek was given a tests-only task but still reported forbidden-path/runtime changes in the shared worktree. Its output was rejected; the accepted fix was implemented and verified locally.

## Verification

- `python -m py_compile game_engine.py agent.py ui/app.py`
- `python -m pytest tests/test_ui_bubble_layout.py -q`
- `python -m pytest tests/test_engine_foundation.py::test_talk_decision_to_crow_speaks_directly_when_adjacent tests/test_engine_foundation.py::test_detective_target_not_inferred_for_weak_suspicion_without_target_person tests/test_engine_foundation.py::test_detective_target_inferred_for_urgent_direct_report_without_target_person tests/test_engine_foundation.py::test_visible_action_omits_reasoning_prefix tests/test_engine_foundation.py::test_path_adjacent_to_horizontal_priority_with_blocked_sides -q`
- `python -m pytest tests/test_engine_foundation.py::test_talk_decision_starts_chat_when_target_person_adjacent tests/test_engine_foundation.py::test_npc_chat_distance_two_keeps_one_gap_and_still_shows_bubbles tests/test_engine_foundation.py::test_talk_decision_to_crow_speaks_directly_when_adjacent tests/test_ui_bubble_layout.py -q`
- `python -m pytest tests/test_engine_foundation.py::test_failed_action_decision_becomes_continue_current_action tests/test_engine_foundation.py::test_detective_target_not_inferred_for_chinese_weak_tip_without_target_person tests/test_engine_foundation.py::test_detective_target_not_inferred_for_weak_suspicion_without_target_person tests/test_engine_foundation.py::test_detective_target_inferred_for_urgent_direct_report_without_target_person tests/test_engine_foundation.py::test_talk_decision_to_crow_speaks_directly_when_adjacent tests/test_engine_foundation.py::test_talk_decision_starts_chat_when_target_person_adjacent tests/test_engine_foundation.py::test_npc_chat_distance_two_keeps_one_gap_and_still_shows_bubbles -q`
- Restarted local server; `http://127.0.0.1:5000/` returned 200 on PID 8356.

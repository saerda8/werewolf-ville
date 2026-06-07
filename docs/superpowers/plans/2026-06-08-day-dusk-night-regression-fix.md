# Day Dusk Night Regression Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the current Day conversation, dusk discussion/voting, and night transition regressions so the game can reliably progress into Day 2 without right-sidebar UI leaks, stuck buttons, stale hints, or skipped visual states.

**Architecture:** Keep game rules and phase transitions in Python, keep the browser as a renderer/input layer, and make every visible state have a single owner. Conversation buttons, clue bulbs, dusk modals, vote buttons, and night progress bars must be driven by explicit state instead of incidental fallback text or side-panel leftovers.

**Tech Stack:** Python, Flask-SocketIO, Phaser/vanilla JavaScript, pytest, built-in browser verification.

---

## Scope Split

This plan has three independent repair areas. They must be implemented and verified separately before the final end-to-end pass.

1. **Day conversation UI:** deep-dive lightbulb clearing, normal chat availability, and active real-conversation locking.
2. **Dusk discussion/voting UI and flow:** no right-bottom UI, centered sheriff statement/vote modals, no filler speeches, disabled vote buttons, abstention row, slower detention sequence.
3. **Night transition:** camera lock at Crow's home, visible night mask, centered unclosable two-progress window, separate wolf and silver-knife progress, controls locked, and Day 2 confirmation working.

Day 1 daytime opening flow remains frozen unless a direct regression is proven.

---

## Current Root-Cause Map

| User-visible problem | Current likely source | Required fix |
| --- | --- | --- |
| Deep-dive lightbulb remains after NPC reveals the clue | Frontend `showBulb` only reads backend hint flags and does not clear locally when a real chat bubble starts | Add immediate local hint clearing for the target when deep-dive conversation begins or response bubble is shown; backend status should also clear delivered hints |
| Deep-dive quota exhausted disables normal chat | Agent list button rendering mixes normal chat availability and deep-dive availability | Render normal chat and deep-dive as separate capabilities; deep-dive quota must not disable normal chat |
| Dusk speech/vote UI appears in right-bottom/right side panel | `dusk-statement-panel` and `voting-panel` are still inside `#side-panel` | Move both panels into centered modal overlays outside the side panel |
| Vote button remains bright/clickable after Crow votes | Local UI only trusts refreshed server state and lacks immediate submit lock | Add local `crowVoteSubmitting`/`crowHasVoted` lock and disabled styling before the server round-trip |
| Abstainers are invisible | Vote summary rendering has candidate rows but no dedicated abstention row | Add bottom abstention row with abstainer portraits/icons |
| NPC dusk speeches say filler such as "先听警长怎么说" | Dusk prompt/fallback permits non-committal placeholder speech | Forbid filler in prompt and sanitize fallback text |
| Detained NPC final words vanish too fast | Result confirmation/escort sequence advances immediately after final words | Add sheriff announcement, final words bubble, 6-second hold, then escort |
| Night UI shows two wolf icons sharing one bar | Night overlay DOM has actor icons plus one shared progress fill | Replace with two rows: wolf icon + wolf progress, silver-knife icon + knife progress |
| Confirm dawn button does nothing | Client emits confirm without guaranteed state refresh, or backend phase result is not rendered after socket path | Add socket response handling and fallback refresh after confirm |
| Night camera/control behavior feels wrong | Phase lock is not a full camera/control lock and camera target is not fixed to Crow home | Add night camera lock target, disable keyboard/camera movement during night overlay |

---

## Worker Strategy

DeepSeek and Antigravity must be used, but with tighter boundaries than the failed read-only DeepSeek attempt.

### Antigravity Worker A: Frontend Modal and Night UI

**Allowed files:**
- `ui/templates/index.html`
- `tests/test_ui_bubble_layout.py`

**Forbidden files:**
- `personas/**`
- `game_engine.py`
- `engine_dusk.py`
- cache/runtime files

**Task:** Implement or review the centered dusk statement modal, centered voting modal, abstention row, disabled vote buttons, night dual progress UI, and source-contract tests.

**Validation:** HTML parse/static UI tests only. Main agent performs browser verification.

### DeepSeek Worker B: Backend Dusk/Night Static Logic

**Allowed files:**
- `engine_dusk.py`
- `ui/app.py`
- `tests/test_vote_flow.py`
- `tests/test_game_engine_night_loop.py`

**Forbidden files:**
- `personas/**`
- `ui/templates/index.html`
- cache/runtime files

**Runtime strategy:** Do not run full game loops that write persona memory. If a test would write runtime state, report the needed test and let the main agent run it.

**Task:** Fix/read-review no-filler dusk speech rules, vote result timing, confirm-dawn response handling, and backend status needed by the frontend.

**Validation:** Static review plus narrow tests only when they do not write `personas/`. Main agent checks `git status` after completion.

### Main Agent

**Responsibilities:**
- Own deep-dive/normal-chat frontend behavior.
- Review all worker diffs before trusting them.
- Run Python syntax checks and targeted tests.
- Restart service, verify frontend version, and use built-in browser for the UI states.
- Commit only clean, reviewed changes. Do not commit untracked `personas/*/typed_memory_index.json`.

---

## Task 1: Deep-Dive Bulb and Normal Chat Separation

**Files:**
- Modify: `ui/templates/index.html`
- Modify if needed: `game_engine.py`
- Test: `tests/test_ui_bubble_layout.py`
- Test if backend touched: `tests/test_engine_foundation.py`

**Requirements:**
- The clue lightbulb disappears as soon as the NPC's real conversation bubble appears for that deep-dive answer.
- A local optimistic clear is allowed so the player does not see stale hints while waiting for the next state refresh.
- Deep-dive quota exhaustion never disables normal chat with other NPCs.
- Normal chat and deep-dive buttons are separate capabilities.
- Deep-dive remains gated by "normal chat already done" and remaining deep-dive quota.

**Steps:**
- [ ] Add a frontend set such as `locallyClearedHintTargets` for NPC names whose clue hint has already been consumed in the current day.
- [ ] Clear that target immediately when a deep-dive request is submitted and again when a deep-dive/chat response bubble is rendered.
- [ ] Reset local cleared hints when the day number changes.
- [ ] Compute `normalChatAvailable` from normal chat state only.
- [ ] Compute `deepDiveAvailable` from clue/deep-dive state only.
- [ ] Render normal chat even when deep-dive quota is `0`.
- [ ] Add static UI tests proving the two availability checks are separate.
- [ ] Add static UI tests proving bulb display checks local cleared hint state.

**Acceptance:**
- After a deep-dive answer starts showing as a white speech bubble, the bulb is gone without waiting for another manual click.
- With deep-dive count used up, the player can still click normal chat for NPCs whose normal chat is still available.

---

## Task 2: Dusk Statement UI Must Be Centered

**Files:**
- Modify: `ui/templates/index.html`
- Test: `tests/test_ui_bubble_layout.py`

**Requirements:**
- Dusk sheriff statement input must not live in or render from the right side panel.
- It should appear as a centered modal similar to the deep-dive popup, with changed title/text/buttons.
- It must not create any chat/transcript UI in the right-bottom area.

**Steps:**
- [ ] Move `dusk-statement-panel` out of `#side-panel`.
- [ ] Wrap it in a centered overlay container.
- [ ] Update `renderDuskVotingFlow` to show/hide it with modal display style.
- [ ] Add a static test that `dusk-statement-panel` is not inside the side panel source range.
- [ ] Add a static test that the panel uses centered modal classes.

**Acceptance:**
- During Crow's dusk statement, the input appears in the center of the screen.
- The right-bottom/right-sidebar area has no extra speech input panel.

---

## Task 3: Voting UI Must Be Centered, Large, and State-Clear

**Files:**
- Modify: `ui/templates/index.html`
- Test: `tests/test_ui_bubble_layout.py`

**Requirements:**
- Voting UI must be a centered modal, not side-panel UI.
- Candidate vote buttons should be large and visually clear.
- After Crow votes, all vote buttons immediately become disabled/dim.
- Vote counts and voter icons update immediately after voting state refresh.
- A bottom row shows all abstainers' portraits/icons.

**Steps:**
- [ ] Move `voting-panel` out of `#side-panel`.
- [ ] Add modal card layout for candidate rows, vote counts, winner state, and abstainer row.
- [ ] Add local `crowVoteSubmitting` state.
- [ ] In `submitCrowVote`, disable all vote buttons immediately before socket/API call.
- [ ] Clear `crowVoteSubmitting` only after state refresh confirms the next stage or failure.
- [ ] Render `#voting-abstainers` from vote summary abstain data.
- [ ] Add static tests for disabled button logic, abstainer row, and no side-panel containment.

**Acceptance:**
- No voting UI appears in the right-bottom/right-sidebar zone.
- After one click, the clicked vote cannot be clicked again and other vote buttons are disabled.
- Abstentions are visible in a dedicated bottom row.

---

## Task 4: Dusk NPC Speech Must Not Be Filler

**Files:**
- Modify: `engine_dusk.py`
- Test: `tests/test_vote_flow.py`

**Forbidden speech patterns:**
- "我没意见"
- "先听警长"
- "先听克罗"
- "等大家说完"
- "暂时没有线索"
- Any equivalent sentence whose only content is waiting for someone else

**Requirements:**
- NPC may be uncertain, but must still give one concrete observation, suspicion, alibi, or reasoning basis.
- If the model returns empty or filler, fallback text must mention a concrete public fact, personal alibi, observed location, or suspicion target.

**Steps:**
- [ ] Add prompt wording that bans filler and requires a concrete claim.
- [ ] Add a sanitizer/helper that detects the forbidden filler patterns.
- [ ] Replace filler output with a deterministic, persona-safe fallback.
- [ ] Add tests for empty output and filler output.

**Acceptance:**
- Dusk discussion no longer shows "先听警长/克罗" style filler lines.
- Fallback still respects NPC knowledge boundaries and does not reveal hidden killer/wolf facts.

---

## Task 5: Vote Result and Detention Sequence Timing

**Files:**
- Modify: `engine_dusk.py`
- Test: `tests/test_vote_flow.py`

**Required sequence:**
1. All votes are complete.
2. Crow announces: highest-vote NPC will be jailed and asks for final words.
3. The selected NPC speaks once at their current position.
4. That final speech bubble remains visible for 6 seconds.
5. Crow escorts/drags the selected NPC to jail.
6. Only after the escort finishes does the next phase transition proceed.

**Steps:**
- [ ] Ensure vote result confirmation triggers Crow's announcement before escort.
- [ ] Ensure final words are generated/displayed before movement starts.
- [ ] Add or reuse a pause function with a 6-second final-words hold.
- [ ] Keep this delay scoped to final words, not every dusk line.
- [ ] Add tests proving phase/escort does not advance before final words are queued.
- [ ] Add tests proving the final-words hold duration is configured as 6 seconds.

**Acceptance:**
- The player can read the selected NPC's final words before they are moved.
- The detention sequence feels deliberate instead of instant.

---

## Task 6: Night Overlay, Camera Lock, and Dual Progress Bars

**Files:**
- Modify: `ui/templates/index.html`
- Modify if needed: `game_engine.py`
- Test: `tests/test_ui_bubble_layout.py`
- Test if backend touched: `tests/test_game_engine_night_loop.py`

**Requirements:**
- Night starts with camera locked on Crow's home.
- Scene remains visible but darkened by a night mask.
- Player camera/keyboard controls are disabled while night overlay is active.
- A centered window appears and cannot be closed.
- Row 1: werewolf icon plus wolf progress bar.
- Row 2: silver-knife icon plus silver-knife progress bar.
- Wolf progress and silver-knife progress are separate values.
- Do not show two wolf icons sharing one bar.

**Steps:**
- [ ] Replace current night actor/icon strip with two progress rows.
- [ ] Add `#night-wolf-progress-fill` and `#night-knife-progress-fill`.
- [ ] Render wolf progress as 0-100 based on wolf stage.
- [ ] Render knife progress as 0-100 based on silver-knife stage.
- [ ] Add a night camera lock key so the camera moves to Crow's home once per night phase.
- [ ] Block camera/keyboard movement while night overlay is active.
- [ ] Add static tests for the two distinct progress fills and absence of shared progress.

**Acceptance:**
- Night UI clearly shows two independent rows.
- The map is dark but visible.
- The player cannot move the camera during night transition.

---

## Task 7: Confirm Dawn Must Advance to Day 2

**Files:**
- Modify: `ui/templates/index.html`
- Modify: `ui/app.py`
- Modify if needed: `game_engine.py`
- Test: `tests/test_game_engine_night_loop.py`
- Test: `tests/test_ui_bubble_layout.py`

**Requirements:**
- Clicking "确认天亮" after progress completes must transition to the next day.
- Socket path and HTTP fallback path must both refresh state.
- If the server returns an error, the UI should not silently look stuck.

**Steps:**
- [ ] Add/verify socket response handler for `confirm_night_transition`.
- [ ] After socket emit, schedule a state refresh fallback.
- [ ] Ensure HTTP fallback already calls `fetchCurrentState()`.
- [ ] Verify backend returns a state-changing result when night is complete.
- [ ] Add source-contract tests for socket response/fallback refresh.
- [ ] Add backend test for confirm night transition after complete night progress.

**Acceptance:**
- The button is visible only when night progress is complete.
- Clicking it advances into the next morning or shows a clear error, never silent no-op.

---

## Task 8: Right-Bottom UI Ban Audit

**Files:**
- Modify: `ui/templates/index.html`
- Test: `tests/test_ui_bubble_layout.py`

**Banned in right-bottom/right-sidebar area:**
- Detective chat transcripts
- Dusk sheriff statement input
- Dusk voting controls
- Vote result controls
- Night confirmation/progress UI

**Allowed in right panel:**
- Game title/day/time summary
- Task progress
- NPC cards and small status indicators
- Existing global logs outside the right panel

**Steps:**
- [ ] Search for all panels rendered inside `#side-panel`.
- [ ] Keep only summary/tasks/NPC list content there.
- [ ] Move interaction modals to centered overlays.
- [ ] Add static tests that forbidden panel ids are outside `#side-panel`.

**Acceptance:**
- No major interaction UI appears in the forbidden right-bottom location.

---

## Task 9: Verification Plan

**Pre-code checks:**
- [ ] Confirm `git status` is clean except known untracked `personas/*/typed_memory_index.json`.
- [ ] Confirm DeepSeek and Antigravity availability before dispatch.

**Code checks:**
- [ ] Run Python syntax checks for changed Python files.
- [ ] Run targeted tests:
  - `tests/test_ui_bubble_layout.py`
  - `tests/test_vote_flow.py`
  - `tests/test_game_engine_night_loop.py`
  - relevant `tests/test_engine_foundation.py` tests for chat/deep-dive status
- [ ] Run broader regression suite if targeted tests pass.

**Browser checks:**
- [ ] Restart the local service on port 5000.
- [ ] Verify the page shows the new frontend version.
- [ ] Verify no `#chat-log` or forbidden right-side transcript exists.
- [ ] Force/render dusk statement state and confirm centered modal.
- [ ] Force/render voting state and confirm centered modal, disabled vote state, counts, and abstainer row.
- [ ] Force/render night state and confirm dark mask, locked camera, two progress rows, and working dawn confirmation.

**Git checks:**
- [ ] Inspect `git diff`.
- [ ] Confirm no `personas/` runtime files are staged.
- [ ] Commit only reviewed source/test/doc changes.

---

## Completion Criteria

This task is not complete until all of these are true:

- Deep-dive bulb disappears at real conversation bubble start.
- Deep-dive quota exhaustion does not block normal chat.
- Dusk statement and voting UI are centered modals.
- No forbidden UI appears in the right-bottom/right-sidebar area.
- Crow vote buttons disable immediately after voting.
- Vote counts and abstainers are visible.
- Dusk NPC speeches do not contain filler "先听警长/克罗" style lines.
- Vote winner final words remain visible for 6 seconds before jail escort.
- Night camera locks to Crow's home, map darkens, controls are locked.
- Night UI has separate wolf and silver-knife progress bars.
- Confirm dawn advances to the next day.
- Tests and browser verification pass.
- Final response reports the frontend version and commit status.


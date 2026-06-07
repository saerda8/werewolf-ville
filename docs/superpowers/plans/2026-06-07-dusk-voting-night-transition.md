# Dusk Voting and Night Transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved dusk gathering, ordered discussion, sheriff-decided tie break, automatic highest-vote detention, and hidden night transition UI.

**Architecture:** Keep dusk voting and detention rules in `engine_dusk.py`, reuse the existing gathering positions and movement helpers from `game_engine.py`, and expose explicit dusk/night presentation state through `get_status()`. Keep the frontend as a renderer and input surface: it sends Crow's statement and vote, displays results, locks interaction at night, and never decides the winning detainee.

**Tech Stack:** Python, Flask-SocketIO, Phaser/vanilla JavaScript, pytest.

---

### Task 1: Lock the approved rules with failing tests

**Files:**
- Modify: `tests/test_vote_flow.py`
- Modify: `tests/test_game_engine_night_loop.py`
- Modify: `tests/test_ui_bubble_layout.py`

- [ ] Add tests proving first-day knowledge reveal always occurs even when Lin Mei and Klaus are wolves.
- [ ] Add tests proving self-votes are valid for NPCs and Crow.
- [ ] Add tests proving the highest vote target is selected automatically and a sheriff vote breaks a top tie.
- [ ] Add tests proving Crow cannot arbitrarily jail a non-winning target.
- [ ] Add tests proving status exposes ordered dusk stages, 30-second voting deadline, vote icons/count data, and hidden night progress.
- [ ] Add frontend source-contract tests for dusk/night dimming, one Crow vote, result confirmation, and night interaction lock.
- [ ] Run targeted tests and confirm they fail for the missing behavior.

### Task 2: Implement dusk gathering and ordered discussion

**Files:**
- Modify: `engine_dusk.py`
- Modify: `game_engine.py`
- Test: `tests/test_vote_flow.py`

- [ ] Add explicit dusk stages: `gathering`, `knowledge_reveal`, `npc_discussion`, `crow_statement`, `voting`, `results`, `escorting`.
- [ ] Reuse the morning gathering ring positions for every living non-jailed participant, including Crow.
- [ ] Queue Crow's fixed gathering announcement before movement.
- [ ] Add the day-one fixed knowledge reveal with Lin Mei priority, Klaus fallback, then another eligible NPC fallback.
- [ ] Keep the long fixed reveal in one bubble unless the existing safe text limit requires sentence-boundary splitting.
- [ ] Determine clockwise speaker order from the final ring positions, starting at Crow's left side and ending with Crow.
- [ ] Generate NPC statements with memory/day-observation context and publish them in that order.
- [ ] Expose stage and ordered statements through status.
- [ ] Run `tests/test_vote_flow.py`.

### Task 3: Implement timed voting and automatic detention winner

**Files:**
- Modify: `engine_dusk.py`
- Modify: `ui/app.py`
- Test: `tests/test_vote_flow.py`
- Test: `tests/test_engine_foundation.py`

- [ ] Add a Crow vote submission endpoint/socket event separate from Crow's discussion statement.
- [ ] Allow every eligible participant to vote for self or abstain.
- [ ] Start a 30-second deadline after Crow says the fixed start-voting line.
- [ ] Generate NPC votes independently and treat an absent Crow vote at deadline as abstention.
- [ ] Compute integer counts and voter lists per target.
- [ ] Select the unique highest count automatically.
- [ ] For a top tie, select Crow's target when it is among tied leaders; otherwise use stable participant order.
- [ ] Reject attempts to jail anyone except the computed winner.
- [ ] Replace player-selected detention with result confirmation that triggers the winner's escort.
- [ ] Run the vote-flow and engine-foundation targeted tests.

### Task 4: Implement dusk and voting UI

**Files:**
- Modify: `ui/templates/index.html`
- Test: `tests/test_ui_bubble_layout.py`

- [ ] Add a dusk scene tint driven by the explicit dusk stage.
- [ ] Show the Crow statement input only when Crow is the current speaker.
- [ ] Render one row per eligible participant with front-facing portrait, name, and vote button.
- [ ] After Crow votes, hide every vote button and show waiting/results state.
- [ ] Render integer counts and voter portrait icons behind each candidate.
- [ ] Highlight the computed winner and show the sheriff tie-break explanation when used.
- [ ] Replace arbitrary jail buttons with one confirm-results button.
- [ ] Disable map, chat, deep-dive, and unrelated controls throughout gathering, voting, escorting, and night.
- [ ] Run JavaScript parse validation and UI source-contract tests.

### Task 5: Implement escort completion and hidden night UI

**Files:**
- Modify: `engine_dusk.py`
- Modify: `game_engine.py`
- Modify: `ui/templates/index.html`
- Test: `tests/test_game_engine_night_loop.py`
- Test: `tests/test_ui_bubble_layout.py`

- [ ] Queue Crow's fixed winner announcement in one bubble where readable.
- [ ] Move Crow and the winning target to the selected jail cell, then return Crow to the sheriff office.
- [ ] Enter night only after Crow reaches the office.
- [ ] Expose anonymous night stages and progress without exposing targets or actor identities.
- [ ] Keep wolf action before silver-knife action.
- [ ] Render two identical wolf icons and one anonymous silver-knife icon.
- [ ] Add a full-screen interaction lock and night progress UI.
- [ ] Show “夜晚结束” confirmation before transitioning to the next day.
- [ ] Run night-loop and UI tests.

### Task 6: Synchronize stable project documents

**Files:**
- Modify: `USER_REQUIREMENTS_LEDGER.md`
- Modify: `PROJECT_CONTINUITY.md`
- Modify: `ROADMAP.md`
- Modify: `CURRENT_SPRINT.md`

- [ ] Record the approved self-vote, automatic highest-vote detention, sheriff tie break, day-one fixed reveal, ordered discussion, and hidden night transition rules.
- [ ] Mark the Phase 3 implementation task active in the sprint.
- [ ] Reference this specification instead of duplicating detailed dialogue everywhere.

### Task 7: Verify the complete flow

**Files:**
- Verify only.

- [ ] Run Python compile checks for all affected Python files.
- [ ] Run targeted vote, night, foundation, and UI tests.
- [ ] Run the broader regression suite.
- [ ] Review `git diff` and confirm no unrelated/runtime persona files were changed.
- [ ] Restart the server and verify the latest page is served.
- [ ] Use the built-in browser to verify dusk tint, ordered discussion, voting rows/results, escort transition, and night lock/progress.
- [ ] Report the displayed frontend version.

## Completion Record

Completed on 2026-06-07.

- Implemented the staged dusk flow, automatic winner resolution, result confirmation, escort transition, and anonymous night confirmation.
- Synchronized the stable requirements ledger, continuity document, roadmap, sprint, and gameplay specification.
- Verified Python syntax and `git diff --check`.
- Verified the formal `tests` directory: `464 passed` with one pre-existing background-thread stderr warning.
- Restarted the local service and confirmed HTTP 200, frontend version `31`, Crow-vote wiring, and night-progress wiring.
- Confirmed the latest page loads in the built-in browser; a later screenshot refresh timed out in the browser bridge.

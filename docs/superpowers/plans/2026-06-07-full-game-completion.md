# Full Game Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Werewolf Ville as a playable Day 1 night through Day 4 endgame loop while freezing the already-stabilized Day 1 daytime flow.

**Architecture:** Keep Day 1 daytime gathering/interview behavior unchanged. Extend the backend from the night phase forward with explicit night stages, silver-knife resolution, multi-body discovery, Day 2/3/4 day scheduling, silver-bullet crafting, and final win resolution. Keep the frontend as a renderer/input layer that displays anonymous night stages, multiple bodies, and the Day 4 silver-shot choice without deciding secret facts.

**Tech Stack:** Python, Flask-SocketIO, Phaser/vanilla JavaScript, pytest, local pixel-art assets.

---

## Hard Rules

- Day 1 daytime is frozen. Do not change morning body discovery, Crow's opening, first daytime interview loop, Day 1 NPC dispersal, or existing Day 1 daytime UI unless a regression test proves a direct break from new night code.
- Night order is always wolf action first, silver-knife stage second.
- The silver-knife stage is shown every night as a fixed 60-second anonymous stage. It must appear even if the holder is dead, has already used the knife, or chooses not to act. The UI must not leak whether the knife is still valid.
- If the silver-knife holder is killed by wolves earlier in the same night, the knife is invalidated, but the anonymous silver-knife stage still runs visually.
- A successful silver-knife use can happen once per game. Choosing not to act does not consume it.
- One night may produce two bodies: one wolf victim and one silver-knife victim.
- A silver-knife kill against a werewolf creates a visibly marked werewolf corpse.
- Silver-knife confession does not cause automatic arrest. Players and NPCs may still suspect and vote against the confessor; other NPCs may falsely claim to be the holder.
- Day 2 and Day 3 required task is interviewing all currently interviewable living residents. Deep dives and silver objectives are optional.
- Day 4 skips free daytime activity: morning body announcement, one discussion round, then immediate vote and endgame resolution.

## Asset Decision

Final decision: use local generated pixel placeholders, not dog/wolf-pack sprites. The werewolf corpse is a project-owned wolf-headed humanoid corpse sprite with blood and a silver wound marker. Asset notes live in `docs/assets/ASSET_LICENSES.md`.

## Task 1: Freeze Current Baseline

**Files:**
- Modify: `tests/test_engine_foundation.py`
- Modify: `tests/test_game_engine_night_loop.py`
- Modify: `tests/test_ui_bubble_layout.py`

- [ ] Add or preserve regression tests proving Day 1 daytime opening/gathering/interview entry behavior still works.
- [ ] Add test names that explicitly document Day 1 daytime is not part of this implementation scope.
- [ ] Run `python -m pytest tests/test_engine_foundation.py tests/test_daytime_npc_behavior.py -q -p no:cacheprovider`.
- [ ] Expected: existing Day 1 daytime tests pass before and after night changes.

## Task 2: Explicit Night Stage State

**Files:**
- Modify: `game_engine.py`
- Modify: `tests/test_game_engine_night_loop.py`

- [ ] Add a public-safe `night_progress` payload with `stage`, `stage_started_at`, `stage_duration_seconds`, `stage_elapsed_seconds`, `stage_progress`, `stage_complete`, and anonymous actor labels.
- [ ] Represent stages as `wolf`, `silver_knife`, `complete`.
- [ ] Keep wolf stage soft-timed: target choice and movement can finish early, but slow model/path execution may extend with timeout fallback.
- [ ] Keep silver-knife stage visually fixed at 60 seconds every night.
- [ ] Add a backend flag that distinguishes visual silver-knife stage completion from actual knife validity.
- [ ] Run `python -m pytest tests/test_game_engine_night_loop.py -q -p no:cacheprovider`.

## Task 3: Wolf Night Action Completion

**Files:**
- Modify: `game_engine.py`
- Modify: `night_hunt.py`
- Modify: `tests/test_game_engine_night_loop.py`

- [ ] Ensure wolves choose one legal non-Crow victim per night while at least one wolf is active.
- [ ] Keep existing risk/path scoring where possible.
- [ ] If the model or path stalls beyond configured fallback time, choose a legal fallback target and complete the kill so the game cannot freeze.
- [ ] Death is immediate once the wolf reaches action range or fallback resolves.
- [ ] Record a body with source `wolf`, corpse kind `human`, and public morning announcement data.
- [ ] Run night-loop tests.

## Task 4: Silver-Knife Resolution

**Files:**
- Modify: `game_engine.py`
- Modify: `simulation_events.py`
- Modify: `tests/test_game_engine_night_loop.py`
- Create if useful: `tests/test_silver_knife_flow.py`

- [ ] Track silver-knife state: holder, used, invalidated, last decision, last target, and public-safe stage status.
- [ ] If holder is killed by wolf action that same night, set `invalidated=True` but still run the visual silver stage.
- [ ] If holder is dead from any earlier day, still run the visual silver stage but resolve as no action.
- [ ] If holder is alive and unused, allow model/rule decision to use or not use the knife.
- [ ] If holder chooses not to use it, leave `used=False` and complete only the visual stage.
- [ ] If holder uses it, move/resolve target and create a second body.
- [ ] If target is werewolf, mark body as `is_werewolf_corpse=True` and kill that werewolf.
- [ ] If target is good, mark body as normal corpse.
- [ ] Add tests for no-use, use-on-good, use-on-wolf, holder killed first, and every-night visual stage.

## Task 5: Multi-Body Morning Discovery

**Files:**
- Modify: `game_engine.py`
- Modify: `simulation_events.py`
- Modify: `ui/templates/index.html`
- Modify: `tests/test_engine_foundation.py`
- Modify: `tests/test_ui_bubble_layout.py`

- [ ] Preserve current first body behavior for Day 1.
- [ ] From Day 2 onward, support discovering and announcing all unannounced night bodies.
- [ ] Crow announcement says one name for one body and two names for two bodies.
- [ ] If any body is a werewolf corpse, announcement and status expose a public-safe indication that the corpse is visibly wolf-like.
- [ ] Ensure bodies remain on the map until existing burial/removal flow handles them.
- [ ] Add tests for one body, two bodies, and one wolf corpse plus one normal corpse.

## Task 6: Day 2 and Day 3 Morning Discussion

**Files:**
- Modify: `game_engine.py`
- Modify: `agent.py`
- Modify: `tests/test_engine_foundation.py`
- Modify: `tests/test_prompt_boundaries.py`

- [ ] After morning death announcement, run a clockwise one-round discussion.
- [ ] NPC statements must use observation packet, memory, public body announcements, and radius-10 observations.
- [ ] NPCs who did not observe anything relevant may say they heard nothing or only saw normal activity.
- [ ] The prompt must forbid hidden killer/holder/werewolf knowledge unless the NPC legitimately knows it.
- [ ] After Day 2/3 morning discussion, residents disperse into free activity.
- [ ] Add tests that a non-witness cannot state the true silver-knife actor.

## Task 7: Day 2 and Day 3 Sheriff Tasks

**Files:**
- Modify: `engine_tasks.py`
- Modify: `game_engine.py`
- Modify: `ui/templates/index.html`
- Modify: `tests/test_engine_foundation.py`
- Modify: `tests/test_ui_bubble_layout.py`

- [ ] Day 2 required task: interview all living, unjailed interviewable NPCs.
- [ ] Day 3 required task: interview all remaining living, unjailed interviewable NPCs.
- [ ] Deep dives remain optional and reset to 3 per day.
- [ ] One optional silver objective can be completed per day.
- [ ] Day 2 may collect either tool or silver item.
- [ ] Day 3 may collect whichever one remains.
- [ ] Optional silver objectives must not block dusk entry.
- [ ] UI task text must clearly mark optional tasks.

## Task 8: Silver Bullet Crafting and Day 4 Shot

**Files:**
- Modify: `game_engine.py`
- Modify: `engine_tasks.py`
- Modify: `ui/app.py`
- Modify: `ui/templates/index.html`
- Modify: `tests/test_engine_foundation.py`
- Modify: `tests/test_ui_bubble_layout.py`

- [ ] If tool and silver item are both collected by the end of Day 3, Day 3 night displays a public message that Crow will craft one silver bullet.
- [ ] The silver bullet is available only after Day 3 night and only once.
- [ ] Day 4 post-vote with exactly one live/free werewolf and a silver bullet enters `pending_silver_shot`.
- [ ] UI displays a modal where Crow chooses one living resident to shoot.
- [ ] Shooting a werewolf ends with villagers winning.
- [ ] Shooting a good resident ends with werewolves winning if any werewolf remains.
- [ ] If two wolves are alive after Day 4 vote, werewolves win immediately because one bullet cannot stop both.
- [ ] If no wolves remain after Day 4 vote, villagers win immediately.
- [ ] If one wolf remains and no silver bullet exists, werewolves win immediately.

## Task 9: Day 4 Flow

**Files:**
- Modify: `game_engine.py`
- Modify: `engine_dusk.py`
- Modify: `tests/test_vote_flow.py`
- Modify: `tests/test_engine_foundation.py`

- [ ] Day 4 morning announces bodies.
- [ ] Day 4 runs one discussion round.
- [ ] Day 4 skips free daytime actions and interview/silver tasks.
- [ ] Day 4 proceeds directly to voting.
- [ ] Day 4 vote result triggers the final win-resolution branch from Task 8.
- [ ] Add tests for all final branches.

## Task 10: Confession, Lying, and Memory Rules

**Files:**
- Modify: `agent.py`
- Modify: `game_engine.py`
- Modify: `tests/test_prompt_boundaries.py`
- Modify: `tests/test_agent_memory_consolidation.py`

- [ ] Silver-knife holder may confess or hide use.
- [ ] Other NPCs may falsely claim they held or used the silver knife.
- [ ] Confession creates a statement memory, not a verified fact memory.
- [ ] The system must not automatically jail a confessor.
- [ ] NPC suspicion may increase from confession or conflicting claims.
- [ ] Prompt must distinguish "someone claimed X" from "X is proven."

## Task 11: Frontend Night and Body UI

**Files:**
- Modify: `ui/templates/index.html`
- Modify: `tests/test_ui_bubble_layout.py`
- Add optional assets under: `static/assets/effects/`

- [ ] Night overlay always renders wolf stage and silver-knife stage.
- [ ] Silver-knife stage uses anonymous icon/text and fixed 60-second display.
- [ ] UI never shows silver holder, whether holder is alive, whether knife is used, or target identity during night.
- [ ] Multiple bodies render simultaneously.
- [ ] Werewolf corpse uses a clear wolf/werewolf visual plus label/marker.
- [ ] Day 4 silver-shot modal lists only living selectable residents.
- [ ] Add rule modal text explaining the silver-knife stage does not reveal whether the holder is alive or active.

## Task 12: Assets

**Files:**
- Add: `static/assets/effects/werewolf_corpse.png`
- Add: `static/assets/effects/body_blood_overlay.png`
- Add: `static/assets/effects/silver_knife_icon.png`
- Add: `static/assets/effects/silver_bullet_icon.png`
- Add: `static/assets/effects/silver_necklace_icon.png`
- Add: `static/assets/effects/tool_icon.png`
- Add or modify: `docs/assets/ASSET_LICENSES.md`

- [ ] Prefer local or CC0 assets.
- [ ] If using OpenGameArt CC0 wolf art, record title, author, source URL, and license.
- [ ] If generated or hand-edited locally, record that the derived file was created for this project.
- [ ] Keep icons small, readable, and consistent with the existing pixel-art map.

## Task 13: Verification

**Files:**
- Verify only.

- [ ] Run `python -m py_compile agent.py game_engine.py llm.py ui/app.py engine_bubbles.py engine_dusk.py engine_tasks.py night_hunt.py simulation_events.py world_config.py`.
- [ ] Run targeted backend tests for night, vote, Day 4, memory, and task logic.
- [ ] Run `python -m pytest tests/test_ui_bubble_layout.py -q -p no:cacheprovider`.
- [ ] Run `python -m pytest -q -p no:cacheprovider`.
- [ ] Confirm `git status --short -- personas` has no runtime pollution; clean generated runtime files if needed.
- [ ] Restart the server from the current workspace.
- [ ] Use the built-in browser to verify page loads, frontend version, night overlay, silver stage, body render, and Day 4 shot UI.
- [ ] Commit all non-runtime project files.

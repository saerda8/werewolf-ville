# Werewolf Ville Gameplay Expansion Roadmap

> **For agentic workers:** Use subagent-driven development when implementing. Each phase below is intentionally separable so DeepSeek or Antigravity can own one slice while the host agent reviews integration and tests.

**Goal:** Expand Werewolf Ville into an 8-player detective/werewolf game with two wolves, dusk voting, jail, silver-resource objectives, a hidden silver knife role, richer NPC buttons, and a persistent task list.

**Architecture:** Add focused rules modules around the existing `game_engine.py`. Preserve engine ownership of phase transitions and world truth, but move voting, roles, silver objectives, knife action, and task generation into small testable modules.

**Tech Stack:** Python 3.10, Flask-SocketIO, Phaser 3, pytest, existing OpenAI-compatible text-model gateway.

---

## Delegation Policy

Before implementation, run:

- DeepSeek preflight: native Windows `claude.exe` through the Claude Code CLI-driven DeepSeek worker.
- Antigravity preflight: Antigravity CLI doctor, CLI worker only.

Preferred split:

- DeepSeek: backend state machines, tests, prompt contracts.
- Antigravity: frontend UI, Phaser interactions, right-panel layout, task list behavior.
- Host agent: task boundaries, review, integration, final verification.

The user has explicitly allowed DeepSeek and Antigravity to read and modify project code. Platform usage limits may still block calls; do not treat those as user policy.

## Phase 1: 8 Active Characters And Double Werewolves

**Goal:** Convert the game from Crow + 5 NPC / 1 wolf to Crow + 7 NPC / 2 wolves.

**Files:**

- Modify `world_config.py`
- Modify `game_engine.py`
- Modify `config.yaml`
- Modify persona initialization if needed
- Add or update `tests/test_world_config.py`
- Add or update `tests/test_runtime_roles.py`
- Add or update `tests/test_engine_foundation.py`

**Requirements:**

- Active participant count is 8.
- Crow is always detective/sheriff and never wolf.
- Exactly 2 wolf names are randomly selected from the 7 NPCs.
- Wolf identities change per game seed.
- Both wolves know each other through runtime prompt/context.
- Public job/persona remains independent from wolf identity.
- Model assignment supports 8 participants. It must allow shared models and not require 8 distinct APIs.
- Every participant has a Chinese player-facing display name. Internal ids may remain stable English keys, but UI, prompts, bubbles, tasks, and action summaries use Chinese names.
- Runtime state separates world truth from per-agent private knowledge, so hidden roles and items are not globally exposed to NPC prompts.
- Crow's sheriff area exposes three player-facing rooms: sheriff office/home plus two prison rooms.

**Tests to add:**

- `test_eight_active_participants_include_crow_and_seven_npcs`
- `test_two_werewolves_are_random_non_crow_residents`
- `test_wolves_receive_each_other_as_runtime_pack_knowledge`
- `test_public_jobs_are_map_aligned_after_expansion`
- `test_model_assignment_allows_reused_models_for_eight_agents`
- `test_visible_character_names_use_chinese_display_names`
- `test_runtime_hidden_roles_are_not_serialized_as_public_agent_knowledge`
- `test_sheriff_area_contains_office_and_two_prison_rooms`

**Acceptance:**

- Starting a game exposes 8 personas in `/api/status`.
- Director summary shows two wolves.
- Existing 6-character tests are updated, not deleted blindly.

## Phase 2: Dusk Discussion, Voting, And Jail

**Goal:** Add the first-day opening script and post-day dusk phase where residents gather, discuss, vote, review vote totals, and Crow jails one selected person.

**Files:**

- Create `dusk_vote.py`
- Modify `game_engine.py`
- Modify `ui/templates/index.html`
- Modify `ui/app.py`
- Add `tests/test_dusk_vote.py`
- Add `tests/test_game_engine_dusk_vote.py`

**Rules:**

- At game start, Crow speaks first in 3-5 short bubbles that introduce himself as sheriff, name the victim, mention beast-like wounds, explain that cause of death still needs investigation, explain that he will interview everyone, and tell the player that a lit right-panel bulb means an NPC has a clue or important thought.
- After Crow's opening script, Crow asks everyone what they did last night.
- The first speaking round is only alibis and reactions; NPCs do not leave yet.
- After first-round alibis, Crow says residents may go do their own work and that he will summon everyone again at dusk.
- Only after that Crow line do NPCs state where they are going and disperse.
- After body-site/day conversation ends, transition to dusk discussion before night.
- The right panel has no direct `enter night` button. The player-facing phase advance button is `结束本回合开始讨论`.
- Clicking `结束本回合开始讨论` gathers all eligible participants and starts dusk discussion.
- Dusk discussion is one short round of statements.
- Dusk discussion statements are model-assisted independent NPC decisions, not fixed templates.
- NPC votes are model-assisted independent decisions with short reasons, constrained to legal candidates.
- Each NPC discussion/vote prompt includes only that NPC's public memory, private memory, observations, suspicion state, and legal hidden knowledge.
- Wolves may protect each other or redirect suspicion, but they do not know knife holder or private clues unless inferred from observed events.
- Knife holder and clue holders may hide information from others; other NPCs treat those identities and thoughts as black boxes.
- NPCs vote before the player makes the final choice.
- After all NPC votes are recorded, show a vote summary panel listing each vote (`voter -> target`) and total votes per candidate.
- Crow/player vote or tiebreak decision is explicit and happens after the player reviews the vote summary panel.
- Highest-vote candidate is jailed.
- Jailed person cannot move, talk, vote, act at night, be killed at night, or count as alive for win conditions.
- If jailed person is wolf, that wolf is eliminated.
- Recommended tie rule: Crow breaks ties; if Crow does not choose, no one is jailed.
- The jailed person gives last words before leaving.
- After last words, Crow escorts the jailed person to one of the two prison rooms in Crow's sheriff area and speaks an end-of-day line warning everyone to return home and lock their doors.
- Prison rooms are physical map rooms with multiple anchor points; jail capacity must not be hardcoded to only two prisoners.
- Night starts only after Crow's escort/lock-door line finishes.

**Tests to add:**

- `test_dusk_phase_starts_after_day_discussion`
- `test_opening_intro_is_split_into_multiple_crow_bubbles`
- `test_opening_intro_mentions_sheriff_victim_beast_marks_and_lightbulb_hint`
- `test_first_round_alibis_happen_before_residents_depart`
- `test_crow_announces_dusk_recall_before_departure_round`
- `test_end_turn_discussion_button_starts_dusk_not_night`
- `test_dusk_discussion_uses_agent_specific_context`
- `test_vote_candidates_exclude_dead_and_jailed_people`
- `test_npc_votes_complete_before_player_final_choice`
- `test_npc_vote_prompt_does_not_reveal_hidden_roles`
- `test_npc_vote_records_model_reason_and_legal_target`
- `test_vote_summary_panel_lists_each_vote_and_candidate_totals`
- `test_jailed_person_cannot_move_or_vote`
- `test_jailed_werewolf_reduces_active_wolf_count`
- `test_tie_requires_crow_tiebreak_or_no_jail`
- `test_jailed_person_last_words_happen_before_night`
- `test_crow_escort_prison_line_happens_before_night_transition`
- `test_jailed_person_is_moved_to_prison_room_anchor`
- `test_multiple_jailed_people_do_not_overlap_in_prison_rooms`

**Acceptance:**

- UI shows dusk discussion and vote state.
- UI has `结束本回合开始讨论` instead of a direct `进入夜晚` control.
- Vote result panel lets the player inspect NPC votes before choosing Crow's final vote or tiebreak decision.
- Game log clearly distinguishes `death` from `jailed`.
- The start of a new game feels like a story/tutorial rather than immediate raw NPC turn-taking.

## Phase 3: Werewolf Knowledge Progression

**Goal:** Make the first two days reveal the werewolf premise gradually.

**Files:**

- Create or extend `simulation_events.py`
- Modify `night_hunt.py`
- Modify `game_engine.py`
- Add `tests/test_werewolf_knowledge_progression.py`

**Rules:**

- Day 1 body has beast-bite wound facts but no confirmed werewolf fact.
- A college/library NPC must investigate a bookshelf/library object on Day 1.
- That NPC discovers the possible werewolf explanation.
- Before Day 1 dusk vote, the possibility of a werewolf must be raised.
- Day 2 second beast-bite body upgrades `werewolf_theory_state` to `confirmed`.
- Crow's silver bullet task only unlocks after confirmation.

**Tests to add:**

- `test_day_one_body_has_beast_bite_but_werewolf_unknown`
- `test_library_research_creates_werewolf_possibility_clue`
- `test_day_one_dusk_discussion_mentions_werewolf_possibility`
- `test_second_beast_bite_confirms_werewolf_for_crow`

**Acceptance:**

- The game no longer tells everyone "it is a werewolf" on Day 1.
- The player can trace how the town learns the premise.

## Phase 4: Silver Bullet Resource Objectives

**Goal:** Add the tool/jewelry resource chain and one-major-action-per-day limit.

**Files:**

- Create `silver_objectives.py`
- Modify `game_engine.py`
- Modify `ui/templates/index.html`
- Modify `ui/app.py`
- Add `tests/test_silver_objectives.py`
- Add `tests/test_game_engine_silver_objectives.py`

**Rules:**

- Resource statuses track tool, jewelry, bullet.
- Crow can acquire either tool or jewelry on Day 2.
- Crow can acquire the remaining resource on Day 3.
- Crow can only complete one silver-resource major action per day.
- Tool source is Harvey Oak Supply Store owner.
- Jewelry source is a random female NPC; she may be wolf.
- If source NPC is wolf, they can refuse or lie.
- Wolves can pre-buy/pre-borrow/pre-steal the resource.
- Any obstruction creates factual clue records tied to a witness/source.
- Crow can craft exactly one silver bullet after both resources are obtained.

**Tests to add:**

- `test_crow_can_collect_only_one_silver_resource_per_day`
- `test_tool_source_can_be_wolf_and_refuse`
- `test_jewelry_holder_can_be_wolf_and_claim_missing`
- `test_wolf_interference_generates_witness_clue`
- `test_bullet_becomes_craftable_after_tool_and_jewelry`
- `test_bullet_can_only_be_crafted_once`

**Acceptance:**

- Task list changes from "collect either" to "collect remaining" based on progress.
- Failed acquisition is not silent; it becomes a suspicion path.

## Phase 5: Hidden Silver Knife Role

**Goal:** Add one good NPC with a one-use silver knife night action.

**Files:**

- Create `knife_role.py`
- Modify `game_engine.py`
- Modify `night_hunt.py`
- Add `tests/test_knife_role.py`
- Add `tests/test_game_engine_knife_night_action.py`

**Rules:**

- Holder is random from non-Crow, non-wolf NPCs.
- Holder knows privately.
- Holder does not reveal by default.
- Knife can be used once at night.
- Knife can kill a normal NPC or wolf.
- If holder dies before use, knife is gone.
- Wolves can infer and target holder.
- Knife action creates traceable events and clues.

**Tests to add:**

- `test_knife_holder_is_good_non_crow_npc`
- `test_knife_can_be_used_once`
- `test_knife_kills_wolf`
- `test_knife_can_accidentally_kill_villager`
- `test_knife_removed_if_holder_dies_before_use`
- `test_wolves_can_prioritize_suspected_knife_holder`

**Acceptance:**

- Director view can show knife holder for debugging.
- Player-facing view should not reveal it unless clue/dialogue exposes it.

## Phase 6: Right Panel NPC Actions And Conversation Flow

**Goal:** Replace the always-on chat entry with NPC-card-driven actions.

**Files:**

- Modify `ui/templates/index.html`
- Modify `ui/app.py`
- Modify `game_engine.py`
- Add `tests/test_detective_conversation_flow.py`
- Add UI smoke tests if browser automation is available.

**Rules:**

- Every NPC card has `记录`, `灯泡`, `交谈`, `深入挖掘` controls as applicable.
- `交谈` appears if the NPC has not had normal chat today.
- Clicking `交谈` moves Crow to the NPC.
- When Crow arrives, NPC speaks first.
- Normal chat consumes that NPC's daily normal chat.
- `深入挖掘` appears after normal chat if global quota remains.
- Clicking `深入挖掘` opens a large modal input.
- After confirm, Crow moves to NPC, Crow speaks first, NPC replies.
- Deep dive quota is 3 total and never resets.
- The right panel or lower-right task area always shows remaining deep dive count, for example `深入挖掘：2 / 3`.

**Tests to add:**

- `test_normal_chat_button_visible_until_daily_chat_used`
- `test_click_normal_chat_moves_crow_and_npc_speaks_first`
- `test_normal_chat_progress_counts_once_per_npc_per_day`
- `test_deep_dive_button_visible_after_normal_chat_when_quota_remains`
- `test_deep_dive_consumes_global_quota_without_daily_reset`
- `test_deep_dive_remaining_count_is_visible_in_task_area`
- `test_dead_or_jailed_npc_has_no_chat_buttons`

**Acceptance:**

- Right panel no longer jitters with live text.
- The player can always see how many deep dives remain without opening a modal.
- Text output stays in bubbles/log/history, not inside NPC card body.

## Phase 7: Task List And Win/Loss Conditions

**Goal:** Add player-facing task list and final victory logic.

**Files:**

- Create `tasks.py`
- Modify `game_engine.py`
- Modify `ui/templates/index.html`
- Add `tests/test_task_list.py`
- Add `tests/test_win_conditions.py`

**Task rules:**

- Every day: talk to all currently talkable NPCs, progress `n / total`.
- Day 1: investigate alibis and beast-bite wound; optional library clue follow-up.
- Day 2: collect one silver resource.
- Day 3: collect remaining silver resource.
- Day 4: craft bullet and optionally shoot suspected wolf.

**Win/loss rules:**

- Good wins when both wolves are eliminated.
- Wolves win when wolves are at parity or better against unjailed good characters.
- Wolves win if Crow dies.
- Prototype default: if Day 4 silver bullet kills one wolf and another wolf remains alive, wolves win.
- If Crow shoots a good NPC with the only bullet while both wolves live, wolves enter immediate win unless another good-side wolf-kill path remains.

**Tests to add:**

- `test_daily_talk_task_counts_living_unjailed_npcs`
- `test_day_two_task_shows_choose_one_silver_resource`
- `test_day_three_task_shows_remaining_resource`
- `test_day_four_optional_bullet_shot_task`
- `test_good_win_when_both_wolves_eliminated`
- `test_wolves_win_on_parity`
- `test_wolves_win_if_crow_dies`
- `test_day_four_remaining_wolf_after_bullet_is_wolf_win`

**Acceptance:**

- Task list serializes through `/api/status`.
- UI renders complete/incomplete/optional states clearly.

## Phase 8: Prompt Contracts And Observability

**Goal:** Make model behavior consistent and debuggable with the new rules.

**Files:**

- Modify `agent.py`
- Modify `llm.py` if needed
- Modify `game_engine.py`
- Add `tests/test_prompt_contracts.py`

**Requirements:**

- Wolf prompts include teammate identity.
- Wolf prompts do not include knife holder, silver-jewelry holder, non-teammate hidden roles, or other NPC private thoughts unless the wolf personally observed enough evidence.
- Villager prompts distinguish facts from suspicion.
- Villager prompts do not include complete wolf lists, director summary, knife holder, or silver-jewelry holder unless that villager is the holder or direct observer.
- Knife-holder prompts preserve secrecy.
- Clue-provider prompts include only the clue they observed and their own interpretation, not the rule-engine truth behind it.
- Discussion, vote, day action, and night action prompts all use per-agent filtered context.
- Model-visible names, locations, tasks, and action summaries use Chinese display strings.
- Silver-objective prompts constrain refusal/interference to legal states.
- LLM errors and empty responses remain visible in director view.
- All free-form model decisions are validated before mutating world truth.

**Tests to add:**

- `test_wolf_prompt_contains_teammate_names`
- `test_wolf_prompt_excludes_unobserved_knife_holder`
- `test_villager_prompt_does_not_reveal_hidden_roles`
- `test_clue_provider_prompt_does_not_reveal_global_truth`
- `test_knife_holder_prompt_mentions_private_secret_only_to_holder`
- `test_phase_prompts_are_built_from_agent_specific_knowledge`
- `test_model_visible_text_uses_chinese_display_names`
- `test_invalid_vote_target_is_rejected`
- `test_invalid_silver_resource_claim_does_not_mutate_state`

**Acceptance:**

- Model failures produce clear fallback actions.
- No model can invent a silver resource, jail result, or wolf death without rule-engine validation.

## First Implementation Slice Recommendation

Start with Phase 1 and Phase 2 together only if worker capacity is available. Otherwise start with Phase 1 alone.

Why:

- 8 active participants and 2 wolves are the foundation for all later rules.
- Voting/jail depends on multiple wolves but not on silver resources.
- Silver resources and knife role should wait until the phase model and jailed-state semantics are stable.

## Verification Commands

Use these after each phase:

```powershell
$env:PYTHONPATH='G:\Trae-Project\werewolf-ville'
pytest -q
python -m py_compile game_engine.py agent.py llm.py ui\app.py world_config.py
```

After frontend changes:

```powershell
netstat -ano | Select-String ':5000\s+.*LISTENING'
```

Restart local server after backend or template changes, then smoke test:

```text
http://127.0.0.1:5000/
```

Runtime checks:

- Start a new game.
- Confirm 8 personas appear.
- Confirm 2 wolves in director summary.
- Confirm right-panel buttons follow state.
- Confirm dusk vote jails one person.
- Confirm night kills exactly one person total.
- Confirm Day 1 library clue and Day 2 werewolf confirmation.
- Confirm silver tasks appear on Days 2-4.

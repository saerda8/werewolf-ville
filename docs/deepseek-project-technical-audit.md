# Werewolf Ville — DeepSeek Project Technical Audit

> Generated: 2026-06-04  
> Scope: Architecture, gameplay systems, LLM/NPC model, UI, test coverage, fragile areas  
> Method: Source-code & file inspection only; no code or persona files were altered.

---

## 1. Project Architecture

| Layer | Key Files | Role |
|---|---|---|
| **Entry** | `main.py` | Single entry; calls `ui.app.start_ui()` |
| **Config** | `config.yaml`, `config_loader.py` | YAML-driven: game durations, LLM providers, agent model map, memory/behavior params |
| **World** | `world_config.py` | 8‑active‑character roster (Crow + 7 NPCs), 6 public landmarks, 18 ambient sprites, sheriff area, `validate_world_config()` assertion guard |
| **Game Engine** | `game_engine.py` (~5.8k lines) | Central state machine: day/dusk/night phases, agent lifecycle, gathering/dusk/night ticks, collision, pathfinding, silver progression, jailed system, voting |
| **Agent** | `agent.py` (~1.4k lines) | Per-NPC MD‑file persistence (`soul.md`, `agent.md`, `memory.md`, `cognition.md`, `notebook.md`), memory index with recency/relevance/importance scoring, BDI‑style `decide_next_action()`, spatial memory, daily plans |
| **LLM** | `llm.py` | OpenAI‑compatible client, semaphore‑limited concurrency, per‑agent model routing, runtime override for non‑chat2api providers, DeepSeek function‑calling path |
| **UI** | `ui/app.py`, `ui/templates/index.html` | Flask + Flask‑SocketIO HTTP/WS server; Phaser.js map rendering (in HTML template); HTTP API for game controls; WebSocket for real‑time state push |
| **Night** | `night_hunt.py` | `HuntCandidate` scoring (path_length + witness_risk×20), `NightHuntState` dataclass, `choose_forced_target()`, `build_trace_clues()` |
| **Simulation Events** | `simulation_events.py` | `BodyRecord`, `ClueRecord` dataclasses; `undelivered_clues_for()` filtering |
| **Utils** | `utils.py` | `safe_truncate()`, `tokenize_chinese()` |

**File sizes (lines):**
- `game_engine.py`: ~5,759 lines (largest, most complex)
- `agent.py`: ~1,431 lines
- `world_config.py`: ~204 lines
- `night_hunt.py`: ~80 lines
- `simulation_events.py`: ~45 lines
- `llm.py`: ~500+ lines (estimated)
- `ui/app.py`: ~638 lines
- `main.py`: ~15 lines
- `config.yaml`: ~97 lines

---

## 2. Implemented Gameplay Systems

### 2.1 Daily Cycle (Day → Dusk Discussion → Night → Day+1)
- **Day** (`GamePhase.DAY`): `_day_tick()` updates `game_hour` (7–24 mapped over real seconds), runs morning gathering (Day 1 only), then `_update_agent_schedules()` + `_move_agents()` + periodic LLM reflection (`_llm_tick()`).
- **Dusk Discussion** (`GamePhase.DUSK_DISCUSSION`): Started by player via `start_dusk_discussion()`. Requires all living non-jailed non-Crow NPCs to have been interviewed (normal chat) first. NPCs generate votes (LLM preferred, deterministic fallback). Player chooses jail target via `jail_vote_target()`.
- **Night** (`GamePhase.NIGHT`): Wolves hunt via `NightHuntState`. `_advance_night_hunt()` moves wolf toward target, kills on adjacency, handles forced completion. Silver knife auto-use (`_maybe_use_silver_knife_at_night()`).
- **Day transition** (`_transition_to_day()`): Checks win conditions (all wolves dead → villagers win; wolf majority → wolf win; day > 5 → wolf win), compresses memories, generates daily plans, re‑gathers agents near body.

### 2.2 Morning Gathering (Day 1)
- Serial round‑robin speech (two rounds). Round 1: speak about whereabouts/unease; no leaving. Round 2: announce departure plan → NPC leaves to scheduled destination.
- Crow delivers multi‑bubble case intro (fallback lines + optional LLM enrichment).
- _Sanitize_round_one_speech() strips accusations, wound analysis, self‑introductions.
- Burial sequence: Crow drags the initial body to Johnson Park grave.
- Configurable timeouts per speaker (gathering_turn_timeout ~18s, gathering_per_speaker_timeout ~20s).

### 2.3 NPC Behaviour (BDI Decision Loop)
- `Agent.decide_next_action()` constructs a JSON prompt with soul, agent.md, memory, cognition, nearby info, scene objects, available locations, action history.
- Returns `action_type` (move_to/stay/observe/inspect/work/rest/investigate/socialize/talk/hide), `target_location`, `target_object`, `target_person`, `action`, `thought`, `expected_result`.
- Game engine validates/fixes decisions: fuzzy location matching, fallback to character defaults, consecutive passive-action avoidance, missing object resolution.
- Async LLM calls per NPC at `action_decision_interval_seconds` (20s), concurrency gated by semaphore.

### 2.4 Jailed/Prison System
- Player chooses a target after dusk votes → `jail_vote_target()` → target placed in one of two prison cells (anchored at sheriff-area coordinates).
- Jailed NPCs: cannot move, cannot be interviewed, cannot vote, cannot be night‑hunt targets, excluded from win-condition counts.
- Per‑persona status exposes `jailed`, `prison_cell`, `chat_available=False`.

### 2.5 Silver Resource Progression
- Day 2+: `acquire_silver_bullet()` (from Arthur at Harvey Oak Supply Store; fails if Arthur is wolf).
- Day 2+: `acquire_silver_jewelry()` (from a random non‑Crow holder; fails if holder is wolf or blocked by nearby wolf).
- Day 4+: `craft_silver_bullet()` (requires both bullet tool and jewelry acquired).
- `shoot_silver_bullet()`: one‑use instant kill on any target.
- `use_silver_knife()`: one‑use night‑only kill by hidden good NPC (non‑Crow, non‑wolf).
- One key silver action per day enforced via `_silver_task_done_today`.

### 2.6 Detective Chat & Deep Dive
- Normal chat: Crow asks three fixed questions (timeline, alibi, suspicion). Marks NPC as interviewed for dusk gate.
- Deep dive: available only after normal chat done + quota remaining (3/day). Player types own question → Crow walks to NPC → asynchronous reply.
- `chat_available` / `deep_dive_available` exposed per persona in `get_status()`.

### 2.7 Collision & Pathfinding
- `collision_maze.csv` (140×100, single‑row CSV) → `load_collision_maze()`.
- `_connect_maze_regions()`: BFS‑based wall‑carving for disconnected components.
- `_navigation_maze()`: blends collision maze + blocking furniture objects (`_BLOCKING_OBJECT_KEYWORDS` list).
- `_path_adjacent_to()`: critical function ensuring agents stop adjacent to (not on) target tiles; excludes furniture‑occupied tiles; expands search radius when direct neighbours are blocked.
- `_best_manual_move_path()`: click‑destination scoring that avoids long wall‑detours.

### 2.8 Clue System
- `ClueRecord` dataclass with `delivered_to_crow` flag.
- `create_clue()` in game engine; clues delivered via detective chat conversation.
- `undelivered_clues_for()` filtering.
- `build_trace_clues()`: generates struggle marks, witness statements, forced‑completion disturbed‑trail clues.
- A clue is also inferred from any NPC whose `current_thought` mentions a finding (`.has_new_clue` heuristic).

---

## 3. LLM/NPC Behaviour Model

### 3.1 Provider Architecture
- Default: local Chat2API (OpenAI‑compatible, `http://127.0.0.1:8000/v1`).
- Runtime override via HTTP API: OpenRouter, OpenAI, DeepSeek, Anthropic, or custom (any OpenAI‑compatible base).
- `test_llm_provider` endpoint validates provider reachability before game starts.
- Per‑agent model assignment in `config.yaml[llm][agent_models]`: 4 models, each assigned to exactly 2 characters, no consecutive same‑model adjacency.

### 3.2 Prompt Architecture
Each agent decision LLM call assembles a system prompt from:
- **Soul** (`soul.md`): immutable personality, background, fears, beliefs.
- **Agent state** (`agent.md`): current mission, goals, plans.
- **Memory** (`memory.md` + `memory_index.json`): triple‑scored retrieval (recency ×0.5, relevance ×0.3, importance ×0.2).
- **Cognition** (`cognition.md`): ongoing reasoning.
- **Scratch** (`scratch.json`): structured short‑term goals.
- **Nearby NPCs** (within 20 tiles), **scene objects** (within 3 tiles), **dead list**, **action history** (last 5).
- Information isolation: `sanitize_prompt_text()` replaces "狼人"→"凶手" for non‑wolf agents.
- `active_town_people_rule()` injected into every prompt to constrain name generation.

### 3.3 Prompt Boundaries (verified)
- First‑round gathering speech sanitized to strip: self‑introductions, accusations, wound/werewolf analysis, forbidden terms.
- Second‑round gathering: JSON schema enforced for `speech`, `leaving_excuse`, `leaving_to`, `leaving_object`.
- Dusk vote prompt includes explicit independent‑judgment clause; allows abstention.
- Action‑decision prompt enforces location list (7 landmarks + home), action_type enum, and person list (8 active characters).

---

## 4. UI Systems

### 4.1 Front-End Technology
- `Flask` HTTP server + `Flask-SocketIO` WebSocket for real‑time push.
- Phaser.js game map rendering (in `ui/templates/index.html`).
- HTTP API endpoints: `/api/start`, `/api/status`, `/api/start_dusk_discussion`, `/api/enter_night`, `/api/move_detective`, `/api/detective_chat`, `/api/detective_announce`, `/api/jail_vote_target`, `/api/acquire_silver_bullet`, `/api/acquire_silver_jewelry`, `/api/craft_silver_bullet`, `/api/shoot_silver_bullet`, `/api/use_silver_knife`, `/api/agent/<name>`, `/api/reset`, `/api/collision_maze`, `/api/objects`, `/api/test_llm_provider`.

### 4.2 Real-Time WebSocket Events
- `game_state` (broadcast every tick), `chat_response`, `jail_result`, `silver_result`, `announce_result`.
- Client `request_state`, `move_detective`, `move_detective_to_agent`, `detective_chat`, `start_dusk_discussion`, `enter_night`, `jail_vote_target`, silver actions.

### 4.3 UI Data Exposure
- `get_status()` returns: phase, day, elapsed times, agent positions/sprites/actions/emojis, role masks (`role` always `villager`/`detective`; `true_role` for director), `chat_available`, `deep_dive_available`, `jailed`/`prison_cell`, `has_new_clue`, `vote_summary`, `vote_history`, `daily_tasks`, `deep_dive_remaining`, `bodies`, `clues`, `llm_provider`, `model_assignments`, `primary_cta` (contextual).
- Crow's internal state is hidden from public status (runtime_state forced to `idle`, path_len=0, action/thought cleared).

### 4.4 Object Translations
- 57 interactive game objects translated from English to Chinese (e.g., `bookshelf`→`藏书架`, `guitar`→`民谣吉他`).

---

## 5. Current Test Coverage

**14 test files, 180+ individual tests.**

| Test File | Focus | Approx. Tests |
|---|---|---|
| `test_engine_foundation.py` | Core engine: world config, game init, gathering, dusk/vote, jail, silver, deep dive, collision, pathfinding | ~80 |
| `test_world_config.py` | Active character roster (8), model distribution, display names, ambient sprites, sheriff area, job alignment | ~18 |
| `test_night_hunt.py` | `HuntCandidate` scoring, target selection, unreachable exclusion, clue generation, witness/forced clues | ~9 |
| `test_vote_flow.py` | Dusk vote independence clause, abstention, deterministic fallback, wolf voters, jailed exclusion, vote history | ~13 |
| `test_simulation_events.py` | `BodyRecord.to_status()`, `ClueRecord` pending/delivered | ~3 |
| `test_daytime_npc_behavior.py` | NPC LLM decision fallbacks, action execution, location matching | (est. 15–20) |
| `test_gathering_timeout.py` | Gathering turn timeout, fallback speech | (est. 5–10) |
| `test_game_engine_night_loop.py` | Night phase loop, wolf movement, kill | (est. 5–10) |
| `test_agent_action_json.py` | Agent JSON parsing, `_extract_json_text`, action type normalization | (est. 10–15) |
| `test_llm_priority.py` | Priority chat semaphore, detective chat ordering | (est. 3–5) |
| `test_prompt_boundaries.py` | Prompt injection boundaries, name constraints | (est. 5–10) |
| `test_runtime_roles.py` | Runtime role override, model assignment | (est. 5–10) |
| `test_ui_bubble_layout.py` | Chat bubble display, target attribution | (est. 3–5) |
| `test_ui_llm_provider.py` | LLM provider test API, error classification | (est. 5–10) |

**Total estimate: ~180–200 test cases.**

### Key Testing Patterns
- `_make_engine(monkeypatch, seed)`: shared test helper that mocks maze loads, LLM calls, agent file I/O.
- Tests use deterministic seeds for reproducibility of wolf selection and silver holders.
- Monkeypatching replaces `chat_for_agent` and `generate_response` to avoid real LLM calls.

---

## 6. Fragile Areas

### 6.1 `game_engine.py` Monolith (5.8k lines)
- Single file contains: state machine, pathfinding (BFS/maze), gathering state machine, dusk vote logic, silver progression, jail system, clue management, NPC scheduling, night hunt, detective chat, body burial, status serialization.
- High coupling: `_day_tick()` calls `_handle_gathering()`, `_update_agent_schedules()`, `_move_agents()`, `_llm_tick()` — all of which access shared mutable state under `_lock`.
- **Risk**: accidental deadlock or performance regression from any change in the tick loop.

### 6.2 Async LLM Race Conditions
- Gathering turns use a `turn_id` / `_complete_gathering_turn()` protocol to discard stale responses. Similar pattern in action‑decision threads.
- `_gathering_busy` flag is toggled from multiple threads; timeouts force‑skip with lock‑guard.
- **Risk**: LLM response arriving after timeout but before lock‑guard check can flip state inconsistently.

### 6.3 Maze/Pathing Edge Cases
- `collision_maze.csv` is a single‑row 14,000‑value CSV — any corruption (wrong count, stray whitespace) causes silent fallback to no collision.
- `_connect_maze_regions()` wall‑carving is heuristic (sampled points, not exhaustive); may fail to connect isolated components.
- `_navigation_maze()` applies blocking‑object detection per pathfinding call — performance concern at 0.16s tick interval for 8 NPCs.
- **Risk**: pathfinding desyncs when collision maze, object maze, and occupied tiles change mid‑tick.

### 6.4 LLM JSON Parsing Brittleness
- `Agent._extract_json_text()` and `_find_first_json_object()` are hand‑rolled with string‑state tracking. Edge cases: escaped quotes in JSON strings, nested braces in values, non‑standard whitespace.
- `_parse_gathering_json()` silent‑catches parse failures → falls back to deterministic.
- **Risk**: non‑deterministic NPC behaviour when different LLMs produce subtly different JSON formats.

### 6.5 Information Isolation
- Non‑wolf NPC prompts replace "狼人"→"凶手". This is a simple substring replacement; context‑dependent occurrences (e.g., "狼人杀"→"杀人推理") may produce awkward text.
- All agents share a single `chat_for_agent()` call path; prompt construction must rely on the caller passing the correct `system_prompt`.
- **Risk**: prompt‑template oversight could leak werewolf knowledge to villagers.

### 6.6 Config/Persona Seed Sensitivity
- Wolf selection, silver holders, and body victims are determined by `random_seed`. Different environments may produce different assignments for the same seed due to iteration order changes.
- `memory_index.json`, `scratch.json`, `spatial_memory.json` persist per‑game state; cross‑game state leakage if `init_files()` is missed.

### 6.7 UI State Duplication
- Both HTTP `/api/status` GET and WebSocket `game_state` emit the same `get_status()` dict. Clients must handle both paths.
- `get_status()` serialises the full agent set and bodies every tick (~0.16s). With 8+ NPCs, this payload is non‑trivial.

### 6.8 Night-Hunt Completion
- `_advance_night_hunt()` relies on `time.time() >= deadline_at` for forced completion. If night duration is short (300s) and the wolf is far from all targets, teleport‑kill may feel jarring.
- `choose_forced_target()` ignores unreachable candidates entirely → if all targets are walled off, the wolf kills nobody (silent pass).

---

## 7. Evidence Files

All files inspected to produce this audit (read‑only, no edits):

| File | Lines | Purpose |
|---|---|---|
| `AGENTS.md` | 17 | Collaboration delegation preferences |
| `main.py` | 15 | Application entry point |
| `config.yaml` | 97 | All configuration (game, LLM, memory, night, UI, werewolf) |
| `world_config.py` | 204 | Character roster, landmarks, body site, sheriff area, validation |
| `game_engine.py` | ~5,759 | Core state machine, all gameplay systems |
| `agent.py` | 1,431 | Agent personality, memory, decision, dialogue |
| `llm.py` | ~500+ | LLM client, provider routing, concurrency |
| `night_hunt.py` | 80 | Hunt candidate scoring, clue generation |
| `simulation_events.py` | 45 | Body/Clue dataclasses |
| `ui/app.py` | 638 | Flask/SocketIO server, HTTP + WS APIs |
| `utils.py` | (brief) | `safe_truncate`, `tokenize_chinese` |
| `config_loader.py` | (brief) | YAML loading with env‑var expansion |
| `tests/test_engine_foundation.py` | ~2,781 | Largest test file, ~80 tests |
| `tests/test_world_config.py` | 266 | World config assertion tests |
| `tests/test_night_hunt.py` | 141 | Night hunt unit tests |
| `tests/test_vote_flow.py` | 188 | Dusk voting flow tests |
| `tests/test_simulation_events.py` | 92 | Body/Clue data tests |
| `tests/test_agent_action_json.py` | (exists) | JSON parsing tests |
| `tests/test_daytime_npc_behavior.py` | (exists) | Daytime NPC behaviour tests |
| `tests/test_gathering_timeout.py` | (exists) | Gathering timeout tests |
| `tests/test_game_engine_night_loop.py` | (exists) | Night loop tests |
| `tests/test_llm_priority.py` | (exists) | LLM priority semaphore tests |
| `tests/test_prompt_boundaries.py` | (exists) | Prompt boundary tests |
| `tests/test_runtime_roles.py` | (exists) | Runtime role tests |
| `tests/test_ui_bubble_layout.py` | (exists) | Bubble layout tests |
| `tests/test_ui_llm_provider.py` | (exists) | LLM provider UI tests |
| `docs/superpowers/specs/2026-06-02-werewolf-ville-gameplay-expansion-design.md` | Design spec for gameplay expansion |
| `docs/superpowers/specs/2026-06-01-werewolf-ville-simulation-design.md` | Simulation design spec |
| `docs/superpowers/plans/2026-06-02-werewolf-ville-gameplay-expansion.md` | Implementation plan |
| `docs/superpowers/plans/2026-06-01-werewolf-ville-night-hunt.md` | Night hunt plan |
| `docs/superpowers/plans/2026-06-01-werewolf-ville-daytime-foundation.md` | Daytime foundation plan |

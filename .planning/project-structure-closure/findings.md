# Findings

## Baseline
- The worktree was clean before structure closure started.
- `game_engine.py` is the main risk file. It currently contains map loading, collision/pathfinding helpers, bubble state, daily task construction, dusk/vote flow, and player movement logic in one file.
- Antigravity CLI health check reported ready.

## Candidate Extraction Areas
- Navigation/map helpers: top-level functions around collision map loading, scene data, nearby object lookup, BFS, and engine movement methods.
- Bubble helpers: chat/thought/action bubble creation and expiry.
- Sheriff task helpers: daily task list construction and progress display data.
- Dusk/vote helpers: dusk discussion eligibility, vote records, prison transition.

## Navigation Slice
- Extracted pure map/collision helpers into `engine_navigation.py`.
- Kept same names imported from `game_engine.py` so tests and callers that import from `game_engine` remain compatible.
- `game_engine.py` keeps `import os` only as compatibility surface for existing tests that monkeypatch `game_engine.os.path`.
- Full movement methods remain in `game_engine.py`; those are more coupled to NPC state and should be split separately.

## Daily Task Slice
- Extracted `_build_daily_tasks()` into `EngineTasksMixin` in `engine_tasks.py`.
- The method only depends on engine state and does not require prompt/model imports, so it is a safe mixin boundary.
- Silver acquisition/crafting actions remain in `game_engine.py`; they are behavior-heavy and should not be mixed with task display extraction.

## Bubble Slice
- Extracted engine-side bubble timing/expiry and thought-summary helpers into `EngineBubbleMixin` in `engine_bubbles.py`.
- This does not alter browser/UI layout code; it only moves engine-side state helpers.
- `engine_bubbles.py` loads config directly to avoid importing back from `game_engine.py`.

## Dusk/Vote Slice
- Extracted dusk discussion, NPC voting, vote history, player jail selection, and prison placement into `EngineDuskMixin` in `engine_dusk.py`.
- Replaced direct `GamePhase` references with `type(self.phase)` to avoid importing `game_engine.py` back into the mixin.
- Added `_chat_for_agent()` compatibility routing so existing tests and callers that patch `game_engine.chat_for_agent` continue to work.
- A first combined vote/foundation run accidentally reached real model calls and took about 19 minutes. The compatibility routing fixed that; `tests/test_vote_flow.py` now completes in about 3 seconds.

## Existing Bug Kept Out Of Structure Scope
- `tests/test_daytime_npc_behavior.py::test_mei_lin_and_klaus_have_different_destinations` failed once during a broader run, then passed when isolated and in the final full suite. It remains covered by existing BUG-006 rather than being treated as fixed here.

## Final Verification
- Full test suite: `python -m pytest tests -q` => 345 passed.
- Full compile gate passed for the main modules and all four extracted engine modules.
- `git diff --check` passed.

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

# Project Structure Closure

## Goal
Finish the first-stage project structure closure before returning to gameplay bug fixing. The immediate target is to reduce `game_engine.py` risk by extracting stable, low-risk responsibilities into focused modules while preserving runtime behavior.

## Scope
- Keep this thread focused on project structure, documentation, and verification.
- Do not implement gameplay/UI bug fixes here except when needed to preserve extracted behavior.
- Use DeepSeek and Antigravity workers for non-trivial code or review work; primary agent owns integration and verification.

## Phases
1. Baseline and planning records - complete
2. Extract navigation/map helpers from `game_engine.py` - complete
3. Extract bubble/status presentation helpers where safe - pending
4. Extract sheriff task/day-progress helpers where safe - complete
5. Extract dusk/vote/prison helpers where safe - pending
6. Update project continuity documents and final verification - pending

## Verification Gates
- `rtk git status --short`
- `python -m py_compile agent.py game_engine.py llm.py ui/app.py`
- Compile any newly extracted module.
- Run focused pytest files when extraction touches behavior covered by tests.

## Non-Goals
- Do not chase individual NPC gameplay bugs in this thread.
- Do not alter model prompts, game balance, or UI behavior unless extraction requires a no-op compatibility shim.

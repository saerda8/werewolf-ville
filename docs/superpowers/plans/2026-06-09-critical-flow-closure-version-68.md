# 2026-06-09 Critical Flow Closure, Version 68

## Fixed

- Real detective chat retries empty model replies inside the 30s lock window.
- Normal chat and deep-dive counts are committed only after a valid NPC reply.
- Day3 no longer ends early on wolf/good parity; Day4 and final silver-bullet rules own late defeat.
- Game-over status now includes reason/detail, and the frontend shows a centered victory or defeat overlay.
- Prison escort completes when the voted-out resident reaches the right-side cell.
- Voted-out residents become inert gray `jailed_corpse` bodies in prison and are excluded from AI, morning gathering, interviews, night targets, and future life.
- Morning round-two departure updates next-speaker time before marking the speaker left, preventing stale 5s waits from leaking to UI.
- Silver-resource task text and hardware-store tool acquisition were rechecked; the hardware tool does not depend on Arthur being alive.

## Verification

- `python -m py_compile game_engine.py engine_dusk.py world_config.py ui/app.py`
- `python -m pytest -q tests/test_vote_flow.py` -> 43 passed
- `python -m pytest -q tests/test_ui_bubble_layout.py tests/test_uncommitted_regressions.py` -> 137 passed
- Targeted real-chat, Day3, prison, jailed exclusion, silver-resource, LLM-provider, gathering, and full-game checks passed.
- Local service restarted; browser confirms `版本 68`.

## Worker Notes

- Antigravity CLI worker completed successfully with no code diff.
- DeepSeek CLI worker started and ran syntax validation, but the worker process ended with a model-result error and only produced a generated server log diff. No DeepSeek code diff was accepted.

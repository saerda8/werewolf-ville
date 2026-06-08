# 2026-06-09 Live Regression Handoff

Current goal: fix the live browser regressions the user screenshotted, not just unit tests.

Open bugs to finish:
- Morning burial route: Crow still walks a bad true-map path and appears to cross walls. Target must move to the park-left rear spot from the user's screenshot, not the current lower/roundabout route.
- Dusk public speech text: public discussion bubbles/logs must read as "`Name` says", not "`Name` says to Crow". Only real private chat/active report may target Crow.
- Dusk vote UI: after Crow votes, all candidate/abstain buttons must disappear immediately. Bottom text must not say "selected abstain" when Crow voted for a person. Vote actor icons are too small.
- Dusk escort: after result confirmation, the voted target must walk into the real prison cell; Crow must not leave alone and stall the game.
- Detective real chat: if the model returns empty/slow, target NPC must remain in real conversation for up to 30 seconds and cannot start thought/plan/move. Empty responses should retry until a valid reply or the 30s deadline.

Workers dispatched:
- Rawls: read-only true-map burial coordinate/path.
- Raman: UI vote click state and icon sizing patch.
- Mendel: read-only escort/prison root cause.
- Franklin: read-only detective chat lock root cause.
- Singer: tests-only true-map/flow regressions.

Completion bar:
- Browser must show version >65.
- Use real browser flow, not empty-map tests, to verify the screenshot bugs are gone.
- Do not claim complete unless burial, vote UI, escort, and detective chat are observed fixed in the running app.

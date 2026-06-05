# Project Skill Allowlist

This file defines the default skill subset for `werewolf-ville`.

The global Codex skill catalog can still be visible to the assistant, but it should not be treated as the working set for this project. Use this allowlist first. Search or expand unrelated global skills only when the user explicitly asks to look in the skill library, or when a task clearly falls outside this list.

## Default Skills

| Work type | Default skills | Notes |
|---|---|---|
| Gameplay and architecture design | `brainstorming` | Use for NPC intelligence, rules, day/night flow, voting, clue systems, and major behavior changes. Do not implement before the design is confirmed. |
| Implementation planning | `writing-plans`, `planning-with-files` | Use after a design is accepted and the work needs a concrete execution plan. |
| Plan execution | `executing-plans` | Use when an accepted plan already exists. |
| Parallel worker delegation | `dispatching-parallel-agents`, `subagent-driven-development` | Use the project's DeepSeek and Antigravity worker rules in `AGENTS.md`; do not let the skill override the worker safety/review process. |
| Bug investigation | `systematic-debugging` or `investigate` | Pick one, not both, unless the first path is insufficient. Keep outputs concise and write durable findings to `BUG_BACKLOG.md` when needed. |
| Frontend/browser QA | `browse`, `qa`, `qa-only` | Use for visual verification, localhost testing, screenshots, and UI regressions. Prefer the in-app browser path documented in `AGENTS.md` when applicable. |
| Completion verification | `verification-before-completion` | Use before claiming a fix or implementation is complete. |
| Documentation | `document-generate`, `document-release` | Use for project docs, design docs, release notes, and continuity updates. |
| Context management | `context-save`, `context-restore`, `learn` | Use only when preserving or restoring project state adds value beyond the project markdown files. |
| Token and context discipline | `caveman`, `keep-codex-fast` | Use `caveman` when the user asks for fewer tokens, terse output, or when summaries/status can be safely compressed. Apply `keep-codex-fast` principles on every task: keep chat lean, prefer repo memory, avoid dumping raw logs. Run the actual maintenance/report workflow only when Codex feels slow/bloated, local state needs cleanup, or the user asks for Codex maintenance. |
| Low-noise command workflow | `rtk` command convention | Use `rtk` for ordinary shell commands in this repo to reduce terminal output and token use. This does not mean Rust/RTK-specific development skills are enabled by default. |

## Usually Do Not Use

These skills are normally outside this project's default workflow:

- Canva and Figma skills, unless the user asks for design-tool work.
- Lark/Feishu skills, unless the user asks for Lark operations.
- iOS skills, because this project is a local Flask/web game.
- Rust/RTK-specific development skills, except for the `rtk` command convention documented above and in `AGENTS.md`.
- Deployment/canary/benchmark skills, unless the project moves beyond local development.
- Scraping or external-site skills, unless the task requires outside data.

## Always-On Efficiency Rules

- Apply `keep-codex-fast` as a working principle in every task: concise updates, external memory first, no unnecessary tool dumps, no long worker logs in chat, and handoff docs for important long-running work.
- Do not run `keep-codex-fast` maintenance/report automatically for every task. Its script is for Codex local-state inspection and cleanup, so use it only when performance, session bloat, archives, logs, worktrees, or Codex metadata are the actual concern.
- Use `caveman` as an optional compression mode, not as the default voice for all product discussion. It is good for token-heavy status, bug summaries, worker handoffs, command results, and “be brief” requests. When context grows long or compaction risk is high, use `caveman` more aggressively to compress chat-history summaries, process notes, worker outputs, and tool results down to executable facts. Avoid it when nuanced design discussion, user-facing explanation, safety warnings, or precise multi-step instructions would become harder to read.

## Duplicate Skill Entries

If the global catalog exposes duplicate paths such as `qa` and `gstack/qa`, choose one matching entry and do not read both unless there is evidence they differ in a way that matters.

## Output Discipline

Skill instructions are work methods, not project facts. Do not paste long skill procedures into chat. Summarize the rule being used, then keep durable project decisions in the appropriate project file:

- Stable user requirements: `USER_REQUIREMENTS_LEDGER.md`
- Collaboration rules: `AGENTS.md`
- Product continuity: `PROJECT_CONTINUITY.md`
- Bugs: `BUG_BACKLOG.md`
- Current execution state: `CURRENT_SPRINT.md`

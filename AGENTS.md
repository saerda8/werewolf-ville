# Project Collaboration Preferences

- Before starting any task, first assess whether analysis or implementation can be delegated to available subagents.
- For any non-trivial investigation or code change, begin by planning subagent delegation first, before doing the work locally. Prefer launching clearly scoped tasks to both DeepSeek and Antigravity in parallel whenever their scopes can be separated.
- If only one subagent can be used, or if a task is too small/unsafe/sequential to delegate, state that reason briefly before proceeding locally.
- Do not leave DeepSeek or Antigravity idle on substantial work merely to save coordination effort; use them to save primary-agent context and tokens.
- For work that requires non-trivial investigation or code changes, prefer splitting clearly scoped tasks between DeepSeek and Antigravity.
- Antigravity can own backend investigation and implementation tasks as well as frontend work. When backend work can be divided into independent scopes, distribute it across both CLI workers instead of queueing all backend tasks behind DeepSeek.
- The primary agent remains responsible for task boundaries, reviewing changes, integration, and final verification.
- Prefix ordinary shell commands with `rtk` in this project to reduce terminal output and token use. Use direct commands only for MCP calls, approved Windows management commands, or cases where `rtk` would interfere with the required operation.
- Before delegating a task to DeepSeek, run a Claude Code CLI preflight with the configured native Windows executable and DeepSeek key file. Confirm that the CLI starts successfully before launching the DeepSeek worker.
- On Windows, use the native Claude Code `claude.exe` configured through `CLAUDE_BIN`; do not rely on `claude.ps1`, because the DeepSeek launcher starts Claude Code through Node.js `spawn()`.
- Before delegating a task to Antigravity, run the Antigravity CLI doctor and confirm that the configured `antigravity.exe` reports ready. Use the CLI worker path, not the desktop language-server integration.
- When the user asks to use DeepSeek as a subagent, this always means the Claude Code CLI-driven DeepSeek worker. It does not mean a direct model API call or an in-game NPC model.
- When the user asks to use Antigravity as a subagent, this always means the Antigravity CLI worker. It does not mean the Antigravity desktop language-server integration.
- When the user asks to use the in-app Browser, do not conclude it is unavailable just because no direct `browser` tool appears. First follow the Browser plugin skill and connect through the Node REPL browser-client (`agent.browsers.get("iab")`), then use that in-app browser for localhost navigation, screenshots, and inspection.

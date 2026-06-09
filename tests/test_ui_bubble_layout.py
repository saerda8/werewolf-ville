from pathlib import Path


INDEX_HTML = Path(__file__).parents[1] / "ui" / "templates" / "index.html"


def test_bubbles_default_above_character_and_split_only_for_mutual_dialogue():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'return "center";' in html
    assert '"translate(-50%, -100%)"' in html
    assert "function bubbleSideOffset(side)" in html
    assert 'if (side === "left") return -64;' in html
    assert 'if (side === "right") return 64;' in html
    assert 'b1.side === "center" ? b1.x - b1.w / 2' in html


def test_right_panel_uses_dusk_discussion_as_primary_cta():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="end-turn-btn" onclick="startDuskDiscussion()"' in html
    assert "结束本回合，进入黄昏讨论" in html
    assert 'socket.emit("start_dusk_discussion")' in html
    assert '<button id="night-btn" onclick="enterNight()" style="display: none;"' in html
    assert '<button id="announce-btn" onclick="showAnnounce()" style="display: none;"' in html


def test_right_top_uses_vote_history_instead_of_director_summary():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="vote-history-panel"' in html
    assert 'id="vote-history-content"' in html
    assert "function renderVoteHistory(state)" in html
    assert "renderVoteHistory(state);" in html
    assert "导演模式摘要" not in html


def test_right_panel_exposes_model_failure_marker_and_readable_task_counts():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'const modelFailed = !!(hasResponseError || hasDecisionError);' in html
    assert 'class="model-health-warning"' in html
    assert 'title="最近一次模型回复未生效"' in html
    assert '.task-progress {' in html
    assert 'color: #ffdd57;' in html
    assert '"Crow": "#66c2ff"' in html


def test_bubble_speech_prefix_uses_chinese_display_names():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'const targetDisplayName = getDisplayName(target, gameState);' in html
    assert 'text.replace(prefixRegex, "")' in html
    assert 'const prefixRegex = /^对\\s*(.*?)\\s*说[：:]\\s*/;' in html


def test_bubble_layer_bounds():
    """#bubble-layer must not clip bubbles; JS clamps them into the game area."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "right: 0; bottom: 0;" in html
    assert "overflow: visible" in html
    assert "width: max-content;" not in html
    assert "overflow-wrap: anywhere;" in html


def test_right_edge_layout_clamping():
    """Bubble width is clamped and positioned based on layout calculation near right edge to prevent squeezing/clipping."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    # No JavaScript code dynamically sets maxWidth (camelCase = JS property)
    # — only CSS `max-width` (hyphenated) is allowed.
    assert "maxWidth" not in html, "JS must not dynamically set maxWidth on bubbles"

    # Bubble left positioning is based on layout.x, never raw screenX
    assert 'bubbleEl.style.left = layout.x + "px"' in html
    assert 'tBubbleEl.style.left = layout.x + "px"' in html

    # Natural width is measured at 0px first to avoid browser squeezing
    assert 'bubbleEl.style.left = "0px"' in html
    assert 'tBubbleEl.style.left = "0px"' in html

    # No code re-calculates bubble width based on residual visible space or layer clipping
    assert "overflow: visible" in html

    # The inVisibleScreen check is present
    assert "inVisibleScreen" in html
    assert "screenX <= viewportWidth" in html


def test_bubble_layer_does_not_clip_overflow():
    """#bubble-layer does not clip bubble overflow; bubbles have fixed max-width."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    # bubble-layer must not be the clipping mechanism.
    assert "overflow: visible" in html

    # Bubbles have fixed pixel max-width — never percentage or dynamic JS value
    assert "max-width: 260px" in html
    assert "min-width: 160px" in html

    # Bubbles must not use max-content; long Chinese sentences should wrap
    # inside max-width instead of stretching across the whole game viewport.
    assert "width: max-content;" not in html
    assert "width: fit-content;" in html

    # Long content wraps within the fixed max-width.
    assert "word-break: break-word;" in html

    # overflow-wrap:anywhere handles long unbreakable strings gracefully.
    assert "overflow-wrap: anywhere;" in html

    # Do not use negative margin hacks.
    assert "margin-right: -300px;" not in html


def test_bubble_anti_collision_limits_lift():
    """Collision resolver uses maxLift to prevent pushing bubbles too far, and records anchorY."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "const maxLift = 300" in html
    assert "dataset.anchorY" in html
    assert "anchorY" in html


def test_side_bubble_transforms():
    """Left/right bubbles have distinct transforms; center bubble uses translate(-50%, -100%)."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert '"translate(-50%, -100%)"' in html
    assert '"translate(-100%, -100%)"' in html
    assert '"translate(0, -100%)"' in html


def test_character_labels_float_above_object_labels():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "nameLabels[name].y = cy - 44;" in html
    assert "modelLabels[name].setVisible(false);" in html
    assert "modelLabels[name].setVisible(true);" not in html
    assert "}).setDepth(22).setOrigin(0.5).setVisible(false);" in html
    assert "}).setDepth(21).setOrigin(0.5).setVisible(false);" in html
    assert "sprite.setDepth(1.5);" in html
    assert "label.setDepth(1.2);" in html
    assert "label.setDepth(1.1);" in html


def test_buried_corpses_are_not_rendered():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "if (body.buried) continue;" in html


def test_pending_detective_chat_locks_button_and_suppresses_bubbles():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "let pendingChatTarget = null;" in html
    assert "let pendingCrowBubble = null;" in html
    assert "function setPendingChat(name, phase)" in html
    assert "function mergePendingCrowBubble(state)" in html
    assert "mergePendingCrowBubble(state);" in html
    assert 'pendingPhase === "moving" ? "前往中..." : "等待回复..."' in html
    assert "const chatBtnDisabled = (!normalChatAvailable || isNight || isDusk || isPendingChat || isGathering) ? \"disabled\" : \"\";" in html
    assert "if (!isNight && gameState)" in html
    assert "const suppressChatDisplay = isChatSuppressedFor(name, bubblePayload);" in html
    assert 'const speechText = suppressChatDisplay ? "" : bubbleSpeechText(name, bubblePayload);' in html
    assert "isWaitBubble(bubblePayload)" in html
    assert 'showLocalCrowQuestion(name, msg);' in html
    assert 'let thoughtText = (isNPCInActiveChat || (suppressChatDisplay && !activeForAction)) ? "" : buildNpcThoughtBubble(name, p, gameState);' in html
    assert "if (resp && resp.pending_response)" in html
    assert "return;" in html
    assert "你说说，为什么你不可能是凶手？" in html
    assert "你先说说，为什么你不可能是凶手？" not in html
    assert "function markPendingChatTargetWaiting(name, state)" in html
    assert "function mergePendingChatTargetWaitBubble(state)" in html
    assert "|${pendingPhase}|${isGathering}|${isPendingChat}" in html


def test_deep_dive_submit_does_not_decrement_until_backend_success():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'function deepDiveRemaining(state)' in html
    assert 'if (typeof state.deep_dive_remaining === "number")' in html
    assert 'const ddLeft = deepDiveRemaining(state);' in html
    assert 'const ddLeftReal = deepDiveRemaining(state);' in html
    assert 'function submitDeepDiveChat(name, msg)' in html
    assert 'setPendingChat(name, "waiting");' in html
    submit_block = html[html.index("function submitDeepDiveChat"):html.index("socket.emit(\"detective_chat\"", html.index("function submitDeepDiveChat"))]
    assert 'state.deep_dive_remaining = Math.max(0, state.deep_dive_remaining - 1);' not in submit_block
    assert 'state.deep_dive_used += 1;' not in submit_block
    assert 'updateUI(state);' in html


def test_dusk_vote_submission_hides_vote_actions_and_confirms_without_delay():
    html = INDEX_HTML.read_text(encoding="utf-8")
    render_start = html.index("function renderDuskVotingFlow(state)")
    render_end = html.index("function renderVoteHistory(state)", render_start)
    render_block = html[render_start:render_end]
    confirm_start = html.index("function confirmVoteResult()")
    confirm_end = html.index("function confirmNightTransition()", confirm_start)
    confirm_block = html[confirm_start:confirm_end]

    assert 'const showVoteButtons = stage === "voting" && voteSummary.active && !crowHasVoted;' in render_block
    assert 'else if (stage === "voting" && crowHasVoted)' in render_block
    assert 'voteSummary.crow_vote === undefined' not in render_block
    assert 'footerAbstainBtn.textContent = "放弃投票 (弃票)";' in render_block
    assert '已选择弃票，投票中...' not in render_block
    assert 'fetch("/api/confirm_vote_result", {method: "POST"})' in confirm_block
    assert 'socket.emit("confirm_vote_result");' not in confirm_block
    assert "}, 2500);" not in confirm_block


def test_frontend_fixes_history_labels_colors_bubble_directions_prefixes():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # (1) Crow card must not render history button, NPC button becomes 详细
    assert 'name === "Crow" ? ""' in html
    assert 'onclick="showAgentHistory(\'${name}\', event)"' in html
    assert '详细</button>' in html
    assert 'background:#5f9e72; color:#fff; border:1px solid #79b88a; border-radius:4px; cursor:pointer;">详细</button>' in html

    # (2) Male NPC label green darker; preserve Crow blue & female pink
    assert '"Arthur Burton": "#7ee787"' in html
    assert '"Klaus Mueller": "#7ee787"' in html
    assert '"Sam Moore": "#7ee787"' in html
    assert '"Crow": "#66c2ff"' in html
    assert '"Mei Lin": "#f39ab6"' in html

    # (3) Mutual dialogue bubble visual ownership based on on-screen character x position
    assert 'p1.x < p2.x ? "left" : "right"' in html
    assert 'bubbleSideFor(name, chatBubbles, gameState)' in html

    # (4) strip both Chinese and English stale prefixes recursively
    assert 'while (prefixRegex.test(text))' in html


def test_thought_bubble_stays_above_own_speech_without_arrow():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert ".thought-bubble::after { display: none; }" in html
    assert "const thoughtSpeechGap = 10;" in html
    assert "function buildNpcThoughtBubble(name, persona, state)" in html
    assert 'runtime === "thinking" || runtime === "planning"' in html
    assert 'runtime === "moving" || runtime === "acting" || Number(p.path_len || 0) > 0' in html
    assert '<span class="bubble-key">思考：</span>' in html
    assert '<span class="bubble-key">计划：</span>' in html
    assert '<span class="bubble-key">开始行动：</span>' in html
    assert "tBubbleEl.dataset.owner = name;" in html
    assert 'type: "thought"' in html
    assert "owner: tB.dataset.owner || name" in html
    assert "if (b1.owner === b2.owner && b1.type !== b2.type)" in html
    assert "thoughtBubble.y = Math.min(thoughtBubble.y, speechTop - thoughtSpeechGap);" in html
    assert 'if (name !== "Crow") {' in html
    assert 'delete thoughtBubbleCache[name];' in html
    assert 'document.getElementById("thought-bubble-Crow")' in html


def test_vertical_dialogue_bubbles_split_by_y_position():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "function bubbleSideByPositions(name, target, state)" in html
    assert "const dx = p1.x - p2.x;" in html
    assert "const dy = p1.y - p2.y;" in html
    assert "if (Math.abs(dx) >= Math.abs(dy))" in html
    assert 'return p1.y > p2.y ? "left" : "right";' in html


def test_thought_bubbles_split_for_active_conversation_without_mutual_speech():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'target = s.personas[name].conversation_with || "";' in html
    assert "Object.entries(bubbles || {}).find(([speaker, b]) => speaker !== name && b && b.target === name)" in html
    assert "return bubbleSideByPositions(name, target, s);" in html


def test_short_display_names_and_auto_chat_arrival_behaviour():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert '"Arthur Burton": "亚瑟"' in html
    assert '"Maria Lopez": "玛利亚"' in html
    assert '"Sam Moore": "山姆"' in html
    assert "深度挖掘次数（可选）" in html
    assert "if (dist <= 2)" in html
    assert 'isMoving && p.path_len > 0' in html


def test_bubble_horizontal_boundary_clamping():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "#bubble-layer" in html
    assert "Horizontally clamp bubbles at the game edge" in html
    assert 'const gameContainer = document.getElementById("game-container");' in html
    assert "gameContainer ? gameContainer.clientWidth : (window.innerWidth - 320)" in html
    assert "right > viewportWidth" not in html
    assert "left < 0" not in html


def test_rules_modal_and_button_exist():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'class="rules-btn" onclick="showRulesModal()"' in html
    assert 'id="rules-modal"' in html
    assert "function showRulesModal()" in html
    assert "function closeRulesModal()" in html
    assert "每局随机产生 2 名狼人" in html
    assert "银质小刀" in html


def test_active_ui_does_not_render_werewolf_role_tags():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "Array.isArray(state.werewolf_names) && state.werewolf_names.includes(name)" not in html
    assert 'roleVal = "werewolf";' not in html
    assert 'roleClass = "role-werewolf";' not in html
    assert ".role-werewolf" not in html


def test_thought_bubble_uses_same_ttl_as_speech_bubble():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "const BUBBLE_LIFETIME_SECONDS = 6;" in html
    assert "let thoughtBubbleCache = {};" in html
    assert "function freshThoughtForDisplay(name, rawText, persona)" in html
    assert "persona.thought_time" in html
    assert '["thinking", "planning", "starting_action", "acting"].includes(persona.runtime_state)' in html
    assert '(!departureWaiting && persona.runtime_state === "moving")' in html
    assert "now - cached.time > BUBBLE_LIFETIME_SECONDS" in html
    assert 'let thoughtText = (isNPCInActiveChat || (suppressChatDisplay && !activeForAction)) ? "" : buildNpcThoughtBubble(name, p, gameState);' in html


def test_chinese_titles_and_log_labels():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "<title>狼人小镇</title>" in html
    assert "<h1>狼人小镇</h1>" in html
    assert '<span class="panel-title">狼人小镇' in html
    assert "Werewolf Ville" not in html
    assert "Agent Log" not in html


def test_frontend_renders_agent_log_panel():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "function updateLog(state)" in html
    assert 'id="log-panel"' in html
    assert 'id="log-content"' in html
    assert 'const showTypes = ["think", "chat", "kill", "action", "error", "system"];' in html
    assert "function shouldDisplayLogEntry(entry)" in html
    assert 'escapeHtml(entry.message || "")' in html
    assert "escapeHtml(parts[0])" in html


def test_agent_log_panel_is_readable_resizable_and_filters_noise():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "#log-resize-handle" in html
    assert 'id="log-resize-handle"' in html
    assert "function initLogPanelResize()" in html
    assert 'document.addEventListener("mousemove", onLogResizeMove)' in html
    assert "setLogPanelHeight(nextHeight)" in html
    assert "--log-panel-height" in html
    assert "font-size: 12px;" in html
    assert "LLM请求" in html
    assert "行动解析" in html
    assert "行动理由" in html
    assert "思考超时" in html


def test_bottom_right_keeps_tasks_and_log_panel_layout():
    """Right-bottom UI keeps sheriff tasks only, while #log-panel is placed at the bottom area next to it without squeezing the right panel."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert '<div id="task-panel">' in html
    assert 'id="log-panel"' in html
    assert 'id="log-content"' in html
    assert "智能体日志" in html
    assert "right: 320px; bottom: 0;" in html or "bottom: 0;" in html

    # Assert #log-panel is NOT inside #side-panel
    chat_panel_close = html.find('</div>', html.find('id="chat-panel"'))
    log_panel_open = html.find('id="log-panel"')
    between = html[chat_panel_close:log_panel_open]
    assert '</div>' in between, "#log-panel must be outside of #side-panel"

    side_panel_open = html.index('<div id="side-panel">')
    log_panel_open = html.index('<div id="log-panel">')
    task_panel_open = html.index('<div id="task-panel">')
    side_panel_markup = html[side_panel_open:log_panel_open]
    assert log_panel_open < task_panel_open
    assert 'id="log-panel"' not in side_panel_markup
    assert "#game-container { position: absolute; top: 0; left: 0; right: 320px; bottom: var(--log-panel-height); overflow: hidden; }" in html
    assert "position: absolute; top: 0; left: 0; right: 320px; bottom: var(--log-panel-height);" in html
    assert "#log-panel {" in html
    assert "right: 320px;" in html
    assert "height: var(--log-panel-height);" in html


def test_bubbles_are_clamped_away_from_right_panel_and_owner_sprite():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "function clampBubbleIntoLayer" in html
    assert "function spriteProtectionRect" in html
    assert "function bubbleRectFromAnchor" in html
    assert "gameContainer.clientWidth" in html
    assert "bubbleRight > viewportWidth - margin" in html
    assert "rectsOverlap(candidateRect, protectedRect)" in html


def test_frontend_keeps_recent_thoughts_and_crow_walk_animation_stable():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'const recentThought = thoughtTime > 0 && ((Date.now() / 1000) - thoughtTime <= BUBBLE_LIFETIME_SECONDS);' in html
    assert "&& !recentThought" in html
    assert 'const isMoving = p.runtime_state === "moving" || p.visual_moving === true;' in html


def test_frontend_version_displayed_in_start_overlay():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="app-version-badge"' in html
    assert 'class="frontend-version"' in html
    assert "版本 {{ frontend_version }}" in html


def test_frontend_name_localization_does_not_corrupt_crown_location():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "text = replaceEnglishNames(text, gameState);" in html
    assert 'Array.from(names).sort((a, b) => b.length - a.length).forEach(name => {' in html
    assert 'new RegExp(`\\\\b${name}\\\\b`, "g")' in html


def test_new_bubble_features():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Proximity split in bubbleSideFor
    assert "let closestNpc = null;" in html
    assert "minDist <= 3" in html

    # 2. Crow suppresses blue thought/action bubbles
    assert 'if (name === "Crow") return "";' in html
    assert 'if (name === "Crow" && tBubbleEl) {' in html
    assert 'tBubbleEl.innerHTML = "";' in html
    assert 'delete thoughtBubbleCache[name];' in html
    assert "continue;" in html

    # 3. Force layout reflow in collision resolver
    assert "const forceReflow = bubbleLayer.offsetHeight;" in html


def test_crow_blue_bubble_suppression_robustness():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Case-insensitive buildNpcThoughtBubble check
    assert 'if (String(name).trim().toLowerCase() === "crow") return "";' in html

    # 2. Case-insensitive thought bubble DOM element creation check
    assert 'if (String(name).trim().toLowerCase() !== "crow") {' in html

    # 3. Clean up stale DOM and query selectors
    assert "[id^='thought-bubble-Crow']" in html
    assert "[id^='thought-bubble-crow']" in html
    assert "allStaleThoughts.forEach(" in html

    # 4. Phaser label style keeps Crow blue, not white
    assert 'fill: PERSONA_LABEL_COLORS[name] || "#ffffff"' in html
    assert 'nameLabels[name].setStyle({ fill: PERSONA_LABEL_COLORS[name] || "#66c2ff" });' in html
    assert 'nameLabels[name].setStyle({ fill: "#ffffff" });' not in html
    assert 'modelLabels[name].setStyle({ fill: "#ffdd57" });' not in html

    # 5. Speech bubble styling guards (preventing blue styles)
    assert 'bubbleEl.classList.remove("thought-bubble");' in html
    assert 'bubbleEl.classList.add("speech-bubble");' in html
    assert 'bubbleEl.style.backgroundColor = "";' in html
    assert 'bubbleEl.style.borderColor = "";' in html
    assert 'bubbleEl.style.color = "";' in html


def test_gathering_disables_chat_and_clickable_conn_indicator():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # Clickable connection indicator to manually fetch state
    assert 'document.getElementById("conn-indicator").onclick =' in html
    assert "fetchCurrentState();" in html

    # Disable chat and NPC action buttons during gathering
    assert 'isGathering = state.primary_cta === "gathering";' in html
    assert 'chatBtnDisabled = (!normalChatAvailable || isNight || isDusk || isPendingThisChat || isGathering) ? "disabled" : "";' in html
    assert 'ddBtnDisabled = (!deepDiveAvailable || isNight || isDusk || isPendingThisChat || isGathering) ? "disabled" : "";' in html
    assert 'chatInput.placeholder = isGathering' in html
    assert '"聚集讨论中，无法私聊..."' in html
    assert '"靠近后才能交谈..."' in html

    # Reset/clear pending chats on start/restart
    assert "clearPendingChat();" in html


def test_delegated_bubble_patch_requirements():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Crow suppresses blue bubbles CSS rules
    assert '[id*="thought-bubble-crow" i]' in html
    assert '[id*="bubble-crow" i]' in html
    assert 'background: rgba(255, 255, 255, 0.92) !important;' in html

    # 2. Blue thought/action bubbles client-side TTL caching
    assert 'let blueBubbleCache = {};' in html
    assert 'function applyBlueBubbleTTL(name, html, persona)' in html
    assert 'thoughtText = applyBlueBubbleTTL(name, thoughtText, p);' in html

    # 3. Collision resolver separation limits and iterations
    assert 'const maxLift = 300;' in html
    assert 'for (let iter = 0; iter < 15; iter++)' in html

    # 4. Hide thought/action bubble when speech bubble visible.
    assert 'const realSpeechVisible = !!speechText && p.alive && !isActionStatusBubble;' in html
    assert 'if (realSpeechVisible) {' in html
    assert 'thoughtText = "";' in html
    speech_block_start = html.find('if (speechText && p.alive) {')
    speech_block = html[speech_block_start:html.find('let displaySpeechText = "";', speech_block_start)]
    assert 'if (!activeForAction) {' not in speech_block

    # 5. History modal localization of memory/cognition/speech
    assert 'const localizedCognition = localizePersonNames(replaceEnglishNames(cognitionContent, gameState), gameState);' in html
    assert 'const localizedMemory = localizePersonNames(replaceEnglishNames(memoryContent, gameState), gameState);' in html
    assert 'title.textContent = `📜 ${getDisplayName(name, gameState)} 的历史言行与思考记录`;' in html


def test_crow_chinese_name_suppression_and_resize_listener():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # Check that "克罗" is explicitly checked alongside "Crow" for bubble suppression
    assert '[id*="thought-bubble-克罗" i]' in html
    assert '[id*="thought_bubble_克罗" i]' in html
    assert '.thought-bubble[id*="克罗" i]' in html
    assert '[id*="bubble-克罗" i]' in html
    
    # Check that name === "克罗" is part of JavaScript guards
    assert 'name === "克罗"' in html
    assert 'String(name).trim() === "克罗"' in html
    
    # Check that window resize listener is present
    assert 'window.addEventListener("resize"' in html


def test_history_modal_formats_structured_dialogue_entries():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'const formatDialogueEntry = (entry) => {' in html
    assert 'typeof entry !== "object"' in html
    assert 'entry.incoming ? `对方：${entry.incoming}` : "";' in html
    assert 'entry.outgoing ? `我：${entry.outgoing}` : "";' in html
    assert '.map(formatDialogueEntry).filter(Boolean).join("\\n").trim()' in html


def test_new_bugfixes_frontend():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Bubble width is stable; clipping is handled by #bubble-layer, not negative margins.
    assert "width: fit-content;" in html
    assert "min-width: 160px;" in html
    assert "margin-right: -260px;" not in html
    assert "margin-right: -300px;" not in html

    # 2. TTL timer safety: do not delete blueBubbleCache when html is empty in applyBlueBubbleTTL
    idx_ttl = html.find("function applyBlueBubbleTTL")
    assert idx_ttl != -1
    ttl_body = html[idx_ttl : html.find("function", idx_ttl + 1)]
    assert "delete blueBubbleCache" not in ttl_body

    # 3. Crow speech bubble anchoring: no early continue in Crow's thought check
    assert 'staleCrowThought.innerHTML = "";\n      }\n      thoughtText = "";\n    }' in html or 'staleCrowThought.innerHTML = "";\n      }\n      thoughtText = "";\n    }' in html.replace("\r\n", "\n")

    # 4. Bubble splitting using Object.assign and smooth sprite coords
    assert "p1 = Object.assign({}, p1);" in html
    assert "p2 = Object.assign({}, p2);" in html
    assert "const sp1 = sprites[name];" in html
    assert "const sp2 = sprites[target];" in html

    # 5. Overlap prevention: force layout reflow on shown bubbles and active bubbles
    assert "const forceSBReflow = bubbleEl.offsetHeight;" in html
    assert "const forceSB = sB.offsetHeight;" in html
    assert "const forceTB = tB.offsetHeight;" in html

    # 6. Disable state checking: input/send disabled globally on any pending target
    # In updateAgentList
    assert "const isPendingChat = !!pendingChatTarget;" in html
    # In clearPendingChat, caches are reset
    assert "blueBubbleCache = {};" in html
    assert "thoughtBubbleCache = {};" in html

    # 7. Detective/NPC chat text must not render into the right-side transcript UI.
    assert "msg.substring(0, 120)" not in html
    assert 'getDisplayName(who, gameState) + ": " + msg' not in html
    assert "chat-ui-disabled" in html


def test_delegated_ui_fixes_and_clamping():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # (1) 底部智能体日志字号偏小，放大一级 (Changed from 11px to 12px)
    assert "font-size: 12px; /* Increased font-size by one level */" in html

    # (2) 恢复日志面板顶部拖拽调整高度，向上增大、向下减小
    assert 'handle.addEventListener("mousedown"' in html
    assert 'document.addEventListener("mousemove", onLogResizeMove)' in html
    assert 'document.addEventListener("mouseup"' in html
    assert "function setLogPanelHeight(nextHeight)" in html

    # (3) 前端日志只显示 NPC 思考/计划/行动和必要错误，过滤系统/LLM请求/行动解析/行动理由等噪声
    assert "function shouldDisplayLogEntry(entry)" in html
    assert "LLM请求" in html
    assert "行动解析" in html
    assert "行动理由" in html
    assert "思考超时" in html

    # (4) NPC 气泡靠近右侧 UI 时不要被挤压到不可读，也不能遮住 NPC 模型，必要时向左/侧边偏移并保持在 game/bubble layer 内
    assert "function clampBubbleIntoLayer" in html
    assert "function spriteProtectionRect" in html
    assert "function bubbleRectFromAnchor" in html
    assert "rectsOverlap(candidateRect, protectedRect)" in html


def test_bubble_speech_prefix_shows_speaker_and_target_tdd():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'function bubbleSpeechText(speaker, payload)' in html
    assert 'bubbleSpeechText(name, bubblePayload)' in html
    assert 'if (kind === "action_status") {' in html
    assert 'text = stripActionPlanningTail(text);' in html
    assert 'return `${text.replace(/[。.!！]+$/, "") || "继续当前事务"}...`;' in html
    assert 'const speakerDisplayName = getDisplayName(speaker, gameState);' in html
    assert 'target && target.toLowerCase() !== speaker.toLowerCase()' in html
    assert '`${speakerDisplayName}对${targetDisplayName}说：${text}`' in html
    assert '`${speakerDisplayName}说：${text}`' in html


def test_rules_logs_and_bubbles_requirements():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Rules modal explains bulb and question icons
    assert "\u706f\u6ce1" in html # 灯泡
    assert "\u95ee\u53f7" in html # 问号
    assert "\u503c\u5f97\u8b66\u957f\u6df1\u6316\u7684\u4fe1\u606f" in html # 值得警长深挖的信息
    assert "\u4e0d\u4e00\u5b9a\u4e3b\u52a8\u6c47\u62a5" in html # 不一定主动汇报
    assert "\u6700\u8fd1\u4e00\u6b21\u53ef\u89c1\u53d1\u8a00\u6216\u884c\u52a8\u56de\u590d\u672a\u751f\u6548" in html # 最近一次可见发言或行动回复未生效

    # 2. No italic in agent log panel
    # We check that #log-content .log-think style does not contain "font-style: italic;"
    assert "#log-content .log-think" in html
    idx = html.find("#log-content .log-think")
    style_block = html[idx:idx+150]
    assert "font-style: italic" not in style_block
    assert "#ff79c6" in style_block
    assert "#log-content .log-tag-think" in html
    assert "#log-content .log-tag-action" in html
    assert "function logTagColorClass(entry)" in html
    assert ".log-entry {" in html

    # 3. Explicit labels in logs: 思考, 计划, 行动, 对话, 错误
    assert 'class="log-tag${tagClass}"' in html
    assert '"\u601d\u8003"' in html # "思考"
    assert '"\u8ba1\u5212"' in html # "计划"
    assert '"\u884c\u52a8"' in html # "行动"
    assert '"\u5bf9\u8bdd"' in html # "对话"
    assert '"\u9519\u8bef"' in html # "错误"


def test_rules_button_handlers_are_global_for_inline_onclick():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'onclick="showRulesModal()"' in html
    assert "function showRulesModal()" in html
    assert "function closeRulesModal()" in html
    assert "window.showRulesModal = showRulesModal;" in html
    assert "window.closeRulesModal = closeRulesModal;" in html


def test_npc_npc_speech_bubble_display_contract():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Check that bubbleSpeechText logic formats speaker and target correctly for NPC-NPC chats
    assert 'function bubbleSpeechText(speaker, payload)' in html
    assert 'const speakerDisplayName = getDisplayName(speaker, gameState);' in html
    assert 'const targetDisplayName = getDisplayName(target, gameState);' in html
    assert '`${speakerDisplayName}对${targetDisplayName}说：${text}`' in html

    # 2. Check that resolveBubbleLayout retrieves bubbleSpeechText and generates speechText
    assert 'const speechText = suppressChatDisplay ? "" : bubbleSpeechText(name, bubblePayload);' in html

    # 3. Check that thought bubble suppression logic does NOT swallow or clear speechText
    # Verify the suppression logic only sets thoughtText = "" and speechText is not altered
    assert 'if (realSpeechVisible) {' in html
    assert 'thoughtText = "";' in html
    # Ensure speechText is not cleared/swallowed in the suppression logic
    assert 'speechText = "";' not in html


def test_static_regression_icons_and_bubble_clamping():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # Verify modelFailed tracks visible response/action failures, not background llm_error noise.
    assert 'const hasResponseError = p.response_error && p.response_error !== "None" && p.response_error !== "null" && p.response_error !== "undefined" && String(p.response_error).trim() !== "";' in html
    assert 'const hasDecisionError = p.last_decision && p.last_decision.ok === false;' in html
    assert 'const modelFailed = !!(hasResponseError || hasDecisionError);' in html

    # Verify lightbulb can read both the legacy alias and explicit hint fields.
    assert 'let locallyClearedHintTargets = new Set();' in html
    assert 'const hasClueHint = p.has_new_clue === true || p.has_visible_clue_hint === true || p.has_detective_hint === true;' in html
    assert 'const showBulb = p.alive && hasClueHint && !locallyClearedHint && !isNight && !isDusk && !isGathering && (normalChatAvailable || deepDiveAvailable);' in html
    assert 'const bulbHtml = showBulb ?' in html
    assert 'locallyClearedHintTargets.clear();' in html
    assert 'pendingDeepDiveTarget = name;' in html
    assert 'locallyClearedHintTargets.add(responseTarget);' in html

    # Verify clampBubbleIntoLayer has the final boundary clamping logic for all currentSide cases
    assert 'Final boundary clamping to prevent any part of the bubble from being cut off' in html
    assert 'if (currentSide === "left") {' in html
    assert 'targetX = width + margin;' in html
    assert 'targetX = viewportWidth - margin;' in html
    assert '} else if (currentSide === "right") {' in html
    assert 'targetX = margin;' in html
    assert 'targetX = viewportWidth - margin - width;' in html


def test_prevent_down_orientation_twitching_during_movement():
    html = INDEX_HTML.read_text(encoding="utf-8")
    # Verify sprite.lastDir is tracked and set correctly
    assert 'sprite.lastDir = "right";' in html
    assert 'sprite.lastDir = "left";' in html
    assert 'sprite.lastDir = "down";' in html
    assert 'sprite.lastDir = "up";' in html
    # Verify we check lastDir on stop to keep standing pose instead of force-switching to "down"
    assert 'if (sprite.lastDir === "left") {' in html
    assert 'sprite.setTexture(key, "left-walk.000");' in html
    assert 'sprite.setTexture(key, "right-walk.000");' in html
    assert 'sprite.setTexture(key, "up-walk.000");' in html
    assert 'sprite.setTexture(key, "down-walk.000");' in html


def test_unified_bubble_ttl_without_exemptions():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Verify that applyBlueBubbleTTL body does not contain activeForAction exemption to bypass TTL
    idx = html.find("function applyBlueBubbleTTL")
    assert idx != -1
    body = html[idx : html.find("function", idx + 1)]
    assert "activeForAction" not in body

    # 2. Verify that freshThoughtForDisplay expires thoughts regardless of activeNow state
    assert "if (now - cached.time > BUBBLE_LIFETIME_SECONDS)" in html
    assert "if (!activeNow && now - cached.time > BUBBLE_LIFETIME_SECONDS)" not in html

    # 3. Verify that buildNpcThoughtBubble has check to return empty string if has thought but it expired
    assert "hasRawThoughtText && !rawThoughtText" in html


def test_chat2api_startup_runs_backend_llm_check():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'fetch("/api/test_llm_provider"' in html
    assert 'runtimeOptions.provider === "chat2api"' not in html
    assert "无需远程 API 检测" not in html



def test_reasoning_effort_select_stays_clickable_for_all_providers():
    html = INDEX_HTML.read_text(encoding="utf-8")
    start = html.index("function updateProviderFields()")
    body = html[start:html.index("function readLlmFieldDraft", start)]

    assert "reasoningEl.disabled = false;" in body
    assert "reasoningEl.disabled = !usesResponses;" not in body
    assert "if (!usesResponses) reasoningEl.value = \"\";" not in body

def test_new_bubble_behavior():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Verify that only 思考 / 计划 / 行动 are returned as labels in thought/action bubbles
    # and no '理由' label is present.
    assert "思考：" in html
    assert "计划：" in html
    assert "行动：" in html
    assert "理由：" not in html

    # 2. Verify thinking/planning gets a fallback bubble, but does not bypass unified TTL.
    idx = html.find("function applyBlueBubbleTTL")
    assert idx != -1
    body = html[idx : html.find("function", idx + 1)]
    assert "activeForPlan" not in body
    assert 'if (!activeForPlan) {' in html

    # 3. Verify action bubble target priorities:
    # action_target_person > action_target_object > action_target_location_label > location_label
    assert "p.action_target_person && String(p.action_target_person).trim() !== \"\"" in html
    assert "p.action_target_object && String(p.action_target_object).trim() !== \"\"" in html
    assert "p.action_target_location_label && String(p.action_target_location_label).trim() !== \"\"" in html
    assert "p.location_label && String(p.location_label).trim() !== \"\"" in html

    # 4. Verify translateObject helper function translates object names to Chinese
    assert "function translateObject(obj)" in html
    assert '"behind the supply store counter": "五金店柜台后"' in html
    assert '"behind the cafe counter": "咖啡馆柜台后"' in html


def test_agent_log_whitelist_covers_action_lifecycle():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'msg.includes("[行动计划]") || msg.includes("[开始行动]") || msg.includes("[行动结果]")' in html


def test_blue_bubble_sequential_thought_plan_action():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'if (activeForAction) {' in html
    assert 'return `${owner}<div class="bubble-row"><span class="bubble-key">开始行动：</span>${escapeHtml(sentence)}</div>`;' in html
    assert "cached.actionKey !== actionKey" in html
    assert "function blueBubbleActionKey(persona, html)" in html
    assert "if (activeForPlan && cached && !cached.expired" in html
    assert 'const target = actionTargetText(p, state);' in html
    assert 'if (target) return `前往${target}，${task}`;' in html
    assert '，目标：' not in html


def test_thought_waiting_text_is_not_treated_as_real_model_thought():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'const hasRawThoughtText = !!(p.thought_summary || p.thought);' in html
    assert 'const rawThoughtText = freshThoughtForDisplay(name, p.thought_summary || p.thought || "", p);' in html
    assert "正在整理当前情况" not in html
    assert "整理当前情况" not in html
    assert 'const thought = compactBubbleText(rawThoughtText, 70);' in html
    assert 'rawThoughtText || "正在整理当前情况。"' not in html
    assert 'p.thought_summary || p.thought || waitingThoughtDisplay' not in html
    assert 'if (!thought) return "";' in html

    build_start = html.find("function buildNpcThoughtBubble")
    build_end = html.find("function freshThoughtForDisplay", build_start)
    assert build_start != -1 and build_end != -1
    build_body = html[build_start:build_end]
    assert "querySelector" not in build_body


def test_white_bubble_displays_ongoing_action_during_movement_or_action():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "function actionStartBubbleEnded(name, persona)" in html
    assert "cached.expired !== true" in html
    assert "cached.actionKey === blueBubbleActionKey(persona, cached.html)" in html
    assert 'const isActionStatusBubble = bubblePayload && typeof bubblePayload === "object" && String(bubblePayload.kind || "") === "action_status";' in html
    assert "const actionStatusVisibleAt = Number(p.action_status_visible_at || 0);" in html
    assert "const actionStatusReady = actionStatusVisibleAt <= 0 || (Date.now() / 1000) >= actionStatusVisibleAt;" in html
    assert 'const canShowActionDuration = !isDusk && !isNight && runtime === "acting" && !isVisuallyMoving && Number(p.path_len || 0) <= 0 && actionStatusReady;' in html
    assert "const departureDelayUntil = Number(p.departure_delay_until || 0);" in html
    assert "const departureWaiting = departureDelayUntil > (Date.now() / 1000);" in html
    assert 'const activeForAction = !departureWaiting && (runtime === "starting_action" || runtime === "moving" || runtime === "acting" || Number(p.path_len || 0) > 0 || p.visual_moving === true || isVisuallyMoving);' in html
    assert "const isRealSpeechBubble = !!speechText && !isActionStatusBubble;" not in html
    assert "if (!thoughtText) {" in html
    assert "if (isActionStatusBubble && !canShowActionDuration) {" in html
    assert "if (!thoughtText || (isRealSpeechBubble && activeForAction)) {" not in html
    assert 'if (!displaySpeechText && p.alive && canShowActionDuration && !isActionStatusBubble) {' in html
    assert 'displaySpeechText = formatActionDurationLine(p, gameState);' in html
    assert 'function formatActionDurationLine(p, state)' in html
    assert 'if (!displaySpeechText && p.alive && (runtime === "moving" || runtime === "acting")) {' not in html


def test_strict_sequential_bubbles_and_action_status_clean():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Planning cache is preserved only while planning; action replaces it immediately.
    assert "blueBubbleCache" in html
    assert "cached.html.includes" in html
    assert "if (activeForPlan && cached && !cached.expired" in html
    assert "cached.actionKey !== actionKey" in html

    # 2. 检查 actionStartBubbleEnded
    assert "actionStartBubbleEnded(name, p)" not in html
    assert 'runtime === "starting_action"' in html

    # 3. 检查 runtime acting, path_len = 0, 非 visually moving 时的白泡显示
    assert 'runtime === "acting"' in html
    assert 'Number(p.path_len || 0) <= 0' in html
    assert '!isVisuallyMoving' in html

    # 4. 检查 action_status 不加说话前缀与以 ... 结尾
    assert "nameCandidates" in html
    assert "toSayRegex" in html
    assert "sayRegex" in html
    assert "colonRegex" in html
    assert 'return `${text.replace(/[。.!！]+$/, "") || "继续当前事务"}...`;' in html


def test_action_status_ttl_exclusion_and_purple_pink_logs():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # (1) Action status ends with ... regardless of path
    assert 'displaySpeechText = displaySpeechText.replace(/[。.!！]+$/, "").trim();' in html
    assert 'if (!displaySpeechText.endsWith("...")) {' in html
    assert 'displaySpeechText = displaySpeechText + "...";' in html

    # (2) Bypassing layout mutual exclusion and TTL while acting
    assert 'action_status 不受普通说话 TTL 提前隐藏，只由 runtime/action gate 控制，且不受 layout 互斥提前隐藏' in html
    assert 'if (canShowActionDuration) {' in html
    assert 'if (isActionStatusBubble) {' in html
    assert 'displaySpeechText = speechText;' in html

    # (3) Blue-bubble logs are purple; action result and chat logs are bright green.
    assert '#log-content .log-action {' in html
    assert '#log-content .log-think {' in html
    idx_action = html.find("#log-content .log-action")
    assert idx_action != -1
    assert "color: #6dff8f;" in html[idx_action:idx_action+100]

    idx_think = html.find("#log-content .log-think")
    assert idx_think != -1
    assert "color: #ff79c6;" in html[idx_think:idx_think+100]

    # (4) Real NPC speech is bright green, not dark green or purple.
    assert "#log-content .log-chat {" in html
    idx_chat = html.find("#log-content .log-chat")
    assert idx_chat != -1
    assert "color: #6dff8f;" in html[idx_chat:idx_chat+100]
    assert 'if (type === "chat") return "log-chat";' in html
    assert 'const showTypes = ["think", "chat", "kill", "action", "error", "system"];' in html
    assert 'const visibleLogTypes = ["think", "chat", "kill", "action", "error", "system"];' in html

    # (5) System logs are golden yellow; error/death logs are red.
    idx_system = html.find("#log-content .log-system")
    assert idx_system != -1
    assert "color: #f6c343;" in html[idx_system:idx_system+100]
    idx_error = html.find("#log-content .log-error")
    assert idx_error != -1
    assert "color: #f85149;" in html[idx_error:idx_error+100]
    idx_kill = html.find("#log-content .log-kill")
    assert idx_kill != -1
    assert "color: #f85149;" in html[idx_kill:idx_kill+100]

    # (6) Names inherit the line color; no extra blue category in log text.
    idx_agent = html.find("#log-content .log-agent")
    assert idx_agent != -1
    assert "color: inherit;" in html[idx_agent:idx_agent+100]
    assert "function isBlueBubbleLogEntry(entry)" in html
    blue_start = html.find("function isBlueBubbleLogEntry(entry)")
    blue_block = html[blue_start:html.find("function logColorClass", blue_start)]
    assert "msg.includes(\"[行动计划]\")" in blue_block
    assert "msg.includes(\"[开始行动]\")" in blue_block
    assert "msg.includes(\"[行动结果]\")" not in blue_block


def test_hidden_blue_action_bubble_does_not_count_as_displayed():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "const realSpeechVisible = !!speechText && p.alive && !isActionStatusBubble;" in html
    assert 'if (realSpeechVisible) {' in html
    assert 'thoughtText = applyBlueBubbleTTL(name, thoughtText, p);' in html
    assert 'A hidden blue' in html


def test_white_speech_bubble_must_not_coexist_with_blue_action_bubble():
    """White speech/conversation bubbles MUST NOT coexist with blue start-action bubbles.
    The activeForAction guard was removed so speech always suppresses thought bubbles."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    # The suppression block must set thoughtText unconditionally when speech exists
    speech_block_start = html.find("if (realSpeechVisible) {")
    assert speech_block_start != -1
    speech_block = html[speech_block_start:html.find('let displaySpeechText = "";', speech_block_start)]
    assert 'thoughtText = "";' in speech_block

    # This block must NOT have an activeForAction condition guarding the suppression.
    assert "if (!activeForAction) {" not in speech_block


def test_departure_delay_until_controls_round_two_speech_exclusively():
    """departure_delay_until is the mechanism for round-two departure speech:
    when departureWaiting is true, activeForAction is false, so speech
    suppresses the action bubble — but the mechanism is defined at the
    activeForAction level, not at the suppression guard level."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    # activeForAction must include departureWaiting
    assert "const departureWaiting = departureDelayUntil > (Date.now() / 1000);" in html
    assert 'const activeForAction = !departureWaiting && (runtime === "starting_action" || runtime === "moving" || runtime === "acting" || Number(p.path_len || 0) > 0 || p.visual_moving === true || isVisuallyMoving);' in html

    # The thought/action bubble building also respects departureWaiting
    assert 'if (!activeForPlan && !activeForAction && !recentThought) return "";' in html
    assert "!departureWaiting &&" in html


def test_dusk_and_night_have_explicit_scene_dimming_layers():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="phase-atmosphere"' in html
    assert "#phase-atmosphere.dusk" in html
    assert "rgba(255, 190, 92" in html
    assert "rgba(255, 169, 77" in html
    assert "#phase-atmosphere.night" in html
    assert 'atmosphere.className = isNight ? "night" : (isDusk ? "dusk" : "");' in html


def test_dusk_stage_renderer_gates_crow_input_and_locks_other_controls():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "function duskStage(state)" in html
    assert "voteSummary.stage || voteSummary.current_stage" in html
    assert 'stage === "crow_statement" || stage === "crow_input"' in html
    assert "function renderDuskVotingFlow(state)" in html
    assert "renderDuskVotingFlow(state);" in html
    assert "const duskInteractionLocked = isDusk && stage !== \"crow_statement\" && stage !== \"crow_input\";" in html


def test_vote_rows_support_self_vote_then_hide_all_vote_buttons():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "function eligibleDuskParticipants(state)" in html
    assert "voteSummary.eligible_participants" in html
    assert 'row.className = `dusk-vote-row' in html
    assert 'class="dusk-portrait"' in html
    assert 'button.className = "dusk-vote-button";' in html
    assert "submitCrowVote(name, e.currentTarget)" in html
    assert 'fetch("/api/submit_crow_vote"' in html
    assert 'fetch("/api/submit_crow_vote"' in html
    assert "const crowHasVoted = hasCrowVoted(voteSummary) || crowVoteSubmitting;" in html
    assert "crowVoteSubmitting = true;" in html
    assert "voteSummary.crow_voted === true" in html
    assert 'const showVoteButtons = stage === "voting" && voteSummary.active && !crowHasVoted;' in html
    assert 'else if (stage === "voting" && crowHasVoted)' in html


def test_vote_results_use_backend_winner_integer_counts_and_voter_icons():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "function normalizeVoteCounts(voteSummary)" in html
    assert "Math.trunc(Number(" in html
    assert "count.voters" in html
    assert 'class="dusk-voter-icon"' in html
    assert "const winner = voteSummary.winner || voteSummary.jail_target || \"\";" in html
    assert 'name === winner ? " winner" : ""' in html
    assert "voteSummary.tie_broken_by_crow" in html
    assert "最高票平票，按警长裁决权，由警长所投对象胜出。" in html
    assert 'onclick="confirmVoteResult()"' in html
    assert 'fetch("/api/confirm_vote_result", {method: "POST"})' in html
    assert 'socket.emit("confirm_vote_result");' not in html
    assert "jailAgent(name)" not in html


def test_night_transition_is_anonymous_fullscreen_and_confirm_only():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="night-transition-overlay"' in html
    assert "#night-transition-overlay.show" in html
    assert 'class="night-actor wolf"' in html
    assert html.count('class="night-actor wolf"') == 1
    assert 'class="night-actor knife"' in html
    assert 'id="night-wolf-progress-fill"' in html
    assert 'id="night-knife-progress-fill"' in html
    assert "function renderNightTransition(state)" in html
    assert "state.night_transition || state.night_sequence" in html
    assert 'id="night-progress-fill"' in html
    assert 'id="night-finish-confirm" onclick="confirmNightTransition()"' in html
    assert 'fetch("/api/confirm_night_transition", {method: "POST"})' in html
    assert 'socket.emit("confirm_night_transition");' not in html
    assert "夜晚结束" in html
    assert "target_name" not in html[html.index("function renderNightTransition(state)"):html.index("function renderNightTransition(state)") + 2500]


def test_night_silver_knife_multiple_corpses_and_silver_shot_ui():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1) Night transitions follow backend real-action progress for wolf and knife stages
    assert "sequence.wolf_progress" in html
    assert "sequence.knife_progress" in html
    assert "sequence.stage_elapsed" in html
    assert "sequence.stage_duration" in html
    assert "displayStageLabel = \"银质小刀阶段\"" in html
    assert "displayStageLabel = \"狼人行动中\"" in html
    assert "银质小刀阶段" in html
    assert "/static/assets/effects/night_moon_icon.png" in html
    assert "/static/assets/effects/wolf_paw_icon.png" in html
    assert "/static/assets/effects/silver_knife_icon.png" in html

    # 2) Anonymity check: no target name or holder leak in night sequence stage rendering
    night_idx = html.index("function renderNightTransition(state)")
    night_fn_content = html[night_idx:night_idx + 3500]
    assert "target_name" not in night_fn_content
    assert "holder_name" not in night_fn_content

    # 3) Check bodies array rendering with multiple bodies and werewolf corpse identification
    assert "const bodies = gameState.bodies || [];" in html
    assert "for (const body of bodies) {" in html
    assert 'body.kind === "werewolf" ||' in html
    assert 'body.corpse_kind === "werewolf" ||' in html
    assert 'body.is_werewolf_corpse === true' in html
    assert '"werewolf_corpse"' in html

    # 4) Check Day 4 silver shot triggers pending_silver_shot or silver_shot_available
    assert 'state.phase === "pending_silver_shot"' in html
    assert "showSilverShotModal" in html
    assert 'id="silver-shot-modal"' in html
    assert 'id="silver-shot-targets"' in html
    assert "/static/assets/effects/silver_bullet_icon.png" in html
    assert 'socket.emit("shoot_silver_bullet"' in html

    # 5) Rules modal update about the anonymity of silver knife validity
    assert "不会泄露银刀是否有效" in html


def test_new_dusk_camera_and_waiting_behavior():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # (1) Hide dusk-discussion-list from right side panel
    assert 'id="dusk-discussion-list"' in html
    assert 'display: none;' in html

    # (2) Wait reply NPC shows '正在聆听警长问询' instead of old action
    assert 'pendingChatTarget === name' in html
    assert 'pendingChatPhase === "waiting"' in html
    assert 'displaySpeechText = "正在聆听警长问询";' in html
    assert 'thoughtText = "";' in html
    assert 'const isNPCInActiveChat = (' in html
    assert 'let thoughtText = (isNPCInActiveChat || (suppressChatDisplay && !activeForAction)) ? "" : buildNpcThoughtBubble(name, p, gameState);' in html
    assert 'if (isNPCInActiveChat && p.alive) {\n      thoughtText = "";\n      if (!speechText) {\n        displaySpeechText = "";\n      }\n      delete blueBubbleCache[name];\n      delete thoughtBubbleCache[name];\n    }' in html.replace("\r\n", "\n")
    assert 'if (kind === "conversation_pending" && target === "Crow") {' in html
    assert 'return "正在聆听警长问询";' in html

    # (3) Dusk/voting camera slow centering
    assert 'const newIsDusk = !isNight &&' in html
    assert 'const site = gameState.initial_gathering_site;' in html
    assert 'sceneRef.cameras.main.pan((site.x * TILE_W) + (TILE_W / 2), (site.y * TILE_W) + (TILE_W / 2), 2000);' in html
    assert 'sceneRef.cameras.main.centerOn((site.x * TILE_W) + (TILE_W / 2), (site.y * TILE_W) + (TILE_W / 2));' in html


def test_dead_non_jailed_persona_sprite_is_hidden_to_avoid_duplicate_body():
    html = INDEX_HTML.read_text(encoding="utf-8")
    update_start = html.index("function update")
    update_block = html[update_start:html.index("// Call global bubble resolver", update_start)]

    assert "if (!p.alive && !p.jailed_corpse)" in update_block
    assert "sprite.setVisible(false);" in update_block
    assert "nameLabels[name].setVisible(false);" in update_block
    assert "modelLabels[name].setVisible(false);" in update_block


def test_game_over_ui_uses_reason_detail_and_closes_phase_modals():
    html = INDEX_HTML.read_text(encoding="utf-8")
    show_start = html.index("function showGameOver(data)")
    show_block = html[show_start:html.index("function gameOverReasonText", show_start)]

    assert 'id="game-over-card"' in html
    assert 'data.game_over_detail || "恭喜你消灭了所有的狼人，获得胜利。"' in show_block
    assert "data.game_over_detail || gameOverReasonText(data.game_over_reason)" in show_block
    assert '"dusk-statement-panel", "voting-panel", "night-transition-overlay", "silver-shot-modal"' in show_block
    assert "function gameOverReasonText(reason)" in html


def test_dev_complete_interviews_button_exists():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="test-complete-interviews-btn"' in html
    assert "一键交谈完" in html
    assert "bottom: calc(var(--log-panel-height) + 8px);" in html
    assert "#test-complete-interviews-btn" in html
    assert "opacity: 0;" in html
    assert "color: transparent;" in html
    assert "cursor: default;" in html
    assert "#test-complete-interviews-btn:hover" in html
    assert "cursor: default !important;" in html
    assert 'title="测试用：直接完成今日所有NPC交谈"' not in html
    assert "pointer-events: auto;" in html
    assert "function completeDailyInterviewsForTest()" in html
    assert 'socket.emit("test_complete_daily_interviews")' in html
    assert 'test_complete_daily_interviews_result' in html


def test_right_sidebar_has_no_chat_transcript_ui():
    html = INDEX_HTML.read_text(encoding="utf-8")
    add_chat_start = html.find("function addChatMsg")
    assert add_chat_start != -1
    add_chat_body = html[add_chat_start : html.find("function", add_chat_start + len("function addChatMsg"))]

    assert 'id="chat-log"' not in html
    assert "#chat-log" not in html
    assert "chat-msg-detective" not in html
    assert "chat-msg-other" not in html
    assert 'document.getElementById("chat-log")' not in html
    assert "#chat-panel {\n  display: none !important;" in html
    assert 'document.getElementById("chat-log")' not in add_chat_body
    assert ".appendChild" not in add_chat_body
    assert "chat-ui-disabled" in add_chat_body


def test_action_and_detective_chat_clear_blue_bubble_cache():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'delete blueBubbleCache[name];' in html
    assert 'delete thoughtBubbleCache[name];' in html
    assert 'conversationWith === "Crow"' in html
    assert 'conversationWith === "克罗"' in html
    assert 'if (isActionStatusBubble) {' in html
    assert 'displaySpeechText = "";' in html
    assert 'p.action_plan = "";' in html
    assert 'p.thought_summary = "";' in html
    assert 'p.last_decision = {};' in html


def test_action_status_and_start_action_mutual_exclusion():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Entering action_status clears caches
    assert 'if (isActionStatusBubble) {\n      delete blueBubbleCache[name];\n      delete thoughtBubbleCache[name];\n    }' in html or 'if (isActionStatusBubble) {\n      delete blueBubbleCache[name];\n      delete thoughtBubbleCache[name];\n    }' in html.replace("\r\n", "\n")

    # 2. Action status bubble and start-action blue bubble cannot coexist on screen (thoughtText is set to empty)
    assert 'if (realSpeechVisible) {' in html
    assert 'else if (isActionStatusBubble) {' in html

    # 3. kind=conversation_pending and target=Crow or 克罗 displays "正在聆听警长问询"
    assert 'if (kind === "conversation_pending" && target === "Crow") {' in html
    assert 'if (kind === "conversation_pending" && target === "克罗") {' in html


def test_pending_chat_wait_merge_has_no_duplicate_server_bubble_const():
    html = INDEX_HTML.read_text(encoding="utf-8")
    marker = "function mergePendingChatTargetWaitBubble"
    start = html.find(marker)
    assert start != -1
    body = html[start : html.find("function", start + len(marker))]
    assert body.count("const serverBubble") == 1
    assert "const existingBubble" in body


def test_dusk_and_voting_panels_outside_side_panel():
    html = INDEX_HTML.read_text(encoding="utf-8")

    side_panel_open = html.index('<div id="side-panel">')
    # Track div nesting to find the closing tag of side-panel
    depth = 1
    cursor = side_panel_open + len('<div id="side-panel">')
    while depth > 0:
        next_open = html.find('<div', cursor)
        next_close = html.find('</div>', cursor)
        if next_close == -1:
            break
        if next_open != -1 and next_open < next_close:
            depth += 1
            cursor = next_open + 4
        else:
            depth -= 1
            cursor = next_close + 6

    side_panel_close = cursor - 6

    dusk_panel_idx = html.index('id="dusk-statement-panel"')
    voting_panel_idx = html.index('id="voting-panel"')

    assert dusk_panel_idx > side_panel_close, "dusk-statement-panel must be outside and after side-panel"
    assert voting_panel_idx > side_panel_close, "voting-panel must be outside and after side-panel"

    # Assert they are not inside side-panel's HTML block
    side_panel_html = html[side_panel_open:side_panel_close]
    assert 'id="dusk-statement-panel"' not in side_panel_html
    assert 'id="voting-panel"' not in side_panel_html


def test_no_chat_log_or_right_transcript():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="chat-log"' not in html
    assert '#chat-log' not in html
    assert 'document.getElementById("chat-log")' not in html
    # The right sidebar should have no transcript container
    assert 'chat-msg-detective' not in html
    assert 'chat-msg-other' not in html


def test_night_progress_fills_for_wolf_and_knife():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Verify progress fills for both wolf and knife exist
    assert 'id="night-wolf-progress-fill"' in html
    assert 'id="night-knife-progress-fill"' in html

    # 2. Verify night-progress-fill is no longer the sole progress bar (it is hidden / display: none)
    assert 'id="night-progress-fill"' in html
    assert 'id="night-progress-fill" style="display: none;"' in html

    # 3. Verify JavaScript logic assigns widths to both fills
    assert 'const wolfFill = document.getElementById("night-wolf-progress-fill");' in html
    assert 'const knifeFill = document.getElementById("night-knife-progress-fill");' in html
    assert 'wolfFill.style.width = ' in html
    assert 'knifeFill.style.width = ' in html


def test_night_ui_shows_silver_bullet_crafting_status():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'id="night-silver-bullet-crafting"' in html
    assert 'sequence.silver_bullet_crafting' in html
    assert '银质子弹正在制作，今晚已完成。' in html


def test_crow_vote_disabled_submitting_lock():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Verify crowVoteSubmitting lock variable is declared
    assert 'let crowVoteSubmitting = false;' in html

    # 2. Verify lock check in submitCrowVote
    assert 'if (name === undefined || name === null || !gameState || crowVoteSubmitting) return;' in html

    # 3. Verify setting the lock and removing vote actions locally on click
    assert 'crowVoteSubmitting = true;' in html
    assert "hideDuskVoteActionsAfterClick();" in html
    assert 'document.querySelectorAll(".dusk-vote-button").forEach(btn => btn.remove());' in html
    assert "footerAbstainBtn.remove();" in html

    # 4. Verify rendering logic honors the lock state
    assert 'const showVoteButtons = stage === "voting" && voteSummary.active && !crowHasVoted;' in html

    # 5. Verify reset of the lock when state is updated
    assert 'crowVoteSubmitting = false;' in html


def test_voting_abstainers_row():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Verify the HTML containers for voting abstainers exist
    assert 'id="voting-abstainers"' in html
    assert 'id="voting-abstainers-list"' in html
    assert '弃票者' in html

    # 2. Verify JS logic parses abstainers from votes
    assert 'const abstainersEl = document.getElementById("voting-abstainers");' in html
    assert 'const abstainersListEl = document.getElementById("voting-abstainers-list");' in html
    assert 'const abstainers = [];' in html
    assert '["none", "null", "abstain"].includes(String(target).toLowerCase())' in html
    assert 'abstainers.push(voter);' in html
    assert 'abstainersEl.style.display = "block";' in html
    assert 'abstainersEl.style.display = "none";' in html


def test_daybreak_socket_handler_or_fallback():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "confirmNightTransition" in html
    assert 'fetch("/api/confirm_night_transition", {method: "POST"})' in html
    assert 'socket.emit("confirm_night_transition")' not in html
    assert 'fetch("/api/confirm_night_transition"' in html
    assert 'overlay.classList.remove("show")' in html
    assert "nightTransitionConfirming = false;" in html
    assert 'fetchCurrentState()' in html



def test_dusk_statement_and_voting_panels_are_centered_modals_outside_side_panel():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # Assert dusk-statement-panel and voting-panel have modal classes
    assert 'id="dusk-statement-panel" class="modal"' in html
    assert 'id="voting-panel" class="modal"' in html

    # Assert dusk-statement-panel and voting-panel are NOT inside #side-panel
    side_panel_open = html.index('<div id="side-panel">')
    announce_btn_open = html.index('id="announce-btn"')
    side_panel_close = html.find('</div>', announce_btn_open)

    side_panel_markup = html[side_panel_open:side_panel_close]
    assert 'id="dusk-statement-panel"' not in side_panel_markup
    assert 'id="voting-panel"' not in side_panel_markup
    assert 'id="chat-panel"' not in side_panel_markup


def test_night_transition_dual_progress_fills():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # Assert separate progress fills exist
    assert 'id="night-wolf-progress-fill"' in html
    assert 'id="night-knife-progress-fill"' in html


def test_vote_submission_disables_buttons_immediately():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # Assert local disabling logic is present in submitCrowVote
    assert 'crowVoteSubmitting = true;' in html
    assert 'btn.disabled = true' in html
    assert 'id="voting-abstainers"' in html
    assert 'footerAbstainBtn.id = "footer-abstain-btn";' in html
    assert 'footerAbstainBtn.addEventListener("click", (e) => submitCrowVote("", e.currentTarget));' in html
    assert 'abstainBtn.id = "abstain-vote-button";' not in html
    assert 'fetch("/api/submit_crow_vote"' in html
    assert 'socket.emit("submit_crow_vote"' not in html


def test_dusk_vote_click_removes_actions_and_keeps_waiting_state_clean():
    html = INDEX_HTML.read_text(encoding="utf-8")
    submit_start = html.index("function submitCrowVote")
    submit_end = html.index("function confirmVoteResult()", submit_start)
    submit_block = html[submit_start:submit_end]
    render_start = html.index("function renderDuskVotingFlow(state)")
    render_end = html.index("function renderVoteHistory(state)", render_start)
    render_block = html[render_start:render_end]

    assert "function hideDuskVoteActionsAfterClick()" in html
    assert "hideDuskVoteActionsAfterClick();" in submit_block
    assert 'document.querySelectorAll(".dusk-vote-button").forEach(btn => btn.remove());' in html
    assert 'const footerAbstainBtn = document.getElementById("footer-abstain-btn");' in html
    assert "footerAbstainBtn.remove();" in html
    assert "已选择弃票，投票中..." not in submit_block
    assert "已选择弃票，投票中..." not in render_block
    assert 'actions.innerHTML = `<div class="dusk-vote-waiting"' in render_block
    assert ".dusk-voter-icon { width: 30px; height: 30px;" in html
    assert "min-width: 88px; min-height: 48px;" in html
    assert "#voting-panel { z-index: 1300;" in html
    assert "function refreshDuskVoteCountdownOnly()" in html
    assert "refreshDuskVoteCountdownOnly();" in html
    assert 'button.addEventListener("pointerdown"' in html
    assert 'onpointerdown="event.preventDefault(); confirmVoteResult()"' in html


def test_dusk_discussion_forces_front_facing_sprites():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "const liveDuskStage = gameState ? duskStage(gameState) : \"\";" in html
    assert "sprite.lastDir = \"down\";" in html
    assert 'sprite.setTexture(key, "down-walk.000");' in html


def test_night_phase_snaps_sprites_and_marks_silver_knife_holder():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'if (isNight || (gameState && gameState.phase === "night")) {' in html
    assert 'sprite.setPosition(targetPx, targetPy);' in html
    assert "state.silver_knife_holder && state.silver_knife_holder === name" in html
    assert "gameState.silver_knife_holder === name" in html
    assert "silver-knife-test-marker" in html


def test_confirm_vote_result_success_hides_voting_panel():
    html = INDEX_HTML.read_text(encoding="utf-8")
    start = html.index('socket.on("confirm_vote_result_response"')
    end = html.index('socket.on("connect"', start)
    block = html[start:end]

    assert 'const panel = document.getElementById("voting-panel");' in block
    assert "voteResultConfirming = false;" in block
    assert 'if (panel) panel.style.display = "none";' in block


def test_normal_chat_button_is_independent_from_deep_dive_quota():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "无深挖" not in html
    assert "const normalChatAvailable =" in html
    assert "if (normalChatAvailable) {" in html
    assert "buttonsListHtml += `" in html
    assert "} else if (deepDiveAvailable)" in html
    assert "if (globalDdRemaining > 0 || deepDiveAvailable)" not in html
    normal_chat_block = html[
        html.index("if (normalChatAvailable) {"):
        html.index("} else if (deepDiveAvailable)")
    ]
    assert "globalDdRemaining" not in normal_chat_block


def test_initial_camera_prefers_original_gathering_site():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "const site = state.initial_gathering_site;" in html
    assert 'state.phase === "day" && state.primary_cta === "gathering"' in html


def test_pending_detective_chat_does_not_suppress_real_reply_bubble():
    html = INDEX_HTML.read_text(encoding="utf-8")
    start = html.index("function isChatSuppressedFor")
    end = html.index("function showLocalCrowQuestion", start)
    block = html[start:end]
    assert 'return !text || kind === "action_status";' in block
    assert "return !!pendingChatTarget && name === pendingChatTarget;" not in block


def test_audited_frontend_additions():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Cross-day lightbulb reset
    assert "let lastCheckedDay = null;" in html
    assert "if (lastCheckedDay !== null && lastCheckedDay !== state.day) {" in html
    assert "locallyClearedHintTargets.clear();" in html
    assert "lastCheckedDay = state.day;" in html
    assert "lastCheckedDay = null;" in html  # inside resetAgentLog

    # 2. Night camera lock at Crow's home and controls disabled
    assert "let nightCameraLocked = false;" in html
    assert "nightCameraLocked = true;" in html
    assert "nightCameraLocked = false;" in html  # reset in updateUI/resetAgentLog
    assert "const homeX = 23 * TILE_W + TILE_W / 2;" in html
    assert "const homeY = 65 * TILE_W + TILE_W / 2;" in html
    assert "if (isNight) return;" in html  # in pointerdown/pointermove

    # 3. Confirm dawn socket refresh and fallback
    assert 'socket.on("confirm_night_transition_response"' in html
    assert 'setTimeout(() => {\n      fetchCurrentState();\n    }, 1000);' not in html.replace('\r\n', '\n')
    assert 'overlay.classList.remove("show")' in html

    # 4. Forbidden UI not inside side panel
    side_panel_open = html.index('<div id="side-panel">')
    announce_btn_open = html.index('id="announce-btn"')
    side_panel_close = html.find('</div>', announce_btn_open)
    side_panel_markup = html[side_panel_open:side_panel_close]

    assert 'id="dusk-statement-panel"' not in side_panel_markup
    assert 'id="voting-panel"' not in side_panel_markup
    assert 'id="chat-panel"' not in side_panel_markup
    assert 'id="night-transition-overlay"' not in side_panel_markup


def test_dusk_npc_facing_and_crow_abstain_button():
    html = INDEX_HTML.read_text(encoding="utf-8")

    # 1. Verify NPC orientation logic forces facing front (down) during dusk discussion or voting phases/stages when stationary
    assert "const isDuskDiscussionOrVoting = gameState && (" in html
    assert 'gameState.phase === "dusk_discussion" ||' in html
    assert 'gameState.phase === "dusk" ||' in html
    assert '(gameState.phase === "day" && gameState.primary_cta === "gathering") ||' in html
    assert '["gathering", "knowledge_reveal", "npc_discussion", "discussion", "crow_statement", "crow_input", "vote_opening", "voting", "results", "result", "result_announcement_pending", "result_announcement", "final_words", "escorting", "escort"].includes(liveDuskStage)' in html
    assert "if (isDuskDiscussionOrVoting) {" in html
    assert 'sprite.setTexture(key, "down-walk.000");' in html

    # 2. Verify Voting UI includes a Crow abstain/skip/no-vote button
    assert 'footerAbstainBtn.id = "footer-abstain-btn";' in html
    assert 'footerAbstainBtn.addEventListener("click", (e) => submitCrowVote("", e.currentTarget));' in html
    assert '放弃投票' in html
    assert '本轮不投票（弃票）' not in html


def test_morning_gathering_hides_normal_action_bubbles():
    html = INDEX_HTML.read_text(encoding="utf-8")
    start = html.index("function buildNpcThoughtBubble")
    end = html.index("function resolveBubbleLayout", start)
    block = html[start:end]
    assert 'state.phase === "day" && state.primary_cta === "gathering"' in block
    assert 'return "";' in block

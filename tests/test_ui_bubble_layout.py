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

    assert 'const modelFailed = !!(p.llm_error || p.last_error || p.response_error || (p.last_decision && p.last_decision.ok === false));' in html
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
    """#bubble-layer must be constrained to game area only — no overlap with right panel or bottom log."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "right: 320px" in html
    assert "bottom: 160px" in html
    assert "overflow: hidden" in html
    assert "width: max-content;" not in html
    assert "overflow-wrap: anywhere;" in html


def test_no_right_edge_width_clamp():
    """Bubble width is NOT dynamically clamped near right edge; overflow hidden handles clipping."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    # No JavaScript code dynamically sets maxWidth (camelCase = JS property)
    # — only CSS `max-width` (hyphenated) is allowed.
    assert "maxWidth" not in html, "JS must not dynamically set maxWidth on bubbles"

    # Bubble left positioning is based on screen coordinate, never clamped to viewportWidth
    assert "bubbleEl.style.left = screenX +" in html
    assert "tBubbleEl.style.left = screenX +" in html

    # No code re-calculates bubble width based on residual visible space
    assert "overflow: hidden" in html or "overflow-x: hidden" in html

    # The inVisibleScreen check only cares about anchor point, not bubble extent
    # — overflow will be clipped by #bubble-layer overflow hidden
    assert "inVisibleScreen" in html
    assert "screenX <= viewportWidth" in html


def test_bubble_layer_clips_overflow():
    """#bubble-layer clips bubble overflow; bubbles have fixed max-width (not dynamic/percentage)."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    # bubble-layer overflow hidden is present — clips bubble overflow
    assert "overflow: hidden" in html

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

    # Do not use negative margin hacks; #bubble-layer clips overflow instead.
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
    assert "modelLabels[name].y = cy - 30;" in html
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
    assert "const chatBtnDisabled = (!chatAvailable || isNight || isDusk || isPendingChat || isGathering) ? \"disabled\" : \"\";" in html
    assert "if (!isNight && gameState && !pendingChatTarget)" in html
    assert "const suppressChatDisplay = isChatSuppressedFor(name);" in html
    assert 'const speechText = suppressChatDisplay ? "" : bubbleSpeechText(bubblePayload);' in html
    assert 'return !!pendingChatTarget && name === pendingChatTarget;' in html
    assert 'showLocalCrowQuestion(name, msg);' in html
    assert 'let thoughtText = suppressChatDisplay ? "" : buildNpcThoughtBubble(name, p, gameState);' in html


def test_deep_dive_submit_decrements_remaining_optimistically():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert 'function deepDiveRemaining(state)' in html
    assert 'if (typeof state.deep_dive_remaining === "number")' in html
    assert 'const ddLeft = deepDiveRemaining(state);' in html
    assert 'const ddLeftReal = deepDiveRemaining(state);' in html
    assert 'function submitDeepDiveChat(name, msg)' in html
    assert 'setPendingChat(name, "waiting");' in html
    assert 'state.deep_dive_remaining = Math.max(0, state.deep_dive_remaining - 1);' in html
    assert 'state.deep_dive_used += 1;' in html
    assert 'updateUI(state);' in html


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
    assert '<span class="bubble-key">行动：</span>' in html
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
    assert "if (dist <= 3)" in html
    assert 'isMoving && p.path_len > 0' in html


def test_bubble_horizontal_boundary_clamping():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "#bubble-layer clips overflow" in html
    assert "Do not horizontally clamp bubbles at the game edge" in html
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


def test_werewolf_role_tag_uses_status_werewolf_names():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "Array.isArray(state.werewolf_names) && state.werewolf_names.includes(name)" in html
    assert 'roleVal = "werewolf";' in html


def test_thought_bubble_uses_same_ttl_as_speech_bubble():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "const BUBBLE_LIFETIME_SECONDS = 12;" in html
    assert "let thoughtBubbleCache = {};" in html
    assert "function freshThoughtForDisplay(name, rawText, persona)" in html
    assert "persona.thought_time" in html
    assert '["thinking", "planning", "moving", "acting"].includes(persona.runtime_state)' in html
    assert "now - cached.time > BUBBLE_LIFETIME_SECONDS" in html
    assert 'let thoughtText = suppressChatDisplay ? "" : buildNpcThoughtBubble(name, p, gameState);' in html


def test_chinese_titles_and_log_labels():
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert "<title>狼人小镇</title>" in html
    assert "<h1>狼人小镇</h1>" in html
    assert '<span class="panel-title">狼人小镇' in html
    assert "Werewolf Ville" not in html
    assert "Agent Log" not in html


def test_frontend_does_not_render_agent_log_panel():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "function updateLog(state)" not in html
    assert "#log-panel" not in html
    assert "log-content" not in html


def test_bottom_right_keeps_tasks_without_extra_log_block():
    """Right-bottom UI keeps sheriff tasks only, not the extra long log block. # covers REQ-086"""
    html = INDEX_HTML.read_text(encoding="utf-8")

    assert '<div id="task-panel">' in html
    assert '<div id="log-panel">' not in html
    assert 'id="log-content"' not in html
    assert "智能体日志" not in html


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
    assert 'modelLabels[name].setStyle({ fill: "#ffdd57" });' in html

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
    assert 'chatBtnDisabled = (!chatAvailable || isNight || isDusk || isPendingChat || isGathering) ? "disabled" : "";' in html
    assert 'ddBtnDisabled = (!deepDiveAvailable || isNight || isDusk || isGathering) ? "disabled" : "";' in html
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

    # 4. Hide thought bubble when speech bubble visible unless activeForAction
    assert 'if (speechText && p.alive) {' in html
    assert 'const activeForAction = runtime === "moving" || runtime === "acting" || Number(p.path_len || 0) > 0;' in html
    assert 'if (!activeForAction) {' in html
    assert 'thoughtText = "";' in html

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

    # 2. TTL timer safety: do not delete blueBubbleCache when html is empty
    assert "delete blueBubbleCache" not in html

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

    # 7. Detective/NPC chat log must not hide model length by hard-truncating text.
    assert "msg.substring(0, 120)" not in html
    assert 'getDisplayName(who, gameState) + ": " + msg' in html

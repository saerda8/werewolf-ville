import threading
import time

import game_engine


def _make_engine(monkeypatch, seed=7):
    empty_maze = [[0] * 140 for _ in range(100)]
    monkeypatch.setattr(game_engine, "load_collision_maze", lambda: empty_maze)
    monkeypatch.setattr(
        game_engine,
        "load_scene_data",
        lambda: (empty_maze, empty_maze, empty_maze, {}, {}, {}),
    )
    monkeypatch.setattr(
        game_engine.WerewolfGameEngine,
        "_build_shared_spatial_memory",
        lambda self: {},
    )
    monkeypatch.setattr(game_engine.Agent, "init_files", lambda self: None)
    monkeypatch.setattr(game_engine.Agent, "init_scratch_from_soul", lambda self: None)
    monkeypatch.setattr(game_engine.Agent, "load_shared_spatial_memory", lambda self, data: None)
    monkeypatch.setattr(game_engine.Agent, "read_soul", lambda self: "test soul")
    monkeypatch.setattr(game_engine.Agent, "read_memory", lambda self: "test memory")
    return game_engine.WerewolfGameEngine(random_seed=seed)


def test_late_round_one_response_is_ignored_after_timeout(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    called = threading.Event()
    release = threading.Event()

    def slow_chat(*args, **kwargs):
        called.set()
        release.wait(timeout=2)
        return "迟到的大模型发言"

    monkeypatch.setattr(game_engine, "chat_for_agent", slow_chat)

    engine._gathering_busy = True
    engine._gathering_speaker_idx = 1
    engine._trigger_round_one_speak("Arthur Burton")
    assert called.wait(timeout=1)

    engine._gathering_speak_start_time = time.time() - engine.gathering_turn_timeout - 1
    engine._handle_gathering()

    assert engine._gathering_speaker_idx == 2
    assert len(engine._gathering_speech_history) == 1
    assert engine._gathering_speech_history[0]["speaker"] == "Arthur Burton"
    assert engine._gathering_speech_history[0]["speech"] != "迟到的大模型发言"

    release.set()
    for _ in range(20):
        if any("迟到响应" in entry["message"] for entry in engine.game_log):
            break
        time.sleep(0.05)

    assert engine._gathering_speaker_idx == 2
    assert len(engine._gathering_speech_history) == 1
    assert any("迟到响应" in entry["message"] for entry in engine.game_log)


def test_gathering_timeout_is_positive_and_configured(monkeypatch):
    engine = _make_engine(monkeypatch)

    assert engine.gathering_turn_timeout >= 15
    assert engine.gathering_per_speaker_timeout >= 10
    assert engine.gathering_per_speaker_timeout <= engine.gathering_turn_timeout


def test_round_one_plain_text_does_not_attempt_json_parse(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    done = threading.Event()

    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "昨晚我在家，今早会配合调查。")

    def reject_json_parse(*args, **kwargs):
        raise AssertionError("round one plain text must not be parsed as JSON")

    monkeypatch.setattr(engine, "_parse_gathering_json", reject_json_parse)
    engine._trigger_round_one_speak("Arthur Burton")

    for _ in range(20):
        if engine._gathering_speech_history:
            done.set()
            break
        time.sleep(0.05)

    assert done.is_set()
    assert engine._gathering_speech_history[-1]["speech"] == "昨晚我在家，今早会配合调查。"


def test_round_one_speech_localizes_names_and_removes_self_intro(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    done = threading.Event()

    monkeypatch.setattr(
        game_engine,
        "chat_for_agent",
        lambda *args, **kwargs: "我是 Isabella Rodriguez。昨晚我在咖啡馆收拾到很晚，今天会留意异常。",
    )

    engine._trigger_round_one_speak("Isabella Rodriguez")

    for _ in range(20):
        if engine._gathering_speech_history:
            done.set()
            break
        time.sleep(0.05)

    assert done.is_set()
    speech = engine._gathering_speech_history[-1]["speech"]
    assert speech == "昨晚我在咖啡馆收拾到很晚，今天会留意异常。"
    assert "Isabella Rodriguez" not in speech
    assert not speech.startswith("我是")


def test_round_one_speech_removes_proactive_accusations():
    """_sanitize_round_one_speech must strip '我怀疑XXX' patterns."""
    sanitized = game_engine.WerewolfGameEngine._sanitize_round_one_speech(
        "Arthur Burton",
        "我怀疑Isabella Rodriguez。昨晚我在店里修工具。",
    )
    assert "我怀疑" not in sanitized, f"Accusation not removed: {sanitized}"
    assert "修工具" in sanitized, f"Legitimate content preserved: {sanitized}"


def test_round_one_speech_removes_wound_analysis():
    """_sanitize_round_one_speech must strip wound analysis language."""
    sanitized = game_engine.WerewolfGameEngine._sanitize_round_one_speech(
        "Mei Lin",
        "伤口像是野兽撕咬，昨晚我在图书馆。",
    )
    assert "撕咬" not in sanitized, f"Wound analysis not removed: {sanitized}"
    assert "图书馆" in sanitized, f"Legitimate content preserved: {sanitized}"


def test_round_one_speech_removes_werewolf_mechanics():
    """_sanitize_round_one_speech must strip werewolf-specific discussion."""
    sanitized = game_engine.WerewolfGameEngine._sanitize_round_one_speech(
        "Sam Moore",
        "狼人的作案手法很残忍。昨晚我在家休息。",
    )
    assert "狼人" not in sanitized, f"Werewolf mention not removed: {sanitized}"
    assert "在家休息" in sanitized, f"Legitimate content preserved: {sanitized}"


def test_round_one_prompt_contains_new_constraints(monkeypatch):
    """The round-one system prompt must include accusation and wound analysis constraints."""
    import inspect
    source = inspect.getsource(game_engine.WerewolfGameEngine._trigger_round_one_speak)
    assert "禁止主动点名或指责其他居民" in source, (
        "Round-one prompt missing accusation constraint"
    )
    assert "禁止分析伤口或讨论狼人作案手法" in source, (
        "Round-one prompt missing wound analysis constraint"
    )


def test_crow_case_intro_uses_deterministic_preset_without_model(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine.gathering_per_speaker_timeout = 2
    engine._init_gathering()
    called = threading.Event()

    def slow_chat(*args, **kwargs):
        called.set()
        time.sleep(10)
        return "我会继续调查，请大家如实说明。"

    monkeypatch.setattr(game_engine, "chat_for_agent", slow_chat)

    engine._trigger_round_one_speak("Crow")
    time.sleep(0.1)
    assert not called.is_set()

    assert engine._gathering_speech_history[0]["speaker"] == "Crow"
    assert engine._gathering_speech_history[0].get("intro") is True
    assert "遇害" in engine._gathering_speech_history[0]["speech"]
    assert engine.chat_bubbles["Crow"]["text"] == engine._gathering_speech_history[0]["speech"]

    deadline = time.time() + 8
    while time.time() < deadline and len([e for e in engine._gathering_speech_history if e.get("intro")]) < 2:
        time.sleep(0.05)

    assert len([e for e in engine._gathering_speech_history if e.get("intro")]) >= 2


def test_crow_case_intro_never_publishes_model_json(monkeypatch):
    """Regression: Crow's opening case intro is fully deterministic.

    It must never call chat_for_agent or parse JSON/model lines, even if
    chat_for_agent returns a JSON-fenced response.  All published intro
    text must be free of JSON delimiters, backtick fence markers, and
    model-generated content.
    """
    call_count = 0
    json_fenced_response = (
        '```json\n'
        '{"lines": ["我是克罗警长，昨晚有人遇害。", "请按顺序说明行踪。"],'
        ' "speech": "模型台词不应出现"}\n'
        '```'
    )

    def counting_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return json_fenced_response

    engine = _make_engine(monkeypatch)
    monkeypatch.setattr(game_engine, "chat_for_agent", counting_chat)
    engine._init_gathering()

    engine._trigger_round_one_speak("Crow")

    deadline = time.time() + 10
    while time.time() < deadline:
        intro_entries = [e for e in engine._gathering_speech_history if e.get("intro")]
        if len(intro_entries) >= 3:
            break
        time.sleep(0.05)

    # 1. chat_for_agent must never have been called
    assert call_count == 0, (
        f"chat_for_agent was called {call_count} time(s); Crow intro must be fully deterministic"
    )

    # 2. None of the published intro text may contain JSON/fence characters
    fence_chars = frozenset("{}\"`")
    for entry in engine._gathering_speech_history:
        if not entry.get("intro"):
            continue
        speech = entry["speech"]
        for ch in fence_chars:
            assert ch not in speech, (
                f"Crow intro leaked JSON/fence char {ch!r} in: {speech!r}"
            )

    # 3. Model-generated content must not appear
    intro_text = "\n".join(
        e["speech"] for e in engine._gathering_speech_history if e.get("intro")
    )
    assert "模型台词不应出现" not in intro_text

    # 4. All intro entries carry the "intro" marker
    assert all(
        e.get("intro") for e in engine._gathering_speech_history
    ), "All Crow speech-history entries must be marked intro=True"


def test_gathering_bubble_replaces_previous_participant_bubble(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine.chat_bubbles["Crow"] = {"text": "old", "time": 0}

    engine._show_gathering_bubble("Arthur Burton", "new")

    assert "Crow" not in engine.chat_bubbles
    assert engine.chat_bubbles["Arthur Burton"]["text"] == "new"


def test_crow_stays_player_controlled_when_round_two_begins(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_speaker_idx = len(engine._gathering_queue)
    crow = engine.agents["Crow"]
    original_target = (crow.target_x, crow.target_y)

    engine._handle_round_one()
    engine._gathering_dismissal_ready_at = 0
    engine._handle_round_one()

    assert engine._gathering_round == 2
    assert engine._gathering_left["Crow"] is True
    assert engine.agents["Crow"].current_action != "investigating"
    assert (crow.target_x, crow.target_y) == original_target
    dismissal = [e for e in engine._gathering_speech_history if e.get("dismissal")]
    assert len(dismissal) == 1
    assert dismissal[0]["speaker"] == "Crow"
    assert "黄昏" in dismissal[0]["speech"]
    assert engine.chat_bubbles["Crow"]["text"] == dismissal[0]["speech"]


def test_gathering_speech_keeps_complete_sentences_under_soft_limit():
    speech = "昨晚我在家中整理资料。今早的命案让我很不安。" + "我会继续留意附近是否有异常。" * 5

    limited = game_engine.WerewolfGameEngine._limit_gathering_speech(speech)

    # No hard truncation: full speech preserved, even if longer than old 72-char limit
    assert limited == speech
    assert len(limited) > 72


def test_gathering_speech_allows_small_overrun_past_sixty_characters():
    speech = "昨晚我在家整理资料，听见外面有一些动静。今天我会去店里开门，也会留意附近有没有异常情况，遇到可疑的人就马上告诉侦探，请大家也小心，我还会记录每个进店人的时间。"

    limited = game_engine.WerewolfGameEngine._limit_gathering_speech(speech)

    # No hard truncation: full speech preserved even over 72 chars
    assert limited == speech
    assert len(speech) > 72


def test_gathering_speech_preserves_long_text_no_fallback():
    """Long text with no sentence breaks is preserved, not fallen back."""
    speech = "这句话没有任何停顿" * 20

    limited = game_engine.WerewolfGameEngine._limit_gathering_speech(speech)

    # No hard truncation: full text preserved regardless of length
    assert limited == speech
    assert len(limited) > 100


def test_gathering_speech_returns_fallback_on_empty():
    """Empty or whitespace-only text still gets fallback."""
    assert game_engine.WerewolfGameEngine._limit_gathering_speech("") == "命案很严重，我会如实配合调查。"
    assert game_engine.WerewolfGameEngine._limit_gathering_speech("   ") == "命案很严重，我会如实配合调查。"
    assert game_engine.WerewolfGameEngine._limit_gathering_speech(None) == "命案很严重，我会如实配合调查。"


def test_departure_speech_uses_chinese_landmark_name(monkeypatch):
    engine = _make_engine(monkeypatch)

    speech = engine._departure_speech("Isabella Rodriguez", "Hobbs Cafe")

    assert "霍布斯咖啡馆" in speech
    assert speech != "我要去霍布斯咖啡馆。"


def test_departure_speech_preserves_model_generated_reason(monkeypatch):
    engine = _make_engine(monkeypatch)
    model_speech = "我得去咖啡馆准备早餐，也会留意有没有陌生客人。"

    assert engine._departure_speech("Isabella Rodriguez", "Hobbs Cafe", model_speech) == model_speech


def test_round_two_departure_targets_real_object_coordinate(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_round = 2
    engine._gathering_speaker_idx = engine._gathering_queue.index("Klaus Mueller")
    klaus = engine.agents["Klaus Mueller"]
    monkeypatch.setattr(
        engine,
        "_find_object_in_spatial_memory",
        lambda agent, location, obj: (122, 20) if obj == "bookshelf" else None,
    )
    monkeypatch.setattr(
        game_engine,
        "chat_for_agent",
        lambda *args, **kwargs: (
            '{"speech":"我得去学院图书馆查旧报纸，也会留意异常。",'
            '"leaving_excuse":"去图书馆查资料",'
            '"leaving_to":"Oak Hill College",'
            '"leaving_object":"bookshelf"}'
        ),
    )

    engine._trigger_round_two_speak("Klaus Mueller")
    for _ in range(20):
        if engine._gathering_left.get("Klaus Mueller"):
            break
        time.sleep(0.05)

    assert engine._gathering_left["Klaus Mueller"] is True
    assert abs(klaus.target_x - 122) + abs(klaus.target_y - 20) == 1
    assert (klaus.target_x, klaus.target_y) != (122, 20)
    assert engine._gathering_speech_history[-1]["leaving_object"] == "bookshelf"


def test_gathering_json_accepts_explanation_around_object(monkeypatch):
    engine = _make_engine(monkeypatch)

    parsed = engine._parse_gathering_json(
        '我的决定如下：{"speech":"我去学院查资料。","leaving_to":"Oak Hill College",'
        '"leaving_object":"bookshelf"}。请大家小心。',
        "Klaus Mueller",
    )

    assert parsed["leaving_object"] == "bookshelf"


def test_crow_starts_scene_investigation_after_gathering_ends(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_round = 2
    engine._gathering_left = {name: True for name in engine._gathering_queue}

    engine._handle_round_two_plus()

    crow = engine.agents["Crow"]
    assert engine._gathering_active is False
    assert engine.bodies[0].burying is True
    for _ in range(200):
        engine._move_agents()
        if engine.bodies[0].buried:
            break

    for _ in range(200):
        engine._move_agents()
        if crow.current_action:
            break

    assert crow.current_action == "调查案发现场与尸体周边线索"
    assert crow.runtime_state == "acting"


# ---------------------------------------------------------------------------
# Regression: deterministic clockwise order around body site (Crow first)
# ---------------------------------------------------------------------------

def test_gathering_order_is_counterclockwise_around_body(monkeypatch):
    """Crow first, then continue counterclockwise from Crow's nearest following resident."""
    import math as _math

    engine = _make_engine(monkeypatch)
    body_x = game_engine.INITIAL_BODY_SITE["x"]
    body_y = game_engine.INITIAL_BODY_SITE["y"]

    engine._init_gathering()
    queue = engine._gathering_queue

    # Crow must be first
    assert queue[0] == "Crow"

    # Remaining NPCs must continue counterclockwise from Crow, allowing one wrap at pi.
    npc_order = queue[1:]
    crow = engine.agents["Crow"]
    crow_angle = _math.atan2(crow.y - body_y, crow.x - body_x)
    angles = []
    for name in npc_order:
        agent = engine.agents[name]
        angle = _math.atan2(agent.y - body_y, agent.x - body_x)
        angles.append(angle)

    unwrapped = [angle if angle > crow_angle else angle + 2 * _math.pi for angle in angles]
    assert unwrapped == sorted(unwrapped)


def test_gathering_queue_contains_all_alive_agents(monkeypatch):
    """_init_gathering must include every alive agent exactly once."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    queue = engine._gathering_queue

    alive = {n for n, a in engine.agents.items() if a.is_alive}
    assert set(queue) == alive
    assert len(queue) == len(alive)


def test_gathering_order_deterministic_same_seed(monkeypatch):
    """Same random seed produces identical gathering order."""
    engine1 = _make_engine(monkeypatch, seed=42)
    engine2 = _make_engine(monkeypatch, seed=42)
    engine1._init_gathering()
    engine2._init_gathering()
    assert engine1._gathering_queue == engine2._gathering_queue


# ---------------------------------------------------------------------------
# Regression: per-speaker timeout prevents LLM hang
# ---------------------------------------------------------------------------

def test_round_one_speak_returns_fallback_on_llm_timeout(monkeypatch):
    """When chat_for_agent does not return within per_speaker_timeout, fallback fires."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    release = threading.Event()
    called = threading.Event()

    def slow_chat(*args, **kwargs):
        called.set()
        release.wait(timeout=10)  # blocked until released
        return "迟到的大模型发言"

    monkeypatch.setattr(game_engine, "chat_for_agent", slow_chat)
    # Force a very short per-speaker timeout for testing
    engine.gathering_per_speaker_timeout = 1

    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Arthur Burton")
    engine._trigger_round_one_speak("Arthur Burton")
    assert called.wait(timeout=2)

    # Wait enough time for the per-speaker timeout to fire inside _do_speak
    deadline = time.time() + 4
    while time.time() < deadline and engine._gathering_speaker_idx == engine._gathering_queue.index("Arthur Burton"):
        time.sleep(0.05)

    # After timeout, idx should have advanced to the next speaker
    assert engine._gathering_speaker_idx > engine._gathering_queue.index("Arthur Burton")
    assert len(engine._gathering_speech_history) >= 1
    assert engine._gathering_speech_history[-1]["speaker"] == "Arthur Burton"
    # Should be the fallback, not the delayed LLM response
    assert "迟到的大模型发言" not in engine._gathering_speech_history[-1]["speech"]

    release.set()


def test_round_two_speak_returns_fallback_on_llm_timeout(monkeypatch):
    """When round-2 chat_for_agent times out, agent departs with fallback destination."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_round = 2
    release = threading.Event()
    called = threading.Event()

    def slow_chat(*args, **kwargs):
        called.set()
        release.wait(timeout=10)
        return '{"speech":"我去学院。","leaving_to":"Oak Hill College","leaving_excuse":"学习"}'

    monkeypatch.setattr(game_engine, "chat_for_agent", slow_chat)
    engine.gathering_per_speaker_timeout = 1

    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Klaus Mueller")
    engine._trigger_round_two_speak("Klaus Mueller")
    assert called.wait(timeout=2)

    deadline = time.time() + 4
    while time.time() < deadline and not engine._gathering_left.get("Klaus Mueller"):
        time.sleep(0.05)

    assert engine._gathering_left.get("Klaus Mueller") is True
    assert len(engine._gathering_speech_history) >= 1
    assert engine._gathering_speech_history[-1]["speaker"] == "Klaus Mueller"
    assert "迟到" not in engine._gathering_speech_history[-1].get("speech", "")

    release.set()


def test_round_one_success_keeps_full_model_speech_without_hard_truncation(monkeypatch):
    """Successful model speech is constrained by prompt, not truncated by backend code."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    long_speech = (
        "昨晚我一直在店里整理货架和账本，听见外面有人急匆匆经过，但我没有看清是谁。"
        "今天我会先把店门打开，也会留意来买异常物品的人。"
    )

    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: long_speech)

    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Arthur Burton")
    engine._trigger_round_one_speak("Arthur Burton")

    deadline = time.time() + 3
    while time.time() < deadline and not engine._gathering_speech_history:
        time.sleep(0.05)

    assert engine._gathering_speech_history[-1]["speech"] == long_speech
    assert engine.chat_bubbles["Arthur Burton"]["text"] == long_speech


def test_late_llm_response_does_not_advance_turn_twice(monkeypatch):
    """Regression: a delayed LLM response after timeout must not increment idx again."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    release = threading.Event()
    called = threading.Event()

    def slow_chat(*args, **kwargs):
        called.set()
        release.wait(timeout=10)
        return "迟到的发言"

    monkeypatch.setattr(game_engine, "chat_for_agent", slow_chat)
    engine.gathering_per_speaker_timeout = 1

    start_idx = engine._gathering_queue.index("Arthur Burton")
    engine._gathering_busy = True
    engine._gathering_speaker_idx = start_idx
    engine._trigger_round_one_speak("Arthur Burton")
    assert called.wait(timeout=2)

    # Wait for timeout and fallback to fire
    deadline = time.time() + 4
    while time.time() < deadline and engine._gathering_speaker_idx == start_idx:
        time.sleep(0.05)

    idx_after_timeout = engine._gathering_speaker_idx
    assert idx_after_timeout > start_idx

    # Now release the slow LLM call
    release.set()

    # Give the late thread time to finish
    time.sleep(0.5)

    # idx must not have advanced again!
    assert engine._gathering_speaker_idx == idx_after_timeout, (
        f"Late response advanced idx from {idx_after_timeout} to {engine._gathering_speaker_idx}"
    )


# ---------------------------------------------------------------------------
# Regression: Crow stays player-controlled and dismissal happens before departures
# ---------------------------------------------------------------------------

def test_crow_not_asked_to_depart_in_round_two(monkeypatch):
    """Crow is marked left before round 2, so _handle_round_two_plus never picks Crow."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    # Simulate end of round 1
    engine._gathering_round = 2
    engine._gathering_speaker_idx = 0
    engine._gathering_left["Crow"] = True

    engine._handle_round_two_plus()
    # Crow should NOT have been the one triggered
    if engine._gathering_busy:
        # The triggered speaker (if any) must not be Crow
        queue = engine._gathering_queue
        idx = engine._gathering_speaker_idx
        if idx < len(queue):
            assert queue[idx] != "Crow"


def test_crow_dismissal_published_before_first_departure(monkeypatch):
    """When round 1 ends, dismissal is published BEFORE _handle_round_two_plus runs."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    # Simulate: all speakers done in round 1
    engine._gathering_speaker_idx = len(engine._gathering_queue)

    engine._handle_round_one()
    engine._gathering_dismissal_ready_at = 0
    engine._handle_round_one()

    assert engine._gathering_crow_dismissal_done is True
    # dismissal entry must be in speech history
    dismissal_entries = [e for e in engine._gathering_speech_history if e.get("dismissal")]
    assert len(dismissal_entries) == 1
    assert dismissal_entries[0]["speaker"] == "Crow"


# ---------------------------------------------------------------------------
# Regression: round-2 timeout handler populates speech history with full fields
# ---------------------------------------------------------------------------

def test_round_two_timeout_produces_complete_speech_history_entry(monkeypatch):
    """When round-2 speaker times out, speech_history entry must include left/leaving fields."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_round = 2

    # Force timeout by setting a very long speak start time in the past
    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Arthur Burton")
    engine._gathering_speak_start_time = time.time() - engine.gathering_turn_timeout - 1

    engine._handle_gathering()

    entry = engine._gathering_speech_history[-1]
    assert entry["speaker"] == "Arthur Burton"
    assert entry.get("left") is True
    assert "leaving_to" in entry
    assert "leaving_object" in entry
    assert "leaving_excuse" in entry


def test_gathering_per_speaker_timeout_configured(monkeypatch):
    """Engine must expose gathering_per_speaker_timeout for tuning."""
    engine = _make_engine(monkeypatch)
    assert hasattr(engine, "gathering_per_speaker_timeout")
    assert engine.gathering_per_speaker_timeout >= 20


def test_gathering_speech_uses_priority_llm_requests(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    captured = []

    def fake_chat(*args, **kwargs):
        captured.append(kwargs)
        return "昨晚我在店里，今早听到消息很不安。"

    monkeypatch.setattr(game_engine, "chat_for_agent", fake_chat)
    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Arthur Burton")
    engine._trigger_round_one_speak("Arthur Burton")

    deadline = time.time() + 3
    while time.time() < deadline and not captured:
        time.sleep(0.05)

    assert captured
    assert captured[0].get("priority") is True


# ---------------------------------------------------------------------------
# Requirement: Delayed departure movement & sequential bubble timing
# ---------------------------------------------------------------------------


def test_round_two_departure_delay_sets_departure_delay_until(monkeypatch):
    """Round-two departure must set _departure_delay_until so NPC walks later,
    not instantly after speech."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_round = 2
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 3.0)

    monkeypatch.setattr(
        game_engine,
        "chat_for_agent",
        lambda *args, **kwargs: (
            '{"speech":"我去学院查资料。","leaving_excuse":"学习",'
            '"leaving_to":"Oak Hill College","leaving_object":"bookshelf"}'
        ),
    )

    klaus = engine.agents["Klaus Mueller"]
    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Klaus Mueller")
    engine._trigger_round_two_speak("Klaus Mueller")

    for _ in range(20):
        if engine._gathering_left.get("Klaus Mueller"):
            break
        time.sleep(0.05)

    assert engine._gathering_left["Klaus Mueller"] is True
    # Agent should have a future departure delay
    assert getattr(klaus, '_departure_delay_until', 0) > time.time(), (
        "Departure delay must be set to a future timestamp"
    )
    # Speech bubble must be visible
    assert "Klaus Mueller" in engine.chat_bubbles


def test_round_two_departure_delay_prevents_immediate_movement(monkeypatch):
    """NPC must not move during the departure delay window."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine._gathering_round = 2

    agent = engine.agents["Klaus Mueller"]
    agent.x, agent.y = 10, 10
    agent.target_x, agent.target_y = 50, 50
    # Set departure delay to 5 seconds in future
    agent._departure_delay_until = time.time() + 5.0
    agent.runtime_state = "moving"

    original = (agent.x, agent.y)
    engine._move_agents()
    # Agent must not have moved
    assert (agent.x, agent.y) == original, "Agent must not move during departure delay"


def test_round_two_departure_delay_allows_movement_after_expiry(monkeypatch):
    """After departure delay expires, NPC resumes normal movement."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine._gathering_round = 2

    agent = engine.agents["Klaus Mueller"]
    agent.x, agent.y = 10, 10
    agent.target_x, agent.target_y = 12, 10
    # Set departure delay in the past
    agent._departure_delay_until = time.time() - 1.0
    agent.runtime_state = "moving"
    engine.agent_paths["Klaus Mueller"] = [(11, 10), (12, 10)]

    engine._move_agents()
    # Agent should have moved at least one step
    assert (agent.x, agent.y) != (10, 10), "Agent must move after departure delay expires"


def test_gathering_speech_visible_seconds_from_config(monkeypatch):
    """_gathering_speech_visible_seconds reads from config."""
    monkeypatch.setitem(game_engine.CONFIG["game"], "gathering_speech_visible_seconds", 3.5)
    assert game_engine.WerewolfGameEngine._gathering_speech_visible_seconds() == 3.5


def test_crow_intro_line_delay_waits_after_estimated_speech():
    short_delay = game_engine.WerewolfGameEngine._crow_intro_line_delay("大家先安静。")
    long_delay = game_engine.WerewolfGameEngine._crow_intro_line_delay(
        "现在先别急着猜凶手，请按顺序说清昨晚在哪里、见过谁、听见过什么异常。"
    )

    assert short_delay == 2.0
    assert long_delay == 2.0


def test_crow_intro_line_delay_reads_config(monkeypatch):
    monkeypatch.setitem(game_engine.CONFIG["game"], "crow_intro_line_delay_seconds", 0.75)

    assert game_engine.WerewolfGameEngine._crow_intro_line_delay("任何长度") == 0.75


def test_departure_delay_seconds_from_config(monkeypatch):
    """_departure_delay_seconds reads from config."""
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 4.0)
    assert game_engine.WerewolfGameEngine._departure_delay_seconds() == 4.0


def test_departure_delays_default_to_one_second(monkeypatch):
    monkeypatch.delitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", raising=False)
    monkeypatch.delitem(game_engine.CONFIG["game"], "gathering_departure_gap_seconds", raising=False)

    assert game_engine.WerewolfGameEngine._departure_delay_seconds() == 1.0
    assert game_engine.WerewolfGameEngine._gathering_departure_gap_seconds() == 1.0


def test_round_one_speech_strips_neutral_mentions_instead_of_fallback(monkeypatch):
    """Neutral words like 看见/听见/路过 should NOT trigger full fallback.
    Other resident display names are stripped, wound/werewolf terms are stripped,
    but the rest of the speech is preserved."""
    engine = _make_engine(monkeypatch)

    # Neutral mention of another resident with neutral word "看见" → strip name, keep rest
    mentions_other = engine._sanitize_round_one_speech(
        "Isabella Rodriguez",
        "昨晚我关门时看见亚瑟一个人在街上游荡，今天我很不安。",
    )
    assert "亚瑟" not in mentions_other, f"Other name should be stripped, got: {mentions_other}"
    assert "游荡" in mentions_other or "不安" in mentions_other, f"Rest of speech preserved: {mentions_other}"
    assert mentions_other != game_engine.GATHERING_FALLBACKS["Isabella Rodriguez"], (
        "Should NOT full-fallback for neutral observation"
    )

    # Wound analysis with forbidden terms should be stripped but rest kept
    analyzes_wound = engine._sanitize_round_one_speech(
        "Arthur Burton",
        "伤口太整齐了，这看起来很不寻常。昨晚我在店里修工具。",
    )
    assert "伤口" not in analyzes_wound, f"Wound term removed: {analyzes_wound}"
    assert "修工具" in analyzes_wound, f"Legitimate content preserved: {analyzes_wound}"

    # Severe forbidden content with nothing left → fallback
    only_forbidden = engine._sanitize_round_one_speech(
        "Sam Moore",
        "狼人撕咬抓痕野兽伤口",
    )
    assert only_forbidden == game_engine.GATHERING_FALLBACKS["Sam Moore"], (
        "All-forbidden text should fallback"
    )


def test_crow_dismissal_published_before_round_two_departures(monkeypatch):
    """Crow dismissal bubble must be published and readable before any NPC
    starts departing in round two."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_speaker_idx = len(engine._gathering_queue)

    engine._handle_round_one()
    assert engine._gathering_crow_dismissal_done is False
    engine._gathering_dismissal_ready_at = 0
    engine._handle_round_one()

    # Dismissal must be done and in speech history
    assert engine._gathering_crow_dismissal_done is True
    dismissal_entries = [e for e in engine._gathering_speech_history if e.get("dismissal")]
    assert len(dismissal_entries) == 1
    # Dismissal bubble must be visible
    assert engine.chat_bubbles.get("Crow", {}).get("text") == dismissal_entries[0]["speech"]
    # No one has left yet (round 2 not started)
    assert not any(
        engine._gathering_left.get(name) for name in engine._gathering_queue if name != "Crow"
    )


def test_crow_dismissal_waits_after_final_round_one_speaker(monkeypatch):
    """After the last resident speaks, Crow waits briefly before dismissing."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_speaker_idx = len(engine._gathering_queue)

    now = [1000.0]
    monkeypatch.setattr(game_engine.time, "time", lambda: now[0])

    engine._handle_round_one()

    assert engine._gathering_crow_dismissal_done is False
    assert engine._gathering_round == 1
    assert engine._gathering_dismissal_ready_at > now[0]

    now[0] = engine._gathering_dismissal_ready_at + 0.1
    engine._handle_round_one()

    assert engine._gathering_crow_dismissal_done is True
    assert engine._gathering_round == 2


def test_crow_buries_body_after_gathering(monkeypatch):
    """Test that when gathering finishes, Crow buries the body, updating its location, status, and speaking a statement."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()

    assert len(engine.bodies) > 0
    initial_body = engine.bodies[0]
    assert not getattr(initial_body, "buried", False)

    # Simulate all agents leaving
    engine._gathering_round = 2
    engine._gathering_left = {name: True for name in engine._gathering_queue}

    # Call the gathering handling which triggers dismissal/scattering end
    engine._handle_round_two_plus()

    # Verify the body is not removed immediately; it enters a dragging sequence.
    assert initial_body.buried is False
    assert initial_body.burying is True
    assert initial_body.burial_target_x == 12
    assert initial_body.burial_target_y == 46

    # Verify Crow's statement is in the chat bubbles
    assert "Crow" in engine.chat_bubbles
    assert "安葬" in engine.chat_bubbles["Crow"]["text"]

    # Verify the body is still serialized while dragging.
    status = engine.get_status()
    assert "bodies" in status
    assert len(status["bodies"]) == 1
    assert status["bodies"][0]["burying"] is True


# ---------------------------------------------------------------------------
# Regression: timeout/fallback logs appear only on real LLM timeout
# ---------------------------------------------------------------------------

def test_round_one_success_no_fallback_log(monkeypatch):
    """Successful round-1 LLM response must NOT produce timeout or fallback logs."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()

    monkeypatch.setattr(
        game_engine,
        "chat_for_agent",
        lambda *args, **kwargs: "昨晚我在店里修工具，今早听到消息很不安。",
    )

    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Arthur Burton")
    engine._trigger_round_one_speak("Arthur Burton")

    for _ in range(20):
        if engine._gathering_speech_history:
            break
        time.sleep(0.05)

    assert engine._gathering_speech_history
    speech = engine._gathering_speech_history[-1]["speech"]
    assert "修工具" in speech, f"Expected model response, got: {speech}"

    # Zero timeout-related logs
    timeout_msg = [e["message"] for e in engine.game_log if "超时" in e.get("message", "")]
    assert len(timeout_msg) == 0, f"Unexpected timeout logs on success: {timeout_msg}"


def test_round_two_success_no_fallback_log(monkeypatch):
    """Successful round-2 LLM response must NOT produce timeout or fallback logs."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_round = 2

    monkeypatch.setattr(
        game_engine,
        "chat_for_agent",
        lambda *args, **kwargs: (
            '{"speech":"我去学院查资料，也会留意异常。",'
            '"leaving_excuse":"去图书馆查资料",'
            '"leaving_to":"Oak Hill College",'
            '"leaving_object":"bookshelf"}'
        ),
    )

    # Ensure spatial memory lookup succeeds for the target object
    monkeypatch.setattr(
        engine,
        "_find_object_in_spatial_memory",
        lambda agent, location, obj: (122, 20) if obj == "bookshelf" else None,
    )

    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Klaus Mueller")
    engine._trigger_round_two_speak("Klaus Mueller")

    for _ in range(20):
        if engine._gathering_left.get("Klaus Mueller"):
            break
        time.sleep(0.05)

    assert engine._gathering_left.get("Klaus Mueller") is True
    speech = engine._gathering_speech_history[-1]["speech"]
    assert "学院" in speech or "资料" in speech, f"Expected model departure, got: {speech}"

    # Zero timeout-related logs
    timeout_msg = [e["message"] for e in engine.game_log if "超时" in e.get("message", "")]
    assert len(timeout_msg) == 0, f"Unexpected timeout logs on success: {timeout_msg}"


def test_gathering_timeout_logs_exactly_once(monkeypatch):
    """When a turn truly times out, exactly one [聚集超时] log must be emitted."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_round = 2

    # Force timeout
    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Arthur Burton")
    engine._gathering_speak_start_time = time.time() - engine.gathering_turn_timeout - 1

    engine._handle_gathering()

    timeout_logs = [e["message"] for e in engine.game_log if "[聚集超时]" in e.get("message", "")]
    assert len(timeout_logs) == 1, (
        f"Expected exactly 1 timeout log, got {len(timeout_logs)}: {timeout_logs}"
    )


def test_round_one_timeout_logs_timeout_not_fallback(monkeypatch):
    """When round-1 LLM call truly times out, log says '超时保底' not '聚集超时'."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    release = threading.Event()
    called = threading.Event()

    def never_returns(*args, **kwargs):
        called.set()
        release.wait(timeout=10)
        return "永远不会被使用的发言"

    monkeypatch.setattr(game_engine, "chat_for_agent", never_returns)
    engine.gathering_per_speaker_timeout = 1  # force quick per-speaker timeout

    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Arthur Burton")
    engine._trigger_round_one_speak("Arthur Burton")
    assert called.wait(timeout=2)

    # Wait for the per-speaker timeout to fire inside _do_speak
    deadline = time.time() + 4
    while time.time() < deadline and engine._gathering_speaker_idx == engine._gathering_queue.index("Arthur Burton"):
        time.sleep(0.05)

    # Should have advanced beyond Arthur
    assert engine._gathering_speaker_idx > engine._gathering_queue.index("Arthur Burton")

    # Should have a 超时保底 log (per-speaker timeout) but NOT a 聚集超时 log (turn timeout)
    has_per_speaker_timeout = any(
        "超时保底" in e["message"] for e in engine.game_log
    )
    has_turn_timeout = any(
        "[聚集超时]" in e["message"] for e in engine.game_log
    )
    assert has_per_speaker_timeout, "Expected per-speaker timeout log"
    assert not has_turn_timeout, "Should NOT have turn-level timeout log"

    release.set()


# ---------------------------------------------------------------------------
# Requirement: gathering_departure_gap_seconds default is 1.0
# ---------------------------------------------------------------------------

def test_gathering_departure_gap_default_is_one_point_zero():
    """The default gathering_departure_gap_seconds must be 1.0."""
    assert game_engine.WerewolfGameEngine._gathering_departure_gap_seconds() == 1.0


def test_gathering_departure_gap_reads_from_config(monkeypatch):
    """_gathering_departure_gap_seconds reads from config override."""
    monkeypatch.setitem(game_engine.CONFIG["game"], "gathering_departure_gap_seconds", 2.5)
    assert game_engine.WerewolfGameEngine._gathering_departure_gap_seconds() == 2.5


def test_gathering_departure_gap_used_in_round_two_transition(monkeypatch):
    """When round one ends, _gathering_next_tick is set using departure_gap."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_speaker_idx = len(engine._gathering_queue)

    monkeypatch.setattr(game_engine.time, "time", lambda: 1000.0)
    engine._handle_round_one()
    engine._gathering_dismissal_ready_at = 0
    engine._handle_round_one()

    assert engine._gathering_round == 2
    # _gathering_next_tick should be 1000 + departure_gap (1.0 by default)
    assert engine._gathering_next_tick == 1001.0, (
        f"Expected 1001.0, got {engine._gathering_next_tick}"
    )


def test_gathering_departure_gap_applied_after_round_two_speech(monkeypatch):
    """After round-two speech completes, next_tick uses departure_gap."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_round = 2

    monkeypatch.setattr(
        game_engine,
        "chat_for_agent",
        lambda *args, **kwargs: (
            '{"speech":"我去学院。","leaving_excuse":"学习",'
            '"leaving_to":"Oak Hill College","leaving_object":"bookshelf"}'
        ),
    )
    monkeypatch.setattr(
        engine,
        "_find_object_in_spatial_memory",
        lambda agent, location, obj: (122, 20),
    )

    mock_now = [1500.0]
    monkeypatch.setattr(game_engine.time, "time", lambda: mock_now[0])

    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Klaus Mueller")
    engine._trigger_round_two_speak("Klaus Mueller")

    for _ in range(20):
        if engine._gathering_left.get("Klaus Mueller"):
            break
        time.sleep(0.05)

    assert engine._gathering_left["Klaus Mueller"] is True
    # After speech completes, next_tick should be set with departure_gap
    assert engine._gathering_next_tick >= 1501.0


def test_crow_case_intro_case_insensitivity_and_round_two_bypass(monkeypatch):
    """Ensure detective/Crow name matching is case-insensitive for both R1 and R2."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()

    # 1. R1 case-insensitive check
    # Set detective_name to lowercase 'crow'
    engine.detective_name = "crow"
    called = threading.Event()
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *a, **k: called.set() or "Not expected")

    # Trigger speak for "Crow" (with capital C)
    engine._trigger_round_one_speak("Crow")
    time.sleep(0.1)

    assert not called.is_set(), "chat_for_agent should not be called for Crow even with mismatched casing"
    assert engine._gathering_speech_history[0]["speaker"] == "Crow"
    assert engine._gathering_speech_history[0].get("intro") is True

    # 2. R2 speak bypass
    engine._gathering_busy = True
    engine._gathering_speaker_idx = 0
    engine._trigger_round_two_speak("Crow")

    assert engine._gathering_left["Crow"] is True
    assert engine._gathering_busy is False


# ---------------------------------------------------------------------------
# New tests — speech length, Chinese logs, sanitize, fallback, Crow status
# ---------------------------------------------------------------------------

def test_limit_gathering_speech_allows_complete_sentence_up_to_75():
    """Text is preserved no matter the length; no truncation."""
    speech_68 = "昨晚我在家整理资料，没出门。今早听到消息后心里很不安，今天会去店里留意可疑的人。"
    assert len(speech_68) <= 75
    result = game_engine.WerewolfGameEngine._limit_gathering_speech(speech_68)
    assert result == speech_68

    long_speech = "昨晚我在家休息。" + "今天准备去咖啡馆看看情况。" * 6
    result = game_engine.WerewolfGameEngine._limit_gathering_speech(long_speech)
    assert result == long_speech, f"Full speech should be preserved: {len(result)} vs {len(long_speech)} chars"


def test_sanitize_round_one_speech_preserves_neutral_observation_words():
    """Neutral words like 看见/听见/路过 should NOT cause fallback."""
    result = game_engine.WerewolfGameEngine._sanitize_round_one_speech(
        "Arthur Burton",
        "昨晚我在店里修工具，路过公园时听见一些动静，今天我会留意。"
    )
    assert "修工具" in result, f"Legitimate content kept: {result}"
    assert "路过" in result or "听见" in result, f"Neutral words kept: {result}"
    assert result != game_engine.GATHERING_FALLBACKS["Arthur Burton"], (
        "Should not fallback for neutral words"
    )


def test_departure_speech_uses_chinese_location_not_english(monkeypatch):
    """_departure_speech must output Chinese location name, not English internal."""
    engine = _make_engine(monkeypatch)

    speech = engine._departure_speech("Klaus Mueller", "Oak Hill College", "我得去学院上课了。")
    assert "橡树山学院" in speech, f"Should use Chinese name, got: {speech}"
    assert "Oak Hill College" not in speech, f"Should NOT leak English, got: {speech}"

    default_speech = engine._departure_speech("Isabella Rodriguez", "Hobbs Cafe")
    assert "霍布斯咖啡馆" in default_speech
    assert "Hobbs Cafe" not in default_speech


def test_recent_log_excludes_llm_raw_entries(monkeypatch):
    """recent_log in get_status must NOT include llm_raw type entries."""
    engine = _make_engine(monkeypatch)

    engine._log("[模型原始输出] Crow: {json}", "llm_raw")
    engine._log("可读的中文行动日志", "action")
    engine._log("超时保底：使用备用发言", "system")

    status = engine.get_status()
    assert isinstance(status["recent_log"], list)
    messages = [e["message"] for e in status["recent_log"]]
    assert "可读的中文行动日志" in messages
    assert "超时保底：使用备用发言" in messages
    assert not any("模型原始输出" in m for m in messages), (
        f"llm_raw entries should be filtered: {messages}"
    )


def test_normalize_destination_falls_back_to_character_default(monkeypatch):
    """Unknown locations fallback to character-specific default, not just 'home'."""
    engine = _make_engine(monkeypatch)

    assert engine._normalize_destination("Klaus Mueller", "gibberish_place") == "Oak Hill College"
    assert engine._normalize_destination("Mei Lin", "unknown_xyz") == "Oak Hill College"
    assert engine._normalize_destination("Arthur Burton", "??bogus") == "Harvey Oak Supply Store"


def test_departure_default_object_per_character():
    """Each character has a unique default departure object at their location."""
    klaus_obj = game_engine.WerewolfGameEngine._departure_object(
        "Klaus Mueller", "Oak Hill College"
    )
    mei_obj = game_engine.WerewolfGameEngine._departure_object(
        "Mei Lin", "Oak Hill College"
    )
    assert klaus_obj == "classroom student seating"
    assert mei_obj == "bookshelf"
    assert klaus_obj != mei_obj, "Klaus and Mei Lin should not crowd same object"


def test_agent_init_files_clears_runtime_state():
    """New game must clear all runtime memory, dialogue/action history, agent state."""
    from agent import Agent
    import os as _os

    name = "test_cleanup_agent"
    folder = _os.path.join("personas", name)
    _os.makedirs(folder, exist_ok=True)

    try:
        agent = Agent(name=name, role="villager")
        agent.current_action = "old action"
        agent.current_action_type = "move_to"
        agent.current_thought = "old thought"
        agent.current_thought_time = 999
        agent.dialogue_history = [{"day": 1, "partner": "Someone", "incoming": "hi", "outgoing": "hello"}]
        agent.action_history = [{"action_type": "stay", "location": "park", "action": "观察"}]
        agent.runtime_state = "moving"
        agent.memory_index = [{"day": 1, "event": "old", "importance": 5}]
        agent.chat_count = {"Crow": 1}
        agent.in_conversation_with = "Klaus Mueller"
        agent._pending_action = {"action_type": "move_to", "target_location": "home"}
        agent._last_decision = {"action_type": "stay", "raw_response": "{}"}
        agent._last_raw_response = '{"old":"json"}'

        agent.init_files()

        assert agent.current_action == ""
        assert agent.current_action_type == ""
        assert agent.current_thought == ""
        assert agent.current_thought_time == 0
        assert agent.dialogue_history == []
        assert agent.action_history == []
        assert agent.runtime_state == "idle"
        assert agent.memory_index == []
        assert agent.chat_count == {}
        assert agent.in_conversation_with is None
        assert agent._pending_action == {}
        assert agent._last_decision == {}
        assert agent._last_raw_response == ""
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def test_stay_action_logs_in_chinese(monkeypatch):
    """When agent does a stay action, the log must be in readable Chinese."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    agent = engine.agents["Arthur Burton"]
    agent.runtime_state = "acting"
    agent.current_action_type = "stay"
    agent.current_action = "在五金店整理工具"
    agent.current_location = "Harvey Oak Supply Store"
    agent._arrived_at_time = time.time() - 20
    # Set a pending action so _complete_agent_action doesn't immediately return
    agent._pending_action = {
        "action_type": "stay",
        "target_location": "Harvey Oak Supply Store",
        "target_object": "",
        "target_person": "",
        "action": "在五金店整理工具",
        "expected_result": "",
    }

    before = len(engine.game_log)
    engine._complete_agent_action("Arthur Burton", agent)
    after = len(engine.game_log)
    assert after > before, "Action completion should add log entries"


def test_action_type_labels_zh_coverage():
    """All known action types have Chinese labels."""
    from game_engine import ACTION_TYPE_LABELS_ZH
    known_types = {"move_to", "stay", "observe", "inspect", "work", "rest",
                   "investigate", "socialize", "talk", "hide"}
    for at in known_types:
        assert at in ACTION_TYPE_LABELS_ZH, f"Missing Chinese label for {at}"
        assert ACTION_TYPE_LABELS_ZH[at], f"Empty Chinese label for {at}"


# ---------------------------------------------------------------------------
# Requirement: fallback logging for timeout / empty model response
# ---------------------------------------------------------------------------

def test_round_one_timeout_logs_unified_fallback_message(monkeypatch):
    """When round-1 per-speaker timeout fires, the unified fallback log must appear."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    release = threading.Event()
    called = threading.Event()

    def never_returns(*args, **kwargs):
        called.set()
        release.wait(timeout=10)
        return "永远不会被使用的发言"

    monkeypatch.setattr(game_engine, "chat_for_agent", never_returns)
    engine.gathering_per_speaker_timeout = 1

    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Arthur Burton")
    engine._trigger_round_one_speak("Arthur Burton")
    assert called.wait(timeout=2)

    deadline = time.time() + 4
    while time.time() < deadline and engine._gathering_speaker_idx == engine._gathering_queue.index("Arthur Burton"):
        time.sleep(0.05)

    assert engine._gathering_speaker_idx > engine._gathering_queue.index("Arthur Burton")

    # Unified fallback log must be present
    fallback_logs = [e["message"] for e in engine.game_log if "模型超时/空结果，使用保底发言" in e.get("message", "")]
    assert len(fallback_logs) >= 1, (
        f"Expected unified fallback log, got: {[e['message'] for e in engine.game_log]}"
    )

    release.set()


def test_round_one_empty_result_logs_unified_fallback_message(monkeypatch):
    """When round-1 model returns empty, the unified fallback log must appear."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()

    monkeypatch.setattr(
        game_engine,
        "chat_for_agent",
        lambda *args, **kwargs: "",
    )

    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Arthur Burton")
    engine._trigger_round_one_speak("Arthur Burton")

    for _ in range(20):
        if engine._gathering_speech_history:
            break
        time.sleep(0.05)

    assert engine._gathering_speech_history
    fallback_logs = [e["message"] for e in engine.game_log if "模型超时/空结果，使用保底发言" in e.get("message", "")]
    assert len(fallback_logs) >= 1, (
        f"Expected unified fallback log for empty result, got: {[e['message'] for e in engine.game_log]}"
    )


def test_round_two_timeout_logs_unified_fallback_message(monkeypatch):
    """When round-2 per-speaker timeout fires, the unified fallback log must appear."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    engine._gathering_round = 2
    release = threading.Event()
    called = threading.Event()

    def never_returns(*args, **kwargs):
        called.set()
        release.wait(timeout=10)
        return '{"speech":"test"}'

    monkeypatch.setattr(game_engine, "chat_for_agent", never_returns)
    engine.gathering_per_speaker_timeout = 1

    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Klaus Mueller")
    engine._trigger_round_two_speak("Klaus Mueller")
    assert called.wait(timeout=2)

    deadline = time.time() + 4
    while time.time() < deadline and not engine._gathering_left.get("Klaus Mueller"):
        time.sleep(0.05)

    assert engine._gathering_left.get("Klaus Mueller") is True
    fallback_logs = [e["message"] for e in engine.game_log if "模型超时/空结果，使用保底发言" in e.get("message", "")]
    assert len(fallback_logs) >= 1

    release.set()


def test_detective_chat_empty_response_logs_unified_fallback(monkeypatch):
    """When detective chat LLM returns empty, the unified fallback log must appear."""
    engine = _make_engine(monkeypatch)
    engine._daily_interviewed = {
        name for name, agent in engine.agents.items()
        if name != engine.detective_name and agent.is_alive
    }

    monkeypatch.setattr(
        engine,
        "_generate_agent_response",
        lambda *args, **kwargs: "",
    )

    result = engine.detective_chat("Arthur Burton", "你好", is_deep_dive=False)

    # Should have fallback log
    fallback_logs = [e["message"] for e in engine.game_log if "模型超时/空结果，使用保底发言" in e.get("message", "")]
    assert len(fallback_logs) >= 1, (
        f"Expected unified fallback log for detective chat empty response, got: {[e['message'] for e in engine.game_log]}"
    )
    assert "还没有想清楚" in result.get("response", "")


def test_unified_fallback_log_not_present_on_success(monkeypatch):
    """Unified fallback log must NOT appear when LLM returns valid content."""
    engine = _make_engine(monkeypatch)
    engine._init_gathering()

    monkeypatch.setattr(
        game_engine,
        "chat_for_agent",
        lambda *args, **kwargs: "昨晚我在店里修工具，今早听到消息很不安。",
    )

    engine._gathering_busy = True
    engine._gathering_speaker_idx = engine._gathering_queue.index("Arthur Burton")
    engine._trigger_round_one_speak("Arthur Burton")

    for _ in range(20):
        if engine._gathering_speech_history:
            break
        time.sleep(0.05)

    assert engine._gathering_speech_history
    fallback_logs = [e["message"] for e in engine.game_log if "模型超时/空结果，使用保底发言" in e.get("message", "")]
    assert len(fallback_logs) == 0, (
        f"Unified fallback log should NOT appear on success: {fallback_logs}"
    )

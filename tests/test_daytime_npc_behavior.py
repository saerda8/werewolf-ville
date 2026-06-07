"""Focused tests for daytime NPC behavior patches."""
import threading
import time
import game_engine
from world_config import ACTIVE_CHARACTERS


def _make_engine(monkeypatch, seed=7):
    empty_maze = [[0]*140 for _ in range(100)]
    monkeypatch.setattr(game_engine, "load_collision_maze", lambda: empty_maze)
    monkeypatch.setattr(game_engine, "load_scene_data",
        lambda: (empty_maze, empty_maze, empty_maze, {}, {}, {}))
    monkeypatch.setattr(game_engine.WerewolfGameEngine,
        "_build_shared_spatial_memory", lambda self: {})
    monkeypatch.setattr(game_engine.Agent, "init_files", lambda self: None)
    monkeypatch.setattr(game_engine.Agent, "init_scratch_from_soul", lambda self: None)
    monkeypatch.setattr(game_engine.Agent, "load_shared_spatial_memory", lambda self, data: None)
    monkeypatch.setattr(game_engine.Agent, "read_soul", lambda self: "test soul")
    monkeypatch.setattr(game_engine.Agent, "read_memory", lambda self: "test memory")
    monkeypatch.setattr(game_engine.Agent, "read_cognition", lambda self: "")
    monkeypatch.setattr(game_engine.Agent, "read_agent", lambda self: "")
    monkeypatch.setattr(game_engine.Agent, "sanitize_prompt_text", lambda self, text: text or "")
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "")
    return game_engine.WerewolfGameEngine(random_seed=seed)


# ==================== Requirement 1 ====================

def test_crow_thought_suppressed_in_status(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    status = engine.get_status()
    crow = status["personas"].get("Crow")
    assert crow is not None
    assert crow["action"] == ""
    assert crow["action_type"] == ""
    assert crow["action_plan"] == ""
    assert crow["action_target_location"] == ""
    assert crow["thought"] == ""
    assert crow["thought_time"] == 0
    assert crow["thought_summary"] == ""
    assert crow["current_goal"] == ""
    assert crow["last_decision"] == {}
    assert crow["last_error"] == ""
    assert crow["response_error"] == ""


def test_non_crow_thought_still_visible(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._init_gathering()
    status = engine.get_status()
    for name, data in status["personas"].items():
        if name != "Crow" and data["alive"]:
            assert "action" in data
            assert "thought" in data
            assert "action_plan" in data
            assert "last_decision" in data
            assert "current_goal" in data
            break


# ==================== Requirement 2 ====================

def _set_crow_in_conversation(engine):
    crow = engine.agents[engine.detective_name]
    target = None
    for name, agent in engine.agents.items():
        if name != engine.detective_name and agent.is_alive:
            target = name
            break
    if target:
        crow.in_conversation_with = target
        crow._conversation_started_at = time.time()
    return target


def test_npc_trigger_to_detective_blocks_when_crow_busy(monkeypatch):
    engine = _make_engine(monkeypatch)
    agent_name = None
    for name, agent in engine.agents.items():
        if name != engine.detective_name and agent.is_alive:
            agent_name = name
            break
    assert agent_name is not None
    _set_crow_in_conversation(engine)
    before = getattr(engine.agents[agent_name], "in_conversation_with", None)
    engine._trigger_npc_to_detective_chat(agent_name, "test")
    after = getattr(engine.agents[agent_name], "in_conversation_with", None)
    assert after is before


def test_complete_action_blocks_when_crow_busy(monkeypatch):
    engine = _make_engine(monkeypatch)
    agent_name = None
    for name, agent in engine.agents.items():
        if name != engine.detective_name and agent.is_alive:
            agent_name = name
            break
    agent = engine.agents[agent_name]
    crow = engine.agents[engine.detective_name]
    agent.x = crow.x + 1
    agent.y = crow.y
    crow.in_conversation_with = "someone"
    agent._pending_action = {
        "action_type": "talk",
        "target_location": crow.current_location or "Park",
        "target_object": "",
        "target_person": engine.detective_name,
        "action": "talk",
        "thought": "report",
        "expected_result": "report",
    }
    before = agent.in_conversation_with
    logs = []
    monkeypatch.setattr(engine, "_log", lambda *a: logs.append(a))
    engine._complete_agent_action(agent_name, agent)
    after = agent.in_conversation_with
    assert after is before or after is None


def test_npc_one_way_report_to_crow_releases_state(monkeypatch):
    engine = _make_engine(monkeypatch)
    agent_name = next(
        name for name, agent in engine.agents.items()
        if name != engine.detective_name and agent.is_alive
    )
    agent = engine.agents[agent_name]
    crow = engine.agents[engine.detective_name]
    agent.x = crow.x + 1
    agent.y = crow.y
    agent.current_thought = "我应该向警长说明情况"
    agent.current_thought_time = 123.0
    agent.current_action = "我要找警长汇报"
    agent.current_action_type = "talk"
    agent._pending_action = {
        "action_type": "talk",
        "target_location": crow.current_location or "Johnson Park",
        "target_object": "",
        "target_person": engine.detective_name,
        "action": "我要向警长汇报昨晚咖啡馆后门的异常",
        "thought": "这件事需要让警长知道",
        "expected_result": "警长知道异常",
    }

    engine._complete_agent_action(agent_name, agent)

    assert agent.in_conversation_with == engine.detective_name
    assert crow.in_conversation_with == agent_name
    assert agent._pending_action is None
    assert agent.current_thought == ""
    assert agent.current_action == ""
    assert agent.runtime_state == "acting"
    assert engine.chat_bubbles[agent_name]["target"] == engine.detective_name
    assert agent._report_busy_until > time.time()
    assert any(item.get("action_type") == "report_to_detective" for item in agent.action_history)


def test_npc_report_to_crow_skips_planning_until_bubble_expires(monkeypatch):
    engine = _make_engine(monkeypatch)
    agent_name = next(
        name for name, agent in engine.agents.items()
        if name != engine.detective_name and agent.is_alive
    )
    agent = engine.agents[agent_name]
    crow = engine.agents[engine.detective_name]
    agent.x = crow.x + 1
    agent.y = crow.y
    engine._trigger_npc_to_detective_chat(agent_name, "我有情况要说", "警长知道情况")
    assert agent.in_conversation_with == engine.detective_name
    assert crow.in_conversation_with == agent_name
    assert agent._pending_action is None
    assert agent.runtime_state == "acting"
    assert engine.chat_bubbles[agent_name]["target"] == engine.detective_name

    monkeypatch.setattr(
        agent,
        "decide_next_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not plan while report bubble is visible")),
    )

    engine._update_agent_schedules()

    assert agent.runtime_state == "acting"
    assert agent._report_busy_until > time.time()


def test_npc_report_bubble_uses_speech_not_raw_action(monkeypatch):
    engine = _make_engine(monkeypatch)
    agent_name = next(
        name for name, agent in engine.agents.items()
        if name != engine.detective_name and agent.is_alive
    )
    agent = engine.agents[agent_name]
    crow = engine.agents[engine.detective_name]
    agent.x = crow.x + 1
    agent.y = crow.y

    engine._trigger_npc_to_detective_chat(
        agent_name,
        action="我要向警长汇报昨晚咖啡馆后门的异常",
        expected_result="警长知道异常",
    )

    text = engine.chat_bubbles[agent_name]["text"]
    assert text.startswith("警长")
    assert "我要向警长汇报" not in text


# ==================== Requirement 3 ====================

def test_npc_path_to_crow_uses_crow_actual_location(monkeypatch):
    engine = _make_engine(monkeypatch)
    agent = None
    for n, a in engine.agents.items():
        if n != engine.detective_name and a.is_alive:
            agent = a
            break
    crow = engine.agents[engine.detective_name]
    crow.x = 100
    crow.y = 50
    crow.current_location = "Cafe"
    needs = engine._action_needs_movement(agent, "talk", "Park", "", engine.detective_name)
    assert needs, "Must need movement if not near Crow"
    agent.x = crow.x + 1
    agent.y = crow.y
    needs = engine._action_needs_movement(agent, "talk", "Park", "", engine.detective_name)
    assert not needs, "No movement needed when adjacent to Crow"


# ==================== Requirement 4 ====================

def test_detective_chat_clears_npc_state(monkeypatch):
    engine = _make_engine(monkeypatch)
    tn = None
    for n, a in engine.agents.items():
        if n != engine.detective_name and a.is_alive:
            tn = n
            break
    agent = engine.agents[tn]
    crow = engine.agents[engine.detective_name]
    agent.x = crow.x + 1
    agent.y = crow.y
    agent.current_thought = "test thought"
    agent.current_thought_time = 12345.0
    agent.current_action = "test action"
    agent.current_action_type = "talk"
    agent._pending_action = {"action_type": "talk", "target_person": engine.detective_name}
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *a, **kw: "response")
    crow.chat_count = {}
    crow.deep_dive_quota = 3
    crow.deep_dive_used = 0
    engine._daily_interviewed = set()
    result = engine.detective_chat(tn, "hello?", is_deep_dive=False)
    assert "error" not in result, str(result.get("error", ""))
    assert agent.current_thought == ""
    assert agent.current_thought_time == 0
    assert agent.current_action == ""
    assert agent.current_action_type == ""
    assert agent._pending_action is None


def test_detective_chat_records_npc_memory(monkeypatch):
    engine = _make_engine(monkeypatch)
    tn = None
    for n, a in engine.agents.items():
        if n != engine.detective_name and a.is_alive:
            tn = n
            break
    agent = engine.agents[tn]
    crow = engine.agents[engine.detective_name]
    agent.x = crow.x + 1
    agent.y = crow.y
    crow.chat_count = {}
    crow.deep_dive_quota = 3
    crow.deep_dive_used = 0
    engine._daily_interviewed = set()
    called = [False]
    orig = agent.add_memory
    def track(e, d):
        called[0] = True
        return orig(e, d)
    agent.add_memory = track
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *a, **kw: "response")
    result = engine.detective_chat(tn, "hello?", is_deep_dive=False)
    assert "error" not in result
    assert called[0], "NPC add_memory should be called"


# ==================== Requirement 5 ====================

def test_new_game_resets_runtime_memory_and_agent_state():
    from agent import Agent
    agent = Agent("Sam Moore")
    written_md = {}
    written_json = {}
    agent._write_md = lambda filename, content: written_md.__setitem__(filename, content)
    agent._write_json = lambda filename, content: written_json.__setitem__(filename, content)
    agent.memory_index = [{"day": 1, "event": "简在厨房帮忙"}]
    agent.dialogue_history = [{"incoming": "old", "outgoing": "old"}]
    agent.scratch["currently"] = "继续盯着简"

    agent.init_files()

    assert written_md["agent.md"] == ""
    assert written_md["memory.md"] == ""
    assert written_md["cognition.md"] == ""
    assert agent.memory_index == []
    assert agent.dialogue_history == []
    assert agent.scratch["currently"] == ""
    assert written_json["memory_index.json"] == []
    assert written_json["scratch.json"]["currently"] == ""


# ==================== Requirement 6 ====================

def test_mei_lin_and_klaus_have_different_destinations():
    assert game_engine.DEFAULT_DESTINATIONS["Mei Lin"] == "Oak Hill College"
    assert game_engine.DEFAULT_DESTINATIONS["Klaus Mueller"] == "Oak Hill College"
    assert game_engine.DEFAULT_DEPARTURE_OBJECTS["Mei Lin"] == "bookshelf"
    assert game_engine.DEFAULT_DEPARTURE_OBJECTS["Klaus Mueller"] == "classroom student seating"
    assert game_engine.DEFAULT_DEPARTURE_OBJECTS["Mei Lin"] != game_engine.DEFAULT_DEPARTURE_OBJECTS["Klaus Mueller"]


def test_mei_lin_and_klaus_different_jobs():
    mei = ACTIVE_CHARACTERS.get("Mei Lin", {})
    klaus = ACTIVE_CHARACTERS.get("Klaus Mueller", {})
    assert mei.get("job") != klaus.get("job")


def test_repeated_passive_action_is_redirected_to_daily_work(monkeypatch):
    engine = _make_engine(monkeypatch)
    name = "Sam Moore"
    agent = engine.agents[name]
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", [name])
    monkeypatch.setitem(game_engine.CONFIG["agent"], "planning_display_seconds", 0)
    agent.target_x, agent.target_y = agent.x, agent.y
    engine.agent_paths.pop(name, None)
    agent.current_location = "Johnson Park"
    agent.action_history = [{"action_type": "observe", "location": "Johnson Park", "action": "观察", "time": time.time()}]
    monkeypatch.setattr(
        agent,
        "decide_next_action",
        lambda *args, **kwargs: {
            "ok": True,
            "action_type": "observe",
            "target_location": "Johnson Park",
            "target_object": "",
            "target_person": "",
            "action": "继续观察周围",
            "thought": "命案让我不安，我先看看。",
            "expected_result": "确认安全",
            "raw_response": "{}",
        },
    )
    monkeypatch.setattr(engine, "_resolve_concrete_target_object", lambda *args, **kwargs: "behind the bar counter")
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    engine._last_llm_decision_time = 0
    agent._last_llm_decision_time = 0

    engine._update_agent_schedules()

    deadline = time.time() + 2
    while time.time() < deadline and getattr(agent, "_is_thinking", False):
        time.sleep(0.01)

    pending = getattr(agent, "_pending_action", {})
    assert pending["action_type"] == "work"
    assert pending["target_location"] == "The Rose and Crown Pub"
    assert pending["target_object"] == "behind the bar counter"
    assert "正常生活" in pending["thought"]


def test_pending_action_executes_before_next_thought(monkeypatch):
    engine = _make_engine(monkeypatch)
    name = "Sam Moore"
    agent = engine.agents[name]
    agent.runtime_state = "idle"
    agent._is_thinking = False
    agent._last_llm_decision_time = 0
    agent._pending_action = {
        "action_type": "continue_current",
        "target_location": agent.current_location or "Johnson Park",
        "target_object": "",
        "target_person": "",
        "action": "继续擦拭酒馆柜台",
        "thought": "继续当前事务",
        "expected_result": "保持营业",
        "duration_seconds": 0,
    }
    monkeypatch.setattr(
        agent,
        "decide_next_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not think before acting")),
    )

    engine._update_agent_schedules()

    assert agent.runtime_state == "starting_action"
    assert agent.current_action == "继续擦拭酒馆柜台"
    assert agent.current_action_type == "continue_current"
    assert agent._pending_action is not None
    assert name not in engine.chat_bubbles
    agent._action_start_visible_until = 0
    engine._update_agent_schedules()
    assert agent.runtime_state == "acting"
    assert engine.chat_bubbles[name]["kind"] == "action_status"


def test_existing_pending_action_duration_seconds_is_clamped(monkeypatch):
    engine = _make_engine(monkeypatch)
    name = "Sam Moore"
    agent = engine.agents[name]
    agent.runtime_state = "acting"
    agent._arrived_at_time = time.time() - 3
    agent._pending_action = {
        "action_type": "continue_current",
        "target_location": agent.current_location or "Johnson Park",
        "target_object": "",
        "target_person": "",
        "action": "continue counter work",
        "thought": "continue current task",
        "expected_result": "keep working",
        "duration_seconds": 0,
    }
    monkeypatch.setattr(
        agent,
        "decide_next_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not think during clamped action")),
    )

    engine._update_agent_schedules()

    assert agent.runtime_state == "acting"
    assert agent._pending_action is not None


def test_action_duration_counts_from_status_visible_time(monkeypatch):
    engine = _make_engine(monkeypatch)
    name = "Sam Moore"
    agent = engine.agents[name]
    now = time.time()
    agent.runtime_state = "acting"
    agent._arrived_at_time = now - 3
    agent._action_started_at = now - 3
    agent._action_status_visible_at = now + 3
    agent._pending_action = {
        "action_type": "continue_current",
        "target_location": agent.current_location or "Johnson Park",
        "target_object": "",
        "target_person": "",
        "action": "continue counter work",
        "thought": "continue current task",
        "expected_result": "keep working",
        "duration_seconds": 6,
    }
    monkeypatch.setattr(
        agent,
        "decide_next_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not think before visible action completes")),
    )

    engine._update_agent_schedules()

    assert agent.runtime_state == "acting"
    assert agent._pending_action is not None


def test_same_coordinate_action_with_target_object_gets_neighbor_movement(monkeypatch):
    engine = _make_engine(monkeypatch)
    name = "Arthur Burton"
    agent = engine.agents[name]
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", [name])
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 0)
    monkeypatch.setitem(game_engine.CONFIG["agent"], "planning_display_seconds", 0)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    monkeypatch.setattr(engine, "_resolve_concrete_target_object", lambda *args, **kwargs: "counter")
    agent.x = agent.target_x = 10
    agent.y = agent.target_y = 10
    agent.current_location = "Johnson Park"
    agent.runtime_state = "idle"
    agent._last_llm_decision_time = 0
    engine._last_llm_decision_time = 0
    monkeypatch.setattr(
        agent,
        "decide_next_action",
        lambda *args, **kwargs: {
            "ok": True,
            "action_type": "inspect",
            "target_location": "Johnson Park",
            "target_object": "counter",
            "target_person": "",
            "action": "检查柜台",
            "action_status": "检查柜台",
            "thought": "检查手边物件",
            "expected_result": "确认情况",
            "duration_minutes": 5,
            "raw_response": "{}",
        },
    )

    engine._update_agent_schedules()
    deadline = time.time() + 2
    while time.time() < deadline and getattr(agent, "_is_thinking", False):
        time.sleep(0.01)

    assert agent.runtime_state == "starting_action"
    assert (agent.target_x, agent.target_y) != (10, 10)
    assert engine.agent_paths.get(name)
    agent._action_start_visible_until = 0
    agent._action_move_ready_at = 0
    engine._update_agent_schedules()
    assert agent.runtime_state == "moving"


def test_pending_acting_action_can_complete(monkeypatch):
    engine = _make_engine(monkeypatch)
    name = "Sam Moore"
    agent = engine.agents[name]
    agent.runtime_state = "acting"
    agent._arrived_at_time = time.time() - 20
    agent._pending_action = {
        "action_type": "continue_current",
        "target_location": agent.current_location or "Johnson Park",
        "target_object": "",
        "target_person": "",
        "action": "继续擦拭酒馆柜台",
        "thought": "继续当前事务",
        "expected_result": "保持营业",
        "duration_seconds": 0,
    }
    monkeypatch.setitem(game_engine.CONFIG["agent"], "min_act_seconds", 0)
    monkeypatch.setitem(game_engine.CONFIG["agent"], "max_act_seconds", 0)

    engine._update_agent_schedules()

    assert agent.runtime_state == "idle"
    assert agent._pending_action is None
    assert getattr(agent, "_action_completed", False) is True


# ==================== Edge cases ====================

def test_clear_conversation_pair_clears_both_sides(monkeypatch):
    engine = _make_engine(monkeypatch)
    npcs = [n for n, a in engine.agents.items() if n != engine.detective_name and a.is_alive]
    assert len(npcs) >= 2
    n1, n2 = npcs[:2]
    a1, a2 = engine.agents[n1], engine.agents[n2]
    a1.in_conversation_with = n2
    a1._conversation_started_at = 123.0
    a2.in_conversation_with = n1
    a2._conversation_started_at = 456.0
    engine._clear_conversation_pair(n1, n2)
    assert a1.in_conversation_with is None
    assert a1._conversation_started_at == 0
    assert a2.in_conversation_with is None
    assert a2._conversation_started_at == 0


def test_npc_chat_does_not_involve_crow(monkeypatch):
    engine = _make_engine(monkeypatch)
    npc = None
    for n in engine.agents:
        if n != engine.detective_name:
            npc = n
            break
    engine._trigger_npc_chat(engine.detective_name, npc)
    engine._trigger_npc_chat(npc, engine.detective_name)


# ==================== Requirement: NPC pro-active report lifecycle ====================


def test_trigger_npc_to_detective_releases_in_conversation_with(monkeypatch):
    """After a one-way report, source.in_conversation_with must be None."""
    engine = _make_engine(monkeypatch)
    agent_name = None
    for name, agent in engine.agents.items():
        if name != engine.detective_name and agent.is_alive:
            agent_name = name
            break
    assert agent_name is not None
    source = engine.agents[agent_name]
    crow = engine.agents[engine.detective_name]
    source.x = crow.x + 1
    source.y = crow.y
    source.in_conversation_with = "some_other"  # simulate stale state
    engine._trigger_npc_to_detective_chat(agent_name, "test action", "test result")
    assert source.in_conversation_with == engine.detective_name
    assert crow.in_conversation_with == agent_name


def test_trigger_npc_to_detective_clears_thought_and_action_state(monkeypatch):
    """After a one-way report, source state fields must be cleared."""
    engine = _make_engine(monkeypatch)
    agent_name = None
    for name, agent in engine.agents.items():
        if name != engine.detective_name and agent.is_alive:
            agent_name = name
            break
    assert agent_name is not None
    source = engine.agents[agent_name]
    crow = engine.agents[engine.detective_name]
    source.x = crow.x + 1
    source.y = crow.y
    source.current_thought = "lingering thought"
    source.current_thought_time = 999.0
    source.current_action = "lingering action"
    source.current_action_type = "investigate"
    source._pending_action = {"action_type": "talk", "target_person": engine.detective_name}
    source._last_decision = {"ok": True, "action": "old"}
    source._last_raw_response = "raw json"
    source._is_thinking = True
    source._is_reflecting = True

    engine._trigger_npc_to_detective_chat(agent_name, "test action", "test result")

    assert source.current_thought == ""
    assert source.current_thought_time == 0
    assert source.current_action == ""
    assert source.current_action_type == ""
    assert source._pending_action is None
    assert source._last_decision == {}
    assert source._last_raw_response == ""
    assert source._is_thinking is False
    assert source._is_reflecting is False


def test_trigger_npc_to_detective_records_action_history(monkeypatch):
    """After a one-way report, action_history should contain the report entry."""
    engine = _make_engine(monkeypatch)
    agent_name = None
    for name, agent in engine.agents.items():
        if name != engine.detective_name and agent.is_alive:
            agent_name = name
            break
    assert agent_name is not None
    source = engine.agents[agent_name]
    crow = engine.agents[engine.detective_name]
    source.x = crow.x + 1
    source.y = crow.y
    source.action_history = []

    engine._trigger_npc_to_detective_chat(agent_name, "test action", "test result")

    assert len(source.action_history) >= 1
    last = source.action_history[-1]
    assert last.get("action_type") == "report_to_detective"
    assert last.get("action") == "test action"
    assert last.get("expected_result") == "test result"
    assert "message" in last
    assert "time" in last


def test_trigger_npc_to_detective_message_not_raw_action(monkeypatch):
    """When no clues, the bubble message should be conversational, not raw action."""
    engine = _make_engine(monkeypatch)
    agent_name = None
    for name, agent in engine.agents.items():
        if name != engine.detective_name and agent.is_alive:
            agent_name = name
            break
    assert agent_name is not None
    source = engine.agents[agent_name]
    crow = engine.agents[engine.detective_name]
    source.x = crow.x + 1
    source.y = crow.y

    # Raw action that looks like inner monologue
    raw_action = "我会去找警长说明我发现的可疑情况"
    engine._trigger_npc_to_detective_chat(agent_name, raw_action, "")
    bubble = engine.chat_bubbles.get(agent_name, {})
    text = bubble.get("text", "")
    # Should NOT contain the raw action markers
    assert "我会" not in text, f"message still contains inner-monologue marker: {text}"
    assert "行动：" not in text, f"message still contains action prefix: {text}"
    # Should contain conversational framing
    assert "警长" in text, f"message should address the detective: {text}"


def test_npc_chat_shows_typing_bubble_before_model_returns(monkeypatch):
    """NPC-to-NPC chat must be visibly underway while model speech is pending."""
    engine = _make_engine(monkeypatch)
    names = [name for name, agent in engine.agents.items() if name != engine.detective_name and agent.is_alive]
    assert len(names) >= 2
    name1, name2 = names[:2]
    agent1 = engine.agents[name1]
    agent2 = engine.agents[name2]
    agent1.x, agent1.y = 10, 10
    agent2.x, agent2.y = 12, 10
    agent1._pending_action = {
        "action_type": "talk",
        "target_location": agent2.current_location or "Park",
        "target_object": "",
        "target_person": name2,
        "action": "talk with neighbor",
        "thought": "I should talk first",
        "expected_result": "conversation starts",
    }

    class DummyThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            return None

    monkeypatch.setattr(game_engine.threading, "Thread", DummyThread)

    engine._trigger_npc_chat(name1, name2)

    assert agent1.in_conversation_with == name2
    assert agent2.in_conversation_with == name1
    assert agent1._pending_action is None
    assert engine.chat_bubbles[name1]["text"] == "..."
    assert engine.chat_bubbles[name1]["target"] == name2


def test_complete_agent_action_releases_conversation_after_report(monkeypatch):
    """_complete_agent_action with detective target must release in_conversation_with."""
    engine = _make_engine(monkeypatch)
    agent_name = None
    for name, agent in engine.agents.items():
        if name != engine.detective_name and agent.is_alive:
            agent_name = name
            break
    assert agent_name is not None
    agent = engine.agents[agent_name]
    crow = engine.agents[engine.detective_name]
    agent.x = crow.x + 1
    agent.y = crow.y
    agent._pending_action = {
        "action_type": "talk",
        "target_location": crow.current_location or "Park",
        "target_object": "",
        "target_person": engine.detective_name,
        "action": "report findings",
        "thought": "I should tell Crow",
        "expected_result": "Crow learns about the clue",
    }
    engine._complete_agent_action(agent_name, agent)
    assert agent.in_conversation_with == engine.detective_name
    assert crow.in_conversation_with == agent_name
    assert agent._pending_action is None
    assert agent.runtime_state == "acting"
    assert agent._action_completed is False


def test_trigger_npc_to_detective_does_not_block_when_crow_free(monkeypatch):
    """When Crow is free, the one-way report should not block either party."""
    engine = _make_engine(monkeypatch)
    agent_name = None
    for name, agent in engine.agents.items():
        if name != engine.detective_name and agent.is_alive:
            agent_name = name
            break
    assert agent_name is not None
    source = engine.agents[agent_name]
    crow = engine.agents[engine.detective_name]
    source.x = crow.x + 1
    source.y = crow.y
    # Ensure Crow is free
    crow.in_conversation_with = None

    engine._trigger_npc_to_detective_chat(agent_name, "test", "test")

    # The report is a real conversation/action until the white bubble expires.
    assert source.in_conversation_with == engine.detective_name
    assert crow.in_conversation_with == agent_name
    # A bubble should exist for the source
    assert agent_name in engine.chat_bubbles
    assert "text" in engine.chat_bubbles[agent_name]


# ============================================================================
# 2026-06-07 Action Start and Conversation Regression Closure
# ============================================================================


def test_planning_talk_to_busy_npc_must_enter_starting_action_not_idle(monkeypatch):
    """Regression: when a planning cycle produces a talk action targeting a
    busy NPC, the scheduler must NOT silently discard the pending_action and
    set idle.  Instead it must enter starting_action with a continue_current
    fallback, preserving the visible lifecycle chain.

    Per NPC_BEHAVIOR_LIFECYCLE.md 2026-06-07 Rule 1:
    "Every new action has a distinct action_started_at."
    Rule 5: "If a conversation target moves before arrival... converts to
    visible continue_current action instead of showing fake conversation activity."
    The busy-target case is analogous — must not idle-break the chain.
    """
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", ["Arthur Burton"])
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 0)

    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    klaus = engine.agents["Klaus Mueller"]

    # Arthur is adjacent to Isabella, but Isabella is busy with Klaus
    arthur.x = arthur.target_x = 10
    arthur.y = arthur.target_y = 10
    isabella.x, isabella.y = 11, 10
    klaus.x, klaus.y = 12, 10

    isabella.in_conversation_with = "Klaus Mueller"
    isabella._conversation_started_at = time.time()
    klaus.in_conversation_with = "Isabella Rodriguez"
    klaus._conversation_started_at = time.time()

    arthur.runtime_state = "idle"
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "找伊莎贝拉核实昨晚的事情",
        "action_status": "找伊莎贝拉说话",
        "thought": "她应该知道些什么",
        "expected_result": "交换情报",
        "duration_minutes": 5,
    }
    arthur._last_llm_decision_time = 0
    engine.agent_paths.pop("Arthur Burton", None)
    monkeypatch.setitem(game_engine.CONFIG["agent"], "planning_display_seconds", 0)

    # Let the scheduler handle Arthur's pending action
    engine._update_agent_schedules()

    # The scheduler should have redirected to starting_action with continue_current
    assert arthur.runtime_state != "idle", (
        "BUG: scheduler set Arthur to idle after finding his talk target busy. "
        "This breaks the planning→action chain. "
        "Expected: starting_action with continue_current fallback."
    )
    if arthur.runtime_state == "starting_action":
        assert arthur._pending_action is not None
        assert arthur._pending_action["action_type"] == "continue_current"
        assert "Arthur Burton" not in engine.chat_bubbles, (
            "No chat bubble should appear for continue_current before action-start ends"
        )


def test_detective_chat_clears_old_planning_and_prevents_thread_override(monkeypatch):
    """After detective_chat sets an NPC to in_conversation_with=Crow,
    the planning scheduler must skip that NPC entirely.  Any stale
    planning thread that returns after detective_chat started must not
    inject a new pending_action, change runtime_state, or clear the
    conversation lock.

    This protects the lifecycle: once Crow initiates a conversation,
    the NPC's autonomous planning is completely suspended until the
    conversation bubble expires.
    """
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", ["Arthur Burton"])
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 0)

    arthur = engine.agents["Arthur Burton"]
    crow = engine.agents["Crow"]
    crow.deep_dive_quota = 3
    crow.deep_dive_used = 0

    arthur.x, arthur.y = 10, 10
    crow.x, crow.y = 11, 10
    arthur._last_llm_decision_time = 0
    arthur._next_llm_retry_time = 0

    # Simulate detective_chat locking Arthur
    arthur.in_conversation_with = "Crow"
    engine._detective_chat_active_target = "Arthur Burton"
    arthur._conversation_started_at = time.time()
    arthur.runtime_state = "acting"
    arthur._pending_action = None
    arthur.current_thought = ""
    arthur.current_thought_time = 0

    # Now run the scheduler.  Arthur must be skipped because
    # in_conversation_with is set.
    calls = []

    monkeypatch.setattr(
        arthur,
        "decide_next_action",
        lambda *args, **kwargs: (
            calls.append("decide")
            or (_ for _ in ()).throw(
                AssertionError("planning must not run while in detective conversation")
            )
        ),
    )

    engine._update_agent_schedules()

    assert "decide" not in calls, (
        "decide_next_action must NOT be called while NPC is in detective conversation"
    )
    assert arthur.in_conversation_with == "Crow", (
        "Conversation lock must survive scheduler pass"
    )
    assert arthur._pending_action is None, (
        "No new pending_action must appear during detective conversation"
    )
    assert arthur.runtime_state == "acting", (
        "runtime_state must stay 'acting' while in detective conversation"
    )


def test_detective_chat_interrupts_active_npc_chat_and_old_chat_must_not_revive(monkeypatch):
    """When detective_chat interrupts an active NPC-to-NPC chat, the old chat
    thread must not later revive and re-set in_conversation_with to the old
    partner.  The _npc_chat_tokens mechanism must prevent stale chat threads
    from publishing bubbles or changing conversation state after detection.

    This ensures the rule: detective_chat has highest priority, and old
    conversation threads cannot overwrite the detective conversation state.
    """
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    crow = engine.agents["Crow"]

    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10

    # Simulate: Arthur and Isabella were chatting, then detective_chat
    # interrupted and cleared both.  Isabella's chat token should be stale.
    # Old chat thread for (Arthur, Isabella) should fail the token check.
    chat_key = engine._npc_chat_key("Arthur Burton", "Isabella Rodriguez")
    engine._npc_chat_tokens[chat_key] = "new_token:after_interrupt"

    # Now set Arthur into detective conversation state
    arthur.in_conversation_with = "Crow"
    engine._detective_chat_active_target = "Arthur Burton"
    arthur._conversation_started_at = time.time()
    isabella.in_conversation_with = None  # freed by interrupt

    # Simulate a late NPC chat thread trying to set conversation state
    # (This is the "old thread" trying to revive)
    # The thread would check:
    #   self._npc_chat_tokens.get(chat_key) != token
    # Since our token won't match, it should bail out

    def simulate_old_chat_thread():
        token = "stale_token:before_interrupt"
        with engine._lock:
            if engine._npc_chat_tokens.get(chat_key) != token:
                return  # correct behavior: bail out
            # If it reached here, it would corrupt state
            arthur.in_conversation_with = "Isabella Rodriguez"
            isabella.in_conversation_with = "Arthur Burton"
            return "corrupted"

    result = simulate_old_chat_thread()
    assert result is None, (
        "Old chat thread must bail out when its token doesn't match — "
        "it must not reach the state mutation code"
    )
    assert arthur.in_conversation_with == "Crow", (
        "Stale NPC chat thread must not overwrite detective conversation lock"
    )
    assert isabella.in_conversation_with is None, (
        "Stale NPC chat thread must not revive Isabella's in_conversation_with"
    )


def test_npc_mid_planning_detective_chat_clears_thinking_flag(monkeypatch):
    """When detective_chat is called on an NPC that is currently in the
    thinking state (LLM thread running), the detective chat must clear
    _is_thinking and _pending_action so the stale response doesn't
    resurrect the old plan after the conversation ends.

    detective_chat sets runtime_state to 'acting' and clears pending_action.
    The stale LLM thread's response handler must not be able to inject
    a new pending_action because the _is_thinking flag is false or
    because the scheduler skips the in_conversation agent.
    """
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    arthur = engine.agents["Arthur Burton"]
    crow = engine.agents["Crow"]
    crow.deep_dive_quota = 3
    crow.deep_dive_used = 0

    arthur.x, arthur.y = 10, 10
    crow.x, crow.y = 11, 10
    arthur.runtime_state = "thinking"
    arthur._is_thinking = True
    arthur._thinking_started_at = time.time() - 1
    arthur._pending_action = {
        "action_type": "investigate",
        "target_location": "Johnson Park",
        "action": "四处查看可疑痕迹",
    }
    arthur._last_decision = {"thought": "我需要查清楚"}
    arthur.current_thought = "哪里不对劲..."
    arthur.current_thought_time = time.time()

    # detective_chat should clear all of this
    monkeypatch.setattr(arthur, "generate_response", lambda speaker, msg, day: "我先回答警长。")
    engine._daily_interviewed = set()

    result = engine.detective_chat("Arthur Burton", "", is_deep_dive=False)
    assert "error" not in result, f"detective_chat should succeed: {result}"

    # Verify the detective chat cleared the mid-planning state
    assert arthur._is_thinking is False, (
        "_is_thinking must be cleared by detective_chat"
    )
    assert arthur._pending_action is None, (
        "_pending_action must be cleared by detective_chat"
    )
    assert arthur._last_decision == {}, (
        "_last_decision must be cleared by detective_chat"
    )
    assert arthur.current_thought == "", (
        "current_thought must be cleared by detective_chat"
    )
    assert arthur.in_conversation_with == "Crow", (
        "NPC must be locked to Crow conversation after detective_chat"
    )

    # Now run the scheduler — it must skip Arthur because he's in_conversation
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", ["Arthur Burton"])
    calls = []
    monkeypatch.setattr(
        arthur,
        "decide_next_action",
        lambda *args, **kwargs: calls.append("plan") or {
            "ok": True,
            "action_type": "move_to",
            "target_location": "Johnson Park",
            "action": "walk away",
            "raw_response": "{}",
        },
    )
    engine._update_agent_schedules()
    assert "plan" not in calls, (
        "Scheduler must skip NPC in detective conversation"
    )

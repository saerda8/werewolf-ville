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

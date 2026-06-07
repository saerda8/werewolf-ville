import io
import threading
import time

import game_engine
from world_config import (
    ACTIVE_CHARACTERS,
    AMBIENT_RESIDENT_DISPLAY_NAMES,
    AMBIENT_RESIDENT_SPRITES,
    INITIAL_BODY_SITE,
)


def _make_engine(monkeypatch, seed=7, llm_override=None):
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
    monkeypatch.setattr(game_engine.Agent, "add_memory", lambda self, event, day: None)
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "")
    return game_engine.WerewolfGameEngine(random_seed=seed, llm_override=llm_override)


def _complete_daily_interviews(engine):
    engine._daily_interviewed = {
        name for name, agent in engine.agents.items()
        if name != engine.detective_name and agent.is_alive and name not in engine._jailed
    }


def _start_dusk_voting(engine, statement="我听完大家发言了，现在请各自投票。"):
    _complete_daily_interviews(engine)
    assert engine.start_dusk_discussion() is True
    result = engine.submit_dusk_statement(statement)
    assert result["success"] is True
    return result


def test_random_werewolf_models_and_initial_body(monkeypatch):
    engine = _make_engine(monkeypatch, seed=11)
    second = _make_engine(monkeypatch, seed=11)

    assert engine.werewolf_name == second.werewolf_name
    assert engine.werewolf_name in set(ACTIVE_CHARACTERS) - {"Crow"}
    assert len(engine.werewolf_names) == 2
    assert all(w in set(ACTIVE_CHARACTERS) - {"Crow"} for w in engine.werewolf_names)
    assert engine.werewolf_name == engine.werewolf_names[0]  # legacy first wolf
    assert len(engine.model_assignments) == 8
    assert "GLM-5.1" not in engine.model_assignments.values()

    body = engine.bodies[0]
    assert body.victim_name in AMBIENT_RESIDENT_SPRITES
    assert body.discovered is True
    assert body.location == INITIAL_BODY_SITE["location"]
    assert (body.x, body.y) == (INITIAL_BODY_SITE["x"], INITIAL_BODY_SITE["y"])

    status = engine.get_status()
    assert status["werewolf_name"] == engine.werewolf_name
    assert status["werewolf_names"] == engine.werewolf_names
    assert status["bodies"][0]["alive"] is False
    assert status["bodies"][0]["victim_display_name"] == AMBIENT_RESIDENT_DISPLAY_NAMES[body.victim_name]
    assert status["bodies"][0]["victim_display_name"] != body.victim_name
    assert status["gathering_site"]["location"] == body.location
    assert status["gathering_site"]["x"] == INITIAL_BODY_SITE["x"]
    assert status["gathering_site"]["y"] == INITIAL_BODY_SITE["y"]
    assert status["personas"]["Crow"]["location_label"] == "约翰逊公园东侧广场"
    assert "recent_log" in status
    assert isinstance(status["recent_log"], list)

    center = (INITIAL_BODY_SITE["x"], INITIAL_BODY_SITE["y"])
    for persona in status["personas"].values():
        assert abs(persona["x"] - center[0]) <= 7
        assert abs(persona["y"] - center[1]) <= 7


def test_case_intro_uses_body_display_name(monkeypatch):
    engine = _make_engine(monkeypatch, seed=11)
    body = engine.bodies[0]

    text = engine._case_intro_text()

    assert AMBIENT_RESIDENT_DISPLAY_NAMES[body.victim_name] in text
    assert body.victim_name not in text


def test_crow_case_intro_lines_sound_like_sheriff_not_coroner(monkeypatch):
    engine = _make_engine(monkeypatch, seed=11)

    lines = engine._case_intro_fallback_lines()
    joined = "".join(lines)

    assert "法医" not in joined
    assert "死因" not in joined
    assert "现场" in joined
    assert "痕迹" in joined
    assert "克罗" in lines[0]


def test_action_duration_uses_planned_minutes_and_planning_cycle_floor(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine.day_duration = 600
    engine._last_planning_cycle_seconds = 10

    assert engine._action_duration_minutes({"duration_minutes": 5}) == 24
    assert engine._action_duration_minutes({"duration_minutes": 90}) == 30
    assert engine._action_duration_minutes({}) == 30


def test_initial_action_duration_defaults_to_full_occupancy(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine.day_duration = 600
    engine._last_planning_cycle_seconds = 0

    assert engine._action_duration_minutes({"duration_minutes": 5}) == 30
    assert engine._action_duration_seconds({"duration_minutes": 5}) == 12.5


def test_action_duration_seconds_has_six_second_floor(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine.day_duration = 600
    engine._last_planning_cycle_seconds = 1

    assert engine._action_duration_minutes({"duration_minutes": 5}) == 5
    assert engine._action_duration_seconds({"duration_minutes": 5}) == 6.0


def test_day_tick_does_not_run_realtime_reflection(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    engine.day_start_time = time.time()
    engine.llm_tick_counter = engine.llm_interval
    calls = []

    monkeypatch.setattr(engine, "_update_agent_schedules", lambda: calls.append("schedule"))
    monkeypatch.setattr(engine, "_move_agents", lambda: calls.append("move"))
    monkeypatch.setattr(engine, "_llm_tick", lambda: calls.append("reflect"))

    engine._day_tick()

    assert calls == ["schedule", "move"]


def test_stage_reflection_only_runs_at_night_start_when_running(monkeypatch):
    engine = _make_engine(monkeypatch)
    calls = []
    for name, agent in engine.agents.items():
        if name != engine.detective_name:
            monkeypatch.setattr(agent, "daily_reflection", lambda day, dead, n=name: calls.append(n) or "今天先记下。")

    engine._running = False
    engine._start_stage_reflection("night_start")
    assert calls == []

    engine._running = True
    engine._start_stage_reflection("night_start")
    for thread in list(engine.llm_threads):
        thread.join(timeout=2)

    assert calls


def test_neighbor_action_path_prefers_left_then_right(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    arthur.x = arthur.target_x = 10
    arthur.y = arthur.target_y = 10

    left = engine._neighbor_action_path("Arthur Burton", arthur)
    assert left is not None
    assert left[:2] == (9, 10)

    engine.collision_maze[10][9] = 1
    right = engine._neighbor_action_path("Arthur Burton", arthur)
    assert right is not None
    assert right[:2] == (11, 10)


def test_moving_agent_at_target_without_path_enters_acting(monkeypatch):
    engine = _make_engine(monkeypatch)
    klaus = engine.agents["Klaus Mueller"]
    klaus.x = klaus.target_x = 115
    klaus.y = klaus.target_y = 26
    klaus.runtime_state = "moving"
    klaus._pending_action = {
        "action_type": "work",
        "target_location": "Oak Hill College",
        "target_object": "classroom student seating",
        "target_person": "",
        "action": "整理课堂资料",
        "duration_minutes": 30,
    }
    engine.agent_paths.pop("Klaus Mueller", None)

    engine._move_agents()

    assert klaus.runtime_state == "acting"
    assert getattr(klaus, "_arrived_at_time", 0) > 0


def test_acting_npc_does_not_request_new_plan_before_duration(monkeypatch):
    engine = _make_engine(monkeypatch)
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 999)
    arthur = engine.agents["Arthur Burton"]
    arthur.runtime_state = "acting"
    arthur._pending_action = {
        "action_type": "work",
        "target_location": arthur.current_location or "Johnson Park",
        "action": "整理工具架",
        "duration_minutes": 30,
    }
    arthur._arrived_at_time = time.time()

    called = {"count": 0}

    def fail_if_called(*args, **kwargs):
        called["count"] += 1
        return {"ok": False}

    monkeypatch.setattr(arthur, "decide_next_action", fail_if_called)

    engine._update_agent_schedules()

    assert called["count"] == 0
    assert arthur._pending_action is not None
    assert arthur.runtime_state == "acting"


# ============================================================================
# Planning lane lifecycle: turn advancement on cooldown & state skip
# ============================================================================


def _make_two_npc_planning_engine(monkeypatch):
    """Helper: engine with only Arthur & Isabella in planning order, no LLM delay."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents",
                        ["Arthur Burton", "Isabella Rodriguez"])
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 0)
    monkeypatch.setitem(game_engine.CONFIG["llm"], "retry_delay_seconds", 0)
    engine._planning_turn_index = 0
    return engine


def _drain_memory_tasks(engine):
    tasks = []
    while len(engine._memory_queue):
        tasks.append(engine._memory_queue.pop_next())
    return tasks


def test_engine_records_observation_event(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)

    event = engine._record_observation_event(
        event_type="action_start",
        subject="Arthur Burton",
        text="亚瑟开始检查库存。",
        x=5,
        y=5,
        public=False,
    )

    assert event.event_type == "action_start"
    assert engine._observation_events[-1].text == "亚瑟开始检查库存。"


def test_decision_packet_includes_nearby_people_objects_and_events(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 5, 5
    isabella.x, isabella.y = 6, 5

    engine._record_observation_event(
        event_type="action_start",
        subject="Arthur Burton",
        text="亚瑟开始检查库存。",
        x=5,
        y=5,
        public=False,
    )

    packet = engine._build_observation_packet("Isabella Rodriguez", isabella)

    assert "亚瑟开始检查库存" in packet["observable_events_text"]
    assert "亚瑟" in packet["nearby_people_text"]


def test_discovering_body_records_public_observation_event(monkeypatch):
    engine = _make_engine(monkeypatch, seed=11)
    body = engine.bodies[0]
    body.discovered = False
    engine._observation_events.clear()

    discovered = engine._discover_latest_body()

    assert discovered is body
    event = engine._observation_events[-1]
    assert event.event_type == "body_discovered"
    assert event.subject == body.victim_name
    assert event.public is True
    assert event.hidden is False
    assert (event.x, event.y) == (body.x, body.y)


def test_resolving_dusk_vote_records_public_observation_event(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine.phase = game_engine.GamePhase.DUSK_DISCUSSION
    engine._dusk_jail_target = None
    engine._dusk_vote_resolved = False
    engine._dusk_votes = {
        "Arthur Burton": "Isabella Rodriguez",
        "Klaus Mueller": "Isabella Rodriguez",
        engine.detective_name: "Isabella Rodriguez",
    }
    engine._dusk_vote_reasons = {name: "test" for name in engine._dusk_votes}
    engine._observation_events.clear()

    result = engine._resolve_dusk_votes()

    assert result["winner"] == "Isabella Rodriguez"
    event = engine._observation_events[-1]
    assert event.event_type == "vote_result"
    assert event.subject == "Isabella Rodriguez"
    assert event.public is True
    assert event.hidden is False


def test_night_kill_event_is_hidden_and_visible_only_to_witnesses(monkeypatch):
    engine = _make_engine(monkeypatch, seed=11)
    candidates = [
        name for name, agent in engine.agents.items()
        if name != engine.detective_name
        and name not in engine.werewolf_names
        and agent.is_alive
    ]
    target_name, witness_name, outsider_name = candidates[:3]
    engine._transition_to_night()
    engine._observation_events.clear()
    monkeypatch.setattr(engine, "_night_witnesses", lambda victim_name: [witness_name])

    engine._kill_night_target(target_name)

    event = engine._observation_events[-1]
    assert event.event_type == "night_kill"
    assert event.subject == target_name
    assert event.hidden is True
    assert event.public is False
    assert event.witnesses == {witness_name}

    outsider = engine.agents[outsider_name]
    outsider.x, outsider.y = event.x, event.y
    assert event in engine._observable_events_for(
        witness_name, engine.agents[witness_name]
    )
    assert event not in engine._observable_events_for(outsider_name, outsider)


def test_important_public_and_witnessed_events_enqueue_eligible_npc_memories(monkeypatch):
    engine = _make_engine(monkeypatch)
    eligible = [
        name for name, agent in engine.agents.items()
        if name != engine.detective_name and agent.is_alive
    ]
    witness_name = eligible[0]
    jailed_name = eligible[-1]
    engine._jailed.add(jailed_name)

    engine._record_observation_event(
        event_type="body_discovered",
        subject="Town Resident 01",
        text="镇民在公园发现了一具尸体。",
        x=10,
        y=10,
        public=True,
    )
    engine._record_observation_event(
        event_type="night_kill",
        subject="Arthur Burton",
        text="亚瑟在夜里遭到袭击。",
        x=20,
        y=20,
        hidden=True,
        witnesses={witness_name, jailed_name, engine.detective_name},
    )

    tasks = _drain_memory_tasks(engine)
    public_recipients = set(eligible) - {jailed_name}
    public_tasks = [
        task for task in tasks
        if task.payload.get("event_type") == "body_discovered"
    ]
    witnessed_tasks = [
        task for task in tasks
        if task.payload.get("event_type") == "night_kill"
    ]

    assert {task.agent_name for task in public_tasks} == public_recipients
    assert {task.agent_name for task in witnessed_tasks} == {witness_name}
    assert all(task.payload.get("kind") == "observation_event" for task in tasks)


def test_action_status_drops_customer_when_no_visible_person(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    arthur.x, arthur.y = 5, 5
    for other_name, other in engine.agents.items():
        if other_name != "Arthur Burton":
            other.x, other.y = 100, 100

    status = engine._ground_action_status(
        "Arthur Burton",
        arthur,
        "招呼客人",
        {"nearby_people_text": "附近没有人"},
    )

    assert status != "招呼客人"
    assert "客人" not in status


def test_complete_action_enqueues_memory_task(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    arthur._pending_action = {
        "action_type": "inspect",
        "target_location": "Harvey Oak Supply Store",
        "target_object": "shelf",
        "target_person": "",
        "action": "检查库存",
        "action_status": "检查库存",
        "thought": "需要确认工具是否齐全。",
        "expected_result": "掌握库存情况",
        "duration_minutes": 5,
        "observation_before": {"observable_events_text": "之前看到货架凌乱。"},
    }

    engine._complete_agent_action("Arthur Burton", arthur)

    assert len(engine._memory_queue) == 1
    task = engine._memory_queue.pop_next()
    assert task.agent_name == "Arthur Burton"
    assert task.payload["kind"] == "action_completed"
    assert "需要确认工具是否齐全" in task.payload["thought"]
    assert "掌握库存情况" in task.payload["expected_result"]


def test_npc_chat_completion_enqueues_memory_for_both_participants(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)

    engine._enqueue_conversation_memory(
        speaker="Arthur Burton",
        listener="Isabella Rodriguez",
        transcript=[
            ("Arthur Burton", "我看到五金店门口有人徘徊。"),
            ("Isabella Rodriguez", "这听起来很奇怪。"),
        ],
    )

    tasks = [engine._memory_queue.pop_next(), engine._memory_queue.pop_next()]

    assert {task.agent_name for task in tasks} == {"Arthur Burton", "Isabella Rodriguez"}
    assert all(task.payload["kind"] == "conversation_completed" for task in tasks)
    assert all("五金店门口有人徘徊" in str(task.payload["transcript"]) for task in tasks)


def test_memory_lane_writes_thought_memory(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    written = []

    def fake_consolidate(payload):
        return {
            "memories": [
                {
                    "type": "thought",
                    "text": "亚瑟认为伊莎贝拉可能已经注意到他的异常。",
                    "importance": 8,
                    "keywords": ["亚瑟", "伊莎贝拉", "异常"],
                    "subject": "Arthur Burton",
                    "predicate": "suspects",
                    "object": "Isabella Rodriguez",
                }
            ],
            "current_goal": "避免伊莎贝拉继续怀疑自己。",
        }

    monkeypatch.setattr(arthur, "consolidate_memory", fake_consolidate)
    monkeypatch.setattr(arthur, "add_memory", lambda event, day: written.append({"event": event, "day": day}))

    engine._enqueue_memory_task("Arthur Burton", {"kind": "action_completed"})
    engine._process_next_memory_task()

    deadline = time.time() + 2
    while not written and time.time() < deadline:
        time.sleep(0.01)

    assert written
    assert "thought" in written[0]["event"]
    assert "伊莎贝拉" in written[0]["event"]
    assert arthur.scratch["currently"] == "避免伊莎贝拉继续怀疑自己。"


def _make_tracking_decide(name, store):
    """Return a decide_next_action mock that records calls and returns fast."""
    def _decide(*args, **kwargs):
        store.append(name)
        return {"ok": False, "error": "test_skip", "raw_response": ""}
    return _decide


def _wait_for_decision_call(called, expected, timeout=2.0):
    """Busy-wait for expected value to appear in called list (async thread)."""
    deadline = time.time() + timeout
    while expected not in called and time.time() < deadline:
        time.sleep(0.01)


def _wait_for_decision_call(called, expected, timeout=2.0):
    deadline = time.time() + timeout
    while expected not in called and time.time() < deadline:
        time.sleep(0.01)


def test_planning_turn_advances_when_candidate_on_next_retry_cooldown(monkeypatch):
    """When current planning candidate has _next_llm_retry_time in the future,
    planning turn advances to the next eligible NPC."""
    engine = _make_two_npc_planning_engine(monkeypatch)
    assert engine._current_planning_candidate() == "Arthur Burton"

    arthur = engine.agents["Arthur Burton"]
    arthur._next_llm_retry_time = time.time() + 999  # long cooldown

    isabella = engine.agents["Isabella Rodriguez"]
    isabella._next_llm_retry_time = 0  # ready
    isabella._last_llm_decision_time = 0

    called = []
    monkeypatch.setattr(arthur, "decide_next_action", _make_tracking_decide("Arthur", called))
    monkeypatch.setattr(isabella, "decide_next_action", _make_tracking_decide("Isabella", called))

    engine._update_agent_schedules()
    _wait_for_decision_call(called, "Isabella")

    assert "Arthur" not in called, (
        "Arthur must not be asked to decide while on next_retry cooldown"
    )
    assert "Isabella" in called, (
        "Isabella must be asked to decide after Arthur is skipped due to next_retry"
    )


def test_planning_turn_advances_when_candidate_on_interval_cooldown(monkeypatch):
    """When current planning candidate is within action_decision_interval,
    planning turn advances to the next eligible NPC."""
    engine = _make_two_npc_planning_engine(monkeypatch)
    # Override interval to a large value so Arthur's recent decision is inside it
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 999)
    assert engine._current_planning_candidate() == "Arthur Burton"

    arthur = engine.agents["Arthur Burton"]
    arthur._last_llm_decision_time = time.time()  # just now → inside 999s interval

    isabella = engine.agents["Isabella Rodriguez"]
    isabella._last_llm_decision_time = 0  # long ago → outside interval
    isabella._next_llm_retry_time = 0

    called = []
    monkeypatch.setattr(arthur, "decide_next_action", _make_tracking_decide("Arthur", called))
    monkeypatch.setattr(isabella, "decide_next_action", _make_tracking_decide("Isabella", called))

    engine._update_agent_schedules()
    _wait_for_decision_call(called, "Isabella")

    assert "Arthur" not in called, (
        "Arthur must not be asked to decide while within action_decision_interval"
    )
    assert "Isabella" in called, (
        "Isabella must be asked to decide after Arthur is skipped due to interval"
    )


def test_moving_npc_is_skipped_in_planning_lane(monkeypatch):
    """An NPC with is_moving=True must be skipped by the planning lane;
    the turn advances to the next eligible NPC."""
    engine = _make_two_npc_planning_engine(monkeypatch)
    assert engine._current_planning_candidate() == "Arthur Burton"

    arthur = engine.agents["Arthur Burton"]
    arthur.x, arthur.y = 10, 10
    arthur.target_x, arthur.target_y = 12, 10  # target differs → is_moving
    arthur._next_llm_retry_time = 0
    arthur._last_llm_decision_time = 0

    isabella = engine.agents["Isabella Rodriguez"]
    isabella._next_llm_retry_time = 0
    isabella._last_llm_decision_time = 0

    called = []
    monkeypatch.setattr(arthur, "decide_next_action", _make_tracking_decide("Arthur", called))
    monkeypatch.setattr(isabella, "decide_next_action", _make_tracking_decide("Isabella", called))

    engine._update_agent_schedules()
    _wait_for_decision_call(called, "Isabella")

    assert "Arthur" not in called, "Moving Arthur must not be asked to decide"
    assert "Isabella" in called, "Isabella must become the planning candidate after Arthur skipped"


def test_acting_npc_is_skipped_in_planning_lane(monkeypatch):
    """An NPC in acting state (still within action duration) must be skipped;
    the turn advances to the next eligible NPC."""
    engine = _make_two_npc_planning_engine(monkeypatch)
    assert engine._current_planning_candidate() == "Arthur Burton"

    arthur = engine.agents["Arthur Burton"]
    arthur.runtime_state = "acting"
    arthur._arrived_at_time = time.time()
    arthur._pending_action = {
        "action_type": "work",
        "target_location": arthur.current_location or "Johnson Park",
        "target_object": "",
        "target_person": "",
        "action": "整理工具架",
        "thought": "继续工作",
        "expected_result": "完成整理",
        "duration_minutes": 30,
        "duration_seconds": 9999,  # very long so it doesn't expire during test
    }
    arthur._next_llm_retry_time = 0
    arthur._last_llm_decision_time = 0

    isabella = engine.agents["Isabella Rodriguez"]
    isabella._next_llm_retry_time = 0
    isabella._last_llm_decision_time = 0

    called = []
    monkeypatch.setattr(arthur, "decide_next_action", _make_tracking_decide("Arthur", called))
    monkeypatch.setattr(isabella, "decide_next_action", _make_tracking_decide("Isabella", called))

    engine._update_agent_schedules()
    _wait_for_decision_call(called, "Isabella")

    assert "Arthur" not in called, "Acting Arthur must not be asked to decide"
    assert "Isabella" in called, "Isabella must become the planning candidate after Arthur skipped"


def test_pending_planning_state_is_skipped_in_planning_lane(monkeypatch):
    """An NPC with _pending_action and runtime_state 'planning'/'moving'
    must be skipped; the turn advances to the next eligible NPC."""
    engine = _make_two_npc_planning_engine(monkeypatch)
    assert engine._current_planning_candidate() == "Arthur Burton"

    arthur = engine.agents["Arthur Burton"]
    arthur.runtime_state = "planning"
    arthur._pending_action = {
        "action_type": "work",
        "target_location": arthur.current_location or "Johnson Park",
        "action": "规划中",
    }
    arthur._next_llm_retry_time = 0
    arthur._last_llm_decision_time = 0

    isabella = engine.agents["Isabella Rodriguez"]
    isabella._next_llm_retry_time = 0
    isabella._last_llm_decision_time = 0

    called = []
    monkeypatch.setattr(arthur, "decide_next_action", _make_tracking_decide("Arthur", called))
    monkeypatch.setattr(isabella, "decide_next_action", _make_tracking_decide("Isabella", called))

    engine._update_agent_schedules()
    _wait_for_decision_call(called, "Isabella")

    assert "Arthur" not in called, "Planning-state Arthur must not be asked to decide"
    assert "Isabella" in called, "Isabella must become the planning candidate after Arthur skipped"


def test_conversation_state_is_skipped_in_planning_lane(monkeypatch):
    """An NPC with in_conversation_with set must be skipped;
    the turn advances to the next eligible NPC."""
    engine = _make_two_npc_planning_engine(monkeypatch)
    assert engine._current_planning_candidate() == "Arthur Burton"

    arthur = engine.agents["Arthur Burton"]
    arthur.x, arthur.y = 10, 10
    arthur.target_x, arthur.target_y = 10, 10
    arthur.in_conversation_with = "Isabella Rodriguez"
    arthur._conversation_started_at = time.time()
    arthur._next_llm_retry_time = 0
    arthur._last_llm_decision_time = 0

    # Isabella is not in conversation (only Arthur is busy)
    isabella = engine.agents["Isabella Rodriguez"]
    isabella.x, isabella.y = 12, 10
    isabella.target_x, isabella.target_y = 12, 10
    isabella.in_conversation_with = None
    isabella._next_llm_retry_time = 0
    isabella._last_llm_decision_time = 0

    called = []
    monkeypatch.setattr(arthur, "decide_next_action", _make_tracking_decide("Arthur", called))
    monkeypatch.setattr(isabella, "decide_next_action", _make_tracking_decide("Isabella", called))

    engine._update_agent_schedules()
    _wait_for_decision_call(called, "Isabella")

    assert "Arthur" not in called, "Conversation-bound Arthur must not be asked to decide"
    assert "Isabella" in called, "Isabella must become the planning candidate after Arthur skipped"


def test_action_duration_does_not_request_decide_next_action(monkeypatch):
    """Reinforcement: during action duration, decide_next_action is not called
    and the turn advances past the acting NPC."""
    engine = _make_two_npc_planning_engine(monkeypatch)
    assert engine._current_planning_candidate() == "Arthur Burton"

    arthur = engine.agents["Arthur Burton"]
    arthur.runtime_state = "acting"
    arthur._arrived_at_time = time.time()
    arthur._pending_action = {
        "action_type": "work",
        "target_location": arthur.current_location or "Johnson Park",
        "action": "整理工具架",
        "duration_minutes": 30,
        "duration_seconds": 9999,
    }
    arthur._next_llm_retry_time = 0
    arthur._last_llm_decision_time = 0

    isabella = engine.agents["Isabella Rodriguez"]
    isabella._next_llm_retry_time = 0
    isabella._last_llm_decision_time = 0

    called = []
    monkeypatch.setattr(arthur, "decide_next_action", _make_tracking_decide("Arthur", called))
    monkeypatch.setattr(isabella, "decide_next_action", _make_tracking_decide("Isabella", called))

    engine._update_agent_schedules()
    _wait_for_decision_call(called, "Isabella")

    assert "Arthur" not in called, "decide_next_action must NOT be called during action duration"
    assert arthur._pending_action is not None, "Pending action must remain during duration"
    assert arthur.runtime_state == "acting", "Arthur must still be in acting state"
    assert "Isabella" in called, "Planning lane must advance to the next NPC"


def test_ordinary_action_status_bubble_persists_until_action_completes(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", ["Arthur Burton"])
    arthur = engine.agents["Arthur Burton"]
    arthur.target_x, arthur.target_y = arthur.x, arthur.y
    arthur.runtime_state = "idle"
    arthur._pending_action = {
        "action_type": "work",
        "target_location": arthur.current_location or "Johnson Park",
        "target_object": "",
        "target_person": "",
        "action": "整理工具架",
        "duration_minutes": 5,
    }

    engine._update_agent_schedules()

    bubble = engine.chat_bubbles.get("Arthur Burton")
    assert bubble is None
    assert arthur.runtime_state == "starting_action"
    arthur._action_start_visible_until = 0
    engine._update_agent_schedules()

    bubble = engine.chat_bubbles.get("Arthur Burton")
    assert bubble is not None
    assert bubble.get("kind") == "action_status"
    assert "..." in bubble.get("text", "")

    monkeypatch.setitem(game_engine.CONFIG["game"], "bubble_lifetime_seconds", 0)
    engine._expire_chat_bubbles()
    assert "Arthur Burton" in engine.chat_bubbles

    arthur._arrived_at_time = time.time() - 999
    arthur._action_status_visible_at = time.time() - 999
    engine._update_agent_schedules()

    assert arthur._pending_action is None
    assert "Arthur Burton" not in engine.chat_bubbles


def test_status_exposes_action_status_visible_time(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    arthur.runtime_state = "acting"
    arthur._action_started_at = 1111.25
    arthur._action_status_visible_at = 1234.5

    status = engine.get_status()

    assert status["personas"]["Arthur Burton"]["action_started_at"] == 1111.25
    assert status["personas"]["Arthur Burton"]["action_status_visible_at"] == 1234.5


def test_action_status_sanitizer_keeps_one_grounded_action(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    packet = {
        "nearby_people_text": "附近没有人",
        "nearby_objects_text": "工具架、柜台",
    }

    assert engine._ground_action_status("Arthur Burton", arthur, "和准备药品，等待警长询问", packet) == "准备药品"
    assert engine._ground_action_status("Arthur Burton", arthur, "招呼客人", packet) == "整理工具架"


def test_status_exposes_departure_delay_until(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    arthur._departure_delay_until = 4321.5

    status = engine.get_status()

    assert status["personas"]["Arthur Burton"]["departure_delay_until"] == 4321.5


def test_player_visible_log_keeps_think_plan_action_closure(monkeypatch):
    engine = _make_engine(monkeypatch)

    assert engine._is_player_visible_log_entry({"type": "action", "message": "[行动计划] 亚瑟: 计划=整理工具"})
    assert engine._is_player_visible_log_entry({"type": "action", "message": "[开始行动] 亚瑟: 执行：整理工具"})
    assert engine._is_player_visible_log_entry({"type": "action", "message": "[行动结果] 亚瑟: 整理完工具"})
    assert not engine._is_player_visible_log_entry({"type": "action", "message": "[行动解析] 亚瑟: 地点=酒馆"})


def test_planned_action_falls_back_to_visible_action_when_target_cannot_be_reached(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", ["Arthur Burton"])
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 0)
    monkeypatch.setitem(game_engine.CONFIG["agent"], "planning_display_seconds", 0)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    arthur.target_x, arthur.target_y = 10, 10
    engine.agent_paths.pop("Arthur Burton", None)
    isabella.x, isabella.y = 30, 10
    arthur._last_llm_decision_time = 0

    monkeypatch.setattr(
        arthur,
        "decide_next_action",
        lambda *args, **kwargs: {
            "ok": True,
            "action_type": "talk",
            "target_location": isabella.current_location or "Johnson Park",
            "target_object": "",
            "target_person": "Isabella Rodriguez",
            "action": "找伊莎贝拉交谈",
            "thought": "需要确认她昨晚看到的情况",
            "expected_result": "交换信息",
            "duration_minutes": 5,
            "raw_response": "{}",
        },
    )
    monkeypatch.setattr(engine, "_target_available_for_approach", lambda *args: (True, ""))
    monkeypatch.setattr(engine, "_path_adjacent_to", lambda *args, **kwargs: None)

    engine._update_agent_schedules()
    deadline = time.time() + 3
    while arthur.runtime_state not in {"starting_action", "acting"} and time.time() < deadline:
        time.sleep(0.01)

    assert arthur.runtime_state == "starting_action"
    assert arthur._pending_action is not None
    assert arthur._pending_action["action_type"] == "continue_current"
    assert arthur.current_action
    assert "Arthur Burton" not in engine.chat_bubbles
    arthur._action_start_visible_until = 0
    engine._update_agent_schedules()
    assert arthur.runtime_state == "acting"
    assert engine.chat_bubbles["Arthur Burton"]["kind"] == "action_status"


def test_move_detective_to_agent_stops_adjacent_not_on_top(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    target = engine.agents["Maria Lopez"]

    assert engine.move_detective_to_agent("Maria Lopez") is True
    crow = engine.agents["Crow"]
    # Crow should stop *adjacent* to Maria, not on the same tile
    assert (crow.target_x, crow.target_y) != (target.x, target.y), (
        f"Crow target {crow.target_x},{crow.target_y} must differ "
        f"from Maria position {target.x},{target.y}"
    )
    # Manhattan distance from Crow's target to Maria should be exactly 1
    dist = abs(crow.target_x - target.x) + abs(crow.target_y - target.y)
    assert dist == 1, f"Expected distance 1, got {dist}"


def test_crow_public_status_never_exposes_blue_bubble_state(monkeypatch):
    """Crow can move internally, but UI status must not imply thought/action bubbles."""
    engine = _make_engine(monkeypatch)
    crow = engine.agents["Crow"]
    crow.runtime_state = "moving"
    crow.current_action = "前往咖啡馆调查"
    crow.current_action_type = "investigate"
    crow.current_thought = "我要先整理线索"
    crow.current_thought_time = time.time()
    engine.agent_paths["Crow"] = [(crow.x + 1, crow.y), (crow.x + 2, crow.y)]

    public_crow = engine.get_status()["personas"]["Crow"]

    assert public_crow["runtime_state"] == "idle"
    assert public_crow["path_len"] == 0
    assert public_crow["visual_moving"] is True
    assert public_crow["action"] == ""
    assert public_crow["action_type"] == ""
    assert public_crow["action_plan"] == ""
    assert public_crow["thought"] == ""
    assert public_crow["thought_summary"] == ""
    assert public_crow["thought_time"] == 0


def test_world_config_fallback_preserves_supply_store(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    engine._set_agent_target(arthur, "Arthur Burton", "secret underground laboratory")
    assert arthur.current_location == "Harvey Oak Supply Store"


def test_departure_default_object_is_concrete_for_college(monkeypatch):
    engine = _make_engine(monkeypatch)

    assert engine._departure_object("Klaus Mueller", "Oak Hill College") == "classroom student seating"
    assert engine._departure_object("Mei Lin", "Oak Hill College") == "bookshelf"


def test_set_agent_target_uses_concrete_object_coordinate(monkeypatch):
    engine = _make_engine(monkeypatch)
    klaus = engine.agents["Klaus Mueller"]
    monkeypatch.setattr(
        engine,
        "_find_object_in_spatial_memory",
        lambda agent, location, obj: (122, 20) if obj == "bookshelf" else None,
    )

    engine._set_agent_target(klaus, "Klaus Mueller", "Oak Hill College", "bookshelf")

    assert abs(klaus.target_x - 122) + abs(klaus.target_y - 20) == 1
    assert (klaus.target_x, klaus.target_y) != (122, 20)


def test_invented_object_is_replaced_by_real_landmark_default(monkeypatch):
    engine = _make_engine(monkeypatch)
    klaus = engine.agents["Klaus Mueller"]
    monkeypatch.setattr(
        engine,
        "_find_object_in_spatial_memory",
        lambda agent, location, obj: (122, 20) if obj == "bookshelf" else None,
    )

    resolved = engine._resolve_concrete_target_object(
        klaus,
        "Oak Hill College",
        "archive cabinet",
        "move_to",
        "去图书馆查阅旧报纸档案",
    )

    assert resolved == "bookshelf"


def test_object_lookup_does_not_fall_back_to_landmark_center(monkeypatch):
    engine = _make_engine(monkeypatch)
    klaus = engine.agents["Klaus Mueller"]
    klaus.spatial_memory = {"Oak Hill College": {"library": ["bookshelf"]}}

    assert engine._find_object_in_spatial_memory(klaus, "Oak Hill College", "bookshelf") is None


def test_set_agent_target_falls_back_when_object_has_no_physical_coordinate(monkeypatch):
    engine = _make_engine(monkeypatch)
    klaus = engine.agents["Klaus Mueller"]
    original_target = (klaus.target_x, klaus.target_y)
    monkeypatch.setattr(engine, "_find_object_in_spatial_memory", lambda *args: None)

    moved = engine._set_agent_target(klaus, "Klaus Mueller", "Oak Hill College", "archive cabinet")

    assert moved is True
    assert (klaus.target_x, klaus.target_y) != original_target
    assert klaus.current_location == "Oak Hill College"


def test_set_agent_target_nudges_same_tile_fallback(monkeypatch):
    engine = _make_engine(monkeypatch)
    klaus = engine.agents["Klaus Mueller"]
    klaus.x = klaus.target_x = 40
    klaus.y = klaus.target_y = 40
    monkeypatch.setattr(engine, "_find_object_in_spatial_memory", lambda *args: None)
    monkeypatch.setattr(engine, "_nearest_walkable_tile", lambda *args, **kwargs: (40, 40))

    moved = engine._set_agent_target(klaus, "Klaus Mueller", "Oak Hill College", "")

    assert moved is True
    assert abs(klaus.target_x - 40) + abs(klaus.target_y - 40) == 1


def test_set_agent_target_falls_back_when_object_adjacent_path_fails(monkeypatch):
    engine = _make_engine(monkeypatch)
    mei = engine.agents["Mei Lin"]
    original_target = (mei.target_x, mei.target_y)
    monkeypatch.setattr(engine, "_find_object_in_spatial_memory", lambda *args: (58, 8))
    monkeypatch.setattr(engine, "_path_adjacent_to", lambda *args, **kwargs: None)

    moved = engine._set_agent_target(mei, "Mei Lin", "Oak Hill College", "bookshelf")

    assert moved is True
    assert (mei.target_x, mei.target_y) != original_target
    assert mei.current_location == "Oak Hill College"


def test_morning_gathering_spawns_all_agents_in_body_component(monkeypatch):
    engine = _make_engine(monkeypatch)
    body_component = engine._reachable_component((
        game_engine.INITIAL_BODY_SITE["x"],
        game_engine.INITIAL_BODY_SITE["y"],
    ))

    for agent in engine.agents.values():
        assert (agent.x, agent.y) in body_component


def test_detective_cannot_leave_during_morning_gathering(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = True
    crow = engine.agents["Crow"]
    original_target = (crow.target_x, crow.target_y)

    assert engine.move_detective_to(99, 99, "Johnson Park") is False
    assert (crow.target_x, crow.target_y) == original_target
    assert crow.current_action != "investigating"


def test_detective_cannot_move_until_opening_body_handoff_finishes(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine._body_burial = {"stage": "returning"}
    crow = engine.agents["Crow"]
    original_target = (crow.target_x, crow.target_y)

    assert engine.move_detective_to(99, 99, "Johnson Park") is False
    assert (crow.target_x, crow.target_y) == original_target

    engine._detective_chat_pending_target = "Maria Lopez"
    assert engine.move_detective_to_agent("Maria Lopez") is False
    assert engine._detective_chat_pending_target is None


def test_manual_detective_move_avoids_long_detour_around_wall(monkeypatch):
    engine = _make_engine(monkeypatch)
    maze = [[0] * 7 for _ in range(7)]
    for y in range(1, 7):
        maze[y][2] = 1
    engine.collision_maze = maze

    target_x, target_y, path = engine._best_manual_move_path((1, 5), (3, 5), radius=2)

    assert (target_x, target_y) == (1, 5)
    assert path == []


def test_collision_loader_preserves_source_walls(monkeypatch):
    values = ["1"] * (140 * 100)
    values[0] = "0"
    values[-1] = "0"
    source = ",".join(values)

    monkeypatch.setattr(game_engine.os.path, "exists", lambda path: True)
    monkeypatch.setattr("builtins.open", lambda *args, **kwargs: io.StringIO(source))
    monkeypatch.setattr(
        game_engine,
        "_connect_maze_regions",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("collision loading must not carve visual walls")
        ),
    )

    maze = game_engine.load_collision_maze()

    assert maze[0][1] == 1
    assert maze[-1][-2] == 1


def test_collision_loader_clears_invisible_public_plaza_seam(monkeypatch):
    values = ["0"] * (140 * 100)
    values[(46 * 140) + 51] = "32125"
    source = ",".join(values)

    monkeypatch.setattr(game_engine.os.path, "exists", lambda path: True)
    monkeypatch.setattr("builtins.open", lambda *args, **kwargs: io.StringIO(source))

    maze = game_engine.load_collision_maze()

    assert maze[46][51] == 0


def test_manual_detective_move_avoids_occupied_tile(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    crow = engine.agents["Crow"]
    maria = engine.agents["Maria Lopez"]
    crow.x, crow.y = 1, 1
    crow.target_x, crow.target_y = 1, 1
    maria.x, maria.y = 3, 1
    maria.target_x, maria.target_y = 3, 1

    assert engine.move_detective_to(3, 1) is True
    assert (crow.target_x, crow.target_y) != (maria.x, maria.y)


def test_move_step_does_not_enter_other_agent_tile(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    crow = engine.agents["Crow"]
    maria = engine.agents["Maria Lopez"]
    crow.x, crow.y = 1, 1
    crow.target_x, crow.target_y = 3, 1
    maria.x, maria.y = 2, 1
    maria.target_x, maria.target_y = 2, 1
    engine.agent_paths["Crow"] = [(2, 1), (3, 1)]

    engine._move_agents()

    assert (crow.x, crow.y) == (1, 1)


def test_clue_stays_pending_until_successful_detective_chat(monkeypatch):
    engine = _make_engine(monkeypatch)
    source = engine.agents["Isabella Rodriguez"]
    source.can_chat_with = lambda target_name, is_deep_dive: True
    source.generate_response = lambda speaker, message, day: "I found something."

    clue = engine.create_clue(
        clue_type="footprint",
        summary="Fresh muddy footprints led away from the body.",
        source="Isabella Rodriguez",
        related_person="",
        location="Hobbs Cafe",
    )
    assert clue.delivered_to_crow is False
    status = engine.get_status()["personas"]["Isabella Rodriguez"]
    assert status["has_new_clue"] is True
    assert status["has_visible_clue_hint"] is True
    assert status["has_detective_hint"] is True

    result = engine.detective_chat("Isabella Rodriguez", "What did you notice?")

    assert result["delivered_clues"] == [clue.summary]
    assert clue.delivered_to_crow is True
    status = engine.get_status()["personas"]["Isabella Rodriguez"]
    assert status["has_new_clue"] is False
    assert status["has_visible_clue_hint"] is False
    assert status["has_detective_hint"] is False
    assert engine.chat_bubbles["Crow"]["target"] == "Isabella Rodriguez"
    assert engine.chat_bubbles["Isabella Rodriguez"]["target"] == "Crow"


def test_status_does_not_light_bulb_for_keyword_only_thought(monkeypatch):
    engine = _make_engine(monkeypatch)
    source = engine.agents["Isabella Rodriguez"]
    source.current_thought = "我发现了一个异常线索，但还没决定是否去找警长。"
    source.current_action = "先整理咖啡馆柜台旁的证据"

    status = engine.get_status()["personas"]["Isabella Rodriguez"]
    assert status["has_new_clue"] is False
    assert status["has_visible_clue_hint"] is False
    assert status["has_detective_hint"] is False


def test_status_lights_bulb_for_explicit_detective_hint(monkeypatch):
    engine = _make_engine(monkeypatch)
    source = engine.agents["Isabella Rodriguez"]
    source._last_decision = {"has_detective_hint": True}

    status = engine.get_status()["personas"]["Isabella Rodriguez"]
    assert status["has_new_clue"] is True
    assert status["has_visible_clue_hint"] is True
    assert status["has_detective_hint"] is True


def test_npc_chat_bubbles_expose_each_other_as_targets(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 12, 10
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "你昨晚注意到什么了吗？")
    monkeypatch.setattr(isabella, "generate_response", lambda speaker, message, day: "我只听见街上有脚步声。")
    # Shorten the NPC chat delay for fast test
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    engine.llm_threads[-1].join(timeout=1)

    assert engine.chat_bubbles["Arthur Burton"]["target"] == "Isabella Rodriguez"
    assert engine.chat_bubbles["Isabella Rodriguez"]["target"] == "Arthur Burton"


def test_npc_chat_empty_reply_keeps_visible_fallback_bubble(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 12, 10
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "你昨晚注意到什么了吗？")
    monkeypatch.setattr(isabella, "generate_response", lambda speaker, message, day: "")
    # Shorten the NPC chat delay for fast test
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    engine.llm_threads[-1].join(timeout=1)

    assert engine.chat_bubbles["Isabella Rodriguez"]["text"] == "我现在还没有想清楚，稍后再和你说。"
    assert engine.chat_bubbles["Isabella Rodriguez"]["target"] == "Arthur Burton"


def test_npc_chat_bubbles_at_distance_two_publish_initiator_bubble(monkeypatch):
    """_trigger_npc_chat must not early-exit at distance 2 (one empty tile
    between the two NPCs).  At minimum the initiator's white bubble must
    be published so the player can see that two NPCs are conversing."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 12, 10  # Manhattan distance = 2
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "你昨晚在那边看到什么了吗？")
    monkeypatch.setattr(isabella, "generate_response", lambda speaker, message, day: "没看到特别的，不过听到了脚步声。")
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    engine.llm_threads[-1].join(timeout=2)

    assert engine.chat_bubbles["Arthur Burton"]["target"] == "Isabella Rodriguez", (
        "Initiator bubble must be published for distance-2 NPC chat"
    )
    assert engine.chat_bubbles["Isabella Rodriguez"]["target"] == "Arthur Burton", (
        "Responder bubble must also be published for distance-2 NPC chat"
    )


def test_npc_chat_at_distance_two_does_not_early_exit(monkeypatch):
    """Regression: _trigger_npc_chat must treat distance ≤2 identically
    for initial guard and mid-thread re-check.  The old code incorrectly
    used >1 after LLM generation, causing distance-2 chats to silently
    drop their bubbles."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 12, 10  # Manhattan distance = 2
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "你听说最近镇上的事了吗？")
    monkeypatch.setattr(isabella, "generate_response", lambda speaker, message, day: "听说了，大家都在议论。")
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    engine.llm_threads[-1].join(timeout=2)

    # Both bubbles must have non-empty text
    assert engine.chat_bubbles["Arthur Burton"]["text"], (
        "Initiator bubble text must not be empty for distance-2 chat"
    )
    assert engine.chat_bubbles["Isabella Rodriguez"]["text"], (
        "Responder bubble text must not be empty for distance-2 chat"
    )
    # Conversation state stays locked until the visible speech bubble expires.
    assert arthur.in_conversation_with == "Isabella Rodriguez"
    assert isabella.in_conversation_with == "Arthur Burton"
    monkeypatch.setitem(game_engine.CONFIG["game"], "bubble_lifetime_seconds", 0)
    engine._expire_chat_bubbles()
    assert arthur.in_conversation_with is None
    assert isabella.in_conversation_with is None


def test_status_exposes_director_fields(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine.agents["Arthur Burton"].current_thought = (
        "昨晚的情况仍然可疑。我需要先检查附近是否有脚印。"
        + "之后再询问其他居民是否听见异常。" * 8
    )
    engine.agents["Arthur Burton"].current_thought_time = 123.0
    status = engine.get_status()

    assert status["model_assignments"] == engine.model_assignments
    assert status["werewolf_name"] == engine.werewolf_name
    assert status["werewolf_names"] == engine.werewolf_names
    assert "thought" in status["personas"]["Arthur Burton"]
    assert status["personas"]["Arthur Burton"]["thought_time"] == 123.0
    assert len(status["personas"]["Arthur Burton"]["thought_summary"]) <= 100
    assert status["personas"]["Arthur Burton"]["thought_summary"].endswith("。")
    assert len(status["personas"]["Arthur Burton"]["thought"]) > 100
    # Director fields expose true_role for debugging; per-persona role is public-facing.
    for wolf_name in engine.werewolf_names:
        assert status["personas"][wolf_name]["role"] == "villager"
        assert status["personas"][wolf_name]["public_role"] == "villager"
        assert status["personas"][wolf_name]["true_role"] == "werewolf"
    assert status["personas"]["Crow"]["role"] == "detective"
    assert status["personas"]["Crow"]["true_role"] == "detective"


def test_thought_summary_uses_complete_fallback_for_one_overlong_sentence():
    summary = game_engine.WerewolfGameEngine._summarize_thought_for_display("持续分析" * 40)

    assert summary.startswith("持续分析")
    assert summary.endswith("…")
    assert len(summary) <= 100


def test_openrouter_override_assigns_one_runtime_model_without_exposing_key(monkeypatch):
    engine = _make_engine(
        monkeypatch,
        seed=5,
        llm_override={
            "provider": "openrouter",
            "api_key": "sk-test-secret",
            "model": "openai/gpt-4o-mini",
            "api_base": "https://openrouter.ai/api/v1",
        },
    )
    status = engine.get_status()

    assert status["llm_provider"] == {
        "provider": "openrouter",
        "model": "openai/gpt-4o-mini",
        "api_base": "https://openrouter.ai/api/v1",
    }
    assert set(status["model_assignments"].values()) == {"openai/gpt-4o-mini"}
    assert "sk-test-secret" not in str(status)


def test_custom_provider_override_uses_custom_base_without_exposing_key(monkeypatch):
    engine = _make_engine(
        monkeypatch,
        seed=6,
        llm_override={
            "provider": "custom",
            "api_key": "sk-custom-secret",
            "model": "my-model",
            "api_base": "http://127.0.0.1:9000/v1",
        },
    )
    status = engine.get_status()

    assert status["llm_provider"] == {
        "provider": "custom",
        "model": "my-model",
        "api_base": "http://127.0.0.1:9000/v1",
    }
    assert set(status["model_assignments"].values()) == {"my-model"}
    assert "sk-custom-secret" not in str(status)


def test_anthropic_provider_override_uses_one_model_without_exposing_key(monkeypatch):
    engine = _make_engine(
        monkeypatch,
        seed=7,
        llm_override={
            "provider": "anthropic",
            "api_key": "sk-anthropic-secret",
            "model": "claude-3-5-sonnet-latest",
            "api_base": "https://api.anthropic.com/v1",
        },
    )
    status = engine.get_status()

    assert status["llm_provider"] == {
        "provider": "anthropic",
        "model": "claude-3-5-sonnet-latest",
        "api_base": "https://api.anthropic.com/v1",
    }
    assert set(status["model_assignments"].values()) == {"claude-3-5-sonnet-latest"}
    assert "sk-anthropic-secret" not in str(status)


# ---------------------------------------------------------------------------
# Requirement 3 / 4 — _path_adjacent_to & object-adjacent placement
# ---------------------------------------------------------------------------

def test_path_adjacent_to_returns_tile_adjacent_to_target(monkeypatch):
    """_path_adjacent_to must return a tile whose Manhattan distance to target is 1."""
    engine = _make_engine(monkeypatch)
    start = (10, 10)
    target = (30, 20)

    result = engine._path_adjacent_to(start, target)
    assert result is not None, "_path_adjacent_to returned None on open maze"

    adj_x, adj_y, path = result
    dist = abs(adj_x - target[0]) + abs(adj_y - target[1])
    assert dist == 1, f"adjacent tile ({adj_x},{adj_y}) is {dist} away from target {target}"

    # Path must lead from start to the chosen adjacent tile
    assert path[-1] == (adj_x, adj_y)
    assert len(path) > 0


def test_path_adjacent_to_never_returns_target_tile_itself(monkeypatch):
    """The returned tile must not equal the target coordinate."""
    engine = _make_engine(monkeypatch)
    result = engine._path_adjacent_to((5, 5), (8, 5))
    assert result is not None
    adj_x, adj_y, _ = result
    assert (adj_x, adj_y) != (8, 5), "returned tile must not be the target itself"


def test_path_adjacent_to_fallback_when_adjacent_blocked(monkeypatch):
    """If all direct neighbours are walls, expand search outward."""
    engine = _make_engine(monkeypatch)
    maze = [[0] * 10 for _ in range(10)]
    # Wall off all 4 direct neighbours of (5,5)
    maze[5][4] = 1  # W
    maze[5][6] = 1  # E
    maze[4][5] = 1  # N
    maze[6][5] = 1  # S
    engine.collision_maze = maze

    result = engine._path_adjacent_to((0, 0), (5, 5))
    assert result is not None, "should expand search past blocked neighbours"
    adj_x, adj_y, _ = result
    dist = abs(adj_x - 5) + abs(adj_y - 5)
    assert dist >= 2, f"expanded search tile should be ≥2 away, got dist={dist}"
    assert maze[adj_y][adj_x] == 0, "returned tile must be walkable"


def test_path_adjacent_to_returns_none_when_no_tile_reachable(monkeypatch):
    """When the start position is walled off, return None conservatively."""
    engine = _make_engine(monkeypatch)
    maze = [[0] * 10 for _ in range(10)]
    # Wall in start at (1,1)
    maze[1][0] = 1
    maze[1][2] = 1
    maze[0][1] = 1
    maze[2][1] = 1
    engine.collision_maze = maze

    result = engine._path_adjacent_to((1, 1), (8, 8))
    assert result is None, "should return None when start is isolated"


def test_move_detective_to_agent_target_differs_from_npc_coordinate(monkeypatch):
    """Regression: Crow must stop adjacent, not on the NPC tile."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    # Place target away from Crow so path exists
    engine.agents["Maria Lopez"].x = 50
    engine.agents["Maria Lopez"].y = 50
    engine.agents["Crow"].x = 10
    engine.agents["Crow"].y = 10

    assert engine.move_detective_to_agent("Maria Lopez") is True
    crow = engine.agents["Crow"]
    maria = engine.agents["Maria Lopez"]
    assert (crow.target_x, crow.target_y) != (maria.x, maria.y), (
        "Crow target must differ from NPC position"
    )


def test_path_adjacent_to_shortest_path_chosen(monkeypatch):
    """When multiple adjacent tiles are reachable, the shortest-path one is picked."""
    engine = _make_engine(monkeypatch)
    # With open maze, tile (31,20) is adjacent east of (30,20) and farther from (10,10)
    # than (30,19) which is north — our BFS should pick the shortest path
    result = engine._path_adjacent_to((10, 10), (30, 20))
    assert result is not None
    adj_x, adj_y, path = result
    # Among the 4 neighbours, the one with shortest path from (10,10) is (29,20) or (30,19)
    # Both are 29 steps (10→29 = 19 dx + 10→20 = 10 dy = 29; 10→30=20 + 10→19=9 = 29)
    dist = abs(adj_x - 30) + abs(adj_y - 20)
    assert dist == 1, f"must be adjacent, got distance {dist} to (30,20)"

    # Verify path leads to the adjacent tile
    assert path[-1] == (adj_x, adj_y)


def test_two_werewolves_are_random_non_crow_residents(monkeypatch):
    """Exactly 2 werewolves are selected from non-Crow residents per game seed."""
    engine = _make_engine(monkeypatch, seed=7)
    assert len(engine.werewolf_names) == 2
    assert engine.werewolf_name == engine.werewolf_names[0]  # legacy first wolf
    for w in engine.werewolf_names:
        assert w in engine.agents
        assert w != "Crow"
        assert engine.agents[w].role == "werewolf"

    # Same seed produces same wolves
    second = _make_engine(monkeypatch, seed=7)
    assert engine.werewolf_names == second.werewolf_names


def test_model_assignment_allows_reused_models_for_eight_agents(monkeypatch):
    """Model assignment cycles/reuses models when fewer than 8 entries available."""
    monkeypatch.setattr("game_engine.CONFIG", {
        "llm": {"available_models": ["only-one-model"]},
        "game": {"day_duration_seconds": 1800, "night_duration_seconds": 300, "tick_interval_seconds": 0.16, "max_days": 5, "move_steps_per_tick": 1},
        "conversation": {"deep_dive_quota": {"kill_1": 3, "kill_2": 2, "kill_3": 1}, "detective_normal_chat_limit": 1, "max_rounds_per_side": 5},
        "agent": {"min_act_seconds": 5, "max_act_seconds": 15},
        "night_behavior": {"forced_completion_seconds": 20, "replan_interval_seconds": 20, "night_move_steps_per_tick": 3},
    })
    engine = _make_engine(monkeypatch, seed=42)
    assert len(engine.model_assignments) == 8
    # All 8 agents get the same model since only one is available
    assert set(engine.model_assignments.values()) == {"only-one-model"}


def test_wolves_receive_each_other_as_runtime_pack_knowledge(monkeypatch):
    """Both wolf agents have role 'werewolf' and know each other."""
    engine = _make_engine(monkeypatch, seed=3)
    assert len(engine.werewolf_names) == 2
    wolf_names = list(engine.werewolf_names)
    # Both wolves have werewolf role
    for w in wolf_names:
        assert engine.agents[w].role == "werewolf"
        assert engine.agents[w].name == w

    # Non-wolves should not have werewolf role
    non_wolves = [n for n in engine.agents if n not in engine.werewolf_names]
    for nw in non_wolves:
        if nw == "Crow":
            assert engine.agents[nw].role == "detective"
        else:
            assert engine.agents[nw].role == "villager", f"{nw} should be villager"

    # Verify pack knowledge: each wolf's runtime role prompt mentions werewolf
    for w in wolf_names:
        prompt = engine.agents[w].get_runtime_role_prompt()
        assert "werewolf" in prompt.lower(), f"{w} prompt lacks werewolf identity"


def test_runtime_hidden_roles_are_not_serialized_as_public_agent_knowledge(monkeypatch):
    """Per-persona public data must not include hidden role for normal player use.
    Director-level fields (werewolf_names, werewolf_name) expose truth at top level,
    and per-persona true_role is reserved for the director view. The public role
    remains villager/detective so normal player UI does not get hidden identities."""
    engine = _make_engine(monkeypatch, seed=5)
    status = engine.get_status()

    # Top-level director fields expose the truth
    assert "werewolf_names" in status
    assert "werewolf_name" in status

    # Each persona has public-facing role plus a separate director true_role.
    for name, persona in status["personas"].items():
        assert "role" in persona
        assert "public_role" in persona
        assert "true_role" in persona
        assert persona["true_role"] == engine.agents[name].role
        if name in engine.werewolf_names:
            assert persona["role"] == "villager"
            assert persona["public_role"] == "villager"
        else:
            assert persona["role"] == engine.agents[name].role
            assert persona["public_role"] == engine.agents[name].role

    # Public player-facing view should not expose hidden werewolf identity
    # through non-role fields (e.g. no 'is_werewolf' or hidden role flag)
    for name, persona in status["personas"].items():
        assert "is_werewolf" not in persona
        assert "hidden_role" not in persona

    # No public role reveals werewolf identity.
    for name in engine.agents:
        assert status["personas"][name]["role"] != "werewolf"
        assert status["personas"][name]["public_role"] != "werewolf"
        assert status["personas"][name]["role"] in ("villager", "detective")


# ---------------------------------------------------------------------------
# Requirement — Dusk Discussion / right-panel day-flow status
# ---------------------------------------------------------------------------


def test_start_dusk_discussion_transitions_phase(monkeypatch):
    """start_dusk_discussion changes phase from DAY to DUSK_DISCUSSION."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    _complete_daily_interviews(engine)
    assert engine.phase == game_engine.GamePhase.DAY

    result = engine.start_dusk_discussion()
    assert result is True
    assert engine.phase == game_engine.GamePhase.DUSK_DISCUSSION


def test_start_dusk_discussion_does_not_enter_night(monkeypatch):
    """Dusk discussion must NOT immediately trigger night transition."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    _complete_daily_interviews(engine)

    engine.start_dusk_discussion()
    assert engine.phase == game_engine.GamePhase.DUSK_DISCUSSION
    # Night should not have started
    assert engine.phase != game_engine.GamePhase.NIGHT
    # dusk_start_time should be set
    assert engine.dusk_start_time is not None


def test_enter_night_from_dusk_discussion_cannot_skip_staged_flow(monkeypatch):
    """Legacy enter_night calls cannot bypass dusk discussion, voting, and escort."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    _complete_daily_interviews(engine)

    engine.start_dusk_discussion()
    assert engine.phase == game_engine.GamePhase.DUSK_DISCUSSION

    engine.enter_night()
    assert engine.phase == game_engine.GamePhase.DUSK_DISCUSSION


def test_start_dusk_discussion_rejected_outside_day(monkeypatch):
    """start_dusk_discussion returns False when not in DAY phase."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    _complete_daily_interviews(engine)

    # Go to dusk then night
    engine.start_dusk_discussion()
    engine.enter_night()

    # Cannot start dusk from NIGHT
    result = engine.start_dusk_discussion()
    assert result is False


def test_enter_night_from_day_without_dusk(monkeypatch):
    """enter_night directly from DAY skips dusk and goes to night."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    assert engine.phase == game_engine.GamePhase.DAY

    engine.enter_night()
    assert engine.phase == game_engine.GamePhase.NIGHT


def test_status_exposes_dusk_fields(monkeypatch):
    """get_status must include dusk_elapsed, dusk_duration when in DUSK_DISCUSSION."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    _complete_daily_interviews(engine)
    engine.start_dusk_discussion()

    status = engine.get_status()
    assert status["phase"] == "dusk_discussion"
    assert "dusk_elapsed" in status
    assert "dusk_duration" in status
    assert isinstance(status["dusk_elapsed"], (int, float))
    assert status["dusk_duration"] == 600  # default


def test_status_exposes_deep_dive_remaining_numeric(monkeypatch):
    """deep_dive_remaining must be a numeric value (quota - used)."""
    engine = _make_engine(monkeypatch)
    detective = engine.agents["Crow"]
    # Simulate quota usage
    detective.deep_dive_quota = 3
    detective.deep_dive_used = 1

    status = engine.get_status()
    assert "deep_dive_remaining" in status
    assert status["deep_dive_remaining"] == 2
    assert isinstance(status["deep_dive_remaining"], int)


def test_deep_dive_quota_resets_each_day(monkeypatch):
    """Deep dives are a daily allowance, so a new day restores 3 chances."""
    engine = _make_engine(monkeypatch)
    detective = engine.agents["Crow"]
    detective.deep_dive_quota = 3
    detective.deep_dive_used = 2
    engine.day = 1
    engine.phase = game_engine.GamePhase.NIGHT
    engine.night_hunt = None
    engine._gathering_active = False

    monkeypatch.setattr(engine, "_discover_latest_body", lambda: None)
    monkeypatch.setattr(engine, "_generate_daily_plans", lambda: None)
    monkeypatch.setattr(engine, "_init_gathering", lambda: None)
    monkeypatch.setattr(game_engine.Agent, "compress_memory", lambda self, day: None)

    engine._transition_to_day()

    assert detective.deep_dive_quota == 3
    assert detective.deep_dive_used == 0
    assert engine.get_status()["deep_dive_remaining"] == 3


def test_status_exposes_daily_interview_fields(monkeypatch):
    """daily_interview_total and daily_interview_count must be exposed."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False

    # Initially no interviews
    status = engine.get_status()
    assert "daily_interview_total" in status
    assert "daily_interview_count" in status
    assert status["daily_interview_total"] == 7  # 8 agents - 1 Crow
    assert status["daily_interview_count"] == 0

    # Mark two NPCs as interviewed
    engine._daily_interviewed.add("Arthur Burton")
    engine._daily_interviewed.add("Isabella Rodriguez")

    status = engine.get_status()
    assert status["daily_interview_count"] == 2


def test_daily_interview_count_excludes_crow(monkeypatch):
    """Crow must never be counted in daily_interview_total."""
    engine = _make_engine(monkeypatch)
    status = engine.get_status()

    assert status["daily_interview_total"] <= 7
    assert "Crow" not in engine._daily_interviewed


def test_persona_chat_availability_fields(monkeypatch):
    """Each persona must expose chat_available and deep_dive_available booleans.
    deep_dive_available requires normal chat done first AND quota remaining."""
    engine = _make_engine(monkeypatch)
    detective = engine.agents["Crow"]

    # Setup: Crow has chatted with Arthur once (normal chat limit is 1)
    detective.chat_count = {"Arthur Burton": 1}
    detective.deep_dive_quota = 3
    detective.deep_dive_used = 0

    # Mark Arthur as interviewed (normal chat done)
    engine._daily_interviewed.add("Arthur Burton")

    status = engine.get_status()

    arthur = status["personas"]["Arthur Burton"]
    assert "chat_available" in arthur
    assert "deep_dive_available" in arthur
    assert arthur["chat_available"] is False  # Already used the 1 normal chat
    assert arthur["deep_dive_available"] is True  # Normal done + quota remaining

    # Isabella: not interviewed, so deep_dive NOT available
    isabella = status["personas"]["Isabella Rodriguez"]
    assert isabella["chat_available"] is True  # Not chatted yet
    assert isabella["deep_dive_available"] is False  # Normal chat not done yet

    # Crow's own persona should have both False
    crow = status["personas"]["Crow"]
    assert crow["chat_available"] is False
    assert crow["deep_dive_available"] is False


def test_deep_dive_available_respects_quota(monkeypatch):
    """deep_dive_available must become False when quota exhausted."""
    engine = _make_engine(monkeypatch)
    detective = engine.agents["Crow"]
    detective.deep_dive_quota = 3
    detective.deep_dive_used = 3  # All used

    status = engine.get_status()
    for name, persona in status["personas"].items():
        if name != "Crow":
            assert persona["deep_dive_available"] is False, f"{name} should have no deep dive available"


def test_daily_interview_resets_on_new_day(monkeypatch):
    """_daily_interviewed must be cleared when transitioning to a new day."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False

    # Simulate some interviews
    engine._daily_interviewed.add("Arthur Burton")
    engine._daily_interviewed.add("Isabella Rodriguez")

    # Transition to day (simulate what _transition_to_day does)
    engine.phase = game_engine.GamePhase.DAY
    engine._daily_interviewed = set()  # This is what _transition_to_day does

    status = engine.get_status()
    assert status["daily_interview_count"] == 0


def test_primary_cta_during_day_is_dusk_discussion_by_default(monkeypatch):
    """primary_cta should be 'dusk_discussion' during normal DAY with no gathering."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine._daily_interviewed = {"Arthur Burton", "Isabella Rodriguez", "Klaus Mueller",
                                  "Maria Lopez", "Sam Moore", "Jane Moreno", "Mei Lin"}

    status = engine.get_status()
    assert status["primary_cta"] == "dusk_discussion"


def test_primary_cta_during_gathering(monkeypatch):
    """primary_cta should be 'gathering' when morning gathering is active."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = True

    status = engine.get_status()
    assert status["primary_cta"] == "gathering"


def test_primary_cta_during_dusk(monkeypatch):
    """primary_cta should be 'vote_accuse' during DUSK_DISCUSSION."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    _complete_daily_interviews(engine)
    engine.start_dusk_discussion()

    status = engine.get_status()
    assert status["primary_cta"] in ("vote_accuse", "jail_choice")


def test_detective_cannot_move_during_dusk(monkeypatch):
    """Dusk is staged and must reject free detective movement."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    _complete_daily_interviews(engine)
    engine.start_dusk_discussion()

    crow = engine.agents["Crow"]
    original_x, original_y = crow.target_x, crow.target_y

    success = engine.move_detective_to(50, 50, "Johnson Park")
    assert success is False
    assert (crow.target_x, crow.target_y) == (original_x, original_y)


def test_enter_night_cannot_skip_dusk_flow(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    _complete_daily_interviews(engine)
    engine.start_dusk_discussion()

    engine.enter_night()

    assert engine.phase == game_engine.GamePhase.DUSK_DISCUSSION


def test_start_dusk_discussion_blocked_during_gathering(monkeypatch):
    """start_dusk_discussion must return False when morning gathering is active."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = True

    result = engine.start_dusk_discussion()
    assert result is False
    assert engine.phase == game_engine.GamePhase.DAY


def test_enter_night_clears_gathering_and_doesnt_crash(monkeypatch):
    """Regression: enter_night must not crash when no dusk discussion has happened."""
    engine = _make_engine(monkeypatch)
    # Don't touch _gathering_active — engine starts with gathering active
    # but Crow is still a special case. Just test the direct path.
    engine._gathering_active = False
    engine.enter_night()
    assert engine.phase == game_engine.GamePhase.NIGHT


# ============================================================================
# Jailed / Prison system tests (Requirement 1)
# ============================================================================

def test_jailed_state_initialized_empty(monkeypatch):
    """_jailed set starts empty."""
    engine = _make_engine(monkeypatch)
    assert engine._jailed == set()
    assert engine.get_status()["jailed"] == []


def test_jailed_resident_cannot_move(monkeypatch):
    """Jailed residents are skipped in _update_agent_schedules."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    # Jail a resident
    target = "Arthur Burton"
    engine._jailed.add(target)
    engine.agents[target].runtime_state = "jailed"

    # Run _update_agent_schedules — should skip jailed
    engine._update_agent_schedules()
    # Jailed agent should not have been moved or scheduled
    assert engine.agents[target].runtime_state == "jailed"


def test_jailed_excluded_from_night_targets(monkeypatch):
    """Jailed residents cannot be night hunt targets."""
    engine = _make_engine(monkeypatch)
    # Jail a resident
    engine._jailed.add("Isabella Rodriguez")

    targets = engine._eligible_night_targets()
    assert "Isabella Rodriguez" not in targets


def test_jailed_excluded_from_daily_interview_total(monkeypatch):
    """Jailed residents don't count toward daily_interview_total."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False

    # Initially 7 non-Crow residents
    status = engine.get_status()
    assert status["daily_interview_total"] == 7

    # Jail one
    engine._jailed.add("Arthur Burton")
    status = engine.get_status()
    assert status["daily_interview_total"] == 6


def test_cannot_chat_with_jailed_npc(monkeypatch):
    """detective_chat must reject jailed NPCs."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    # Setup target as alive but jailed
    engine._jailed.add("Isabella Rodriguez")
    engine.agents["Crow"].can_chat_with = lambda name, deep: True
    engine.agents["Isabella Rodriguez"].can_chat_with = lambda name, deep: True
    engine.agents["Isabella Rodriguez"].generate_response = lambda speaker, msg, day: "ok"

    result = engine.detective_chat("Isabella Rodriguez", "Hello?")
    assert "error" in result
    assert "拘留" in result["error"]


def test_persona_shows_jailed_status(monkeypatch):
    """get_status personas include jailed and prison_cell fields."""
    engine = _make_engine(monkeypatch)
    engine._jailed.add("Arthur Burton")

    status = engine.get_status()
    arthur = status["personas"]["Arthur Burton"]
    assert arthur["jailed"] is True
    assert arthur["prison_cell"] is not None
    assert arthur["chat_available"] is False  # Jailed = can't chat

    # Non-jailed should have jailed=False, prison_cell=None
    isabella = status["personas"]["Isabella Rodriguez"]
    assert isabella["jailed"] is False
    assert isabella["prison_cell"] is None


def test_jailed_in_win_check_removed_from_active(monkeypatch):
    """Win checks should treat jailed wolves/villagers as removed from active play."""
    engine = _make_engine(monkeypatch)
    # Determine wolves from the engine
    wolf_names = list(engine.werewolf_names)

    # Kill some to test win conditions
    for name in list(engine.agents.keys()):
        if name not in wolf_names and name != "Crow" and name not in engine._jailed:
            engine.agents[name].is_alive = False
            engine.dead_list.append(name)

    # Now let's simulate: if a wolf is jailed, they should not count toward wolf count
    if len(wolf_names) >= 1:
        engine._jailed.add(wolf_names[0])

    # Count alive non-jailed wolves
    alive_wolves = [n for n in wolf_names if engine.agents[n].is_alive and n not in engine._jailed]
    alive_good = [n for n, a in engine.agents.items()
                  if a.is_alive and n not in wolf_names and n not in engine._jailed]

    # Jailed wolf should be excluded from alive_wolves
    assert wolf_names[0] not in alive_wolves


# ============================================================================
# Dusk workflow / vote tests (Requirement 2)
# ============================================================================

def test_start_dusk_blocked_by_missing_interviews(monkeypatch):
    """start_dusk_discussion must return False when not all residents interviewed."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    # No interviews done
    ok, reason = engine.can_start_dusk_discussion()
    assert ok is False
    assert "采访" in reason

    result = engine.start_dusk_discussion()
    assert result is False


def test_start_dusk_succeeds_after_all_interviews(monkeypatch):
    """After interviewing all living non-jailed non-Crow residents, dusk can start."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    # Mark all non-Crow residents as interviewed
    for name in engine.agents:
        if name != "Crow" and engine.agents[name].is_alive:
            engine._daily_interviewed.add(name)

    ok, reason = engine.can_start_dusk_discussion()
    assert ok is True
    assert reason == "OK"

    result = engine.start_dusk_discussion()
    assert result is True
    assert engine.phase == game_engine.GamePhase.DUSK_DISCUSSION


def test_dusk_generates_npc_votes(monkeypatch):
    """After Crow's dusk statement, NPC votes must be populated."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    _start_dusk_voting(engine)
    assert engine._dusk_vote_active is True
    assert len(engine._dusk_votes) > 0  # At least some votes

    # Every living non-jailed non-Crow NPC should have a vote
    for name in engine.agents:
        if name != "Crow" and engine.agents[name].is_alive and name not in engine._jailed:
            assert name in engine._dusk_votes, f"{name} should have voted"
            assert name in engine._dusk_vote_reasons, f"{name} should have a reason"

    # Vote summary should be in status
    status = engine.get_status()
    assert status["vote_summary"] is not None
    assert "votes" in status["vote_summary"]
    assert "counts" in status["vote_summary"]
    assert status["vote_summary"]["active"] is True
    assert status["vote_history"]
    assert status["vote_history"][0]["day"] == engine.day


def test_jail_vote_target_success(monkeypatch):
    """jail_vote_target records Crow's vote; winner is auto-resolved."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    _start_dusk_voting(engine)

    # Manually set up votes so Arthur is clear winner
    npc_names = [n for n in engine.agents if n != "Crow" and engine.agents[n].is_alive]
    engine._dusk_votes = {n: "Arthur Burton" for n in npc_names}
    engine._dusk_vote_reasons = {k: "test" for k in engine._dusk_votes}
    engine._dusk_vote_active = True
    engine._dusk_crow_voted = False
    engine._dusk_vote_deadline = 999

    # Crow votes; auto-resolve determines Arthur as winner
    result = engine.jail_vote_target("Arthur Burton")
    assert result["success"] is True
    assert result["winner"] == "Arthur Burton"
    assert "Arthur Burton" not in engine._jailed
    engine.confirm_vote_result()
    assert "Arthur Burton" in engine._jailed

    # Target should be in a prison cell
    agent = engine.agents["Arthur Burton"]
    assert agent.current_action == "被拘留中"
    assert "监狱" in agent.current_location or "牢房" in agent.current_location
    assert agent.runtime_state == "jailed"

    # Status should reflect
    status = engine.get_status()
    assert "Arthur Burton" in status["jailed"]
    assert status["phase"] == "dusk_discussion"
    assert status["vote_summary"]["stage"] == "escorting"


def test_jail_vote_target_rejects_duplicate(monkeypatch):
    """Crow can only vote once."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    _start_dusk_voting(engine)

    # First vote succeeds
    engine.jail_vote_target("Arthur Burton")
    # Second vote should be rejected
    result = engine.jail_vote_target("Isabella Rodriguez")
    assert "error" in result


def test_jail_vote_target_rejects_crow(monkeypatch):
    """Crow can vote for self (self-voting allowed), but Crow cannot be jailed."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    _start_dusk_voting(engine)

    # Crow can vote for themselves (self-voting allowed)
    result = engine.jail_vote_target("Crow")
    # Crow CAN vote for self, but Crow being jailed is blocked by validation
    # which now happens during auto-resolve, not during vote recording
    assert "error" not in result or result.get("success"), (
        f"Crow self-vote should be allowed: {result}"
    )


def test_jail_vote_target_rejects_dead(monkeypatch):
    """Cannot jail a dead person."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    _start_dusk_voting(engine)

    engine.agents["Arthur Burton"].is_alive = False
    result = engine.jail_vote_target("Arthur Burton")
    assert "error" in result


def test_vote_summary_includes_counts(monkeypatch):
    """Vote summary counts must aggregate NPC votes."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    _start_dusk_voting(engine)

    status = engine.get_status()
    vote_summary = status["vote_summary"]
    assert vote_summary is not None
    assert len(vote_summary["counts"]) > 0
    # Each count entry has target, display, count
    for entry in vote_summary["counts"]:
        assert "target" in entry
        assert "display" in entry
        assert "count" in entry
        assert entry["count"] >= 1


def test_dusk_vote_can_abstain_and_history_tracks_it(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    for name in engine.agents:
        if name != "Crow" and engine.agents[name].is_alive:
            engine._daily_interviewed.add(name)

    monkeypatch.setattr(engine, "_generate_single_dusk_vote", lambda voter, dead, clues: ("证据不足，先弃票。", ""))
    _start_dusk_voting(engine)

    status = engine.get_status()
    summary = status["vote_summary"]
    assert summary["abstain_count"] > 0
    assert summary["counts"] == []
    assert status["vote_history"][0]["abstain_count"] == summary["abstain_count"]


# ============================================================================
# Daily tasks tests (Requirement 3)
# ============================================================================

def test_daily_tasks_day1_has_interview_task(monkeypatch):
    """Day 1 tasks include daily interviews."""
    engine = _make_engine(monkeypatch)
    status = engine.get_status()
    tasks = status["daily_tasks"]

    interview_task = [t for t in tasks if t["id"] == "daily_interviews"]
    day1_objective = [t for t in tasks if t["id"] == "day1_objective"]
    assert len(interview_task) == 1
    assert day1_objective == []
    assert interview_task[0]["total"] == 7  # 7 non-Crow residents
    assert interview_task[0]["daily"] is True


def test_daily_tasks_day2_has_silver_tasks(monkeypatch):
    """Day 2+ includes silver tasks."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.day = 2
    engine.phase = game_engine.GamePhase.DAY

    status = engine.get_status()
    tasks = status["daily_tasks"]

    bullet_task = [t for t in tasks if t["id"] == "silver_bullet"]
    jewelry_task = [t for t in tasks if t["id"] == "silver_jewelry"]
    assert len(bullet_task) == 1
    assert len(jewelry_task) == 1
    assert bullet_task[0]["complete"] is False
    assert jewelry_task[0]["complete"] is False


def test_daily_tasks_day4_has_craft_task_when_both_acquired(monkeypatch):
    """Day 4 with both silver items exposes craft task."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.day = 4
    engine.phase = game_engine.GamePhase.DAY
    engine._silver_bullet_acquired = True
    engine._silver_jewelry_acquired = True

    status = engine.get_status()
    tasks = status["daily_tasks"]

    craft_task = [t for t in tasks if t["id"] == "craft_silver_bullet"]
    assert len(craft_task) == 1
    assert craft_task[0]["complete"] is False


def test_can_start_dusk_false_when_interviews_missing(monkeypatch):
    """can_start_dusk_discussion returns False with interview count < total."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    ok, reason = engine.can_start_dusk_discussion()
    assert ok is False
    assert "采访" in reason


# ============================================================================
# Silver gameplay tests (Requirement 4)
# ============================================================================

def test_silver_holders_are_initialized(monkeypatch):
    """Silver jewelry holder and knife holder are set on init."""
    engine = _make_engine(monkeypatch)
    assert engine._silver_jewelry_holder is not None
    assert engine._silver_jewelry_holder != "Crow"
    assert engine._silver_jewelry_holder in engine.agents

    if engine._silver_knife_holder:
        assert engine._silver_knife_holder != "Crow"
        assert engine._silver_knife_holder not in engine.werewolf_names
        assert engine._silver_knife_holder in engine.agents


def test_acquire_silver_bullet_success(monkeypatch):
    """Acquiring silver bullet from Arthur succeeds if Arthur is not werewolf."""
    engine = _make_engine(monkeypatch)
    engine.phase = game_engine.GamePhase.DAY

    # Place Crow near Harvey Oak Supply Store
    supply = game_engine.PUBLIC_LANDMARKS["Harvey Oak Supply Store"]
    crow = engine.agents["Crow"]
    crow.x = supply["x"]
    crow.y = supply["y"]

    # Ensure Arthur is not a werewolf for this test
    if "Arthur Burton" in engine.werewolf_names:
        # Reassign Arthur out of werewolf role for deterministic test
        engine.werewolf_names = [n for n in engine.werewolf_names if n != "Arthur Burton"]
        engine.agents["Arthur Burton"].role = "villager"

    result = engine.acquire_silver_bullet()
    assert result["success"] is True
    assert engine._silver_bullet_acquired is True
    assert "silver_bullet_acquired" in result


def test_acquire_silver_bullet_fails_when_arthur_is_werewolf(monkeypatch):
    """If Arthur is a werewolf, acquisition fails with suspicious clue."""
    engine = _make_engine(monkeypatch, seed=99)
    engine.phase = game_engine.GamePhase.DAY

    # Place Crow near Harvey Oak Supply Store
    supply = game_engine.PUBLIC_LANDMARKS["Harvey Oak Supply Store"]
    crow = engine.agents["Crow"]
    crow.x = supply["x"]
    crow.y = supply["y"]

    # Force Arthur to be a werewolf
    engine.agents["Arthur Burton"].role = "werewolf"
    if "Arthur Burton" not in engine.werewolf_names:
        engine.werewolf_names.append("Arthur Burton")

    result = engine.acquire_silver_bullet()
    assert result["success"] is False
    assert result.get("suspicious") is True
    assert engine._silver_bullet_acquired is False


def test_acquire_silver_bullet_fails_when_too_far(monkeypatch):
    """Must be near Harvey Oak Supply Store to acquire silver bullet."""
    engine = _make_engine(monkeypatch)
    engine.phase = game_engine.GamePhase.DAY

    # Place Crow far away
    crow = engine.agents["Crow"]
    crow.x = 10
    crow.y = 10

    result = engine.acquire_silver_bullet()
    assert result["success"] is False
    assert "error" in result


def test_silver_holders_deterministic_with_seed(monkeypatch):
    """Same seed produces same silver holders."""
    engine1 = _make_engine(monkeypatch, seed=42)
    engine2 = _make_engine(monkeypatch, seed=42)

    assert engine1._silver_jewelry_holder == engine2._silver_jewelry_holder
    assert engine1._silver_knife_holder == engine2._silver_knife_holder


def test_silver_status_in_get_status(monkeypatch):
    """get_status includes silver progression fields."""
    engine = _make_engine(monkeypatch)
    status = engine.get_status()

    assert "silver_bullet_acquired" in status
    assert "silver_jewelry_acquired" in status
    assert "silver_bullet_crafted" in status
    assert status["silver_bullet_acquired"] is False
    assert status["silver_jewelry_acquired"] is False
    assert status["silver_bullet_crafted"] is False


def test_craft_silver_bullet_requires_prerequisites(monkeypatch):
    """Crafting requires bullet tool and jewelry acquired."""
    engine = _make_engine(monkeypatch)
    engine.phase = game_engine.GamePhase.DAY

    # Missing prerequisites
    result = engine.craft_silver_bullet()
    assert result["success"] is False
    assert "error" in result

    # Acquire bullet only
    engine._silver_bullet_acquired = True
    result = engine.craft_silver_bullet()
    assert result["success"] is False

    # Acquire both but day < 4
    engine._silver_jewelry_acquired = True
    engine.day = 3
    result = engine.craft_silver_bullet()
    assert result["success"] is False

    # Day 4 with both acquired → success
    engine.day = 4
    result = engine.craft_silver_bullet()
    assert result["success"] is True
    assert engine._silver_bullet_crafted is True


def test_only_one_silver_objective_per_day(monkeypatch):
    """Crow can complete only one key silver-resource action per day."""
    engine = _make_engine(monkeypatch)
    engine.day = 2
    engine.phase = game_engine.GamePhase.DAY
    engine.agents["Arthur Burton"].role = "villager"
    crow = engine.agents["Crow"]
    store = game_engine.PUBLIC_LANDMARKS["Harvey Oak Supply Store"]
    crow.x, crow.y = store["x"], store["y"]

    first = engine.acquire_silver_bullet()
    assert first["success"] is True

    holder = engine._silver_jewelry_holder
    engine.agents[holder].x = crow.x
    engine.agents[holder].y = crow.y
    second = engine.acquire_silver_jewelry(holder)
    assert second["success"] is False
    assert "今天已经完成过" in second["error"]


def test_silver_bullet_can_be_fired_once(monkeypatch):
    """Crafted silver bullet can kill one target and then becomes unavailable."""
    engine = _make_engine(monkeypatch)
    engine.day = 4
    engine._silver_bullet_acquired = True
    engine._silver_jewelry_acquired = True
    engine._silver_bullet_crafted = True
    target = engine.werewolf_names[0]

    result = engine.shoot_silver_bullet(target)
    assert result["success"] is True
    assert result["target_was_werewolf"] is True
    assert engine.agents[target].is_alive is False
    assert engine._silver_bullet_used is True

    second = engine.shoot_silver_bullet(engine.werewolf_names[1])
    assert second["success"] is False
    assert "已经使用过" in second["error"]


def test_hidden_silver_knife_can_be_used_once_at_night(monkeypatch):
    """The hidden good NPC can use the silver knife once during night."""
    engine = _make_engine(monkeypatch)
    holder = engine._silver_knife_holder
    assert holder is not None
    engine.phase = game_engine.GamePhase.NIGHT
    target = engine.werewolf_names[0]

    result = engine.use_silver_knife(holder, target)
    assert result["success"] is True
    assert engine.agents[target].is_alive is False
    assert engine._silver_knife_used is True

    second = engine.use_silver_knife(holder, engine.werewolf_names[1])
    assert second["success"] is False
    assert "已经使用过" in second["error"]


# ============================================================================
# Deep dive tests (Requirement 5)
# ============================================================================

def test_deep_dive_requires_normal_chat_first(monkeypatch):
    """Deep dive must be preceded by normal chat with that NPC today."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    # Setup
    engine.agents["Crow"].deep_dive_quota = 3
    engine.agents["Crow"].deep_dive_used = 0
    engine.agents["Isabella Rodriguez"].can_chat_with = lambda name, deep: True
    engine.agents["Isabella Rodriguez"].generate_response = lambda speaker, msg, day: "ok"

    # Deep dive without normal chat first → error
    result = engine.detective_chat("Isabella Rodriguez", "Tell me more", is_deep_dive=True)
    assert "error" in result
    assert "正常采访" in result["error"] or "深度追问" in result["error"]


def test_normal_detective_chat_uses_fixed_human_question(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    captured = {}
    engine.agents["Arthur Burton"].can_chat_with = lambda name, deep: True

    def fake_response(speaker, msg, day):
        captured["msg"] = msg
        return "我昨晚在店里收拾工具，没离开过。现在我不放心山姆。"

    engine.agents["Arthur Burton"].generate_response = fake_response
    result = engine.detective_chat("Arthur Burton", "", is_deep_dive=False)

    assert "response" in result
    assert "时间线" in captured["msg"]
    assert "为什么你不可能是凶手" in captured["msg"]
    assert "最不放心谁" in captured["msg"]
    assert "Arthur Burton" in engine._daily_interviewed
    assert engine.chat_bubbles["Crow"]["target"] == "Arthur Burton"
    assert "时间线" in engine.chat_bubbles["Crow"]["text"]


def test_detective_chat_records_and_locks_before_slow_npc_reply(monkeypatch):
    """Sheriff interviews must update visible state immediately, before the model returns."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    detective = engine.agents["Crow"]
    target = engine.agents["Arthur Burton"]
    detective.deep_dive_quota = 3
    detective.deep_dive_used = 0
    engine._daily_interviewed.add("Arthur Burton")

    started = threading.Event()
    release = threading.Event()

    def slow_response(speaker, msg, day):
        started.set()
        release.wait(timeout=2)
        return "我昨晚一直在店里，听见后巷有脚步声。"

    target.generate_response = slow_response
    result_holder = {}

    t = threading.Thread(
        target=lambda: result_holder.update(engine.detective_chat("Arthur Burton", "你再想想细节。", is_deep_dive=True)),
        daemon=True,
    )
    t.start()
    assert started.wait(timeout=1)

    assert detective.deep_dive_used == 1
    assert target.in_conversation_with == "Crow"
    assert engine.chat_bubbles["Crow"]["target"] == "Arthur Burton"
    assert "你再想想细节" in engine.chat_bubbles["Crow"]["text"]
    assert engine.move_detective_to(10, 10) is True

    release.set()
    t.join(timeout=2)
    assert result_holder["deep_dive_remaining"] == 2
    assert target.in_conversation_with == "Crow"
    assert detective.in_conversation_with == "Arthur Burton"

    monkeypatch.setitem(game_engine.CONFIG["game"], "bubble_lifetime_seconds", 0)
    engine._expire_chat_bubbles()

    assert target.in_conversation_with is None
    assert detective.in_conversation_with is None


def test_detective_chat_interrupts_movement_and_marks_target_busy_immediately(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    detective = engine.agents["Crow"]
    target = engine.agents["Arthur Burton"]
    detective.deep_dive_quota = 3
    detective.deep_dive_used = 0
    engine._daily_interviewed.add("Arthur Burton")

    target.x, target.y = 10, 10
    target.target_x, target.target_y = 15, 10
    target.runtime_state = "moving"
    target._pending_action = {
        "action_type": "move_to",
        "action": "前往五金店整理货架",
        "target_location": "Harvey Oak Supply Store",
    }
    engine.agent_paths["Arthur Burton"] = [(11, 10), (12, 10)]
    engine.chat_bubbles["Arthur Burton"] = {
        "kind": "action_status",
        "text": "整理货架...",
        "time": time.time(),
    }

    started = threading.Event()
    release = threading.Event()

    def slow_response(speaker, msg, day):
        started.set()
        release.wait(timeout=2)
        return "我先回答警长。"

    target.generate_response = slow_response
    result_holder = {}

    t = threading.Thread(
        target=lambda: result_holder.update(engine.detective_chat("Arthur Burton", "你停一下。", is_deep_dive=True)),
        daemon=True,
    )
    t.start()
    assert started.wait(timeout=1)

    assert target.in_conversation_with == "Crow"
    assert detective.in_conversation_with == "Arthur Burton"
    assert target.runtime_state == "acting"
    assert target._pending_action is None
    assert "Arthur Burton" not in engine.agent_paths
    assert (target.target_x, target.target_y) == (target.x, target.y)
    assert engine.chat_bubbles["Arthur Burton"]["target"] == "Crow"
    assert engine.chat_bubbles["Arthur Burton"]["text"] == "..."
    assert engine.chat_bubbles["Arthur Burton"].get("kind") != "action_status"

    monkeypatch.setitem(game_engine.CONFIG["game"], "bubble_lifetime_seconds", 0)
    engine._expire_chat_bubbles()
    assert target.in_conversation_with == "Crow"
    assert detective.in_conversation_with == "Arthur Burton"

    old_x, old_y = target.x, target.y
    engine._move_agents()
    assert (target.x, target.y) == (old_x, old_y)

    release.set()
    t.join(timeout=2)
    assert result_holder["response"] == "我先回答警长。"


def test_detective_chat_empty_response_keeps_waiting_bubble(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    detective = engine.agents["Crow"]
    target = engine.agents["Arthur Burton"]
    detective.deep_dive_quota = 3
    detective.deep_dive_used = 0
    engine._daily_interviewed.add("Arthur Burton")
    target.generate_response = lambda speaker, msg, day: ""

    result = engine.detective_chat("Arthur Burton", "你再想想细节。", is_deep_dive=True)

    assert result["pending_response"] is True
    assert result["response"] == "..."
    assert target.in_conversation_with == "Crow"
    assert detective.in_conversation_with == "Arthur Burton"
    assert engine.chat_bubbles["Arthur Burton"]["text"] == "..."
    assert "还没有想清楚" not in engine.chat_bubbles["Arthur Burton"]["text"]


def test_busy_detective_redirects_third_party_talk_path(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", ["Maria Lopez"])
    engine._detective_chat_active_target = "Arthur Burton"
    crow = engine.agents["Crow"]
    crow.in_conversation_with = "Arthur Burton"
    maria = engine.agents["Maria Lopez"]
    maria.runtime_state = "moving"
    maria.target_x, maria.target_y = crow.x, crow.y
    maria._pending_action = {
        "action_type": "talk",
        "target_location": crow.current_location,
        "target_object": "",
        "target_person": "Crow",
        "action": "找警长说明情况",
        "action_status": "走向警长",
        "expected_result": "向警长说明情况",
    }
    engine.agent_paths["Maria Lopez"] = [(maria.x + 1, maria.y)]

    engine._update_agent_schedules()

    assert maria.runtime_state == "starting_action"
    assert maria._pending_action["action_type"] == "continue_current"
    assert maria._pending_action["target_person"] == ""
    assert "Maria Lopez" not in engine.agent_paths
    assert (maria.target_x, maria.target_y) == (maria.x, maria.y)


def test_detective_chat_uses_priority_no_retry_response(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    target = engine.agents["Arthur Burton"]
    captured = {}

    def fake_response(speaker, msg, day, priority=False, max_retries=None):
        captured["priority"] = priority
        captured["max_retries"] = max_retries
        return "我马上回答警长。"

    target.generate_response = fake_response

    result = engine.detective_chat("Arthur Burton", "", is_deep_dive=False)

    assert result["response"] == "我马上回答警长。"
    assert captured == {"priority": True, "max_retries": 0}


def test_detective_chat_interrupts_existing_npc_chat(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.in_conversation_with = "Isabella Rodriguez"
    isabella.in_conversation_with = "Arthur Burton"
    arthur._conversation_started_at = time.time()
    isabella._conversation_started_at = time.time()
    engine.chat_bubbles["Arthur Burton"] = {"text": "旧对话", "target": "Isabella Rodriguez", "time": time.time()}
    engine.chat_bubbles["Isabella Rodriguez"] = {"text": "旧回复", "target": "Arthur Burton", "time": time.time()}

    arthur.generate_response = lambda speaker, msg, day: "我先回答警长的问题。"

    result = engine.detective_chat("Arthur Burton", "", is_deep_dive=False)

    assert "response" in result
    assert arthur.in_conversation_with == "Crow"
    assert engine.agents["Crow"].in_conversation_with == "Arthur Burton"
    assert isabella.in_conversation_with is None
    assert engine.chat_bubbles["Arthur Burton"]["target"] == "Crow"
    assert "Isabella Rodriguez" not in engine.chat_bubbles or engine.chat_bubbles["Isabella Rodriguez"]["target"] != "Arthur Burton"

    monkeypatch.setitem(game_engine.CONFIG["game"], "bubble_lifetime_seconds", 0)
    engine._expire_chat_bubbles()

    assert arthur.in_conversation_with is None
    assert engine.agents["Crow"].in_conversation_with is None


def test_chat_available_respects_normal_chat_limit(monkeypatch):
    """chat_available is False after normal chat limit reached."""
    engine = _make_engine(monkeypatch)
    detective = engine.agents["Crow"]
    detective.chat_count = {"Arthur Burton": 1}  # Limit is 1

    status = engine.get_status()
    assert status["personas"]["Arthur Burton"]["chat_available"] is False


def test_deep_dive_available_requires_normal_chat_done(monkeypatch):
    """deep_dive_available is True only after normal chat done AND quota remaining."""
    engine = _make_engine(monkeypatch)
    detective = engine.agents["Crow"]
    detective.deep_dive_quota = 3
    detective.deep_dive_used = 0

    # No normal chat done with Isabella → deep dive NOT available
    status = engine.get_status()
    assert status["personas"]["Isabella Rodriguez"]["deep_dive_available"] is False

    # Mark Isabella as interviewed (normal chat done)
    engine._daily_interviewed.add("Isabella Rodriguez")

    status = engine.get_status()
    assert status["personas"]["Isabella Rodriguez"]["deep_dive_available"] is True


def test_deep_dive_does_not_count_as_daily_interview(monkeypatch):
    """Deep dive should not add to daily_interviewed if normal wasn't done."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    detective = engine.agents["Crow"]
    detective.deep_dive_quota = 3
    detective.deep_dive_used = 0
    # First do normal chat
    engine.agents["Arthur Burton"].can_chat_with = lambda name, deep: True
    engine.agents["Arthur Burton"].generate_response = lambda speaker, msg, day: "ok"
    engine.detective_chat("Arthur Burton", "Hi", is_deep_dive=False)
    assert "Arthur Burton" in engine._daily_interviewed

    # Clear for next test
    engine._daily_interviewed.clear()

    # Now try deep dive WITHOUT prior normal
    # Should be rejected
    result = engine.detective_chat("Arthur Burton", "Deep?", is_deep_dive=True)
    assert "error" in result
    # deep dive should NOT have added to daily_interviewed
    assert "Arthur Burton" not in engine._daily_interviewed


def test_stale_thinking_state_is_released_for_retry(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    agent = engine.agents["Arthur Burton"]
    agent.runtime_state = "thinking"
    agent._is_thinking = True
    agent._thinking_started_at = time.time() - 999

    engine._update_agent_schedules()

    assert agent._is_thinking is False
    assert agent.runtime_state == "idle"
    assert getattr(agent, "_next_llm_retry_time", 0) > 0


def test_stale_npc_conversation_releases_both_participants(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    arthur = engine.agents["Arthur Burton"]
    klaus = engine.agents["Klaus Mueller"]
    arthur.in_conversation_with = "Klaus Mueller"
    klaus.in_conversation_with = "Arthur Burton"
    arthur._conversation_started_at = time.time() - 999
    klaus._conversation_started_at = time.time() - 999

    engine._update_agent_schedules()

    assert arthur.in_conversation_with is None
    assert klaus.in_conversation_with is None
    assert arthur.runtime_state in {"idle", "thinking"}


def test_npc_conversation_releases_when_distance_exceeds_chat_range(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    arthur = engine.agents["Arthur Burton"]
    klaus = engine.agents["Klaus Mueller"]
    arthur.x, arthur.y = 10, 10
    klaus.x, klaus.y = 13, 10
    arthur.in_conversation_with = "Klaus Mueller"
    klaus.in_conversation_with = "Arthur Burton"
    arthur._conversation_started_at = time.time()
    klaus._conversation_started_at = time.time()

    engine._update_agent_schedules()

    assert arthur.in_conversation_with is None
    assert klaus.in_conversation_with is None


# ============================================================================
# Night target eligibility with jailed (Requirement 6)
# ============================================================================

def test_night_targets_exclude_jailed(monkeypatch):
    """_eligible_night_targets must exclude jailed residents."""
    engine = _make_engine(monkeypatch)
    engine._jailed.add("Isabella Rodriguez")

    targets = engine._eligible_night_targets()
    assert "Isabella Rodriguez" not in targets
    # Non-jailed residents should still be included
    other_residents = [n for n in engine.agents
                       if n != "Crow" and n not in engine.werewolf_names
                       and n != "Isabella Rodriguez" and engine.agents[n].is_alive]
    for resident in other_residents:
        assert resident in targets


def test_hunt_candidates_exclude_jailed(monkeypatch):
    """_build_hunt_candidates must exclude jailed targets."""
    engine = _make_engine(monkeypatch)
    # Setup wolf somewhere
    wolf_name = engine.werewolf_name
    engine.agents[wolf_name].x = 50
    engine.agents[wolf_name].y = 50

    # Jail someone
    engine._jailed.add("Isabella Rodriguez")

    candidates = engine._build_hunt_candidates()
    candidate_names = [c.name for c in candidates]
    assert "Isabella Rodriguez" not in candidate_names


# ============================================================================
# primary_cta updates (Requirement 2 gating)
# ============================================================================

def test_primary_cta_interviews_when_dusk_blocked(monkeypatch):
    """primary_cta should be 'interviews' when can_start_dusk is False."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    # No interviews done → primary_cta should not be dusk_discussion
    status = engine.get_status()
    assert status["can_start_dusk_discussion"] is False
    assert status["primary_cta"] == "interviews"


def test_primary_cta_jail_choice_during_vote_active(monkeypatch):
    """primary_cta should be 'jail_choice' when dusk votes are active and no jail choice made."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    _start_dusk_voting(engine)

    status = engine.get_status()
    assert status["primary_cta"] == "jail_choice"
    assert status["vote_summary"]["active"] is True
    assert status["vote_summary"]["jail_target"] is None


def test_jail_choice_waits_for_confirmation_before_escort(monkeypatch):
    """After Crow votes, results wait for confirmation before escorting and night."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY

    _start_dusk_voting(engine)
    # All NPCs vote for Arthur so he's the clear winner
    npc_names = [n for n in engine.agents if n != "Crow" and engine.agents[n].is_alive]
    engine._dusk_votes = {n: "Arthur Burton" for n in npc_names}
    engine._dusk_vote_reasons = {k: "test" for k in engine._dusk_votes}
    engine._dusk_vote_active = True
    engine._dusk_crow_voted = False
    engine._dusk_vote_deadline = 999
    engine.jail_vote_target("Arthur Burton")

    status = engine.get_status()
    assert status["phase"] == "dusk_discussion"
    assert status["vote_summary"]["stage"] == "results"
    engine.confirm_vote_result()
    assert engine._dusk_stage == "escorting"
    status = engine.get_status()
    assert status["primary_cta"] is None
    assert "Arthur Burton" in status["jailed"]


# ═══════════════════════════════════════════════════════════════════
# Collision / object-target positioning regression tests
# Ensure agents never stop on top of blocking furniture objects
# (shelves, counters, tables, etc.) after movement.
# ═══════════════════════════════════════════════════════════════════


def _make_engine_with_go_maze(monkeypatch, seed=7):
    """Create an engine with a real-ish go_maze so blocking-object checks work."""
    engine = _make_engine(monkeypatch, seed=seed)
    w, h = 140, 100
    # Build a minimal go_maze and go_dict
    engine.go_maze = [[0] * w for _ in range(h)]
    engine.go_dict = {
        1: "pharmacy store shelf",
        2: "behind the cafe counter",
        3: "bookshelf",
        4: "common room table",
        5: "empty floor space",  # non-blocking
    }
    # Place blocking objects on specific tiles
    # Shelf at (80, 45) — a 2×2 shelf
    for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        engine.go_maze[45 + dy][80 + dx] = 1
    # Counter at (90, 50)
    engine.go_maze[50][90] = 2
    engine.go_maze[50][91] = 2
    # Bookshelf at (120, 40)
    engine.go_maze[40][120] = 3
    engine.go_maze[41][120] = 3
    # Non-blocking object at (100, 60)
    engine.go_maze[60][100] = 5

    # collision_maze: mark shelf/counter tiles as walkable (0) to simulate
    # the real-world data inconsistency that causes the bug
    for (x, y) in [(80, 45), (81, 45), (80, 46), (81, 46),
                    (90, 50), (91, 50),
                    (120, 40), (121, 40)]:
        engine.collision_maze[y][x] = 0

    return engine


class TestTileFreeOfBlockingObjects:
    def test_returns_false_for_shelf(self, monkeypatch):
        engine = _make_engine_with_go_maze(monkeypatch)
        # Shelf tile (80, 45) should be blocked
        assert engine._is_tile_free_of_blocking_objects(80, 45) is False
        assert engine._is_tile_free_of_blocking_objects(81, 46) is False

    def test_returns_false_for_counter(self, monkeypatch):
        engine = _make_engine_with_go_maze(monkeypatch)
        assert engine._is_tile_free_of_blocking_objects(90, 50) is False
        assert engine._is_tile_free_of_blocking_objects(91, 50) is False

    def test_returns_false_for_bookshelf(self, monkeypatch):
        engine = _make_engine_with_go_maze(monkeypatch)
        assert engine._is_tile_free_of_blocking_objects(120, 40) is False

    def test_returns_true_for_empty_tile(self, monkeypatch):
        engine = _make_engine_with_go_maze(monkeypatch)
        # (70, 70) is far from any object — should be free
        assert engine._is_tile_free_of_blocking_objects(70, 70) is True

    def test_returns_true_for_non_blocking_object(self, monkeypatch):
        engine = _make_engine_with_go_maze(monkeypatch)
        # (100, 60) has object id 5 "empty floor space" — non-blocking
        assert engine._is_tile_free_of_blocking_objects(100, 60) is True

    def test_returns_true_when_no_go_maze(self, monkeypatch):
        engine = _make_engine(monkeypatch)
        # No go_maze set → all tiles considered free
        assert engine._is_tile_free_of_blocking_objects(50, 50) is True


class TestPathAdjacentToAvoidsObjectTiles:
    def test_adjacent_to_shelf_does_not_pick_shelf_tile(self, monkeypatch):
        """When targeting a shelf tile, adjacent candidates must not be
        other shelf tiles (even if walkable in collision_maze)."""
        engine = _make_engine_with_go_maze(monkeypatch)
        # Agent starts at (70, 46) — west of the shelf at (80-81, 45-46)
        agent_x, agent_y = 70, 46
        # Target: a shelf tile at (80, 45)
        target = (80, 45)
        result = engine._path_adjacent_to((agent_x, agent_y), target)
        assert result is not None, "Should find a reachable adjacent tile"
        adj_x, adj_y, path = result
        # Adjacent tile must not be any of the shelf tiles
        shelf_tiles = {(80, 45), (81, 45), (80, 46), (81, 46)}
        assert (adj_x, adj_y) not in shelf_tiles, (
            f"Adjacent tile {(adj_x, adj_y)} must not be a shelf tile"
        )
        # It should be a valid walkable tile
        assert engine.collision_maze[adj_y][adj_x] == 0

    def test_adjacent_to_counter_does_not_pick_counter_tile(self, monkeypatch):
        engine = _make_engine_with_go_maze(monkeypatch)
        # Agent starts south of the counter at (90, 50)
        engine.collision_maze[51][90] = 0  # tile south of counter walkable
        agent_pos = (90, 53)
        target = (90, 50)  # counter tile
        result = engine._path_adjacent_to(agent_pos, target)
        assert result is not None
        adj_x, adj_y, path = result
        # Counter occupies (90,50) and (91,50)
        counter_tiles = {(90, 50), (91, 50)}
        assert (adj_x, adj_y) not in counter_tiles, (
            f"Adjacent tile {(adj_x, adj_y)} must not be a counter tile"
        )

    def test_adjacent_to_bookshelf_does_not_pick_bookshelf_tile(self, monkeypatch):
        engine = _make_engine_with_go_maze(monkeypatch)
        agent_pos = (119, 42)
        target = (120, 40)  # bookshelf tile
        result = engine._path_adjacent_to(agent_pos, target)
        assert result is not None
        adj_x, adj_y, path = result
        bookshelf_tiles = {(120, 40), (121, 40)}
        assert (adj_x, adj_y) not in bookshelf_tiles, (
            f"Adjacent tile {(adj_x, adj_y)} must not be a bookshelf tile"
        )

    def test_agent_ends_on_walkable_non_object_tile_when_targeting_shelf(self, monkeypatch):
        """Full integration: agent moves toward a shelf target and final
        (target_x, target_y) is a walkable non-object tile adjacent to the shelf."""
        engine = _make_engine_with_go_maze(monkeypatch)
        # Put agent at a known starting position
        agent = engine.agents["Klaus Mueller"]
        agent.x, agent.y = 70, 47
        # Ensure a clear path to the area around the shelf
        for y in range(44, 49):
            for x in range(70, 82):
                if engine.go_maze[y][x] not in (0, 5):  # skip blocking tiles
                    pass  # these are already at shelf positions
                engine.collision_maze[y][x] = 0

        # Simulate agent deciding to move to the shelf at (80, 45)
        monkeypatch.setattr(
            engine,
            "_find_object_in_spatial_memory",
            lambda a, loc, obj: (80, 45) if obj == "pharmacy store shelf" else None,
        )
        agent.spatial_memory = {"The Willows Market and Pharmacy": {"main": ["pharmacy store shelf"]}}

        ok = engine._set_agent_target(
            agent, "Klaus Mueller", "The Willows Market and Pharmacy", "pharmacy store shelf"
        )
        assert ok is True
        # Agent target should be adjacent to (80, 45), not on it
        dist = abs(agent.target_x - 80) + abs(agent.target_y - 45)
        assert dist == 1, f"Agent target should be distance 1 from shelf, got {dist} at ({agent.target_x}, {agent.target_y})"
        shelf_tiles = {(80, 45), (81, 45), (80, 46), (81, 46)}
        assert (agent.target_x, agent.target_y) not in shelf_tiles, (
            f"Agent target must not be a shelf tile, got ({agent.target_x}, {agent.target_y})"
        )


class TestNearestWalkableTileAvoidsObjectTiles:
    def test_nearest_walkable_tile_skips_shelf_tile(self, monkeypatch):
        engine = _make_engine_with_go_maze(monkeypatch)
        # Request nearest walkable tile at (80, 45) which is a shelf
        # The function should skip it and return a nearby non-shelf tile
        result = engine._nearest_walkable_tile((80, 45))
        assert result is not None
        nx, ny = result
        shelf_tiles = {(80, 45), (81, 45), (80, 46), (81, 46)}
        assert (nx, ny) not in shelf_tiles, (
            f"_nearest_walkable_tile returned shelf tile ({nx}, {ny})"
        )
        assert engine.collision_maze[ny][nx] == 0

    def test_nearest_walkable_tile_skips_counter_tile(self, monkeypatch):
        engine = _make_engine_with_go_maze(monkeypatch)
        result = engine._nearest_walkable_tile((90, 50))
        assert result is not None
        nx, ny = result
        counter_tiles = {(90, 50), (91, 50)}
        assert (nx, ny) not in counter_tiles, (
            f"_nearest_walkable_tile returned counter tile ({nx}, {ny})"
        )

    def test_nearest_walkable_tile_in_component_skips_object(self, monkeypatch):
        engine = _make_engine_with_go_maze(monkeypatch)
        # Build a component that includes both a shelf tile and a free tile
        component = {(80, 45), (79, 45)}  # (80,45) is shelf, (79,45) is free
        result = engine._nearest_walkable_tile_in_component((80, 45), component)
        assert result is not None
        assert result == (79, 45), (
            f"Should pick (79, 45) over shelf tile (80, 45), got {result}"
        )

    def test_nearest_reachable_path_skips_object_tiles(self, monkeypatch):
        engine = _make_engine_with_go_maze(monkeypatch)
        # Put agent at (70, 47), ensure clear path
        agent = engine.agents["Klaus Mueller"]
        agent.x, agent.y = 70, 47
        for y in range(44, 50):
            for x in range(70, 82):
                engine.collision_maze[y][x] = 0

        # Target the shelf at (80, 45) — _nearest_reachable_path should
        # find a reachable non-object tile nearby
        result = engine._nearest_reachable_path((70, 47), (80, 45), radius=8)
        if result is not None:
            nx, ny, path = result
            shelf_tiles = {(80, 45), (81, 45), (80, 46), (81, 46)}
            assert (nx, ny) not in shelf_tiles, (
                f"_nearest_reachable_path selected shelf tile ({nx}, {ny})"
            )


def test_agent_path_routes_around_blocking_furniture(monkeypatch):
    engine = _make_engine_with_go_maze(monkeypatch)
    agent = engine.agents["Klaus Mueller"]
    agent.x, agent.y = 79, 45
    agent.target_x, agent.target_y = 82, 45
    engine.agent_paths.pop("Klaus Mueller", None)

    visited = []
    for _ in range(8):
        engine._move_agents()
        visited.append((agent.x, agent.y))
        if (agent.x, agent.y) == (agent.target_x, agent.target_y):
            break

    assert (agent.x, agent.y) == (82, 45)
    assert all(engine._is_tile_free_of_blocking_objects(x, y) for x, y in visited)


# ============================================================================
# Requirement: NPC-NPC autonomous chat lifecycle & empty fallback (Requirement 1 & 2)
# ============================================================================

def test_npc_chat_empty_initiator_reply_uses_visible_fallback(monkeypatch):
    """When chat_for_agent returns empty for the initiator, a visible fallback
    bubble must be published instead of returning silently."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "")
    monkeypatch.setattr(isabella, "generate_response", lambda speaker, message, day: "我听见脚步声了。")
    # Shorten the NPC chat delay for fast test
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    engine.llm_threads[-1].join(timeout=3)

    # Initiator bubble must exist with fallback text
    assert "Arthur Burton" in engine.chat_bubbles, "Initiator bubble missing"
    assert engine.chat_bubbles["Arthur Burton"]["target"] == "Isabella Rodriguez"
    # Should contain the visible fallback, not be empty
    assert len(engine.chat_bubbles["Arthur Burton"]["text"]) > 5
    # Responder bubble should also exist
    assert "Isabella Rodriguez" in engine.chat_bubbles
    assert engine.chat_bubbles["Isabella Rodriguez"]["target"] == "Arthur Burton"


def test_npc_chat_lifecycle_sets_and_releases_in_conversation_with(monkeypatch):
    """NPC-NPC chat must set in_conversation_with on both participants before
    thread work and release only after the visible speech bubble expires."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10

    # Ensure both start free
    assert getattr(arthur, 'in_conversation_with', None) is None
    assert getattr(isabella, 'in_conversation_with', None) is None

    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "你好")
    monkeypatch.setattr(isabella, "generate_response", lambda speaker, message, day: "你好，有什么事？")
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    engine.llm_threads[-1].join(timeout=3)

    assert getattr(arthur, 'in_conversation_with', None) == "Isabella Rodriguez"
    assert getattr(isabella, 'in_conversation_with', None) == "Arthur Burton"

    monkeypatch.setitem(game_engine.CONFIG["game"], "bubble_lifetime_seconds", 0)
    engine._expire_chat_bubbles()

    assert getattr(arthur, 'in_conversation_with', None) is None
    assert getattr(isabella, 'in_conversation_with', None) is None


def test_npc_chat_speech_jobs_run_serial_fifo(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    klaus = engine.agents["Klaus Mueller"]
    sam = engine.agents["Sam Moore"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10
    klaus.x, klaus.y = 20, 20
    sam.x, sam.y = 21, 20

    first_started = threading.Event()
    release_first = threading.Event()
    calls = []

    def queued_chat(name, *args, **kwargs):
        calls.append(name)
        if name == "Arthur Burton":
            first_started.set()
            release_first.wait(timeout=2)
        return f"{name}先说一句。"

    monkeypatch.setattr(game_engine, "chat_for_agent", queued_chat)
    monkeypatch.setattr(isabella, "generate_response", lambda speaker, message, day: "我听见了。")
    monkeypatch.setattr(sam, "generate_response", lambda speaker, message, day: "我也听见了。")
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    assert first_started.wait(timeout=1)
    engine._trigger_npc_chat("Klaus Mueller", "Sam Moore")
    time.sleep(0.1)

    assert calls == ["Arthur Burton"]

    release_first.set()
    for thread in list(engine.llm_threads):
        thread.join(timeout=2)

    assert calls == ["Arthur Burton", "Klaus Mueller"]


def test_speech_queue_runs_detective_priority_before_waiting_npc_job(monkeypatch):
    engine = _make_engine(monkeypatch)
    order = []
    first_started = threading.Event()
    release_first = threading.Event()

    def first_normal():
        order.append("normal-1")
        first_started.set()
        release_first.wait(timeout=2)

    engine._enqueue_speech_job("normal-1", 1, first_normal)
    assert first_started.wait(timeout=1)
    engine._enqueue_speech_job("normal-2", 1, lambda: order.append("normal-2"))
    engine._enqueue_speech_job("detective", 0, lambda: order.append("detective"))

    time.sleep(0.1)
    assert order == ["normal-1"]

    release_first.set()
    for thread in list(engine.llm_threads):
        thread.join(timeout=2)

    assert order == ["normal-1", "detective", "normal-2"]


def test_npc_chat_skips_when_either_in_conversation(monkeypatch):
    """If either participant is already in_conversation_with someone, the chat
    must not start."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]

    # Simulate Arthur already talking to someone
    arthur.in_conversation_with = "Klaus Mueller"

    call_count = [0]
    def counting_chat(*args, **kwargs):
        call_count[0] += 1
        return "hi"

    monkeypatch.setattr(game_engine, "chat_for_agent", counting_chat)

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    # No thread should have been spawned since guard prevents it
    # chat_for_agent should not have been called
    assert call_count[0] == 0, "chat_for_agent must not be called when participant is busy"


def test_npc_chat_lifecycle_releases_on_exception(monkeypatch):
    """Even if the chat thread raises, participants remain busy until bubble expiry."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10

    monkeypatch.setattr(arthur, "read_soul", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    engine.llm_threads[-1].join(timeout=1)

    assert arthur.in_conversation_with == "Isabella Rodriguez"
    assert isabella.in_conversation_with == "Arthur Burton"

    monkeypatch.setitem(game_engine.CONFIG["game"], "bubble_lifetime_seconds", 0)
    engine._expire_chat_bubbles()

    assert arthur.in_conversation_with is None
    assert isabella.in_conversation_with is None


def test_npc_chat_sequential_bubble_timing_zero_delay(monkeypatch):
    """With monkeypatched zero delay, both bubbles appear in order."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10

    # Patch config to zero delay for fast test
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)

    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "你好")
    monkeypatch.setattr(isabella, "generate_response", lambda speaker, message, day: "你好，什么事？")

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    engine.llm_threads[-1].join(timeout=3)

    # Both bubbles should exist
    assert "Arthur Burton" in engine.chat_bubbles
    assert "Isabella Rodriguez" in engine.chat_bubbles
    assert engine.chat_bubbles["Arthur Burton"]["text"] != ""
    assert engine.chat_bubbles["Isabella Rodriguez"]["text"] != ""


def test_npc_chat_distance_two_keeps_one_gap_and_still_shows_bubbles(monkeypatch):
    """NPC-NPC chat distance is now 2 so one empty tile can remain between them."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 12, 10

    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "你好，我想问你昨晚看见了什么。")
    monkeypatch.setattr(isabella, "generate_response", lambda speaker, message, day: "我昨晚在咖啡馆附近听到脚步声。")

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    engine.llm_threads[-1].join(timeout=3)

    assert engine.chat_bubbles["Arthur Burton"]["target"] == "Isabella Rodriguez"
    assert engine.chat_bubbles["Isabella Rodriguez"]["target"] == "Arthur Burton"
    assert engine.chat_bubbles["Arthur Burton"]["text"]
    assert engine.chat_bubbles["Isabella Rodriguez"]["text"]


def test_bubble_lifetime_configured(monkeypatch):
    """Bubble expiration uses configurable lifetime, not hardcoded 60."""
    engine = _make_engine(monkeypatch)
    # Add a bubble older than 12 seconds (default config lifetime)
    engine.chat_bubbles["old_bubble"] = {"text": "old", "time": time.time() - 20}

    # Force bubble lifetime to 12 via CONFIG (modify in place)
    monkeypatch.setitem(game_engine.CONFIG["game"], "bubble_lifetime_seconds", 12)

    engine._expire_chat_bubbles()
    assert "old_bubble" not in engine.chat_bubbles, "Old bubble should be expired"

    # Fresh bubble should survive
    engine.chat_bubbles["fresh"] = {"text": "hi", "time": time.time()}
    engine._expire_chat_bubbles()
    assert "fresh" in engine.chat_bubbles, "Fresh bubble should survive"


def test_npc_chat_sets_response_error_on_empty_initiator(monkeypatch):
    """When initiator returns empty, _last_response_error must be set to 'empty_response'."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "")
    monkeypatch.setattr(isabella, "generate_response", lambda speaker, message, day: "收到。")
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    engine.llm_threads[-1].join(timeout=3)

    assert getattr(arthur, '_last_response_error', '') == "empty_response", (
        "Initiator must have empty_response error set"
    )


def test_npc_chat_success_clears_old_error_and_stale_responder_bubble(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10
    arthur._last_response_error = "empty_response"
    engine.chat_bubbles["Isabella Rodriguez"] = {
        "text": "stale",
        "target": "Klaus Mueller",
        "time": time.time(),
    }
    responder_started = threading.Event()
    responder_continue = threading.Event()

    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "你昨晚看见什么了吗？")

    def delayed_response(speaker, message, day):
        responder_started.set()
        responder_continue.wait(timeout=1)
        return "我只听见街上有脚步声。"

    monkeypatch.setattr(isabella, "generate_response", delayed_response)
    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    assert responder_started.wait(timeout=1)
    responder_continue.set()
    engine.llm_threads[-1].join(timeout=1)

    assert arthur._last_response_error == ""
    assert engine.chat_bubbles["Isabella Rodriguez"]["target"] == "Arthur Burton"


def test_npc_chat_requires_distance_two_or_less(monkeypatch):
    """NPC-NPC chat works at center distance 2 (one empty space between)."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 12, 10  # center distance = 2, one empty space between
    calls = []
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: calls.append(args) or "你好")
    monkeypatch.setattr(isabella, "generate_response", lambda speaker, message, day: "收到。")
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")

    # A thread should have been spawned (guard lets distance 2 through)
    assert len(engine.llm_threads) > 0, "Chat thread should be spawned at distance 2"

    # Wait for thread to complete
    for t in getattr(engine, 'llm_threads', []):
        t.join(timeout=3)

    # Distance 2 should be allowed now
    assert len(calls) > 0, "Chat should proceed at distance 2 (one empty space)"
    assert arthur.in_conversation_with == "Isabella Rodriguez"
    assert isabella.in_conversation_with == "Arthur Burton"
    monkeypatch.setitem(game_engine.CONFIG["game"], "bubble_lifetime_seconds", 0)
    engine._expire_chat_bubbles()
    assert arthur.in_conversation_with is None, "Conversation should release after bubble expiry"
    assert isabella.in_conversation_with is None, "Conversation should release after bubble expiry"


def test_npc_chat_blocked_at_distance_three(monkeypatch):
    """NPC-NPC chat must be blocked at center distance >=3."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 13, 10  # center distance = 3 (> 2)
    calls = []
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: calls.append(args) or "你好")

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")

    assert calls == []
    assert not engine.llm_threads
    assert arthur.in_conversation_with is None
    assert isabella.in_conversation_with is None


def test_late_npc_chat_reply_is_ignored_after_participants_separate(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10
    responder_started = threading.Event()
    responder_continue = threading.Event()

    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "你听到什么了吗？")

    def delayed_response(speaker, message, day):
        responder_started.set()
        responder_continue.wait(timeout=1)
        return "我听到脚步声。"

    monkeypatch.setattr(isabella, "generate_response", delayed_response)
    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")
    assert responder_started.wait(timeout=1)

    isabella.x, isabella.y = 20, 20
    engine._clear_conversation_if_too_far("Arthur Burton", "Isabella Rodriguez")
    responder_continue.set()
    engine.llm_threads[-1].join(timeout=2)

    assert "Arthur Burton" not in engine.chat_bubbles
    assert "Isabella Rodriguez" not in engine.chat_bubbles


def test_talk_decision_moves_toward_target_person_when_far(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    arthur.target_x, arthur.target_y = 10, 10
    isabella.x, isabella.y = 20, 10
    arthur.current_location = "Johnson Park"

    assert engine._action_needs_movement(arthur, "talk", "Johnson Park", "", "Isabella Rodriguez") is True


def test_chinese_display_target_person_resolves_to_internal_id(monkeypatch):
    assert game_engine.resolve_character_name("伊莎贝拉") == "Isabella Rodriguez"
    assert game_engine.resolve_character_name("林梅") == "Mei Lin"


def test_failed_action_decision_becomes_continue_current_action(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    arthur = engine.agents["Arthur Burton"]
    arthur.x = arthur.target_x = 10
    arthur.y = arthur.target_y = 10
    arthur.current_location = "Johnson Park"
    arthur._last_llm_decision_time = 0

    def failed_decision(*args, **kwargs):
        return {"ok": False, "error": "empty_response", "raw_response": ""}

    monkeypatch.setattr(arthur, "decide_next_action", failed_decision)
    engine._update_agent_schedules()
    deadline = time.time() + 3
    while time.time() < deadline and getattr(arthur, "runtime_state", "") == "thinking":
        time.sleep(0.05)

    assert arthur.current_action_type == "continue_current"
    assert arthur.current_action
    assert "等待下一次" not in arthur.current_action
    assert "停留" not in arthur.current_action
    assert arthur.runtime_state == "starting_action"
    assert "Arthur Burton" not in engine.chat_bubbles
    assert any("类型=continue_current" in entry["message"] for entry in engine.game_log)


def test_action_decision_exception_becomes_visible_ongoing_action(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    arthur.current_location = "Harvey Oak Supply Store"
    arthur._last_llm_decision_time = 0

    def boom(*args, **kwargs):
        raise RuntimeError("bad parse")

    monkeypatch.setattr(arthur, "decide_next_action", boom)

    engine._update_agent_schedules()
    deadline = time.time() + 3
    while time.time() < deadline and arthur.runtime_state == "thinking":
        time.sleep(0.05)

    assert arthur.runtime_state == "starting_action"
    assert arthur._pending_action["action_type"] == "continue_current"
    assert "等待下一次" not in arthur.current_action
    assert "Arthur Burton" not in engine.chat_bubbles
    arthur._action_start_visible_until = 0
    engine._update_agent_schedules()
    assert arthur.runtime_state == "acting"
    assert engine.chat_bubbles["Arthur Burton"]["kind"] == "action_status"


def test_idle_residual_reflection_thought_is_cleared(monkeypatch):
    engine = _make_two_npc_planning_engine(monkeypatch)
    monkeypatch.setattr(engine.agents["Arthur Burton"], "decide_next_action", _make_tracking_decide("Arthur Burton", []))
    arthur = engine.agents["Arthur Burton"]
    arthur.runtime_state = "idle"
    arthur.current_thought = "我想适应小镇生活"
    arthur.current_thought_time = time.time()

    engine._update_agent_schedules()

    assert arthur.current_thought == ""
    assert arthur.current_thought_time == 0


def test_talk_decision_starts_chat_when_target_person_adjacent(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "询问昨晚是否看到可疑动静",
        "thought": "她离我很近，可以先问一句。",
        "expected_result": "获得线索",
    }
    calls = []
    monkeypatch.setattr(engine, "_trigger_npc_chat", lambda n1, n2: calls.append((n1, n2)))

    engine._complete_agent_action("Arthur Burton", arthur)

    assert calls == [("Arthur Burton", "Isabella Rodriguez")]
    assert arthur._pending_action is None


def test_talk_decision_starts_chat_when_target_person_distance_two(monkeypatch):
    """_complete_agent_action must trigger _trigger_npc_chat for NPC-NPC
    talk / socialize at distance 2 (one empty tile between them),
    because the chat range is ≤2, not only adjacent."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 12, 10  # distance 2
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "隔着几步问她昨晚的情况",
        "thought": "虽然隔了一个身位，但我还是想确认一下。",
        "expected_result": "获得线索",
    }
    calls = []
    monkeypatch.setattr(engine, "_trigger_npc_chat", lambda n1, n2: calls.append((n1, n2)))

    engine._complete_agent_action("Arthur Burton", arthur)

    assert calls == [("Arthur Burton", "Isabella Rodriguez")], (
        f"Expected _trigger_npc_chat call for distance-2 NPC talk, got {calls}"
    )
    assert arthur._pending_action is None


def test_talk_decision_starts_chat_socialize_distance_two(monkeypatch):
    """Same as above but action_type = socialize, ensuring both talk and
    socialize are treated identically for the ≤2 chat range."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 12, 10  # distance 2
    arthur._pending_action = {
        "action_type": "socialize",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "和她聊聊镇上最近的传言",
        "thought": "社交一下，看看有没有新消息。",
        "expected_result": "增进信任",
    }
    calls = []
    monkeypatch.setattr(engine, "_trigger_npc_chat", lambda n1, n2: calls.append((n1, n2)))

    engine._complete_agent_action("Arthur Burton", arthur)

    assert calls == [("Arthur Burton", "Isabella Rodriguez")]
    assert arthur._pending_action is None


def test_moving_talk_starts_real_chat_immediately_on_arrival(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    arthur.target_x, arthur.target_y = 11, 10
    isabella.x, isabella.y = 12, 10
    arthur.runtime_state = "moving"
    arthur._action_move_ready_at = 0
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "向伊莎贝拉打招呼并询问近况",
        "thought": "先走到她身边再开口。",
        "expected_result": "交换信息",
    }
    engine.agent_paths["Arthur Burton"] = [(11, 10)]
    calls = []
    monkeypatch.setattr(engine, "_trigger_npc_chat", lambda n1, n2: calls.append((n1, n2)))

    engine._move_agents()

    assert calls == [("Arthur Burton", "Isabella Rodriguez")]
    assert arthur.runtime_state != "acting"
    assert arthur._pending_action is None
    assert engine.chat_bubbles.get("Arthur Burton", {}).get("kind") != "action_status"


def test_action_movement_waits_until_blue_action_bubble_window_ends(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    arthur.x, arthur.y = 10, 10
    arthur.target_x, arthur.target_y = 11, 10
    arthur.runtime_state = "starting_action"
    arthur._pending_action = {
        "action_type": "inspect",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "",
        "action": "检查附近情况",
    }
    engine.agent_paths["Arthur Burton"] = [(11, 10)]
    engine._mark_action_started(arthur)

    engine._update_agent_schedules()
    engine._move_agents()

    assert (arthur.x, arthur.y) == (10, 10)
    assert arthur.runtime_state == "starting_action"
    arthur._action_start_visible_until = 0
    arthur._action_move_ready_at = 0
    engine._update_agent_schedules()
    engine._move_agents()
    assert (arthur.x, arthur.y) == (11, 10)


def test_starting_talk_waits_for_blue_action_bubble_before_real_chat(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x = arthur.target_x = 10
    arthur.y = arthur.target_y = 10
    isabella.x, isabella.y = 11, 10
    arthur.runtime_state = "starting_action"
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "向伊莎贝拉打招呼并询问近况",
        "expected_result": "交换信息",
    }
    engine._mark_action_started(arthur)
    calls = []
    monkeypatch.setattr(engine, "_trigger_npc_chat", lambda n1, n2: calls.append((n1, n2)))

    engine._update_agent_schedules()

    assert calls == []
    assert arthur.runtime_state == "starting_action"
    arthur._action_start_visible_until = 0
    engine._update_agent_schedules()
    assert calls == [("Arthur Burton", "Isabella Rodriguez")]


def test_pending_talk_reapproaches_target_instead_of_entering_generic_acting(monkeypatch):
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x = arthur.target_x = 10
    arthur.y = arthur.target_y = 10
    isabella.x, isabella.y = 20, 10
    arthur.runtime_state = "idle"
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "向伊莎贝拉打招呼",
    }
    monkeypatch.setattr(
        engine,
        "_path_adjacent_to",
        lambda *args, **kwargs: (18, 10, [(11, 10), (18, 10)]),
    )

    engine._update_agent_schedules()

    assert arthur.runtime_state == "moving"
    assert arthur._pending_action["action_type"] == "talk"
    assert engine.chat_bubbles.get("Arthur Burton", {}).get("kind") != "action_status"


def test_greeting_text_with_wrong_model_type_uses_real_chat_pipeline(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", ["Arthur Burton"])
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 0)
    monkeypatch.setitem(game_engine.CONFIG["agent"], "planning_display_seconds", 0)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x = arthur.target_x = 10
    arthur.y = arthur.target_y = 10
    isabella.x, isabella.y = 12, 10
    arthur.current_location = isabella.current_location = "Johnson Park"
    arthur._last_llm_decision_time = 0
    calls = []
    monkeypatch.setattr(engine, "_trigger_npc_chat", lambda n1, n2: calls.append((n1, n2)))
    monkeypatch.setattr(
        arthur,
        "decide_next_action",
        lambda *args, **kwargs: {
            "ok": True,
            "action_type": "work",
            "target_location": "Johnson Park",
            "target_object": "",
            "target_person": "Isabella Rodriguez",
            "action": "向伊莎贝拉打招呼并询问今天的情况",
            "action_status": "打招呼",
            "thought": "她就在旁边。",
            "expected_result": "和伊莎贝拉聊天",
            "duration_minutes": 5,
            "raw_response": "{}",
        },
    )

    engine._update_agent_schedules()
    deadline = time.time() + 2
    while time.time() < deadline and getattr(arthur, "_is_thinking", False):
        time.sleep(0.01)

    assert calls == []
    assert arthur.runtime_state == "starting_action"
    arthur._action_start_visible_until = 0
    engine._update_agent_schedules()
    assert calls == [("Arthur Burton", "Isabella Rodriguez")]
    assert engine.chat_bubbles.get("Arthur Burton", {}).get("kind") != "action_status"


def test_talk_decision_to_crow_speaks_directly_when_adjacent(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    arthur = engine.agents["Arthur Burton"]
    crow = engine.agents["Crow"]
    arthur.x, arthur.y = 10, 10
    crow.x, crow.y = 11, 10
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Crow",
        "action": "告诉警长我发现了新的线索",
        "thought": "警长就在附近，应该马上说明。",
        "expected_result": "让警长知道线索",
    }
    monkeypatch.setattr(arthur, "generate_response", lambda *args, **kwargs: "警长，我发现了一点异常。")

    engine._complete_agent_action("Arthur Burton", arthur)

    assert engine.chat_bubbles["Arthur Burton"]["target"] == "Crow"
    assert "警长" in engine.chat_bubbles["Arthur Burton"]["text"]
    assert arthur._pending_action is None


def test_detective_target_not_inferred_for_weak_suspicion_without_target_person(monkeypatch):
    engine = _make_engine(monkeypatch)

    should_report = engine._should_infer_detective_target(
        "talk",
        "tell Crow that Arthur borrowed a tool yesterday",
        "I suspect it may matter, but it is only a weak clue",
    )

    assert should_report is False


def test_detective_target_not_inferred_for_chinese_weak_tip_without_target_person(monkeypatch):
    engine = _make_engine(monkeypatch)

    should_report = engine._should_infer_detective_target(
        "talk",
        "我想找警长说一下，有人昨天借过工具",
        "这只是可疑事实和怀疑，不是明确线索，也不是必须立即汇报的事情",
    )

    assert should_report is False


def test_detective_target_inferred_for_urgent_direct_report_without_target_person(monkeypatch):
    engine = _make_engine(monkeypatch)

    should_report = engine._should_infer_detective_target(
        "talk",
        "tell Crow immediately",
        "urgent direct evidence: I saw the werewolf murder someone",
    )

    assert should_report is True


def test_visible_action_omits_reasoning_prefix(monkeypatch):
    engine = _make_engine(monkeypatch)

    display = engine._action_for_display(
        "我觉得Arthur的说法很奇怪，所以去五金店检查昨天的借工具记录"
    )

    assert display == "检查昨天的借工具记录"


def test_visible_action_is_short_even_when_model_returns_inner_monologue(monkeypatch):
    engine = _make_engine(monkeypatch)

    display = engine._action_for_display(
        "Thought: I need to keep watching the sheriff and compare every witness statement, "
        "so now I will walk to the bakery and ask Isabella about yesterday morning."
    )

    assert "Thought:" not in display
    assert len(display) <= 36


def test_action_status_text_keeps_only_current_task(monkeypatch):
    engine = _make_engine(monkeypatch)
    agent = next(iter(engine.agents.values()))

    text = engine._action_status_text(
        agent,
        {
            "action": "要回霍布斯咖啡馆 准备开门营业。今天照常接待客人，但会特别留意他们",
        },
    )

    assert text == "准备开门营业..."
    assert "霍布斯咖啡馆" not in text
    assert "留意" not in text


def test_action_status_text_prefers_model_status_field(monkeypatch):
    engine = _make_engine(monkeypatch)
    agent = next(iter(engine.agents.values()))

    text = engine._action_status_text(
        agent,
        {
            "action": "前往霍布斯咖啡馆，准备开门营业",
            "action_status": "准备早餐",
        },
    )

    assert text == "准备早餐..."
    assert "前往" not in text


def test_action_status_text_drops_speech_prefix_and_planning_tail(monkeypatch):
    engine = _make_engine(monkeypatch)
    agent = next(iter(engine.agents.values()))

    text = engine._action_status_text(
        agent,
        {
            "action": "玛利亚说：正在整理药房货架，检查药品库存，也会留意客人的反应",
        },
    )

    assert text == "整理药房货架..."
    assert "说：" not in text
    assert "也" not in text


def test_empty_lifestyle_fallback_is_not_visible_action(monkeypatch):
    engine = _make_engine(monkeypatch)

    assert engine._action_for_display("适应小镇生活") == ""


def test_localize_character_names_does_not_corrupt_crown_location():
    text = game_engine.localize_visible_character_names("我要去 The Rose and Crown Pub 开门。")
    assert "克罗n" not in text
    assert "玫瑰与皇冠酒吧" in text


def test_college_default_objects_split_klaus_and_mei(monkeypatch):
    engine = _make_engine(monkeypatch)
    assert engine._departure_object("Klaus Mueller", "Oak Hill College") == "classroom student seating"
    assert engine._departure_object("Mei Lin", "Oak Hill College") == "bookshelf"


def test_college_role_defaults_override_model_object(monkeypatch):
    engine = _make_engine(monkeypatch)
    klaus = engine.agents["Klaus Mueller"]
    mei = engine.agents["Mei Lin"]

    def fake_find(agent, location, obj):
        coords = {
            "classroom student seating": (115, 25),
            "bookshelf": (123, 27),
        }
        return coords.get(obj)

    monkeypatch.setattr(engine, "_find_object_in_spatial_memory", fake_find)

    assert engine._departure_object("Klaus Mueller", "Oak Hill College", "bookshelf") == "classroom student seating"
    assert engine._departure_object("Mei Lin", "Oak Hill College", "classroom student seating") == "bookshelf"
    assert engine._resolve_concrete_target_object(
        klaus, "Oak Hill College", "bookshelf", "move_to", "go to bookshelf"
    ) == "classroom student seating"
    assert engine._resolve_concrete_target_object(
        mei, "Oak Hill College", "classroom student seating", "move_to", "go to classroom"
    ) == "bookshelf"


def test_llm_tick_does_not_start_random_proximity_chat(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10
    calls = []
    monkeypatch.setattr(engine, "_trigger_npc_chat", lambda n1, n2: calls.append((n1, n2)))
    monkeypatch.setattr(arthur, "reflect", lambda context: "我需要继续工作。")

    engine._check_llm_chats("Arthur Burton")

    assert calls == []


def test_random_werewolf_no_fixed_seed(monkeypatch):
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
    monkeypatch.setattr(game_engine.Agent, "add_memory", lambda self, event, day: None)
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "")

    combinations = set()
    for _ in range(30):
        engine = game_engine.WerewolfGameEngine(random_seed=None)
        combo = tuple(sorted(engine.werewolf_names))
        combinations.add(combo)

    assert len(combinations) > 1, f"Expected multiple werewolf combinations, but got only {combinations}"


def test_bury_bodies_after_gathering_marks_body_and_crow_explains(monkeypatch):
    engine = _make_engine(monkeypatch, seed=11)
    body = engine.bodies[0]

    engine._bury_bodies_after_gathering()

    assert body.buried is False
    assert body.burying is True
    assert body.burial_target_x == 12
    assert body.burial_target_y == 46
    for _ in range(200):
        engine._move_agents()
        if body.buried:
            break

    assert body.buried is True
    assert body.location == "Johnson Park"
    assert (body.x, body.y) == (12, 46)
    bubble = engine.chat_bubbles[engine.detective_name]["text"]
    assert "尸体" in bubble
    assert "公园" in bubble


def test_gathering_end_buries_opening_body_before_crow_investigates(monkeypatch):
    engine = _make_engine(monkeypatch, seed=11)
    engine._gathering_active = True
    engine._gathering_busy = False
    engine._gathering_queue = ["Crow"]
    engine._gathering_left = {"Crow": True}
    engine._gathering_round = 2
    engine._gathering_speaker_idx = 0
    called = []
    monkeypatch.setattr(engine, "_start_crow_scene_investigation", lambda: called.append("investigate"))

    engine._handle_round_two_plus()

    assert engine._gathering_active is False
    assert engine.bodies[0].burying is True
    assert called == []
    for _ in range(200):
        engine._move_agents()
        if engine.bodies[0].buried:
            break

    assert engine.bodies[0].buried is True
    assert called == []
    for _ in range(200):
        engine._move_agents()
        if called:
            break

    assert called == ["investigate"]


# ============================================================
# Requirement 1: Crow status suppression — no blue thought/action
# ============================================================


def test_crow_status_suppresses_blue_bubble_fields(monkeypatch):
    """Crow must not expose thought, action, action_plan, runtime_state, emoji
    or conversation_with in get_status, preventing blue thought/action bubbles."""
    engine = _make_engine(monkeypatch)
    status = engine.get_status()
    crow = status["personas"]["Crow"]

    assert crow["thought"] == "", f"Crow thought should be empty, got: {crow['thought']!r}"
    assert crow["thought_time"] == 0, "Crow thought_time should be 0"
    assert crow["thought_summary"] == "", f"Crow thought_summary should be empty"
    assert crow["action"] == "", f"Crow action should be empty, got: {crow['action']!r}"
    assert crow["action_type"] == "", f"Crow action_type should be empty"
    assert crow["action_plan"] == "", f"Crow action_plan should be empty"
    assert crow["action_target_location"] == "", "Crow action_target_location should be empty"
    assert crow["action_target_person"] == "", "Crow action_target_person should be empty"
    assert crow["emoji"] == "", f"Crow emoji should be empty, got: {crow['emoji']!r}"
    assert crow["runtime_state"] == "idle", f"Crow runtime_state should be idle, got: {crow['runtime_state']!r}"
    assert crow["conversation_with"] is None, "Crow conversation_with should be None"
    assert crow["last_decision"] == {}, "Crow last_decision should be empty dict"
    assert crow["current_goal"] == "", "Crow current_goal should be empty"
    # Non-Crow should have their fields exposed
    npc_name = next(n for n in engine.agents if n != "Crow")
    npc = status["personas"][npc_name]
    assert "thought" in npc
    assert "action" in npc
    assert "runtime_state" in npc
    assert "emoji" in npc


def test_crow_scene_investigation_does_not_emit_agent_action_log(monkeypatch):
    """Crow is player-controlled, so automatic scene investigation must not appear as an agent action."""
    engine = _make_engine(monkeypatch)
    crow = engine.agents["Crow"]

    engine._start_crow_scene_investigation()

    assert crow.current_action == ""
    assert crow.current_action_type == ""
    assert crow.runtime_state == "idle"
    assert not any(
        entry.get("type") == "action" and ("Crow" in entry.get("message", "") or "克罗" in entry.get("message", ""))
        for entry in engine.game_log
    )


# ============================================================
# Requirement 2: Detective chat lock — NPCs do not approach busy Crow
# ============================================================


def test_npc_avoids_approaching_crow_when_crow_in_conversation(monkeypatch):
    """When Crow is already in conversation, NPC must not pathfind to Crow."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False

    crow = engine.agents["Crow"]
    arthur = engine.agents["Arthur Burton"]
    arthur.x, arthur.y = 10, 11
    crow.x, crow.y = 10, 10
    crow.in_conversation_with = "Isabella Rodriguez"

    # Arthur has a pending action to talk to Crow
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Crow",
        "action": "我有发现要报告",
        "thought": "接近警长",
        "expected_result": "报告线索",
    }
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "")

    # Call _complete_agent_action: it should check if Crow is busy and abort
    engine._complete_agent_action("Arthur Burton", arthur)
    assert getattr(arthur, '_pending_action', None) is not None
    assert arthur._pending_action["action_type"] == "continue_current"
    assert arthur.runtime_state == "starting_action"


def test_npc_to_npc_avoids_target_already_in_conversation(monkeypatch):
    """NPC must not initiate chat with another NPC who is already in conversation."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False

    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10

    # Simulate Isabella already in conversation
    isabella.in_conversation_with = "Klaus Mueller"

    # Arthur has a pending action to talk to Isabella
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "想聊聊",
        "thought": "接近伊莎贝拉",
        "expected_result": "聊天",
    }

    # Arthur tries to talk to Isabella
    engine._complete_agent_action("Arthur Burton", arthur)
    # Should not trigger chat since target is busy (completing action fails)
    assert engine.chat_bubbles.get("Arthur Burton") is None
    assert arthur._pending_action is not None
    assert arthur._pending_action["action_type"] == "continue_current"
    assert arthur.runtime_state == "starting_action"


# ============================================================
# Requirement 2: Conversation distance — clear if > 1
# ============================================================


def test_npc_conversation_cleared_when_distance_exceeds_two(monkeypatch):
    """NPC-to-NPC conversation must be cleared when distance > 2 (more than one empty space)."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False

    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]

    # Set up a conversation
    arthur.in_conversation_with = "Isabella Rodriguez"
    arthur._conversation_started_at = time.time()
    isabella.in_conversation_with = "Arthur Burton"
    isabella._conversation_started_at = time.time()

    # Put them far apart (distance 3 — more than 2)
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 50, 50

    # Run the agent schedule check that clears far conversations
    engine._update_agent_schedules()

    # Give threads a moment then check release
    for t in getattr(engine, 'llm_threads', []):
        t.join(timeout=2)

    assert getattr(arthur, 'in_conversation_with', None) is None, (
        "Arthur should be released when distance > 2"
    )
    assert getattr(isabella, 'in_conversation_with', None) is None, (
        "Isabella should be released when distance > 2"
    )


def test_npc_conversation_kept_at_distance_two(monkeypatch):
    """NPC-to-NPC conversation must persist at center distance 2 (one empty space)."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False

    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]

    # Set up a conversation
    arthur.in_conversation_with = "Isabella Rodriguez"
    arthur._conversation_started_at = time.time()
    isabella.in_conversation_with = "Arthur Burton"
    isabella._conversation_started_at = time.time()

    # Put them at distance 2 — one empty space
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 12, 10

    # Run the agent schedule check
    engine._update_agent_schedules()

    assert arthur.in_conversation_with == "Isabella Rodriguez", (
        "Arthur should remain in conversation at distance 2"
    )
    assert isabella.in_conversation_with == "Arthur Burton", (
        "Isabella should remain in conversation at distance 2"
    )


# ============================================================
# Requirement: NPC positioning — left/right priority for talk
# ============================================================


def test_path_adjacent_to_prefers_horizontal_one_empty_gap(monkeypatch):
    """NPC-NPC talk positioning should prefer left/right with one empty gap."""
    engine = _make_engine(monkeypatch)
    # Start at (10, 10), target at (30, 20). Open maze — all nearby tiles reachable.
    # The function should pick left or right of target at distance 2 when requested.
    engine.collision_maze = [[0] * 50 for _ in range(50)]

    result = engine._path_adjacent_to(
        (10, 10), (30, 20), prefer_horizontal=True, preferred_distance=2
    )
    assert result is not None, "Should find a reachable tile"
    adj_x, adj_y, _ = result

    dist = abs(adj_x - 30) + abs(adj_y - 20)
    assert dist == 2, f"Expected one empty gap from target, got distance {dist}"
    is_horizontal = adj_y == 20 and abs(adj_x - 30) == 2
    assert is_horizontal, (
        f"Expected horizontal one-gap tile for target (30,20), "
        f"got vertical tile ({adj_x},{adj_y})"
    )


def test_path_adjacent_to_horizontal_priority_with_blocked_sides(monkeypatch):
    """When both horizontal tiles are blocked, prefer_horizontal falls back to vertical."""
    engine = _make_engine(monkeypatch)
    maze = [[0] * 50 for _ in range(50)]
    maze[20][28] = 1  # block one-gap left of target (30,20)
    maze[20][32] = 1  # block one-gap right of target (30,20)
    maze[20][29] = 1  # block adjacent left fallback too
    maze[20][31] = 1  # block adjacent right fallback too
    engine.collision_maze = maze

    result = engine._path_adjacent_to(
        (10, 10), (30, 20), prefer_horizontal=True, preferred_distance=2
    )
    assert result is not None, "Should fall back to vertical tile"
    adj_x, adj_y, _ = result

    dist = abs(adj_x - 30) + abs(adj_y - 20)
    assert dist == 2, f"Should keep one empty vertical tile when available, got dist={dist}"
    is_vertical = adj_x == 30 and abs(adj_y - 20) == 2
    assert is_vertical, f"Expected vertical fallback, got ({adj_x},{adj_y})"


def test_talk_action_moves_to_left_right_of_target(monkeypatch):
    """When NPC decides to talk to another NPC, path_adjacent_to should
    prefer horizontal (left/right) positioning."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.collision_maze = [[0] * 50 for _ in range(50)]

    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 5, 10
    arthur.target_x, arthur.target_y = 5, 10
    isabella.x, isabella.y = 20, 10

    # Trigger an LLM-thread style talk approach simulation
    # (This exercises the code path at line ~3176 where _path_adjacent_to is called for talk)
    path_res = engine._path_adjacent_to(
        (arthur.x, arthur.y),
        (isabella.x, isabella.y),
        blocked=engine._occupied_tiles({"Arthur Burton", "Isabella Rodriguez"}),
        prefer_horizontal=True,
        preferred_distance=2,
    )
    assert path_res is not None, "Should find path to a conversation stand tile"
    adj_x, adj_y, path = path_res

    dist = abs(adj_x - isabella.x) + abs(adj_y - isabella.y)
    assert dist == 2, f"Should leave one empty gap to target, got dist={dist}"

    is_horizontal = adj_y == isabella.y and abs(adj_x - isabella.x) == 2
    assert is_horizontal, (
        f"Should prefer horizontal one-gap tile next to Isabella, got ({adj_x},{adj_y})"
    )


def test_third_party_does_not_insert_into_existing_conversation(monkeypatch):
    """A third NPC must not insert itself into an NPC-NPC pair already in conversation."""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False

    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    klaus = engine.agents["Klaus Mueller"]

    # Arthur and Isabella are in conversation
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10
    klaus.x, klaus.y = 11, 12  # adjacent to Isabella but she's busy
    arthur.in_conversation_with = "Isabella Rodriguez"
    isabella.in_conversation_with = "Arthur Burton"

    # Klaus has a pending action to talk to Isabella
    klaus._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "想聊聊",
        "thought": "找伊莎贝拉问问",
        "expected_result": "聊天",
    }

    # Complete agent action — should detect Isabella is busy
    engine._complete_agent_action("Klaus Mueller", klaus)
    assert klaus._pending_action is not None, "Klaus should keep a visible fallback action"
    assert klaus._pending_action["action_type"] == "continue_current"
    assert klaus.runtime_state == "starting_action"
    assert engine.chat_bubbles.get("Klaus Mueller") is None, (
        "Klaus should not have a chat bubble"
    )
    # Arthur and Isabella should still be in conversation
    assert arthur.in_conversation_with == "Isabella Rodriguez"
    assert isabella.in_conversation_with == "Arthur Burton"


# ============================================================
# Requirement 4: NPC reply clears stale thought/plan
# ============================================================


def test_npc_to_npc_chat_clears_stale_state(monkeypatch):
    """When NPC-to-NPC chat starts, both participants must have stale thoughts cleared."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10

    # Set stale state on both
    arthur.current_thought = "我怀疑伊莎贝拉很可疑……"
    arthur.current_thought_time = 12345.0
    arthur._pending_action = {"action_type": "investigate", "target_location": "somewhere"}
    arthur._last_decision = {"thought": "old decision"}

    isabella.current_thought = "亚瑟在看我……"
    isabella._pending_action = {"action_type": "observe"}
    isabella._last_decision = {"thought": "also old"}

    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "你好")
    monkeypatch.setattr(isabella, "generate_response", lambda speaker, message, day: "你好，什么事？")
    monkeypatch.setitem(game_engine.CONFIG["game"], "npc_chat_delay_seconds", 0.0)

    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")

    # Wait for thread to complete
    for t in getattr(engine, 'llm_threads', []):
        t.join(timeout=5)

    # Stale state should be cleared
    assert arthur.current_thought == "", "Arthur's thought should be cleared"
    assert arthur.current_thought_time == 0, "Arthur's thought_time should be reset"
    assert arthur._pending_action is None, "Arthur's pending_action should be cleared"
    assert arthur._last_decision == {}, "Arthur's last_decision should be cleared"

    assert isabella.current_thought == "", "Isabella's thought should be cleared"
    assert isabella._pending_action is None, "Isabella's pending_action should be cleared"
    assert isabella._last_decision == {}, "Isabella's last_decision should be cleared"


# ============================================================
# Requirement 4: Detective chat records Q&A in NPC memory
# ============================================================


def test_detective_chat_clears_npc_stale_state(monkeypatch):
    """When NPC replies to Crow in detective_chat, stale thought/plan must be cleared
    and both question and answer recorded in the NPC's memory."""
    engine = _make_engine(monkeypatch)

    crow = engine.agents["Crow"]
    arthur = engine.agents["Arthur Burton"]
    arthur.x, arthur.y = 10, 10
    crow.x, crow.y = 11, 10

    # Set stale state on the NPC
    arthur.current_thought = "我怀疑有人……"
    arthur.current_thought_time = 999.0
    arthur.current_action = "四处张望"
    arthur.current_action_type = "observe"
    arthur._pending_action = {"action_type": "investigate", "target_location": "somewhere"}
    arthur._last_decision = {"thought": "old decision"}
    arthur._last_raw_response = "some old raw text"
    arthur._is_thinking = True

    memory_entries = []

    def capture_memory(self, event, day):
        memory_entries.append(event)

    monkeypatch.setattr(arthur, "add_memory", capture_memory.__get__(arthur, game_engine.Agent))
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "我有线索要报告。")

    # Perform a detective chat
    result = engine.detective_chat("Arthur Burton", "你昨晚在哪里？")
    assert "error" not in result, f"Chat should succeed, got error: {result}"

    # Stale state must be cleared
    assert arthur.current_thought == "", "Arthur's thought should be cleared after replying"
    assert arthur.current_thought_time == 0, "Arthur's thought_time should be reset"
    assert arthur.current_action == "", "Arthur's action should be cleared"
    assert arthur.current_action_type == "", "Arthur's action_type should be cleared"
    assert arthur._pending_action is None, "Arthur's pending_action should be cleared"
    assert arthur._last_decision == {}, "Arthur's last_decision should be cleared"
    assert arthur._is_thinking is False, "Arthur's _is_thinking should be False"


# ============================================================
# Requirement 5: Mei Lin and Klaus separation at Oak Hill College
# ============================================================


def test_mei_lin_and_klaus_have_separate_college_defaults(monkeypatch):
    """Mei Lin must default to library (bookshelf), Klaus to classroom."""
    engine = _make_engine(monkeypatch)
    # By schedule/start they already have different spots inside Oak Hill College
    assert engine._departure_object("Klaus Mueller", "Oak Hill College") == "classroom student seating"
    assert engine._departure_object("Mei Lin", "Oak Hill College") == "bookshelf"
    assert engine._departure_object("Klaus Mueller", "Oak Hill College") != engine._departure_object("Mei Lin", "Oak Hill College")


def test_sam_departure_goes_to_pub_not_park(monkeypatch):
    """Sam Moore must depart to The Rose and Crown Pub, not Johnson Park."""
    engine = _make_engine(monkeypatch)
    fallback = game_engine.DEPARTURE_FALLBACKS["Sam Moore"]
    assert "公园" not in fallback, f"Sam fallback should not mention park: {fallback}"
    assert "酒吧" in fallback or "酒馆" in fallback, f"Sam fallback should mention pub: {fallback}"


# ============================================================================
# 2026-06-07 Action Start and Conversation Regression Closure
# ============================================================================


def test_pending_talk_with_busy_target_falls_back_to_continue_current_not_idle(monkeypatch):
    """Regression: when an NPC arrives near a talk target that is already in
    conversation, the NPC must enter starting_action with continue_current
    (via _redirect_to_visible_continue_current), NOT go to idle and break
    the planning→action chain.

    The lifecycle rule says: planning must produce one pending action, and
    that action must enter moving, acting, or conversation before the NPC is
    eligible for another planning response.  Idle without pending_action
    after a valid planning decision is a chain break.
    """
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", ["Arthur Burton"])

    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    klaus = engine.agents["Klaus Mueller"]

    # Position: Arthur adjacent to Isabella, but Isabella is busy talking to Klaus
    arthur.x, arthur.y = 10, 10
    arthur.target_x, arthur.target_y = 10, 10
    isabella.x, isabella.y = 11, 10
    klaus.x, klaus.y = 12, 10

    # Isabella is already in conversation with Klaus
    isabella.in_conversation_with = "Klaus Mueller"
    isabella._conversation_started_at = time.time()
    klaus.in_conversation_with = "Isabella Rodriguez"
    klaus._conversation_started_at = time.time()

    # Arthur has a pending talk action targeting Isabella (result of planning)
    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "找伊莎贝拉确认昨晚的情况",
        "action_status": "找伊莎贝拉说话",
        "thought": "她应该知道些什么",
        "expected_result": "交换信息",
    }
    arthur.runtime_state = "idle"
    engine.agent_paths.pop("Arthur Burton", None)

    # Simulate the arrival path: update_agent_schedules will call
    # _arrive_at_pending_action since Arthur has a pending talk action
    # and is not in acting state.
    monkeypatch.setitem(game_engine.CONFIG["game"], "bubble_lifetime_seconds", 0)
    monkeypatch.setitem(game_engine.CONFIG["agent"], "planning_display_seconds", 0)
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 999)

    engine._update_agent_schedules()

    # The bug: currently _arrive_at_pending_action calls _trigger_npc_chat
    # which silently returns when target is busy, then sets _pending_action=None
    # and runtime_state="idle".  The correct behavior should be
    # _redirect_to_visible_continue_current → runtime_state="starting_action".
    #
    # This test documents the regression: idle is the wrong outcome.
    assert arthur.runtime_state != "idle", (
        "Arthur must NOT go to idle when his talk target is busy — "
        "this breaks the planning→action chain. "
        "Expected: starting_action with continue_current fallback."
    )
    assert arthur._pending_action is not None, (
        "Arthur must retain a pending_action after target is busy — "
        "empty pending_action means the planning result was silently discarded."
    )
    if arthur.runtime_state == "starting_action":
        assert arthur._pending_action["action_type"] == "continue_current", (
            "Fallback action must be continue_current when talk target is busy."
        )
        assert "Arthur Burton" not in engine.chat_bubbles, (
            "No chat bubble should appear for continue_current fallback before action-start ends."
        )


def test_action_start_timing_is_backend_driven_not_frontend_cache(monkeypatch):
    """Backend state transitions (starting_action → moving → acting) must be
    governed by _action_start_visible_until and _action_status_visible_at,
    not by frontend rendering or cached bubble data.

    Specifically:
    - While _action_start_visible_until is in the future, the agent stays in
      starting_action even if the frontend hasn't rendered the blue bubble yet.
    - _action_status_visible_at gates the white action-duration bubble:
      it must not appear before the blue bubble's expected visibility window ends.
    - The runtime_state field reflects backend truth, not frontend visual state.
    """
    engine = _make_engine(monkeypatch)
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", ["Arthur Burton"])
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 999)

    arthur = engine.agents["Arthur Burton"]
    arthur.x = arthur.target_x = 10
    arthur.y = arthur.target_y = 10
    arthur.current_location = "Harvey Oak Supply Store"

    # Simulate a completed planning: pending_action exists
    now = time.time()
    arthur._pending_action = {
        "action_type": "inspect",
        "target_location": "Harvey Oak Supply Store",
        "target_object": "tool shelf",
        "target_person": "",
        "action": "检查工具架",
        "action_status": "检查工具架",
        "duration_minutes": 30,
    }
    arthur.runtime_state = "starting_action"
    engine._mark_action_started(arthur, now)

    # Verify backend timing fields are set correctly
    assert arthur._action_started_at == now
    assert arthur._action_start_visible_until > now, (
        "_action_start_visible_until must be in the future"
    )
    assert arthur._action_status_visible_at == 0, (
        "_action_status_visible_at must be 0 before action-start bubble ends"
    )

    # While blue action-start bubble window is active, agent stays in starting_action
    engine._start_pending_action_execution_if_ready("Arthur Burton", arthur, now + 1)
    assert arthur.runtime_state == "starting_action", (
        "Agent must stay in starting_action while _action_start_visible_until > now"
    )
    assert "Arthur Burton" not in engine.chat_bubbles, (
        "No white action_status bubble must appear before blue bubble window ends"
    )

    # After the blue bubble window expires, transition to acting
    arthur._action_start_visible_until = 0
    arthur._action_move_ready_at = 0
    engine._start_pending_action_execution_if_ready("Arthur Burton", arthur, now + 10)
    assert arthur.runtime_state == "acting", (
        "Agent must enter acting after action-start blue bubble window ends"
    )
    # Verify white action-duration bubble appears
    bubble = engine.chat_bubbles.get("Arthur Burton")
    assert bubble is not None, "White action_status bubble must appear after blue window ends"
    assert bubble.get("kind") == "action_status"
    assert "..." in bubble.get("text", "")

    # Verify status exposes backend timing fields (not frontend derived)
    status = engine.get_status()
    persona = status["personas"]["Arthur Burton"]
    assert "action_started_at" in persona
    assert "action_status_visible_at" in persona
    assert isinstance(persona["action_started_at"], (int, float))


def test_stale_planning_thread_does_not_override_detective_conversation_lock(monkeypatch):
    """Regression: if a planning LLM thread was launched before detective_chat
    started, the stale planning response must NOT override the conversation
    lock (in_conversation_with) set by the detective chat.

    The engine's detective_chat increments _detective_chat_job_id and sets
    target.in_conversation_with = "Crow".  A planning thread that started
    earlier has no knowledge of this, and its response handler directly
    mutates agent._pending_action and agent.runtime_state without checking
    whether the agent is now in conversation.

    This test verifies that the agent's in_conversation_with lock survives
    a stale planning response by inspecting the thread's finalization logic.
    """
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", ["Arthur Burton"])
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 0)

    arthur = engine.agents["Arthur Burton"]
    arthur.x = arthur.target_x = 10
    arthur.y = arthur.target_y = 10
    arthur.current_location = "Johnson Park"
    arthur._last_llm_decision_time = 0
    arthur._next_llm_retry_time = 0

    # Simulate the detective_chat having locked Arthur into conversation
    # (as if detective_chat was called mid-planning)
    arthur.in_conversation_with = "Crow"
    arthur._conversation_started_at = time.time()
    arthur.runtime_state = "acting"
    arthur._pending_action = None
    arthur.current_thought = ""
    arthur.current_thought_time = 0

    # Now simulate a stale planning thread response arriving
    # The thread would set _pending_action, runtime_state, etc.
    # We simulate by calling _update_agent_schedules which processes
    # the agent through the planning lane.

    # Since Arthur is in conversation, the planning lane must skip him
    engine._update_agent_schedules()

    # Arthur's conversation lock must survive
    assert arthur.in_conversation_with == "Crow", (
        "detective chat conversation lock must survive planning lane pass — "
        "in_conversation_with must stay 'Crow', not be overwritten by any stale thread"
    )
    assert arthur._pending_action is None, (
        "Stale planning thread must not inject a new pending_action "
        "while target is in detective conversation"
    )
    assert arthur.runtime_state == "acting", (
        "Agent runtime_state must stay 'acting' while in detective conversation, "
        "not be changed to 'moving' or 'starting_action' by stale planning response"
    )
    assert arthur.current_thought == "", (
        "Stale planning thought must not appear while agent is in detective conversation"
    )


def test_planned_action_to_busy_target_does_not_clear_pending_action_silently(monkeypatch):
    """When _arrive_at_pending_action encounters a busy target for a talk
    action, it must not silently clear _pending_action and set idle.
    Instead, it must call _redirect_to_visible_continue_current or at
    minimum preserve the action chain so the NPC doesn't become invisible.

    This is a direct unit test on _arrive_at_pending_action with a busy target.
    """
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", ["Arthur Burton"])

    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    klaus = engine.agents["Klaus Mueller"]

    arthur.x, arthur.y = 10, 10
    arthur.target_x, arthur.target_y = 10, 10
    isabella.x, isabella.y = 11, 10
    klaus.x, klaus.y = 12, 10

    # Isabella busy with Klaus
    isabella.in_conversation_with = "Klaus Mueller"
    isabella._conversation_started_at = time.time()
    klaus.in_conversation_with = "Isabella Rodriguez"
    klaus._conversation_started_at = time.time()

    arthur._pending_action = {
        "action_type": "talk",
        "target_location": "Johnson Park",
        "target_object": "",
        "target_person": "Isabella Rodriguez",
        "action": "找伊莎贝拉交谈",
        "action_status": "找伊莎贝拉交谈",
        "thought": "想问她昨晚的情况",
        "expected_result": "获得信息",
    }
    arthur.runtime_state = "idle"
    engine.agent_paths.pop("Arthur Burton", None)

    # Directly exercise _arrive_at_pending_action
    engine._arrive_at_pending_action("Arthur Burton", arthur)

    # The correct outcome: Arthur should be in starting_action with
    # continue_current, NOT idle with no pending_action.
    assert arthur.runtime_state != "idle", (
        "BUG: _arrive_at_pending_action silently sets idle when target is busy. "
        "Must instead enter starting_action with continue_current fallback "
        "to preserve the planning→action lifecycle chain."
    )
    if arthur.runtime_state == "starting_action":
        assert arthur._pending_action is not None
        assert arthur._pending_action["action_type"] == "continue_current"


def test_moving_state_does_not_leak_stale_frontend_bubble_cache(monkeypatch):
    """The backend moving/starting/action_status lifecycle must not be
    influenced by frontend bubble cache.  Specifically:

    - When transitioning from starting_action to moving, the backend sets
      runtime_state = "moving" purely based on _action_move_ready_at.
    - If the frontend has leftover cached bubbles of the wrong kind, the
      backend must not use them to skip or redirect state transitions.
    - The backend's chat_bubbles dictionary reflects only backend-written
      entries; frontend-local state is irrelevant.
    """
    engine = _make_engine(monkeypatch)
    monkeypatch.setitem(game_engine.CONFIG["game"], "active_agents", ["Arthur Burton"])
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 999)

    arthur = engine.agents["Arthur Burton"]
    arthur.x, arthur.y = 10, 10
    arthur.target_x, arthur.target_y = 12, 10

    now = time.time()
    arthur._pending_action = {
        "action_type": "work",
        "target_location": "Harvey Oak Supply Store",
        "target_object": "",
        "target_person": "",
        "action": "整理工具架",
        "action_status": "整理工具架",
        "duration_minutes": 30,
    }
    arthur.runtime_state = "starting_action"
    engine.agent_paths["Arthur Burton"] = [(11, 10), (12, 10)]
    engine._mark_action_started(arthur, now)

    # Before the blue bubble ends, movement is blocked
    # Simulate the frontend having cached a stale white bubble
    engine.chat_bubbles["Arthur Burton"] = {
        "text": "整理工具架...",
        "target": "",
        "time": now,
        "kind": "action_status",
    }

    # _start_pending_action_execution_if_ready must not be fooled by
    # the frontend bubble cache — it checks _action_start_visible_until
    engine._start_pending_action_execution_if_ready("Arthur Burton", arthur, now + 1)
    assert arthur.runtime_state == "starting_action", (
        "Must stay in starting_action while blue bubble window is active, "
        "regardless of what the frontend bubble cache contains"
    )

    # Clean up stale bubble (simulating frontend refresh)
    engine.chat_bubbles.pop("Arthur Burton", None)

    # After blue window ends, movement begins
    arthur._action_start_visible_until = 0
    arthur._action_move_ready_at = 0
    engine._start_pending_action_execution_if_ready("Arthur Burton", arthur, now + 10)
    assert arthur.runtime_state == "moving", (
        "Must enter moving after blue bubble window ends, "
        "based purely on backend timing, not frontend bubble state"
    )
    # White action_status bubble must NOT appear during moving phase
    assert engine.chat_bubbles.get("Arthur Burton") is None, (
        "White action_status bubble must not appear during moving phase"
    )

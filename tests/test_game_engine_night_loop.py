import time

import game_engine


def _make_engine(monkeypatch, seed=11):
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
    return game_engine.WerewolfGameEngine(random_seed=seed)


def _start_hunt(monkeypatch):
    engine = _make_engine(monkeypatch)
    wolf = engine.agents[engine.werewolf_name]
    wolf.werewolf_choose_target = lambda names, day: names[0]
    engine._transition_to_night()
    return engine


def test_enter_night_starts_hunt_without_immediate_kill(monkeypatch):
    engine = _start_hunt(monkeypatch)

    assert engine.phase == game_engine.GamePhase.NIGHT
    assert engine.dead_list == []
    assert engine.night_hunt.stage == "choosing"


def test_detective_is_excluded_until_other_residents_are_dead(monkeypatch):
    engine = _start_hunt(monkeypatch)

    names = [candidate.name for candidate in engine._build_hunt_candidates()]

    assert "Crow" not in names
    assert names


def test_werewolf_kills_only_after_reaching_target(monkeypatch):
    engine = _start_hunt(monkeypatch)
    target_name = engine._eligible_night_targets()[0]
    wolf = engine.agents[engine.werewolf_name]
    victim = engine.agents[target_name]
    wolf.x, wolf.y = victim.x, victim.y

    engine._advance_night_hunt(now=engine.night_hunt.started_at + 1)

    assert engine.night_hunt.killed_name == target_name
    assert target_name in engine.dead_list
    assert engine.bodies[-1].victim_name == target_name
    assert engine.bodies[-1].discovered is False


def test_deadline_forces_kill_and_adds_extra_trace_clue(monkeypatch):
    engine = _start_hunt(monkeypatch)
    wolf = engine.agents[engine.werewolf_name]

    engine._advance_night_hunt(now=engine.night_hunt.deadline_at)

    assert engine.night_hunt.killed_name
    assert engine.night_hunt.forced_completion is True
    assert len(engine.clues) >= 2
    victim = engine.agents[engine.night_hunt.killed_name]
    assert (wolf.x, wolf.y) != (victim.x, victim.y)


def test_dawn_discovers_body_and_starts_body_site_gathering(monkeypatch):
    engine = _start_hunt(monkeypatch)
    engine._advance_night_hunt(now=engine.night_hunt.deadline_at)
    monkeypatch.setattr(engine, "_generate_daily_plans", lambda: None)
    monkeypatch.setattr(game_engine.Agent, "compress_memory", lambda self, day: None)

    engine._transition_to_day()

    body = engine.bodies[-1]
    assert body.discovered is True
    assert engine._gathering_active is True
    positions = []
    for agent in engine.agents.values():
        if agent.is_alive:
            assert agent.current_location == body.location
            assert engine.collision_maze[agent.y][agent.x] == 0
            positions.append((agent.x, agent.y))
    assert len(positions) == len(set(positions))


def test_night_waits_for_player_confirmation_before_dawn(monkeypatch):
    engine = _start_hunt(monkeypatch)
    monkeypatch.setattr(engine, "_generate_daily_plans", lambda: None)
    monkeypatch.setattr(game_engine.Agent, "compress_memory", lambda self, day: None)
    engine._silver_knife_used = True

    engine._advance_night_hunt(now=engine.night_hunt.deadline_at)
    engine._night_tick()

    assert engine.phase == game_engine.GamePhase.NIGHT
    assert engine._night_progress["complete"] is True
    assert engine.confirm_night_transition()["success"] is True
    assert engine.phase == game_engine.GamePhase.DAY


def test_night_ends_in_defeat_if_detective_is_killed(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine.phase = game_engine.GamePhase.NIGHT
    engine.day = 3
    engine._night_progress = {"complete": True, "wolf_complete": True, "knife_complete": True}
    engine.agents["Crow"].is_alive = False

    result = engine.confirm_night_transition()

    assert result["success"] is True
    assert result["game_over"] is True
    assert engine.game_over is True
    assert engine.winner == "werewolf"
    assert engine.game_over_reason == "detective_killed_at_night"
    assert engine.phase == game_engine.GamePhase.GAME_OVER


def test_silver_knife_phase_does_not_run_before_wolf_phase(monkeypatch):
    engine = _start_hunt(monkeypatch)
    calls = []
    monkeypatch.setattr(engine, "_advance_silver_knife_action", lambda: calls.append("knife"))

    engine._night_tick()
    assert calls == []

    engine._advance_night_hunt(now=engine.night_hunt.deadline_at)
    engine._night_tick()
    assert calls == ["knife"]


def test_day3_night_crafts_silver_bullet_and_exposes_status(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine.day = 3
    engine._silver_bullet_acquired = True
    engine._silver_jewelry_acquired = True
    engine._silver_bullet_crafted = False

    engine._transition_to_night()
    status = engine._public_night_progress_status()

    assert engine._silver_bullet_crafted is True
    assert status["silver_bullet_crafting"] is True
    assert status["silver_bullet_crafting_complete"] is True
    assert "银质子弹" in status["silver_bullet_crafting_message"]


def test_silver_knife_kills_after_reaching_target(monkeypatch):
    engine = _start_hunt(monkeypatch)
    holder_name = engine._silver_knife_holder
    assert holder_name
    holder = engine.agents[holder_name]
    target_name = next(
        name for name, agent in engine.agents.items()
        if name not in {holder_name, "Crow"} and agent.is_alive
    )
    target = engine.agents[target_name]
    holder.x, holder.y = target.x, target.y

    engine._night_progress = {
        "active": True,
        "stage": "silver_knife",
        "complete": False,
        "wolf_complete": True,
        "knife_complete": False,
    }
    monkeypatch.setattr(engine, "_choose_silver_knife_target", lambda holder, candidates: target_name)

    engine._advance_silver_knife_action()

    assert target_name in engine.dead_list
    assert engine.bodies[-1].victim_name == target_name
    assert engine._night_progress["knife_complete"] is True


def test_silver_knife_does_not_force_kill_when_path_ends_after_target_moves(monkeypatch):
    engine = _start_hunt(monkeypatch)
    holder_name = engine._silver_knife_holder
    holder = engine.agents[holder_name]
    target_name = next(
        name for name, agent in engine.agents.items()
        if name not in {holder_name, "Crow"} and agent.is_alive
    )
    target = engine.agents[target_name]

    holder.x = holder.target_x = 20
    holder.y = holder.target_y = 20
    target.x = target.target_x = 70
    target.y = target.target_y = 70
    engine._silver_knife_night_checked = True
    engine._silver_knife_action = {
        "status": "moving",
        "complete": False,
        "holder": holder_name,
        "target": target_name,
        "initial_path_len": 1,
        "started_at": 1.0,
        "deadline_at": time.time() + 60.0,
    }
    engine._night_progress = {
        "active": True,
        "stage": "silver_knife",
        "complete": False,
        "wolf_complete": True,
        "knife_complete": False,
    }

    engine._advance_silver_knife_action()

    assert target_name not in engine.dead_list
    assert target.is_alive is True
    assert engine._night_progress["knife_complete"] is True
    assert engine._silver_knife_action["complete"] is True
    assert engine._silver_knife_action["reason"] == "path_ended_not_adjacent"
    assert holder_name not in engine.agent_paths
    assert holder.runtime_state == "idle"

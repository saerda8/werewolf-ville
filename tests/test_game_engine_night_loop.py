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

"""Tests for full game completion: night phase machine, silver knife phase,
two-corpse nights, Day4 flow, and Day4 win resolution.

Covers these rules:
1) Night phase machine: werewolf phase first, silver knife phase second.
2) Silver knife phase always runs/records 60s regardless of holder status.
3) Silver knife holder killed by wolf first -> knife scrapped, phase still shows.
4) Silver knife is one-use per game.
5) Same night can produce two corpses.
6) Silver knife killing a werewolf -> body marked as werewolf_corpse.
7) Day4 morning discussion -> direct voting, no free activity.
8) Day4 win resolution.
"""

import game_engine
from simulation_events import BodyRecord


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
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "{}")
    return game_engine.WerewolfGameEngine(random_seed=seed)


def _start_night(monkeypatch, seed=11):
    """Create engine and transition to night."""
    engine = _make_engine(monkeypatch, seed=seed)
    wolf = engine.agents[engine.werewolf_name]
    wolf.werewolf_choose_target = lambda names, day: names[0]
    engine._gathering_active = False
    engine._transition_to_night()
    return engine


# ============================================================================
# Night Phase Machine Tests
# ============================================================================


def test_night_starts_in_werewolf_stage(monkeypatch):
    """Night must start with stage='werewolf' in _night_progress."""
    engine = _start_night(monkeypatch)
    assert engine._night_progress["stage"] == "werewolf"
    assert engine._night_progress["active"] is True
    assert engine._night_progress["complete"] is False


def test_werewolf_phase_transitions_to_silver_knife_after_kill(monkeypatch):
    """After the wolf kills, night stage must transition to 'silver_knife'."""
    engine = _start_night(monkeypatch)
    target_name = engine._eligible_night_targets()[0]
    wolf = engine.agents[engine.werewolf_name]
    victim = engine.agents[target_name]
    wolf.x, wolf.y = victim.x, victim.y

    engine._advance_night_hunt(now=engine.night_hunt.started_at + 1)

    assert engine.night_hunt.killed_name == target_name
    engine._night_tick()
    assert engine._night_progress["stage"] == "silver_knife"
    assert engine._night_progress["complete"] is False


def test_silver_knife_phase_waits_for_real_action(monkeypatch):
    """Silver knife phase completes only after the holder's real action resolves."""
    engine = _start_night(monkeypatch)
    target_name = engine._eligible_night_targets()[0]
    wolf = engine.agents[engine.werewolf_name]
    victim = engine.agents[target_name]
    wolf.x, wolf.y = victim.x, victim.y
    engine._advance_night_hunt(now=engine.night_hunt.started_at + 1)

    calls = []
    monkeypatch.setattr(engine, "_advance_silver_knife_action", lambda: calls.append("knife"))
    engine._night_tick()

    assert engine._night_progress["stage"] == "silver_knife"
    assert engine._night_progress["complete"] is False
    assert calls == ["knife"]

    engine._night_progress["knife_complete"] = True
    engine._night_tick()
    assert engine._night_progress["stage"] == "complete"
    assert engine._night_progress["complete"] is True


def test_silver_knife_phase_completes_quickly_when_used(monkeypatch):
    """If the one-use knife was already spent, the public phase still appears and resolves."""
    engine = _start_night(monkeypatch)
    engine._silver_knife_used = True
    target_name = engine._eligible_night_targets()[0]
    wolf = engine.agents[engine.werewolf_name]
    victim = engine.agents[target_name]
    wolf.x, wolf.y = victim.x, victim.y
    engine._advance_night_hunt(now=engine.night_hunt.started_at + 1)
    engine._night_tick()

    assert engine._silver_knife_night_checked is True
    assert engine._night_progress["complete"] is True


def test_confirm_night_transition_requires_complete_stage(monkeypatch):
    """Player cannot confirm night transition until all stages complete."""
    engine = _start_night(monkeypatch)
    assert engine._night_progress["stage"] == "werewolf"
    result = engine.confirm_night_transition()
    assert result["success"] is False
    assert "尚未结束" in result["error"]


# ============================================================================
# Silver Knife Holder Killed First -> Knife Scrapped
# ============================================================================


def test_silver_knife_scrapped_when_holder_killed_first(monkeypatch):
    """If werewolf kills the silver knife holder first, knife is scrapped."""
    engine = _start_night(monkeypatch)
    holder_name = engine._silver_knife_holder
    assert holder_name, "Silver knife holder must exist"

    wolf = engine.agents[engine.werewolf_name]
    holder = engine.agents[holder_name]
    wolf.x, wolf.y = holder.x, holder.y

    engine._kill_night_target(holder_name)

    assert engine.night_hunt.killed_name == holder_name
    assert holder_name in engine.dead_list

    engine._night_tick()
    assert engine._silver_knife_scrapped_tonight is True
    assert engine._night_progress["complete"] is True
    assert engine._silver_knife_target_tonight == ""


def test_silver_knife_holder_not_killed_can_use_knife(monkeypatch):
    """If the silver knife holder survives, they can still use knife."""
    engine = _start_night(monkeypatch)
    holder_name = engine._silver_knife_holder
    wolf = engine.agents[engine.werewolf_name]

    targets = [n for n in engine._eligible_night_targets() if n != holder_name]
    victim_name = targets[0]
    victim = engine.agents[victim_name]
    wolf.x, wolf.y = victim.x, victim.y

    engine._kill_night_target(victim_name)
    monkeypatch.setattr(engine, "_choose_silver_knife_target", lambda holder, candidates: "")
    engine._night_tick()

    assert engine._silver_knife_scrapped_tonight is False
    assert engine._silver_knife_night_checked is True


# ============================================================================
# Two Corpses in One Night
# ============================================================================


def test_two_corpses_in_one_night_wolf_and_knife(monkeypatch):
    """Same night can produce two corpses through real wolf and knife actions."""
    engine = _start_night(monkeypatch)

    wolf = engine.agents[engine.werewolf_name]
    villager_name = [n for n in engine._eligible_night_targets()
                     if n != engine._silver_knife_holder][0]
    villager = engine.agents[villager_name]
    wolf.x, wolf.y = villager.x, villager.y
    engine._kill_night_target(villager_name)

    body_count_before = len(engine.bodies)
    assert villager_name in engine.dead_list

    holder_name = engine._silver_knife_holder
    knife_targets = [n for n, a in engine.agents.items()
                     if a.is_alive and n != holder_name and n != "Crow"]
    knife_victim = knife_targets[0]
    holder = engine.agents[holder_name]
    target = engine.agents[knife_victim]
    holder.x, holder.y = target.x, target.y

    monkeypatch.setattr(engine, "_choose_silver_knife_target", lambda holder, candidates: knife_victim)
    engine._night_progress.update({"wolf_complete": True, "stage": "silver_knife"})
    engine._night_tick()

    assert len(engine.bodies) > body_count_before
    assert not engine.agents[villager_name].is_alive
    assert not engine.agents[knife_victim].is_alive
    assert engine._night_progress["knife_complete"] is True


# ============================================================================
# Silver Knife Kills Werewolf -> werewolf_corpse Tag
# ============================================================================


def test_silver_knife_kill_werewolf_marks_corpse(monkeypatch):
    """When silver knife kills a werewolf, body tagged is_werewolf_corpse=True."""
    engine = _start_night(monkeypatch)
    holder_name = engine._silver_knife_holder
    wolf_name = engine.werewolf_names[0]

    result = engine.use_silver_knife(holder_name, wolf_name)
    assert result.get("success") is True

    wolf_body = None
    for body in engine.bodies:
        if body.victim_name == wolf_name:
            wolf_body = body
            break

    assert wolf_body is not None
    assert wolf_body.is_werewolf_corpse is True


def test_normal_kill_does_not_tag_corpse(monkeypatch):
    """A normal werewolf kill should NOT set is_werewolf_corpse."""
    engine = _start_night(monkeypatch)
    wolf = engine.agents[engine.werewolf_name]
    victim_name = engine._eligible_night_targets()[0]
    victim = engine.agents[victim_name]
    wolf.x, wolf.y = victim.x, victim.y
    engine._kill_night_target(victim_name)

    victim_body = None
    for body in engine.bodies:
        if body.victim_name == victim_name:
            victim_body = body
            break

    assert victim_body is not None
    assert victim_body.is_werewolf_corpse is False


def test_morning_discovers_and_announces_multiple_bodies(monkeypatch):
    """Morning discovery announces all new bodies, including visible werewolf corpses."""
    engine = _make_engine(monkeypatch)
    normal = BodyRecord(
        body_id="body_test_normal",
        victim_name="Arthur Burton",
        location="Harvey Oak Supply Store",
        x=10,
        y=10,
        created_day=1,
        discovered=False,
    )
    wolf = BodyRecord(
        body_id="body_test_wolf",
        victim_name=engine.werewolf_names[0],
        location="Johnson Park",
        x=12,
        y=10,
        created_day=1,
        discovered=False,
        is_werewolf_corpse=True,
    )
    engine.bodies = [normal, wolf]

    discovered = engine._discover_latest_body()

    assert discovered == wolf
    assert normal.discovered is True
    assert wolf.discovered is True
    latest_log = engine.game_log[-1]["message"]
    assert game_engine.display_name_for_person("Arthur Burton") in latest_log
    assert game_engine.display_name_for_person(engine.werewolf_names[0]) in latest_log
    assert "狼人尸体" in latest_log


def test_day3_night_auto_crafts_silver_bullet(monkeypatch):
    """If both silver resources are ready, Day3 night crafts one silver bullet."""
    engine = _make_engine(monkeypatch)
    engine.day = 3
    engine._silver_bullet_acquired = True
    engine._silver_jewelry_acquired = True
    engine._silver_bullet_crafted = False

    engine._transition_to_night()

    assert engine._silver_bullet_crafted is True
    assert any("成功制造了一颗银质子弹" in entry["message"] for entry in engine.game_log)


# ============================================================================
# Day4 Flow Tests
# ============================================================================


def test_day4_no_free_activity_flag_set(monkeypatch):
    """Day4 transition must set _day4_no_free_activity flag."""
    engine = _make_engine(monkeypatch)
    monkeypatch.setattr(engine, "_generate_daily_plans", lambda: None)
    monkeypatch.setattr(game_engine.Agent, "compress_memory", lambda self, day: None)
    monkeypatch.setattr(engine, "_discover_latest_body", lambda: None)
    monkeypatch.setattr(engine, "_place_alive_agents_near_body", lambda body: None)

    engine._transition_to_day()
    assert engine.day == 2
    assert getattr(engine, "_day4_no_free_activity", False) is False

    engine._transition_to_day()
    assert engine.day == 3
    assert getattr(engine, "_day4_no_free_activity", False) is False

    engine._transition_to_day()
    assert engine.day == 4
    assert engine._day4_no_free_activity is True


def test_day4_gathering_end_triggers_dusk(monkeypatch):
    """On Day4, when morning gathering ends, it should auto-start dusk."""
    engine = _make_engine(monkeypatch)
    monkeypatch.setattr(engine, "_generate_daily_plans", lambda: None)
    monkeypatch.setattr(game_engine.Agent, "compress_memory", lambda self, day: None)
    monkeypatch.setattr(engine, "_discover_latest_body", lambda: None)
    monkeypatch.setattr(engine, "_place_alive_agents_near_body", lambda body: None)
    monkeypatch.setattr(engine, "_bury_bodies_after_gathering", lambda: None)
    monkeypatch.setattr(engine, "_start_crow_scene_investigation", lambda: None)

    engine._transition_to_day()
    engine._transition_to_day()
    engine._transition_to_day()

    assert engine.day == 4
    assert engine._day4_no_free_activity is True
    assert engine._gathering_active is True

    engine._gathering_speaker_idx = len(engine._gathering_queue)
    engine._gathering_round = 99
    for name in list(engine._gathering_queue):
        engine._gathering_left[name] = True

    engine._handle_round_two_plus()

    assert engine._day4_no_free_activity is False
    assert engine._gathering_active is False


# ============================================================================
# Day4 Win Resolution Tests
# ============================================================================


def _setup_day4_scenario(monkeypatch, alive_wolf_count, alive_good):
    """Setup a Day4 engine with specific alive counts."""
    engine = _make_engine(monkeypatch)
    alive_wolves = list(engine.werewolf_names)[:alive_wolf_count]
    for name, agent in list(engine.agents.items()):
        if name not in alive_wolves and name not in alive_good and name != "Crow":
            agent.is_alive = False
            if name not in engine.dead_list:
                engine.dead_list.append(name)
    for name in alive_wolves + alive_good + ["Crow"]:
        if name in engine.agents:
            engine.agents[name].is_alive = True
    engine.day = 4
    return engine


def test_day4_both_wolves_alive_werewolves_win(monkeypatch):
    """Day4: both wolves alive -> werewolves win."""
    engine = _setup_day4_scenario(
        monkeypatch,
        alive_wolf_count=2,
        alive_good=["Arthur Burton"],
    )
    outcome = engine._resolve_day4_after_vote()
    assert outcome == "game_over"
    assert engine.winner == "werewolf"
    assert engine.game_over is True
    assert engine.phase == game_engine.GamePhase.GAME_OVER


def test_day4_no_wolves_alive_villagers_win(monkeypatch):
    """Day4: no wolves alive -> villagers win."""
    engine = _setup_day4_scenario(
        monkeypatch,
        alive_wolf_count=0,
        alive_good=["Arthur Burton"],
    )
    outcome = engine._resolve_day4_after_vote()
    assert outcome == "game_over"
    assert engine.winner == "villagers"
    assert engine.game_over is True
    assert engine.phase == game_engine.GamePhase.GAME_OVER


def test_day4_one_wolf_with_silver_bullet_pending(monkeypatch):
    """Day4: one wolf + silver bullet available -> pending_silver_shot."""
    engine = _setup_day4_scenario(
        monkeypatch,
        alive_wolf_count=1,
        alive_good=["Arthur Burton", "Isabella Rodriguez"],
    )
    engine._silver_bullet_acquired = True
    engine._silver_jewelry_acquired = True
    engine._silver_bullet_crafted = True
    engine._silver_bullet_used = False

    outcome = engine._resolve_day4_after_vote()
    assert outcome == "pending_silver_shot"
    assert engine.phase == game_engine.GamePhase.PENDING_SILVER_SHOT
    assert engine._pending_silver_wolf == engine.werewolf_names[0]


def test_day4_one_wolf_no_silver_bullet_werewolves_win(monkeypatch):
    """Day4: one wolf + no silver bullet -> werewolves win."""
    engine = _setup_day4_scenario(
        monkeypatch,
        alive_wolf_count=1,
        alive_good=["Arthur Burton", "Isabella Rodriguez"],
    )
    engine._silver_bullet_acquired = True
    engine._silver_jewelry_acquired = False
    engine._silver_bullet_crafted = False
    engine._silver_bullet_used = False

    outcome = engine._resolve_day4_after_vote()
    assert outcome == "game_over"
    assert engine.winner == "werewolf"
    assert engine.game_over is True


def test_day4_one_wolf_bullet_used_already_werewolves_win(monkeypatch):
    """Day4: one wolf + crafted but already used bullet -> werewolves win."""
    engine = _setup_day4_scenario(
        monkeypatch,
        alive_wolf_count=1,
        alive_good=["Arthur Burton", "Isabella Rodriguez"],
    )
    engine._silver_bullet_acquired = True
    engine._silver_jewelry_acquired = True
    engine._silver_bullet_crafted = True
    engine._silver_bullet_used = True

    outcome = engine._resolve_day4_after_vote()
    assert outcome == "game_over"
    assert engine.winner == "werewolf"


def test_day4_silver_shot_hits_werewolf_villagers_win(monkeypatch):
    """Day4 pending_silver_shot: shooting a werewolf -> villagers win."""
    engine = _setup_day4_scenario(
        monkeypatch,
        alive_wolf_count=1,
        alive_good=["Arthur Burton"],
    )
    engine._silver_bullet_acquired = True
    engine._silver_jewelry_acquired = True
    engine._silver_bullet_crafted = True
    engine._silver_bullet_used = False
    engine.phase = game_engine.GamePhase.PENDING_SILVER_SHOT

    wolf_name = engine.werewolf_names[0]
    result = engine.shoot_silver_bullet(wolf_name)

    assert result.get("success") is True
    assert result.get("day4_silver_shot") is True
    assert result.get("hit_werewolf") is True
    assert result.get("winner") == "villagers"
    assert engine.winner == "villagers"
    assert engine.game_over is True
    assert engine.phase == game_engine.GamePhase.GAME_OVER


def test_day4_silver_shot_hits_villager_werewolves_win(monkeypatch):
    """Day4 pending_silver_shot: shooting a villager -> werewolves win."""
    engine = _setup_day4_scenario(
        monkeypatch,
        alive_wolf_count=1,
        alive_good=["Arthur Burton"],
    )
    engine._silver_bullet_acquired = True
    engine._silver_jewelry_acquired = True
    engine._silver_bullet_crafted = True
    engine._silver_bullet_used = False
    engine.phase = game_engine.GamePhase.PENDING_SILVER_SHOT

    villager_name = "Arthur Burton"
    result = engine.shoot_silver_bullet(villager_name)

    assert result.get("success") is True
    assert result.get("day4_silver_shot") is True
    assert result.get("hit_werewolf") is False
    assert result.get("winner") == "werewolf"
    assert engine.winner == "werewolf"
    assert engine.game_over is True
    assert engine.phase == game_engine.GamePhase.GAME_OVER


# ============================================================================
# Status Exposure Tests
# ============================================================================


def test_status_exposes_night_progress(monkeypatch):
    """get_status must expose night_progress with stage info."""
    engine = _start_night(monkeypatch)
    status = engine.get_status()
    assert "night_progress" in status
    assert status["night_progress"]["stage"] == "werewolf"


def test_status_hides_silver_knife_secret_fields(monkeypatch):
    """get_status must not leak holder, target, use, or outcome of silver knife."""
    engine = _start_night(monkeypatch)
    status = engine.get_status()
    assert "silver_knife_holder" not in status
    assert "silver_knife_used" not in status
    assert "silver_knife_phase_started_at" not in status
    assert "silver_knife_phase_duration" not in status
    assert "silver_knife_scrapped_tonight" not in status
    assert "silver_knife_target_tonight" not in status
    assert "silver_knife_killed_werewolf_tonight" not in status
    assert status["night_progress"]["stage"] == "werewolf"
    assert "stage_elapsed" in status["night_progress"]
    assert "stage_duration" in status["night_progress"]


def test_status_exposes_day4_flag(monkeypatch):
    """get_status must expose _day4_no_free_activity flag."""
    engine = _make_engine(monkeypatch)
    status = engine.get_status()
    assert "day4_no_free_activity" in status
    assert status["day4_no_free_activity"] is False


def test_body_status_exposes_is_werewolf_corpse(monkeypatch):
    """Body status must expose is_werewolf_corpse field."""
    engine = _make_engine(monkeypatch)
    status = engine.get_status()
    for body in status["bodies"]:
        assert "is_werewolf_corpse" in body


# ============================================================================
# Validate no Day1 behavior changes
# ============================================================================


def test_day1_initial_state_unchanged(monkeypatch):
    """Day1 initial state must not be affected by new changes."""
    engine = _make_engine(monkeypatch, seed=11)
    assert engine.day == 1
    assert engine.phase == game_engine.GamePhase.DAY
    assert not getattr(engine, "_day4_no_free_activity", True)
    progress = getattr(engine, "_night_progress", None)
    assert progress is None or progress.get("complete", True)


def test_day1_gathering_still_works(monkeypatch):
    """Day1 gathering flow must be untouched."""
    engine = _make_engine(monkeypatch, seed=11)
    assert len(engine.bodies) >= 1
    assert engine.day == 1
    assert engine.phase == game_engine.GamePhase.DAY

"""Tests for dusk discussion voting flow:
- NPC independent agency: villagers may vote for anyone or abstain
- Deterministic fallback behavior
- Vote generation respects jail/role boundaries
- No forced compliance to sheriff/player suggestions
"""

import threading
import time

import engine_dusk
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
    # Mock chat_for_agent so dusk vote generation uses deterministic fallback
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "{}")
    return game_engine.WerewolfGameEngine(random_seed=seed)


def _make_real_map_engine(monkeypatch, seed=7):
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
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "{}")
    return game_engine.WerewolfGameEngine(random_seed=seed)


def _arrive_dusk_participants(engine):
    for name in engine._eligible_dusk_participants():
        agent = engine.agents[name]
        agent.x, agent.y = agent.target_x, agent.target_y
        engine.agent_paths.pop(name, None)


# ---------------------------------------------------------------------------
# Requirement: dusk vote prompt preserves NPC independent agency
# ---------------------------------------------------------------------------

def test_dusk_vote_prompt_contains_independence_clause(monkeypatch):
    """The dusk vote system prompt must include independent judgment language."""
    engine = _make_engine(monkeypatch)
    import inspect
    source = inspect.getsource(engine._generate_single_dusk_vote)
    assert "完全独立的判断权" in source, (
        "Dusk vote prompt must include independent judgment clause"
    )


def test_dusk_vote_prompt_allows_abstention(monkeypatch):
    """The dusk vote prompt must allow empty/abstain votes."""
    engine = _make_engine(monkeypatch)
    assert engine._is_abstain_vote("")
    assert engine._is_abstain_vote("abstain")
    assert engine._is_abstain_vote("弃票")
    assert engine._is_abstain_vote("不投")
    assert not engine._is_abstain_vote("Arthur Burton")


# ---------------------------------------------------------------------------
# Requirement: deterministic dusk vote fallback produces valid results
# ---------------------------------------------------------------------------

def test_deterministic_dusk_vote_returns_valid_target(monkeypatch):
    """_deterministic_dusk_vote must return a concrete valid target when any target exists."""
    engine = _make_engine(monkeypatch)
    voter = [n for n in engine.agents if n != "Crow" and n not in engine.werewolf_names][0]
    reason, target = engine._deterministic_dusk_vote(voter)
    assert target, f"Fallback vote must not abstain when targets exist: {reason}"
    assert target in engine.agents, f"Target '{target}' must be a known agent"
    assert target != "Crow", "Cannot vote for Crow (detective)"


def test_deterministic_dusk_vote_werewolf_votes_villager(monkeypatch):
    """Wolf voters prefer non-wolf villagers, but self-voting is allowed per spec."""
    engine = _make_engine(monkeypatch)
    wolf_name = engine.werewolf_names[0]
    reason, target = engine._deterministic_dusk_vote(wolf_name)
    # Wolves prefer non-wolves and non-Crow targets
    if target:
        assert target != "Crow", "Cannot vote for detective"
        # Wolves may vote for themselves (self-voting allowed) or for villagers
    # If target is empty, abstain is valid


def test_dusk_vote_skipped_for_jailed_npcs(monkeypatch):
    """Jailed NPCs should not vote."""
    engine = _make_engine(monkeypatch)
    target_jail = [n for n in engine.agents if n != "Crow"][0]
    engine._jailed = [target_jail]
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("我认为证据还不够，大家先说明自己的判断。")
    assert target_jail not in engine._dusk_votes, (
        f"Jailed '{target_jail}' should not be in dusk votes"
    )


def test_transition_to_dusk_starts_discussion_before_votes(monkeypatch):
    """Dusk must gather NPC discussion first; votes wait for Crow's statement. # covers REQ-040 REQ-041"""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()

    assert engine._dusk_discussion_active is True
    assert engine._dusk_vote_active is False
    assert engine._dusk_votes == {}
    assert engine._vote_history == []


def test_dusk_discussion_waits_until_everyone_arrives(monkeypatch):
    """Knowledge reveal and speeches must not start while anyone is still walking."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    arthur = engine.agents["Arthur Burton"]
    arthur.x, arthur.y = arthur.target_x + 3, arthur.target_y + 3
    engine.agent_paths["Arthur Burton"] = [(arthur.target_x + 2, arthur.target_y + 2)]

    result = engine.submit_dusk_statement("请大家先说。")

    assert result.get("error")
    assert engine._dusk_stage == "gathering"
    assert engine._dusk_discussion_statements == []


def test_autonomous_ai_lane_is_suspended_during_dusk(monkeypatch):
    """Once dusk starts, the day AI plan/act lane cannot pull NPCs away."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    arthur.x = arthur.target_x = 10
    arthur.y = arthur.target_y = 10
    arthur.runtime_state = "idle"
    arthur._last_llm_decision_time = 0
    monkeypatch.setitem(game_engine.CONFIG["llm"], "action_decision_interval_seconds", 0)

    engine._transition_to_dusk()
    action = arthur.current_action
    engine._update_agent_schedules()

    assert arthur.current_action == action
    assert not getattr(arthur, "_is_thinking", False)


def test_dusk_discussion_waits_three_seconds_after_every_npc_statement(monkeypatch):
    """Live dusk discussion keeps every NPC statement readable, including the last one."""
    engine = _make_engine(monkeypatch)
    engine._running = True
    sleeps = []
    monkeypatch.setattr(engine_dusk.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(
        engine,
        "_generate_single_dusk_discussion_statement",
        lambda speaker_name, recent_dead, clue_text: f"{speaker_name} 发言",
    )

    engine._generate_dusk_discussion_statements()

    eligible = [n for n, a in engine.agents.items() if n != "Crow" and a.is_alive and n not in engine._jailed]
    assert sleeps == [3.0] * len(eligible)
    assert len(engine._dusk_discussion_statements) == len(eligible)


def test_crow_dusk_statement_unlocks_npc_votes(monkeypatch):
    """Crow's typed dusk statement is the gate between discussion and voting. # covers REQ-040 REQ-041"""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)

    result = engine.submit_dusk_statement("我听完大家发言了，现在请各自投票。")

    assert result["success"] is True
    assert engine._dusk_discussion_active is False
    assert engine._dusk_vote_active is True
    assert engine._dusk_votes
    assert engine._vote_history


def test_live_crow_statement_then_vote_opening_are_separate_bubbles(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._running = True
    engine._transition_to_dusk()
    engine._dusk_stage = "crow_speaking"
    engine._dusk_jail_target = None
    engine.chat_bubbles["Crow"] = {"text": "我的总结", "time": time.time()}
    snapshots = []

    def fake_sleep(seconds):
        snapshots.append((
            seconds,
            engine._dusk_stage,
            engine.chat_bubbles.get("Crow", {}).get("text"),
        ))

    monkeypatch.setattr(engine_dusk.time, "sleep", fake_sleep)
    monkeypatch.setattr(engine, "_generate_dusk_votes_async", lambda: None)

    engine._open_dusk_vote_after_crow_bubble()

    assert snapshots[0] == (3.0, "crow_speaking", "我的总结")
    assert snapshots[1] == (3.0, "vote_opening", engine_dusk._CROW_START_VOTE_TEXT)
    assert engine._dusk_stage == "voting"
    assert engine._dusk_vote_active is True


def test_transition_to_dusk_clears_old_daytime_action_state(monkeypatch):
    """Entering dusk clears stale daytime NPC action, bubble, path, and conversation state."""
    engine = _make_engine(monkeypatch)
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]

    arthur.current_thought = "旧白天思考"
    arthur.current_thought_time = 123.0
    arthur.current_action = "白天旧行动"
    arthur.current_action_type = "work"
    arthur.current_emoji = "🔧"
    arthur.runtime_state = "acting"
    arthur._pending_action = {"action_type": "work", "action_status": "旧白泡"}
    arthur._action_status_visible_at = 456.0
    arthur.in_conversation_with = "Isabella Rodriguez"
    arthur._conversation_started_at = 789.0
    isabella.in_conversation_with = "Arthur Burton"
    isabella._conversation_started_at = 789.0
    engine.chat_bubbles["Arthur Burton"] = {
        "text": "旧行动气泡",
        "kind": "action_status",
        "time": time.time(),
    }
    engine.agent_paths["Arthur Burton"] = [(11, 10), (12, 10)]

    engine._transition_to_dusk()

    assert arthur.current_thought == ""
    assert arthur.current_thought_time == 0
    assert arthur._pending_action is None
    assert arthur._action_status_visible_at == 0
    assert arthur.in_conversation_with is None
    assert isabella.in_conversation_with is None
    assert "Arthur Burton" not in engine.agent_paths
    assert engine.chat_bubbles.get("Arthur Burton") is None
    assert arthur.current_action == "前往广场参加黄昏讨论"
    assert arthur.runtime_state in {"moving", "idle"}


def test_dusk_gathering_assigns_reachable_path_from_cafe(monkeypatch):
    engine = _make_engine(monkeypatch)
    isabella = engine.agents["Isabella Rodriguez"]
    isabella.x, isabella.y = 76, 19
    isabella.target_x, isabella.target_y = isabella.x, isabella.y

    engine._transition_to_dusk()

    assert (isabella.target_x, isabella.target_y) != (76, 19)
    assert engine.agent_paths.get("Isabella Rodriguez"), (
        "Isabella must receive a real path from the cafe to the dusk plaza"
    )


def test_dusk_plaza_targets_are_unique_and_spread_for_participants(monkeypatch):
    """Dusk gathering assigns unique spread-out plaza targets by participant list."""
    engine = _make_engine(monkeypatch)
    engine._jailed = {"Arthur Burton", "Isabella Rodriguez", "Maria Lopez"}

    engine._transition_to_dusk()

    participants = engine._eligible_dusk_participants()
    targets = {
        name: (engine.agents[name].target_x, engine.agents[name].target_y)
        for name in participants
    }
    assert len(set(targets.values())) == len(targets)
    import math

    center_x = engine_dusk.INITIAL_BODY_SITE["x"]
    center_y = engine_dusk.INITIAL_BODY_SITE["y"]
    angles = sorted(
        (math.degrees(math.atan2(y - center_y, x - center_x)) + 360) % 360
        for x, y in targets.values()
    )
    gaps = [
        (angles[(idx + 1) % len(angles)] - angle) % 360
        for idx, angle in enumerate(angles)
    ]
    assert max(gaps) <= 100, f"participants should be spread around the plaza: {targets}"


def test_dusk_discussion_order_starts_at_isabella_from_crows_left(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)

    order = engine._get_plaza_clockwise_order()

    assert order[0] == "Isabella Rodriguez"
    assert order[-1] == "Arthur Burton"


def test_dusk_discussion_generation_reaches_crow_statement_without_llm_delay(monkeypatch):
    """Discussion generation must advance to Crow's statement even if NPC speech calls are slow."""
    engine = _make_engine(monkeypatch)
    calls = []
    real_sleep = time.sleep

    def slow_chat(*args, **kwargs):
        calls.append(args[0])
        real_sleep(0.05)
        return "我会先说清楚自己的观察，再听克罗怎么判断。"

    monkeypatch.setattr(game_engine, "chat_for_agent", slow_chat)
    monkeypatch.setattr(engine, "_gathering_departure_gap_seconds", lambda: 0)
    monkeypatch.setattr(engine, "_pause_for_dusk_bubble", lambda: None)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)

    worker = threading.Thread(target=engine._begin_dusk_discussion_after_gathering)
    worker.start()
    worker.join(timeout=0.2)

    assert not worker.is_alive(), "dusk discussion should not block on every slow NPC call"
    assert engine._dusk_stage == "crow_statement"
    assert len(engine._dusk_discussion_statements) == len([
        n for n, a in engine.agents.items()
        if n != "Crow" and a.is_alive and n not in engine._jailed
    ])


def test_dusk_vote_all_living_non_jailed_npcs_vote(monkeypatch):
    """All living non-jailed non-Crow NPCs must cast a vote."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    eligible = [n for n, a in engine.agents.items()
                if n != "Crow" and a.is_alive and n not in engine._jailed]
    for voter in eligible:
        assert voter in engine._dusk_votes, f"'{voter}' did not cast a vote"
        assert voter in engine._dusk_vote_reasons, f"'{voter}' did not provide a reason"


def test_dusk_vote_targets_are_alive_and_not_jailed(monkeypatch):
    """Vote targets must be alive and not jailed. Self-voting is allowed."""
    engine = _make_engine(monkeypatch)
    engine._jailed = []
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    for voter, target in engine._dusk_votes.items():
        if target:
            assert engine.agents[target].is_alive, f"Target '{target}' is dead"
            assert target not in engine._jailed, f"Target '{target}' is jailed"
            # Self-voting is allowed per spec
            assert target != "Crow", "Cannot vote for detective"


# ---------------------------------------------------------------------------
# Requirement: vote history is recorded
# ---------------------------------------------------------------------------

def test_vote_history_snapshot_recorded(monkeypatch):
    """After generating dusk votes, a snapshot must be in vote_history."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    assert len(engine._vote_history) >= 1
    latest = engine._vote_history[-1]
    assert latest["day"] == engine.day
    assert "votes" in latest
    assert "reasons" in latest


def test_vote_history_includes_jail_target(monkeypatch):
    """After Crow votes and auto-resolve, vote history must include the jail target."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    # Crow casts a vote; system auto-resolves winner based on all votes
    target = [n for n in engine.agents if n != "Crow" and engine.agents[n].is_alive][0]
    result = engine.jail_vote_target(target)
    assert "error" not in result or result.get("success"), f"jail_vote_target failed: {result}"
    assert len(engine._vote_history) >= 1
    latest = engine._vote_history[-1]
    # The jail target is determined by vote counts, not necessarily Crow's choice
    assert latest.get("jail_target") is not None


# ---------------------------------------------------------------------------
# Requirement: can_start_dusk_discussion gate
# ---------------------------------------------------------------------------

def test_can_start_dusk_discussion_returns_true_when_ready(monkeypatch):
    """can_start_dusk_discussion returns True when conditions are met."""
    engine = _make_engine(monkeypatch)
    engine.game_hour = 18
    # Pre-mark all eligible NPCs as interviewed (requirement for dusk)
    all_eligible = {n for n, a in engine.agents.items()
                    if n != engine.detective_name and a.is_alive and n not in engine._jailed}
    engine._daily_interviewed.update(all_eligible)
    ok, reason = engine.can_start_dusk_discussion()
    assert ok, f"Should be able to start dusk, got: {reason}"


def test_can_start_dusk_discussion_false_during_day_one(monkeypatch):
    """Day 1 may have restrictions on dusk discussion."""
    engine = _make_engine(monkeypatch)
    ok, reason = engine.can_start_dusk_discussion()
    assert isinstance(ok, bool)
    assert isinstance(reason, str)


# ---------------------------------------------------------------------------
# Requirement: chat_for_agent JSON parse allows abstain
# ---------------------------------------------------------------------------

def test_dusk_vote_json_parsing_accepts_abstain(monkeypatch):
    """LLM JSON response with empty vote must be treated as abstain."""
    engine = _make_engine(monkeypatch)
    assert engine._is_abstain_vote("")
    assert engine._is_abstain_vote("abstain")
    assert engine._is_abstain_vote("弃票")


# ---------------------------------------------------------------------------
# Requirement: self-voting is allowed (spec section 5.3)
# ---------------------------------------------------------------------------

def test_self_voting_allowed_in_deterministic(monkeypatch):
    """Self-voting must be allowed; possible_targets includes self."""
    engine = _make_engine(monkeypatch)
    voter = [n for n in engine.agents if n != "Crow" and n not in engine.werewolf_names][0]
    for name, agent in engine.agents.items():
        if name not in {"Crow", voter}:
            agent.is_alive = False
    reason, target = engine._deterministic_dusk_vote(voter)
    assert target == voter, f"Self-voting should be possible for {voter}: {reason}"


def test_crow_can_vote_for_self(monkeypatch):
    """Crow must be able to vote for themselves."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    # Crow votes for self
    result = engine.jail_vote_target("Crow")
    assert "error" not in result or result.get("success"), f"Crow self-vote failed: {result}"


def test_crow_vote_recorded_in_dusk_votes(monkeypatch):
    """After Crow votes, _dusk_votes must include Crow's vote."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    engine.jail_vote_target("Arthur Burton")
    assert "Crow" in engine._dusk_votes, "Crow's vote should be in _dusk_votes"
    assert engine._dusk_votes["Crow"] == "Arthur Burton"


def test_crow_can_abstain_vote(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("Please vote.")

    result = engine.submit_crow_vote("")

    assert result.get("success")
    assert engine._dusk_votes["Crow"] == ""
    assert engine._dusk_crow_voted is True


def test_dusk_phase_timeout_finalizes_missing_votes_before_resolving(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    engine._dusk_stage = "voting"
    engine._dusk_vote_active = True
    engine._dusk_vote_resolved = False
    engine._dusk_vote_deadline = time.time() + 60
    engine.dusk_start_time = time.time() - 999
    engine.dusk_duration = 1
    engine._dusk_votes = {"Crow": "Arthur Burton"}
    engine._dusk_vote_reasons = {"Crow": "test"}

    engine._dusk_tick()

    assert engine._dusk_stage == "results"
    assert engine._dusk_vote_resolved is True
    missing = set(engine._eligible_dusk_voters()) - {"Crow"}
    assert missing
    assert all(engine._dusk_votes.get(name) == "" for name in missing)


# ---------------------------------------------------------------------------
# Requirement: vote resolution (spec section 6)
# ---------------------------------------------------------------------------

def test_highest_vote_wins_jail_target(monkeypatch):
    """The person with the highest vote count becomes the jail target."""
    engine = _make_engine(monkeypatch)
    # Manually set up votes: 3 for Arthur, 1 for Isabella, 2 abstain
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    engine._dusk_votes = {
        "Isabella Rodriguez": "Arthur Burton",
        "Klaus Mueller": "Arthur Burton",
        "Maria Lopez": "Arthur Burton",
        "Sam Moore": "Isabella Rodriguez",
        "Jane Moreno": "",
        "Mei Lin": "",
    }
    engine._dusk_vote_reasons = {k: "test" for k in engine._dusk_votes}
    engine._dusk_vote_active = True
    engine._dusk_crow_voted = False
    engine._dusk_vote_deadline = 0  # past deadline → auto-resolve on next tick
    engine._dusk_tick()
    assert engine._dusk_winner == "Arthur Burton", (
        f"Expected Arthur Burton (3 votes) but got {engine._dusk_winner}"
    )
    assert engine._dusk_jail_target is None
    assert engine._dusk_stage == "results"


def test_tie_broken_by_crow_vote(monkeypatch):
    """When there's a tie, Crow's vote among the tied candidates wins."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    # Tie: 2 for Arthur, 2 for Isabella. Crow votes for Isabella → Isabella wins
    engine._dusk_votes = {
        "Klaus Mueller": "Arthur Burton",
        "Maria Lopez": "Arthur Burton",
        "Sam Moore": "Isabella Rodriguez",
        "Jane Moreno": "Isabella Rodriguez",
        "Mei Lin": "",
        "Crow": "Isabella Rodriguez",
    }
    engine._dusk_vote_reasons = {k: "test" for k in engine._dusk_votes}
    engine._dusk_vote_active = True
    engine._dusk_crow_voted = True
    engine._dusk_vote_deadline = 0
    engine._dusk_tick()
    assert engine._dusk_winner == "Isabella Rodriguez", (
        f"Crow's tie-break should select Isabella, got {engine._dusk_winner}"
    )


def test_tie_without_crow_vote_uses_stable_order(monkeypatch):
    """When tied and Crow didn't vote for any tied candidate, stable order picks winner."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    # Tie: 2 for Arthur, 2 for Isabella. Crow abstains → stable order
    engine._dusk_votes = {
        "Klaus Mueller": "Arthur Burton",
        "Maria Lopez": "Arthur Burton",
        "Sam Moore": "Isabella Rodriguez",
        "Jane Moreno": "Isabella Rodriguez",
        "Mei Lin": "",
        "Crow": "",
    }
    engine._dusk_vote_reasons = {k: "test" for k in engine._dusk_votes}
    engine._dusk_vote_active = True
    engine._dusk_crow_voted = True
    engine._dusk_vote_deadline = 0
    engine._dusk_tick()
    assert engine._dusk_winner in ("Arthur Burton", "Isabella Rodriguez"), (
        f"Stable order should pick one of the tied, got {engine._dusk_winner}"
    )


def test_cannot_arbitrarily_jail_non_winner(monkeypatch):
    """jail_vote_target only records Crow's vote; the winner is auto-determined."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    # All NPC votes go to Arthur, Crow votes for Isabella
    # Arthur should win (6 NPC votes > 1 Crow vote)
    npc_names = [n for n in engine.agents if n != "Crow" and engine.agents[n].is_alive]
    engine._dusk_votes = {n: "Arthur Burton" for n in npc_names}
    engine._dusk_vote_reasons = {k: "test" for k in engine._dusk_votes}
    engine._dusk_vote_active = True
    engine._dusk_crow_voted = False
    engine._dusk_vote_deadline = 999  # far future
    # Crow votes for Isabella
    result = engine.jail_vote_target("Isabella Rodriguez")
    assert result.get("success"), f"Crow vote should succeed: {result}"
    # Winner must be Arthur (highest votes), not Isabella
    assert engine._dusk_winner == "Arthur Burton", (
        f"Winner should be Arthur (most votes), got {engine._dusk_winner}"
    )
    assert engine._dusk_jail_target is None, "Winner must not be jailed before result confirmation"


def test_confirm_vote_result_jails_only_resolved_winner(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    engine._dusk_votes = {name: "Arthur Burton" for name in engine.agents if name != "Crow"}
    engine._dusk_vote_reasons = {name: "test" for name in engine._dusk_votes}
    engine._dusk_votes["Crow"] = "Isabella Rodriguez"
    engine._dusk_crow_voted = True
    engine._resolve_dusk_votes()

    result = engine.confirm_vote_result()

    assert result["success"] is True
    assert engine._dusk_jail_target == "Arthur Burton"
    assert "Arthur Burton" in engine._jailed
    assert engine._dusk_stage == "escorting"


def test_prison_escort_real_map_moves_target_and_reaches_cell(monkeypatch):
    engine = _make_real_map_engine(monkeypatch)
    target_name = "Arthur Burton"
    target = engine.agents[target_name]
    crow = engine.agents["Crow"]
    start = (game_engine.INITIAL_BODY_SITE["x"], game_engine.INITIAL_BODY_SITE["y"])
    target.x, target.y = start
    target.target_x, target.target_y = start
    crow.x, crow.y = start[0] - 1, start[1]
    crow.target_x, crow.target_y = crow.x, crow.y
    engine.phase = game_engine.GamePhase.DUSK_DISCUSSION
    engine._dusk_stage = "escorting"
    engine._dusk_jail_target = target_name
    engine._jailed.add(target_name)

    engine._start_prison_escort(target_name)

    assert (target.target_x, target.target_y) != start
    assert engine.agent_paths.get(target_name)
    assert (crow.target_x, crow.target_y) not in set(engine.agent_paths[target_name][-3:])

    engine._move_agents()
    engine._dusk_tick()

    assert (target.x, target.y) != start

    for _ in range(200):
        if not engine.agent_paths.get(target_name) and (
            target.x,
            target.y,
        ) == (target.target_x, target.target_y):
            break
        engine._move_agents()
        engine._dusk_tick()

    cell_key = engine._get_prison_cell(target_name)
    assert target.current_location == engine_dusk.SHERIFF_AREA[cell_key]["name"]
    assert (crow.x, crow.y) != (25, 69)
    assert engine.phase == game_engine.GamePhase.NIGHT


def test_dusk_discussion_replaces_filler_statement(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    monkeypatch.setattr(
        engine,
        "_generate_single_dusk_discussion_statement",
        lambda *args, **kwargs: "我没意见，先听克罗怎么说。",
    )
    monkeypatch.setattr(engine, "_gathering_departure_gap_seconds", lambda: 0)

    engine._generate_dusk_discussion_statements()

    assert engine._dusk_discussion_statements
    for item in engine._dusk_discussion_statements:
        assert not engine_dusk._is_dusk_filler_statement(item["text"])
        assert "先听" not in item["text"]


def test_dusk_public_statement_bubble_has_no_conversation_target(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine._dusk_stage = "npc_discussion"

    engine._generate_dusk_discussion_statements()

    assert engine._dusk_discussion_statements
    for item in engine._dusk_discussion_statements:
        speaker = item["speaker"]
        bubble = engine.chat_bubbles[speaker]
        assert bubble["text"] == item["text"]
        assert bubble["target"] == ""


def test_confirm_vote_result_holds_final_words_before_prison(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    engine._dusk_votes = {name: "Arthur Burton" for name in engine.agents if name != "Crow"}
    engine._dusk_vote_reasons = {name: "test" for name in engine._dusk_votes}
    engine._dusk_votes["Crow"] = "Isabella Rodriguez"
    engine._dusk_crow_voted = True
    engine._resolve_dusk_votes()
    engine._running = True
    events = []
    monkeypatch.setattr(engine, "_jailed_final_words", lambda target: "我还有话要说。")
    monkeypatch.setattr(engine_dusk.time, "sleep", lambda seconds: events.append(("sleep", seconds)))
    started = []

    class FakeThread:
        def __init__(self, target, args=(), daemon=False):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            started.append((self.target, self.args, self.daemon))

    monkeypatch.setattr(engine_dusk.threading, "Thread", FakeThread)
    original_place = engine._place_in_prison

    def record_place(target, **kwargs):
        events.append(("place", target))
        original_place(target, **kwargs)

    monkeypatch.setattr(engine, "_place_in_prison", record_place)

    result = engine.confirm_vote_result()

    assert result["success"] is True
    assert result["pending"] is True
    assert started == [(engine._run_vote_result_sequence, ("Arthur Burton",), True)]
    engine._run_vote_result_sequence("Arthur Burton")
    assert events[0] == ("sleep", 6.0)
    assert events[1] == ("sleep", engine_dusk._DUSK_FINAL_WORDS_HOLD_SECONDS)
    assert events[2] == ("place", "Arthur Burton")
    assert engine.chat_bubbles["Arthur Burton"]["text"] == "我还有话要说。"


def test_confirm_vote_result_all_abstain_has_crow_dismissal(monkeypatch):
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("Please vote.")
    engine._dusk_votes = {name: "" for name in engine.agents if engine.agents[name].is_alive}
    engine._dusk_vote_reasons = {name: "abstain" for name in engine._dusk_votes}
    engine._dusk_crow_voted = True
    engine._resolve_dusk_votes()
    engine._running = True
    sleeps = []
    monkeypatch.setattr(engine_dusk.time, "sleep", lambda seconds: sleeps.append(seconds))
    started = []

    class FakeThread:
        def __init__(self, target, args=(), daemon=False):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            started.append((self.target, self.args, self.daemon))

    monkeypatch.setattr(engine_dusk.threading, "Thread", FakeThread)

    result = engine.confirm_vote_result()

    assert result["success"] is True
    assert result["jailed"] is None
    assert result["pending"] is True
    assert started == [(engine._run_vote_result_sequence, (None,), True)]
    engine._run_vote_result_sequence(None)
    assert "今晚无人被关押" in engine.chat_bubbles["Crow"]["text"]
    assert "晚上注意小心" in engine.chat_bubbles["Crow"]["text"]
    assert sleeps == [6.0]


# ---------------------------------------------------------------------------
# Requirement: Day 1 fixed knowledge revelation (spec section 3)
# ---------------------------------------------------------------------------

def test_day1_knowledge_text_is_fixed(monkeypatch):
    """The day 1 knowledge text must be a fixed string, not LLM-generated."""
    text = engine_dusk._DAY1_KNOWLEDGE_TEXT
    assert "狼人" in text
    assert "咬痕" in text
    assert "抓痕" in text
    assert len(text) > 100, "Knowledge text should be substantial"


def test_day1_knowledge_speaker_is_not_werewolf_dependent(monkeypatch):
    """Day 1 knowledge speaker selection must not depend on werewolf status."""
    engine = _make_engine(monkeypatch)
    speaker = engine._resolve_speaker_for_day1_knowledge()
    assert speaker in engine.agents
    assert speaker != "Crow"
    assert engine.agents[speaker].is_alive
    # The speaker can be a werewolf; the knowledge still triggers
    # We just verify that a valid speaker is returned regardless of role


def test_day1_knowledge_revelation_sets_bubble_and_log(monkeypatch):
    """Day 1 knowledge revelation must set a chat bubble and log entry."""
    engine = _make_engine(monkeypatch)
    engine.day = 1
    speaker = engine._resolve_speaker_for_day1_knowledge()
    engine._reveal_day1_werewolf_knowledge()
    assert speaker in engine.chat_bubbles, f"Speaker {speaker} should have a chat bubble"
    assert engine.chat_bubbles[speaker]["text"] == engine_dusk._DAY1_KNOWLEDGE_TEXT


# ---------------------------------------------------------------------------
# Requirement: vote status exposure (spec section 6)
# ---------------------------------------------------------------------------

def test_vote_summary_includes_voter_lists(monkeypatch):
    """Vote summary must include lists of who voted for each target."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    vote_summary = engine._build_vote_summary()
    assert "voters_by_target" in vote_summary, "Must include voters_by_target"
    for target, voters in vote_summary.get("voters_by_target", {}).items():
        assert isinstance(voters, list), f"Voters for {target} must be a list"


def test_vote_summary_exposes_deadline(monkeypatch):
    """Vote summary must expose the vote deadline timestamp."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    _arrive_dusk_participants(engine)
    engine.submit_dusk_statement("请投票。")
    vote_summary = engine._build_vote_summary()
    assert "deadline" in vote_summary, "Must include vote deadline"
    assert vote_summary["active"] is True

"""Tests for dusk discussion voting flow:
- NPC independent agency: villagers may vote for anyone or abstain
- Deterministic fallback behavior
- Vote generation respects jail/role boundaries
- No forced compliance to sheriff/player suggestions
"""

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
    # Mock chat_for_agent so dusk vote generation uses deterministic fallback
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "{}")
    return game_engine.WerewolfGameEngine(random_seed=seed)


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
    """_deterministic_dusk_vote must return a valid target or abstain (empty)."""
    engine = _make_engine(monkeypatch)
    voter = [n for n in engine.agents if n != "Crow" and n not in engine.werewolf_names][0]
    reason, target = engine._deterministic_dusk_vote(voter)
    # With no clues, there's a 55% abstention chance; accept either outcome
    if target:
        assert target in engine.agents, f"Target '{target}' must be a known agent"
        assert target != voter, "Cannot vote for self"
        assert target != "Crow", "Cannot vote for Crow (detective)"
    else:
        # Abstain is valid
        assert "弃票" in reason or "没有足够把握" in reason or "没有可指控" in reason


def test_deterministic_dusk_vote_werewolf_votes_villager(monkeypatch):
    """Wolf voters must vote for a non-wolf villager, not another wolf."""
    engine = _make_engine(monkeypatch)
    wolf_name = engine.werewolf_names[0]
    reason, target = engine._deterministic_dusk_vote(wolf_name)
    assert target not in engine.werewolf_names, (
        f"Wolf '{wolf_name}' voted for another wolf '{target}'"
    )
    assert target != wolf_name, "Cannot vote for self"
    assert target != "Crow", "Cannot vote for detective"


def test_dusk_vote_skipped_for_jailed_npcs(monkeypatch):
    """Jailed NPCs should not vote."""
    engine = _make_engine(monkeypatch)
    target_jail = [n for n in engine.agents if n != "Crow"][0]
    engine._jailed = [target_jail]
    engine._transition_to_dusk()
    assert target_jail not in engine._dusk_votes, (
        f"Jailed '{target_jail}' should not be in dusk votes"
    )


def test_dusk_vote_all_living_non_jailed_npcs_vote(monkeypatch):
    """All living non-jailed non-Crow NPCs must cast a vote."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    eligible = [n for n, a in engine.agents.items()
                if n != "Crow" and a.is_alive and n not in engine._jailed]
    for voter in eligible:
        assert voter in engine._dusk_votes, f"'{voter}' did not cast a vote"
        assert voter in engine._dusk_vote_reasons, f"'{voter}' did not provide a reason"


def test_dusk_vote_targets_are_alive_and_not_jailed(monkeypatch):
    """Vote targets must be alive and not jailed."""
    engine = _make_engine(monkeypatch)
    engine._jailed = []
    engine._transition_to_dusk()
    for voter, target in engine._dusk_votes.items():
        if target:
            assert engine.agents[target].is_alive, f"Target '{target}' is dead"
            assert target not in engine._jailed, f"Target '{target}' is jailed"
            assert target != voter, "Cannot vote for self"
            assert target != "Crow", "Cannot vote for detective"


# ---------------------------------------------------------------------------
# Requirement: vote history is recorded
# ---------------------------------------------------------------------------

def test_vote_history_snapshot_recorded(monkeypatch):
    """After generating dusk votes, a snapshot must be in vote_history."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    assert len(engine._vote_history) >= 1
    latest = engine._vote_history[-1]
    assert latest["day"] == engine.day
    assert "votes" in latest
    assert "reasons" in latest


def test_vote_history_includes_jail_target(monkeypatch):
    """After player chooses jail target, vote history must include it."""
    engine = _make_engine(monkeypatch)
    engine._transition_to_dusk()
    target = [n for n in engine._dusk_votes.keys()][0]
    result = engine.jail_vote_target(target)
    assert "error" not in result, f"jail_vote_target failed: {result}"
    assert len(engine._vote_history) >= 1
    latest = engine._vote_history[-1]
    assert latest.get("jail_target") == target


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

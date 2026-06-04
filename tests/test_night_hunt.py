import pytest
from night_hunt import (
    HuntCandidate,
    NightHuntState,
    choose_forced_target,
    build_trace_clues,
)


def test_hunt_candidate_score():
    """Verify that HuntCandidate calculates scores correctly favoring short paths and low witness risk."""
    # Score = path_length + witness_risk * 20
    c1 = HuntCandidate(name="Alice", path_length=10, witness_risk=0, reachable=True)
    c2 = HuntCandidate(name="Bob", path_length=10, witness_risk=1, reachable=True)
    c3 = HuntCandidate(name="Charlie", path_length=50, witness_risk=0, reachable=True)

    assert c1.score == 10
    assert c2.score == 30
    assert c3.score == 50


def test_target_selection_prefers_lowest_score():
    """Verify that choose_forced_target selects the reachable candidate with the lowest score."""
    candidates = [
        HuntCandidate(name="Far Safe", path_length=60, witness_risk=0, reachable=True),      # score = 60
        HuntCandidate(name="Near Risky", path_length=10, witness_risk=3, reachable=True),    # score = 70
        HuntCandidate(name="Optimal", path_length=20, witness_risk=1, reachable=True),       # score = 40
    ]
    selected = choose_forced_target(candidates)
    assert selected is not None
    assert selected.name == "Optimal"


def test_unreachable_exclusion():
    """Verify that unreachable candidates are completely excluded from selection."""
    candidates = [
        HuntCandidate(name="Blocked Easy", path_length=5, witness_risk=0, reachable=False),
        HuntCandidate(name="Blocked Risky", path_length=10, witness_risk=2, reachable=False),
        HuntCandidate(name="Reachable Far", path_length=80, witness_risk=1, reachable=True),
    ]
    selected = choose_forced_target(candidates)
    assert selected is not None
    assert selected.name == "Reachable Far"


def test_no_reachable_candidates_returns_none():
    """Verify that if all candidates are unreachable, choose_forced_target returns None."""
    candidates = [
        HuntCandidate(name="Blocked 1", path_length=5, witness_risk=0, reachable=False),
        HuntCandidate(name="Blocked 2", path_length=12, witness_risk=1, reachable=False),
    ]
    selected = choose_forced_target(candidates)
    assert selected is None


def test_night_hunt_state_initialization():
    """Verify that NightHuntState initializes with correct default values and types."""
    state = NightHuntState(started_at=100.0, deadline_at=400.0)
    assert state.started_at == 100.0
    assert state.deadline_at == 400.0
    assert state.stage == "choosing"
    assert state.target_name == ""
    assert state.target_changes == []
    assert state.witnessed_by == set()
    assert state.killed_name == ""
    assert state.withdrawal_complete is False
    assert state.forced_completion is False


def test_normal_kill_produces_at_least_one_clue():
    """Verify that a normal clean unwitnessed kill produces at least one factual trace clue."""
    clues = build_trace_clues(
        victim_name="Isabella Rodriguez",
        location="Johnson Park",
        witnesses=[],
        forced_completion=False,
    )
    
    assert len(clues) >= 1
    # Check factual fields
    for clue in clues:
        assert "clue_type" in clue
        assert "summary" in clue
        assert "source" in clue
        assert clue["related_person"] == "Isabella Rodriguez"
        assert clue["location"] == "Johnson Park"


def test_witness_clues_increase_clue_count():
    """Verify that each witness increases clue count and produces witness-specific clues."""
    clues_no_witness = build_trace_clues(
        victim_name="Sam Moore",
        location="Tavern",
        witnesses=[],
        forced_completion=False,
    )
    
    clues_one_witness = build_trace_clues(
        victim_name="Sam Moore",
        location="Tavern",
        witnesses=["Alice"],
        forced_completion=False,
    )
    
    clues_two_witnesses = build_trace_clues(
        victim_name="Sam Moore",
        location="Tavern",
        witnesses=["Alice", "Bob"],
        forced_completion=False,
    )
    
    assert len(clues_one_witness) == len(clues_no_witness) + 1
    assert len(clues_two_witnesses) == len(clues_one_witness) + 1
    
    # Check that witness statements are properly credited
    witness_sources = [c["source"] for c in clues_two_witnesses if c["clue_type"] == "witness_statement"]
    assert "Alice" in witness_sources
    assert "Bob" in witness_sources


def test_forced_completion_produces_strictly_more_clues():
    """Verify forced completion produces strictly more clues than clean unwitnessed kill."""
    clean_clues = build_trace_clues(
        victim_name="Sam Moore",
        location="Tavern",
        witnesses=[],
        forced_completion=False,
    )
    
    forced_clues = build_trace_clues(
        victim_name="Sam Moore",
        location="Tavern",
        witnesses=[],
        forced_completion=True,
    )
    
    assert len(forced_clues) > len(clean_clues)
    
    # Check that forced completion clue type exists
    clue_types = [c["clue_type"] for c in forced_clues]
    assert "disturbed_trail" in clue_types

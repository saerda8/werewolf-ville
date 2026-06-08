import threading
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import engine_dusk
import game_engine
from engine_navigation import bfs_path, load_collision_maze
from world_config import SHERIFF_AREA


class _Phase(Enum):
    DUSK_DISCUSSION = "dusk_discussion"


class _VoteResultHarness(engine_dusk.EngineDuskMixin):
    def __init__(self):
        self._lock = threading.RLock()
        self.phase = _Phase.DUSK_DISCUSSION
        self._dusk_stage = "results"
        self._dusk_winner = "Arthur Burton"
        self._dusk_result_sequence_running = False
        self._dusk_jail_target = None
        self._running = True
        self.broadcasts = 0
        self.sequence_calls = []

    def _broadcast_state(self):
        self.broadcasts += 1

    def _run_vote_result_sequence(self, winner):
        self.sequence_calls.append(winner)


def test_confirm_vote_result_returns_pending_and_starts_background_sequence(monkeypatch):
    engine = _VoteResultHarness()
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

    assert result == {"success": True, "jailed": "Arthur Burton", "pending": True}
    assert engine._dusk_stage == "result_announcement_pending"
    assert engine._dusk_jail_target == "Arthur Burton"
    assert engine._dusk_result_sequence_running is True
    assert engine.broadcasts == 1
    assert engine.sequence_calls == []
    assert started == [(engine._run_vote_result_sequence, ("Arthur Burton",), True)]


def test_sheriff_office_and_right_prison_cell_are_reachable_on_real_map():
    maze = load_collision_maze()
    plaza = (48, 46)
    office = (23, 66)

    for start in (plaza, office):
        for point in SHERIFF_AREA["sheriff_office"]["anchor_points"]:
            assert bfs_path(maze, start, point) is not None
        for point in SHERIFF_AREA["prison_cell_2"]["anchor_points"]:
            assert bfs_path(maze, start, point) is not None


def test_silver_knife_path_exhaustion_without_adjacency_marks_phase_complete():
    holder = SimpleNamespace(x=0, y=0, is_alive=True)
    target = SimpleNamespace(x=5, y=5, is_alive=True)
    engine = SimpleNamespace(
        _silver_knife_action={
            "status": "moving",
            "complete": False,
            "holder": "Holder",
            "target": "Target",
            "initial_path_len": 4,
        },
        _night_progress={
            "active": True,
            "stage": "silver_knife",
            "complete": False,
            "wolf_complete": True,
            "knife_complete": False,
        },
        agents={"Holder": holder, "Target": target},
        agent_paths={"Holder": []},
        werewolf_names=[],
        bodies=[],
        complete_reasons=[],
    )

    def prepare():
        return None

    def move_agents():
        return None

    def complete(reason=""):
        engine.complete_reasons.append(reason)
        engine._silver_knife_action["complete"] = True
        engine._silver_knife_action["reason"] = reason
        engine._night_progress["knife_complete"] = True

    def use_silver_knife(holder_name, target_name):
        raise AssertionError("knife must not fire when holder is not adjacent")

    engine._prepare_silver_knife_action = prepare
    engine._move_agents = move_agents
    engine._complete_silver_knife_action = complete
    engine.use_silver_knife = use_silver_knife

    game_engine.WerewolfGameEngine._advance_silver_knife_action(engine)

    assert engine._silver_knife_action["complete"] is True
    assert engine._night_progress["knife_complete"] is True
    assert engine.complete_reasons


def test_dusk_vote_ui_hides_vote_totals_and_has_only_footer_abstain_before_results():
    html = (Path(__file__).parents[1] / "ui" / "templates" / "index.html").read_text(encoding="utf-8")
    start = html.index("function renderDuskVotingFlow(state)")
    end = html.index("function renderVoteHistory(state)", start)
    block = html[start:end]

    assert 'const showVoteButtons = stage === "voting" && voteSummary.active' in block
    assert 'const showVoteResults = ["results", "result"].includes(stage);' in block
    assert "showVoteResults ? `${Math.trunc(Number(count.count) || 0)}" in block
    assert 'if (showVoteResults && abstainers.length)' in block
    assert 'footerAbstainBtn.id = "footer-abstain-btn";' in block
    assert 'footerAbstainBtn.addEventListener("click", (e) => submitCrowVote("", e.target));' in block
    assert 'id="abstain-vote-button"' not in block
    assert "const abstainRow" not in block

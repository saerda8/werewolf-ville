import threading

import game_engine
import llm


class _ImmediateClient:
    class chat:
        class completions:
            @staticmethod
            def create(**kwargs):
                class _Message:
                    content = "ok"

                class _Choice:
                    message = _Message()

                class _Response:
                    choices = [_Choice()]

                return _Response()


def test_priority_agent_chat_bypasses_full_background_semaphore(monkeypatch):
    original = llm._MODEL_SEMAPHORE
    held = threading.Semaphore(1)
    assert held.acquire(blocking=False) is True
    monkeypatch.setattr(llm, "_MODEL_SEMAPHORE", held)
    monkeypatch.setattr(llm, "_client", _ImmediateClient())

    try:
        result = llm.chat_for_agent(
            "Arthur Burton",
            "system",
            "user",
            priority=True,
            max_retries=0,
        )
    finally:
        original_release = getattr(original, "release", None)
        if original_release:
            pass

    assert result == "ok"


def test_agent_error_normalizes_insufficient_balance(monkeypatch):
    class _BalanceClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise Exception("APIStatusError: Error code: 402 - {'error': {'type': 'insufficient_balance'}}")

    monkeypatch.setattr(llm, "_client", _BalanceClient())

    result = llm.chat_for_agent("Arthur Burton", "system", "user", max_retries=0)

    assert result == ""
    assert "余额不足" in llm.get_last_error_for_agent("Arthur Burton")


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
    monkeypatch.setattr(game_engine.Agent, "read_soul", lambda self: "test soul")
    monkeypatch.setattr(game_engine.Agent, "read_memory", lambda self: "test memory")
    return game_engine.WerewolfGameEngine(random_seed=seed)


def test_detective_move_to_agent_reserves_target_from_npc_chat(monkeypatch):
    """Crow's pending interview target is reserved while he walks. # covers REQ-067 REQ-068 REQ-077"""
    engine = _make_engine(monkeypatch)
    engine._gathering_active = False
    engine.phase = game_engine.GamePhase.DAY
    monkeypatch.setattr(game_engine, "chat_for_agent", lambda *args, **kwargs: "我想和你聊聊。")

    crow = engine.agents["Crow"]
    arthur = engine.agents["Arthur Burton"]
    isabella = engine.agents["Isabella Rodriguez"]
    crow.x, crow.y = 1, 1
    arthur.x, arthur.y = 10, 10
    isabella.x, isabella.y = 11, 10

    assert engine.move_detective_to_agent("Arthur Burton") is True
    engine._trigger_npc_chat("Arthur Burton", "Isabella Rodriguez")

    assert getattr(engine, "_detective_chat_pending_target", None) == "Arthur Burton"
    assert arthur.in_conversation_with != "Isabella Rodriguez"
    assert isabella.in_conversation_with != "Arthur Burton"

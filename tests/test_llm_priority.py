import threading

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

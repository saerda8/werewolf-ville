from ui.app import (
    _classify_llm_test_error,
    _friendly_llm_test_error,
    _test_local_chat2api_agent,
    _local_chat2api_override,
    _runtime_llm_override_from_data,
)


def test_chat2api_provider_uses_local_config():
    assert _runtime_llm_override_from_data({"provider": "chat2api"}) is None


def test_local_chat2api_override_uses_config():
    override = _local_chat2api_override()

    assert override["provider"] == "chat2api"
    assert override["api_base"].endswith("/v1")
    assert override["model"]
    assert "api_key" in override


def test_local_chat2api_agent_test_uses_npc_path(monkeypatch):
    import ui.app as app_module

    monkeypatch.setattr(app_module, "chat_for_agent", lambda *args, **kwargs: "OK")
    monkeypatch.setattr(app_module, "get_model_for_agent", lambda name: "Qwen3.6-35B-A3B")

    model, sample = _test_local_chat2api_agent()

    assert model == "Qwen3.6-35B-A3B"
    assert sample == "OK"


def test_preset_provider_uses_known_base_url():
    override = _runtime_llm_override_from_data({
        "provider": "deepseek",
        "api_key": "sk-test",
        "model": "deepseek-chat",
        "api_base": "http://ignored.example/v1",
    })

    assert override == {
        "provider": "deepseek",
        "api_key": "sk-test",
        "model": "deepseek-chat",
        "api_base": "https://api.deepseek.com/v1",
    }


def test_custom_provider_requires_custom_base_url():
    override = _runtime_llm_override_from_data({
        "provider": "custom",
        "api_key": "sk-test",
        "model": "custom-model",
        "api_base": "http://127.0.0.1:9000/v1",
    })

    assert override == {
        "provider": "custom",
        "api_key": "sk-test",
        "model": "custom-model",
        "api_base": "http://127.0.0.1:9000/v1",
    }


def test_anthropic_provider_uses_messages_base_url():
    override = _runtime_llm_override_from_data({
        "provider": "anthropic",
        "api_key": "sk-ant-test",
        "model": "claude-3-5-sonnet-latest",
        "api_base": "http://ignored.example/v1",
    })

    assert override == {
        "provider": "anthropic",
        "api_key": "sk-ant-test",
        "model": "claude-3-5-sonnet-latest",
        "api_base": "https://api.anthropic.com/v1",
    }


def test_custom_anthropic_provider_requires_custom_base_url():
    override = _runtime_llm_override_from_data({
        "provider": "custom_anthropic",
        "api_key": "sk-ant-test",
        "model": "claude-compatible-model",
        "api_base": "http://127.0.0.1:9001/v1",
    })

    assert override == {
        "provider": "custom_anthropic",
        "api_key": "sk-ant-test",
        "model": "claude-compatible-model",
        "api_base": "http://127.0.0.1:9001/v1",
    }


def test_remote_provider_requires_api_key():
    override = _runtime_llm_override_from_data({
        "provider": "openai",
        "model": "gpt-4o-mini",
    })

    assert "error" in override
    assert "API key" in override["error"]


def test_rate_limit_error_is_classified():
    err = Exception("RateLimitError: Error code: 429 - model is temporarily rate-limited upstream")

    assert _classify_llm_test_error(err) == "rate_limited"


def test_insufficient_balance_error_is_classified_and_friendly():
    err = Exception("APIStatusError: Error code: 402 - {'error': {'code': '402', 'type': 'insufficient_balance'}}")

    reason = _classify_llm_test_error(err)

    assert reason == "insufficient_balance"
    assert "余额不足" in _friendly_llm_test_error(reason, "openrouter", "test-model", str(err))

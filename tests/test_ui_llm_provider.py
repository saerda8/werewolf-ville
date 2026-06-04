from ui.app import _classify_llm_test_error, _friendly_llm_test_error, _runtime_llm_override_from_data


def test_chat2api_provider_uses_local_config():
    assert _runtime_llm_override_from_data({"provider": "chat2api"}) is None


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

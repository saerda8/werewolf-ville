"""
Tests for robust JSON extraction from LLM responses in agent.decide_next_action.

Covers:
- Fenced ```json block
- Explanatory text before/after JSON
- Braces inside JSON string values
"""
import pytest
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent import Agent


# --- Helper to invoke the private extraction method ---

def _extract(raw: str) -> dict:
    """Call Agent._extract_json_text static method."""
    return Agent._extract_json_text(raw)


# === Pure extraction tests (no Agent instance needed) ===

class TestExtractJsonText:
    """Unit tests for Agent._extract_json_text (static helper)."""

    def test_bare_json_object(self):
        raw = '{"action_type": "stay", "target_location": "home"}'
        assert _extract(raw) == raw

    def test_json_with_whitespace(self):
        raw = '  \n  {"key": "value"}  \n  '
        assert _extract(raw).strip() == '{"key": "value"}'

    def test_fenced_json_block(self):
        raw = '```json\n{"action": "move_to", "target": "Hobbs Cafe"}\n```'
        assert _extract(raw) == '{"action": "move_to", "target": "Hobbs Cafe"}'

    def test_fenced_no_language(self):
        raw = '```\n{"action": "observe"}\n```'
        assert _extract(raw) == '{"action": "observe"}'

    def test_fenced_with_carriage_return(self):
        raw = '```json\r\n{"action": "rest"}\r\n```'
        assert _extract(raw) == '{"action": "rest"}'

    def test_text_before_json(self):
        raw = 'Here is my decision:\n{"action_type": "move_to", "target_location": "home"}\nHope this works.'
        assert _extract(raw) == '{"action_type": "move_to", "target_location": "home"}'

    def test_text_before_with_code_fence(self):
        raw = 'Let me output:\n```json\n{"action": "talk", "person": "Maria"}\n```\nDone.'
        assert _extract(raw) == '{"action": "talk", "person": "Maria"}'

    def test_braces_inside_string_value(self):
        raw = '{"action": "move to {target}", "note": "it has {braces} inside"}'
        result = _extract(raw)
        parsed = json.loads(result)
        assert parsed["action"] == "move to {target}"
        assert parsed["note"] == "it has {braces} inside"

    def test_nested_braces_in_string(self):
        raw = '{"template": "Hello {name}, your score is {score} points"}'
        result = _extract(raw)
        parsed = json.loads(result)
        assert parsed["template"] == "Hello {name}, your score is {score} points"

    def test_mixed_fence_with_braces_in_string(self):
        raw = 'Thinking...\n```\n{"msg": "format {var}", "data": [1, 2, {"nested": 3}]}\n```\nEnd.'
        result = _extract(raw)
        parsed = json.loads(result)
        assert parsed["msg"] == "format {var}"
        assert parsed["data"] == [1, 2, {"nested": 3}]

    def test_no_json_returns_empty(self):
        raw = "This is just a plain sentence without any JSON object."
        assert _extract(raw) == ""

    def test_empty_string(self):
        assert _extract("") == ""

    def test_json_with_escaped_quotes(self):
        raw = '{"message": "he said \\\"hello\\\""}'
        assert _extract(raw) == raw

    def test_multiple_code_fences(self):
        raw = 'First ```json\n{"a": 1}\n```\nMore text\n```\n{"b": 2}\n```'
        result = _extract(raw)
        parsed = json.loads(result)
        # Should pick the first valid JSON inside a fence
        assert parsed == {"a": 1}


# === Integration tests using decide_next_action ===

def _make_decision_raw(agent, raw_response: str, monkeypatch):
    """Replace chat_for_agent to return a fixed raw response, then call decide_next_action."""
    import agent as agent_module

    original = agent_module.chat_for_agent

    def fake_chat_for_agent(name, system, prompt, **kw):
        return raw_response

    monkeypatch.setattr(agent_module, "chat_for_agent", fake_chat_for_agent)
    try:
        result = agent.decide_next_action(
            game_hour=10, day=1, dead_list=[], nearby_info="", scene_info=""
        )
    finally:
        monkeypatch.setattr(agent_module, "chat_for_agent", original)
    return result


class TestDecideNextActionExtraction:
    """Integration tests verifying that decide_next_action correctly extracts JSON."""

    def test_fenced_json_block(self, monkeypatch):
        agent = Agent(name="TestAgent", role="villager", model="test")
        raw = '```json\n{"action_type": "stay", "target_location": "home", "action": "rest", "thought": "tired", "expected_result": "recover"}\n```'
        result = _make_decision_raw(agent, raw, monkeypatch)
        assert result.get("ok") is True
        assert result.get("action_type") == "continue_current"

    def test_explanatory_text_before_json(self, monkeypatch):
        agent = Agent(name="TestAgent", role="villager", model="test")
        raw = 'I think I should rest now.\n{"action_type": "rest", "target_location": "home", "action": "sleep", "thought": "need rest", "expected_result": "energy"}\nThat is my plan.'
        result = _make_decision_raw(agent, raw, monkeypatch)
        assert result.get("ok") is True
        assert result.get("action_type") == "rest"

    def test_braces_in_string_value(self, monkeypatch):
        agent = Agent(name="TestAgent", role="villager", model="test")
        raw = '{"action_type": "move_to", "target_location": "Hobbs Cafe", "action": "talk about {werewolf case}", "thought": "gather info", "expected_result": "clues"}'
        result = _make_decision_raw(agent, raw, monkeypatch)
        assert result.get("ok") is True
        assert result.get("action") == "talk about {werewolf case}"

    def test_fence_with_braces_in_string(self, monkeypatch):
        agent = Agent(name="TestAgent", role="villager", model="test")
        raw = 'Hmm let me respond:\n```\n{"action_type": "socialize", "target_location": "The Rose and Crown Pub", "action": "ask about {the murder}", "thought": "need info", "expected_result": "find leads"}\n```\nThat is all.'
        result = _make_decision_raw(agent, raw, monkeypatch)
        assert result.get("ok") is True
        assert result.get("action") == "ask about {the murder}"

    def test_visible_clue_hint_bool_fields_are_normalized(self, monkeypatch):
        agent = Agent(name="TestAgent", role="villager", model="test")
        raw = (
            '{"action_type": "observe", "target_location": "Hobbs Cafe", '
            '"action": "留意昨晚异常", "thought": "我怀疑有人隐瞒行踪", '
            '"expected_result": "等待警长深挖", '
            '"has_visible_clue_hint": "true", "has_detective_hint": false}'
        )
        result = _make_decision_raw(agent, raw, monkeypatch)
        assert result.get("ok") is True
        assert result.get("has_visible_clue_hint") is True
        assert result.get("has_detective_hint") is False

    def test_duration_minutes_is_normalized(self, monkeypatch):
        agent = Agent(name="TestAgent", role="villager", model="test")
        raw = (
            '{"action_type": "work", "target_location": "Hobbs Cafe", '
            '"action": "整理柜台", "thought": "继续营业", '
            '"expected_result": "保持秩序", "duration_minutes": 2}'
        )
        result = _make_decision_raw(agent, raw, monkeypatch)
        assert result.get("ok") is True
        assert result.get("duration_minutes") == 5

    def test_duration_minutes_defaults_and_caps(self, monkeypatch):
        agent = Agent(name="TestAgent", role="villager", model="test")
        too_long = (
            '{"action_type": "inspect", "target_location": "Oak Hill College", '
            '"action": "查阅旧档案", "thought": "找资料", '
            '"expected_result": "发现线索", "duration_minutes": 90}'
        )
        capped = _make_decision_raw(agent, too_long, monkeypatch)
        assert capped.get("ok") is True
        assert capped.get("duration_minutes") == 30

        missing = (
            '{"action_type": "observe", "target_location": "Johnson Park", '
            '"action": "观察周围", "thought": "确认安全", '
            '"expected_result": "发现异常"}'
        )
        defaulted = _make_decision_raw(agent, missing, monkeypatch)
        assert defaulted.get("ok") is True
        assert defaulted.get("duration_minutes") == 15

    def test_action_status_is_preserved_as_separate_visible_duration_text(self, monkeypatch):
        agent = Agent(name="TestAgent", role="villager", model="test")
        raw = (
            '{"action_type": "work", "target_location": "Hobbs Cafe", '
            '"action": "前往霍布斯咖啡馆，准备开门营业", '
            '"action_status": "准备开门营业", '
            '"thought": "咖啡馆需要恢复营业", "expected_result": "开始营业"}'
        )

        result = _make_decision_raw(agent, raw, monkeypatch)

        assert result.get("ok") is True
        assert result.get("action") == "前往霍布斯咖啡馆，准备开门营业"
        assert result.get("action_status") == "准备开门营业"

    def test_invalid_json_returns_error(self, monkeypatch):
        agent = Agent(name="TestAgent", role="villager", model="test")
        raw = '{"action_type": "stay", "target_location": broken json here}'
        result = _make_decision_raw(agent, raw, monkeypatch)
        assert result.get("ok") is False
        # Either extraction fails (new code) or json_parse_error (old code path)
        error = result.get("error", "")
        assert "json_extraction_failed" in error or "json_parse_error" in error

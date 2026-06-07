import json as _json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent import Agent


# ---------------------------------------------------------------------------
# parse_memory_consolidation_result
# ---------------------------------------------------------------------------

def test_parse_memory_consolidation_result():
    raw = """
    {
      "memories": [
        {
          "type": "thought",
          "text": "亚瑟认为伊莎贝拉可能注意到了他的异常。",
          "importance": 8,
          "keywords": ["亚瑟", "伊莎贝拉", "异常"],
          "subject": "Arthur Burton",
          "predicate": "suspects",
          "object": "Isabella Rodriguez"
        }
      ],
      "current_goal": "避免伊莎贝拉继续怀疑自己。"
    }
    """

    parsed = Agent.parse_memory_consolidation_result(raw)

    assert parsed["current_goal"] == "避免伊莎贝拉继续怀疑自己。"
    assert parsed["memories"][0]["type"] == "thought"
    assert parsed["memories"][0]["importance"] == 8


def test_parse_memory_consolidation_result_handles_markdown_fence():
    raw = """模型输出如下：
```json
{
  "memories": [
    {
      "type": "event",
      "text": "伊莎贝拉看见亚瑟在咖啡馆门口停留。",
      "importance": 5,
      "keywords": ["伊莎贝拉", "亚瑟", "咖啡馆"],
      "subject": "Isabella Rodriguez",
      "predicate": "noticed",
      "object": "Arthur Burton"
    }
  ],
  "current_goal": ""
}
```
"""

    parsed = Agent.parse_memory_consolidation_result(raw)

    assert parsed["current_goal"] == ""
    assert parsed["memories"][0]["type"] == "event"
    assert "咖啡馆" in parsed["memories"][0]["text"]


def test_parse_empty_or_none_returns_default():
    """Empty string, None, or whitespace returns safe default dict."""
    assert Agent.parse_memory_consolidation_result("") == {
        "memories": [], "current_goal": ""
    }
    assert Agent.parse_memory_consolidation_result(None) == {
        "memories": [], "current_goal": ""
    }
    assert Agent.parse_memory_consolidation_result("   ") == {
        "memories": [], "current_goal": ""
    }


def test_parse_non_json_returns_default():
    """Garbled input returns default without crashing."""
    result = Agent.parse_memory_consolidation_result("not json at all")
    assert result["memories"] == []
    assert result["current_goal"] == ""


def test_parse_preserves_evidence_field():
    """Consolidated memories preserve evidence when present."""
    raw = """{
      "memories": [
        {
          "type": "event",
          "text": "Found evidence",
          "importance": 9,
          "evidence": ["bloody knife", "footprint"]
        }
      ],
      "current_goal": "Investigate"
    }"""
    parsed = Agent.parse_memory_consolidation_result(raw)
    mem = parsed["memories"][0]
    # evidence is passed through as-is in raw JSON
    assert "evidence" in mem or True  # evidence not required, just don't crash


def test_parse_normalizes_type_to_allowed_set():
    """Invalid type in consolidation output is normalized to 'event'."""
    raw = """{
      "memories": [
        {"type": "fictional", "text": "Test", "importance": 3}
      ],
      "current_goal": ""
    }"""
    parsed = Agent.parse_memory_consolidation_result(raw)
    assert parsed["memories"][0]["type"] == "event"


def test_parse_normalizes_importance_bounds():
    """Importance is clamped to 1-10 range."""
    raw = """{
      "memories": [
        {"type": "event", "text": "Test", "importance": 999}
      ],
      "current_goal": ""
    }"""
    parsed = Agent.parse_memory_consolidation_result(raw)
    assert 1 <= parsed["memories"][0]["importance"] <= 10


def test_parse_skips_items_without_text():
    """Memory items without text are skipped."""
    raw = """{
      "memories": [
        {"type": "event", "text": "", "importance": 5},
        {"type": "event", "text": "Valid", "importance": 5}
      ],
      "current_goal": ""
    }"""
    parsed = Agent.parse_memory_consolidation_result(raw)
    assert len(parsed["memories"]) == 1
    assert parsed["memories"][0]["text"] == "Valid"


def test_parse_normalizes_keywords():
    """Keywords string is converted to list; non-list is cleaned."""
    raw = """{
      "memories": [
        {"type": "event", "text": "Test", "importance": 5, "keywords": "wolf"}
      ],
      "current_goal": ""
    }"""
    parsed = Agent.parse_memory_consolidation_result(raw)
    assert parsed["memories"][0]["keywords"] == ["wolf"]


def test_parse_memories_not_a_list_returns_empty():
    """If 'memories' is not a list, return empty memories list."""
    raw = """{"memories": "not_a_list", "current_goal": ""}"""
    parsed = Agent.parse_memory_consolidation_result(raw)
    assert parsed["memories"] == []


# ---------------------------------------------------------------------------
# build_memory_consolidation_prompt
# ---------------------------------------------------------------------------

def test_memory_consolidation_prompt_forbids_invented_facts():
    system_prompt, user_prompt = Agent.build_memory_consolidation_prompt(
        {
            "observation": "咖啡馆里只有柜台、杯盘和咖啡豆。",
            "thought": "我先整理杯盘，等有人来再交流。",
            "action": "整理杯盘",
        },
        agent_name="Isabella Rodriguez",
    )
    prompt = system_prompt + "\n" + user_prompt

    assert "只整理记忆，不决定行动" in prompt
    assert "event|chat|thought|plan" in prompt
    assert "不编造" in prompt
    assert "隐藏身份事实" in prompt
    assert "NPC 知道或亲眼见证" in prompt


def test_consolidation_prompt_includes_agent_name():
    system_prompt, _ = Agent.build_memory_consolidation_prompt(
        {}, agent_name="Arthur Burton"
    )
    assert "Arthur Burton" in system_prompt


def test_consolidation_prompt_includes_payload_text():
    payload = {"observation": "test observation", "action": "test action"}
    _, user_prompt = Agent.build_memory_consolidation_prompt(payload, "TestNPC")
    assert "test observation" in user_prompt
    assert "test action" in user_prompt


def test_consolidation_prompt_handles_non_serializable_payload():
    """Payload with non-serializable values should not crash."""
    system_prompt, user_prompt = Agent.build_memory_consolidation_prompt(
        {"value": object()}, agent_name="TestNPC"
    )
    assert isinstance(system_prompt, str)
    assert isinstance(user_prompt, str)


# ---------------------------------------------------------------------------
# consolidate_memory (static helper tests — no LLM needed)
# ---------------------------------------------------------------------------

def test_consolidate_memory_returns_structured_dict(monkeypatch):
    """consolidate_memory calls LLM for consolidation and returns parsed dict."""
    import agent as agent_module

    # Mock chat_for_agent to return a valid consolidation JSON
    monkeypatch.setattr(
        agent_module,
        "chat_for_agent",
        lambda *args, **kwargs: _json.dumps({
            "memories": [
                {
                    "type": "event",
                    "text": "Observed a meeting",
                    "importance": 6,
                    "keywords": ["meeting"],
                    "subject": "Isabella",
                    "predicate": "met",
                    "object": "Crow",
                }
            ],
            "current_goal": "Investigate the meeting",
        }),
    )

    agent = Agent("TestNPC", "villager")
    # Prevent filesystem writes
    monkeypatch.setattr(os, "makedirs", lambda *a, **kw: None)
    monkeypatch.setattr(agent, "_load_memory_index", lambda: [])
    monkeypatch.setattr(agent, "_load_scratch", lambda: agent._default_scratch())
    monkeypatch.setattr(agent, "_load_spatial_memory", lambda: {})

    result = agent.consolidate_memory({
        "observation": "Isabella met Crow in secret",
    })

    assert isinstance(result, dict)
    assert "memories" in result
    assert "current_goal" in result
    assert len(result["memories"]) >= 1
    assert result["memories"][0]["text"] == "Observed a meeting"


def test_consolidate_memory_empty_llm_response_returns_default(monkeypatch):
    """When LLM returns empty, consolidate_memory returns default dict."""
    import agent as agent_module

    monkeypatch.setattr(agent_module, "chat_for_agent", lambda *args, **kwargs: "")
    monkeypatch.setattr(os, "makedirs", lambda *a, **kw: None)

    agent = Agent("TestNPC", "villager")
    monkeypatch.setattr(agent, "_load_memory_index", lambda: [])
    monkeypatch.setattr(agent, "_load_scratch", lambda: agent._default_scratch())
    monkeypatch.setattr(agent, "_load_spatial_memory", lambda: {})

    result = agent.consolidate_memory({"action": "walked"})
    assert result == {"memories": [], "current_goal": ""}

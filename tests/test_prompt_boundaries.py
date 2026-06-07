from pathlib import Path

import agent
import game_engine
from world_config import ACTIVE_CHARACTERS, display_name_for_person


ROOT = Path(__file__).parents[1]


def test_active_people_rule_lists_only_current_town_characters():
    rule = agent.active_town_people_rule()

    assert "只有以下8个" in rule
    assert "不得编造" in rule
    for name in ACTIVE_CHARACTERS:
        assert name not in rule
        assert display_name_for_person(name) in rule
    assert "英文名" in rule


def test_llm_prompt_sources_include_active_people_boundary():
    agent_source = (ROOT / "agent.py").read_text(encoding="utf-8")
    engine_source = (ROOT / "game_engine.py").read_text(encoding="utf-8")
    dusk_source = (ROOT / "engine_dusk.py").read_text(encoding="utf-8")

    assert agent_source.count("active_town_people_rule()") >= 5
    assert engine_source.count("active_town_people_rule()") + dusk_source.count("active_town_people_rule()") >= 5
    assert "target_person" in agent_source
    assert "可选指控对象" in engine_source + dusk_source


def test_action_status_prompt_forbids_fictional_customers(monkeypatch):
    captured = {}

    def fake_chat_for_agent(agent_name, system_prompt, user_prompt, **kwargs):
        captured["user_prompt"] = user_prompt
        return """{
          "action_type": "work",
          "target_location": "Hobbs Cafe",
          "target_object": "",
          "target_person": "",
          "action": "留在咖啡馆整理杯盘",
          "action_status": "整理杯盘",
          "thought": "咖啡馆里暂时没有可交流的人，我根据当前能看见的柜台和杯盘先处理本职事务，避免凭空假设有人需要接待。",
          "expected_result": "保持柜台整洁",
          "duration_minutes": 10,
          "has_visible_clue_hint": false,
          "has_detective_hint": false
        }"""

    monkeypatch.setattr(agent, "chat_for_agent", fake_chat_for_agent)

    npc = agent.Agent.__new__(agent.Agent)
    npc.name = "Isabella Rodriguez"
    npc.role = "villager"
    npc.current_location = "Hobbs Cafe"
    npc.current_action = "idle"
    npc.action_history = []
    npc.daily_plan = []
    npc.scratch = {"currently": ""}
    npc.read_soul = lambda: ""
    npc.get_retrieved_memory_text = lambda query, max_chars=500: ""
    npc.get_current_plan_action = lambda game_hour: {}
    npc.read_cognition = lambda: ""
    npc.read_agent = lambda: ""
    npc.sanitize_prompt_text = lambda text: text
    npc.get_runtime_role_prompt = lambda: "Role: villager"
    npc.get_location_description = lambda location_name: ""

    result = npc.decide_next_action(
        game_hour=9,
        day=1,
        dead_list=[],
        nearby_info="附近没有人。",
        scene_info="咖啡馆里只有柜台、杯盘和咖啡豆。",
    )

    assert result["ok"] is True
    prompt = captured["user_prompt"]
    assert "action_status 必须" in prompt
    assert "真实存在的人、物或事务" in prompt
    assert "不得虚构客人、顾客、镇民" in prompt

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

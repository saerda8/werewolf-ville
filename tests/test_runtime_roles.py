import os
import pytest
from llm import set_runtime_model_assignments, get_model_for_agent, _RUNTIME_MODEL_MAP
from agent import Agent
from world_config import ACTIVE_CHARACTERS

def test_runtime_model_assignments():
    # Setup
    set_runtime_model_assignments({"Arthur Burton": "model-a", "Crow": "model-b"})
    
    # Test preference over default
    assert get_model_for_agent("Arthur Burton") == "model-a"
    assert get_model_for_agent("Crow") == "model-b"
    
    # Test copy behavior (should not reference original dict directly)
    original_dict = {"Isabella Rodriguez": "model-c"}
    set_runtime_model_assignments(original_dict)
    original_dict["Isabella Rodriguez"] = "model-d" # Should not affect runtime map
    assert get_model_for_agent("Isabella Rodriguez") == "model-c"
    
    # Test string validation
    set_runtime_model_assignments({123: "model-e", "Sam Moore": 456, "Klaus Mueller": " model-f ", "  ": "model-g", "Maria": ""})
    assert get_model_for_agent("Klaus Mueller") == "model-f" # Should strip and accept valid strings
    
    # Clear for other tests
    set_runtime_model_assignments({})

def test_dynamic_role_prompt_requirements():
    villager = Agent("Test Villager", role="villager")
    detective = Agent("Test Detective", role="detective")
    werewolf = Agent("Test Werewolf", role="werewolf")
    
    villager_prompt = villager.get_runtime_role_prompt()
    detective_prompt = detective.get_runtime_role_prompt()
    werewolf_prompt = werewolf.get_runtime_role_prompt()
    
    assert "villager" in villager_prompt.lower()
    assert "investigate" in villager_prompt.lower()
    assert "report" in villager_prompt.lower()
    
    assert "detective" in detective_prompt.lower()
    assert "evidence" in detective_prompt.lower()
    
    assert "werewolf" in werewolf_prompt.lower()
    assert "hide" in werewolf_prompt.lower()
    assert "kill" in werewolf_prompt.lower()

def test_neutral_generator_content():
    import create_villagers
    # Run the generation again to ensure it creates the files
    create_villagers.generate_personas()
    
    personas_dir = create_villagers.PERSONAS_DIR
    arthur_agent = os.path.join(personas_dir, "Arthur_Burton", "agent.md")
    
    assert os.path.exists(arthur_agent)
    
    with open(arthur_agent, "r", encoding="utf-8") as f:
        content = f.read()
        # Should not contain any hardcoded werewolf hints
        assert "狼人" not in content or "失踪" in content # allowed to mention missing people
        assert "你是狼人" not in content


def test_neutral_generator_covers_all_active_characters():
    import create_villagers

    generated_names = {name.replace("_", " ") for name in create_villagers.villagers}
    assert generated_names == set(ACTIVE_CHARACTERS)

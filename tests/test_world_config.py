"""
Unit tests for world configuration.
Asserts active characters (8 participants), detective identity, map-valid resident primary locations,
ambient sprites name exclusion, config.yaml requirements,
Chinese display names, and sheriff area metadata.
"""

from pathlib import Path

from world_config import (
    ACTIVE_CHARACTERS,
    PUBLIC_LANDMARKS,
    AMBIENT_RESIDENT_SPRITES,
    INITIAL_BODY_SITE,
    CHARACTER_DISPLAY_NAMES,
    AMBIENT_RESIDENT_DISPLAY_NAMES,
    SHERIFF_AREA,
    validate_world_config,
)
from config_loader import reload_config


def test_eight_active_participants_include_crow_and_seven_npcs():
    """Assert there are exactly 8 active characters: Crow + 7 NPCs."""
    assert len(ACTIVE_CHARACTERS) == 8, f"Expected exactly 8 active characters, got {len(ACTIVE_CHARACTERS)}"
    assert "Crow" in ACTIVE_CHARACTERS, "Crow must be an active character"
    # All 7 non-Crow characters must be residents
    non_crow = [n for n, c in ACTIVE_CHARACTERS.items() if n != "Crow"]
    assert len(non_crow) == 7, f"Expected 7 NPCs, got {len(non_crow)}"
    for name in non_crow:
        assert ACTIVE_CHARACTERS[name]["role"] == "resident", f"{name} must be a resident"


def test_active_characters_count():
    """Assert there are exactly 8 active characters (backward compat wrapper)."""
    assert len(ACTIVE_CHARACTERS) == 8, f"Expected exactly 8 active characters, got {len(ACTIVE_CHARACTERS)}"


def test_only_crow_is_detective():
    """Assert that only Crow is detective."""
    detectives = [name for name, char in ACTIVE_CHARACTERS.items() if char["role"] == "detective"]
    assert detectives == ["Crow"], f"Expected only Crow to be the detective, found: {detectives}"


def test_map_valid_resident_primary_locations():
    """Assert that all resident primary locations are valid public landmarks."""
    for name, character in ACTIVE_CHARACTERS.items():
        if character["role"] != "detective":
            assert character["role"] == "resident"
            primary_loc = character["primary_location"]
            assert primary_loc in PUBLIC_LANDMARKS, (
                f"Resident {name} has invalid primary location '{primary_loc}' "
                f"not found in PUBLIC_LANDMARKS"
            )


def test_ambient_sprites_exclude_active_names():
    """Assert that ambient sprites exclude active character names and include required names."""
    active_names = set(ACTIVE_CHARACTERS.keys())
    ambient_names = set(AMBIENT_RESIDENT_SPRITES)
    
    overlap = active_names.intersection(ambient_names)
    assert not overlap, f"Active characters and ambient sprites overlap: {overlap}"
    
    # Assert minimum set of required ambient sprites is present
    required_ambient = {
        "Abigail Chen", "Adam Smith", "Ayesha Khan", "Carlos Gomez",
        "Carmen Ortiz", "Eddy Lin", "Francisco Lopez", "Giorgio Rossi",
        "Hailey Johnson", "Jennifer Moore", "John Lin",
        "Latoya Williams", "Rajiv Patel", "Ryan Park",
        "Tamara Taylor", "Tom Moreno", "Wolfgang Schulz", "Yuriko Yamamoto"
    }
    
    missing = required_ambient - ambient_names
    assert not missing, f"Missing required ambient sprites: {missing}"


def test_config_available_models_count():
    """Assert available models are configured."""
    # Force reload config to make sure we load the newly modified config.yaml
    config = reload_config()

    assert "llm" in config, "Config missing 'llm' section"
    assert "available_models" in config["llm"], "Config 'llm' missing 'available_models'"

    available_models = config["llm"]["available_models"]
    assert isinstance(available_models, list), "llm.available_models must be a list"
    assert len(available_models) >= 1, "Must have at least 1 available model"

    assert "GLM-5.1" not in available_models
    assert "Qwen3.6-35B-A3B" not in available_models
    assert "MiMo-V2.5-Pro" not in available_models
    assert "Qwen3.5-Flash" in available_models
    assert "MiMo-V2-Flash" in available_models


def test_agent_models_no_consecutive_duplicates():
    """Assert each model is assigned to exactly 2 characters and no consecutive characters in active_agents use the same model."""
    config = reload_config()
    agent_models = config["llm"]["agent_models"]
    active_agents = config["game"]["active_agents"]

    assert len(active_agents) == 8

    model_counts = {}
    for agent in active_agents:
        model = agent_models[agent]
        model_counts[model] = model_counts.get(model, 0) + 1

    expected_models = {"Qwen3.5-Flash", "Kimi-K2.6", "deepseek-v4-flash", "MiMo-V2-Flash"}
    assert set(model_counts.keys()) == expected_models
    for model, count in model_counts.items():
        assert count == 2, f"Model {model} should be assigned to exactly 2 characters, got {count}"

    for i in range(len(active_agents) - 1):
        agent_a = active_agents[i]
        agent_b = active_agents[i+1]
        assert agent_models[agent_a] != agent_models[agent_b], f"Adjacent agents {agent_a} and {agent_b} use the same model: {agent_models[agent_a]}"



def test_config_werewolf_rules():
    """Assert werewolf settings in config.yaml are correctly loaded."""
    config = get_config_or_reload()
    assert "werewolf" in config, "Config missing 'werewolf' section"
    
    werewolf_cfg = config["werewolf"]
    assert werewolf_cfg.get("randomize_each_game") is True
    assert werewolf_cfg.get("kill_detective_last") is True
    assert werewolf_cfg.get("avoid_silver") is True
    # Make sure werewolf.character is no longer in config
    assert "character" not in werewolf_cfg, "werewolf.character should be removed from config"


def test_validate_world_config_helper():
    """Call the validate_world_config function to check that it executes successfully."""
    validate_world_config()


def test_initial_body_site_is_outdoor_plaza():
    """The opening scene should start in an outdoor meeting space, not inside a building."""
    assert INITIAL_BODY_SITE == {
        "location": "Johnson Park east plaza",
        "x": 48,
        "y": 46,
    }


def test_home_semantics_sam_pub_adjacent():
    """Sam (pub owner) lives near The Rose and Crown Pub."""
    sam = ACTIVE_CHARACTERS["Sam Moore"]
    pub = PUBLIC_LANDMARKS["The Rose and Crown Pub"]
    # Sam's home should be close to the pub (within 10 tiles)
    dist = abs(sam["home"]["x"] - pub["x"]) + abs(sam["home"]["y"] - pub["y"])
    assert dist <= 10, f"Sam lives {dist} tiles from the pub, expected ≤10"


def test_home_semantics_crow_sheriff_complex_lower_left():
    """Crow (sheriff) lives in the lower-left sheriff-complex area."""
    crow = ACTIVE_CHARACTERS["Crow"]
    # Lower-left: x < 70, y > 50
    assert crow["home"]["x"] < 70, f"Crow home x={crow['home']['x']} not in lower-left"
    assert crow["home"]["y"] > 50, f"Crow home y={crow['home']['y']} not in lower-left"


def test_home_semantics_match_map_labels():
    """Resident homes should match the labeled map buildings."""
    assert ACTIVE_CHARACTERS["Arthur Burton"]["home"] == {"x": 89, "y": 73}
    assert ACTIVE_CHARACTERS["Crow"]["home"] == {"x": 23, "y": 65}
    assert ACTIVE_CHARACTERS["Klaus Mueller"]["home"] == {"x": 58, "y": 73}
    assert ACTIVE_CHARACTERS["Sam Moore"]["home"] == {"x": 54, "y": 16}
    assert ACTIVE_CHARACTERS["Jane Moreno"]["home"] == {"x": 43, "y": 65}
    assert ACTIVE_CHARACTERS["Mei Lin"]["home"] == {"x": 112, "y": 38}


def test_jane_persona_is_park_groundkeeper_not_pub_worker():
    """Jane should be distributed to Johnson Park instead of crowding Sam's pub."""
    root = Path(__file__).resolve().parents[1]
    text = "\n".join(
        (root / rel).read_text(encoding="utf-8")
        for rel in [
            "personas/Jane_Moreno/soul.md",
            "personas/Jane_Moreno/agent.md",
            "personas/Jane_Moreno/scratch.json",
        ]
    )
    assert "约翰逊公园" in text or "Johnson Park" in text
    assert "酒馆" not in text
    assert "pub" not in text.lower()
    assert "厨房" not in text
    assert "kitchen" not in text.lower()


def test_crow_job_is_sheriff_role_remains_detective():
    """Surface semantics: Crow is a sheriff to players but role enum stays detective."""
    crow = ACTIVE_CHARACTERS["Crow"]
    assert crow["job"] == "sheriff", f"Crow job should be 'sheriff', got '{crow['job']}'"
    assert crow["role"] == "detective", "Internal role enum must remain 'detective' for compatibility"


def get_config_or_reload():
    """Helper to ensure fresh config is loaded."""
    return reload_config()


def test_visible_character_names_use_chinese_display_names():
    """Every active character has a Chinese display name for player-facing use."""
    for name in ACTIVE_CHARACTERS:
        assert name in CHARACTER_DISPLAY_NAMES, f"Missing display name for {name}"
        display = CHARACTER_DISPLAY_NAMES[name]
        assert isinstance(display, str) and len(display) > 0, f"Empty display name for {name}"
        # Display names should contain Chinese characters (not pure ASCII)
        assert any('一' <= c <= '鿿' for c in display), \
            f"Display name '{display}' for {name} does not contain Chinese characters"


def test_active_character_display_names_use_short_given_names():
    assert CHARACTER_DISPLAY_NAMES["Arthur Burton"] == "亚瑟"
    assert CHARACTER_DISPLAY_NAMES["Crow"] == "克罗"
    assert CHARACTER_DISPLAY_NAMES["Isabella Rodriguez"] == "伊莎贝拉"
    assert CHARACTER_DISPLAY_NAMES["Klaus Mueller"] == "克劳斯"
    assert CHARACTER_DISPLAY_NAMES["Maria Lopez"] == "玛利亚"
    assert CHARACTER_DISPLAY_NAMES["Sam Moore"] == "山姆"
    assert CHARACTER_DISPLAY_NAMES["Jane Moreno"] == "简"


def test_ambient_resident_names_have_chinese_display_names_for_corpses():
    """Ambient residents can become the opening corpse, so they need Chinese names too."""
    for name in AMBIENT_RESIDENT_SPRITES:
        assert name in AMBIENT_RESIDENT_DISPLAY_NAMES, f"Missing ambient display name for {name}"
        display = AMBIENT_RESIDENT_DISPLAY_NAMES[name]
        assert any('一' <= c <= '鿿' for c in display), \
            f"Ambient display name '{display}' for {name} does not contain Chinese characters"


def test_sheriff_area_contains_office_and_two_prison_rooms():
    """SHERIFF_AREA metadata defines sheriff office and two prison rooms with anchor points."""
    assert "sheriff_office" in SHERIFF_AREA
    assert "prison_cell_1" in SHERIFF_AREA
    assert "prison_cell_2" in SHERIFF_AREA

    # Each room must have multiple anchor points
    for room_key in ("sheriff_office", "prison_cell_1", "prison_cell_2"):
        room = SHERIFF_AREA[room_key]
        assert "name" in room, f"{room_key} missing name"
        assert "anchor_points" in room, f"{room_key} missing anchor_points"
        assert len(room["anchor_points"]) >= 2, f"{room_key} needs >= 2 anchor points"

    # Sheriff office should be near Crow's home
    office_pts = SHERIFF_AREA["sheriff_office"]["anchor_points"]
    crow_home = ACTIVE_CHARACTERS["Crow"]["home"]
    assert any(abs(pt[0] - crow_home["x"]) + abs(pt[1] - crow_home["y"]) <= 3
               for pt in office_pts), "Sheriff office should be near Crow's home"


def test_public_jobs_are_map_aligned_after_expansion():
    """Each active resident has a primary_location that is a valid public landmark
    and a job description that relates to that location."""
    for name, char in ACTIVE_CHARACTERS.items():
        if char["role"] == "detective":
            continue
        assert char["primary_location"] in PUBLIC_LANDMARKS, \
            f"{name} primary_location '{char['primary_location']}' not in landmarks"
        assert "job" in char, f"{name} missing job field"
        assert isinstance(char["job"], str) and len(char["job"]) > 0, \
            f"{name} has empty job"

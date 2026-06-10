"""
World configuration for Werewolf Ville.
Defines public landmarks, active characters with their locations and roles,
ambient resident sprites, display names, sheriff area metadata,
and validation functions.
"""

# Chinese player-facing display names for all active characters.
# Internal English ids remain stable; UI/prompts use display_name where visible.
CHARACTER_DISPLAY_NAMES = {
    "Arthur Burton": "亚瑟",
    "Crow": "克罗",
    "Isabella Rodriguez": "伊莎贝拉",
    "Klaus Mueller": "克劳斯",
    "Maria Lopez": "玛利亚",
    "Sam Moore": "山姆",
    "Jane Moreno": "简",
    "Mei Lin": "林梅",
}

LANDMARK_DISPLAY_NAMES = {
    "Hobbs Cafe": "霍布斯咖啡馆",
    "The Rose and Crown Pub": "玫瑰与皇冠酒吧",
    "Oak Hill College": "橡树山学院",
    "The Willows Market and Pharmacy": "柳树市场药房",
    "Harvey Oak Supply Store": "哈维橡树五金店",
    "Johnson Park": "约翰逊公园",
}

PUBLIC_LANDMARKS = {
    "Hobbs Cafe": {"x": 77, "y": 21},
    "The Rose and Crown Pub": {"x": 57, "y": 22},
    "Oak Hill College": {"x": 118, "y": 41},
    "The Willows Market and Pharmacy": {"x": 84, "y": 47},
    "Harvey Oak Supply Store": {"x": 63, "y": 47},
    "Johnson Park": {"x": 27, "y": 46},
}

INITIAL_BODY_SITE = {
    "location": "Johnson Park east plaza",
    "x": 48,
    "y": 46,
}

ACTIVE_CHARACTERS = {
    "Arthur Burton": {
        "role": "resident",
        "job": "hardware store owner/tool repairer",
        "primary_location": "Harvey Oak Supply Store",
        "home": {"x": 89, "y": 73},
    },
    "Crow": {
        "role": "detective",
        "job": "sheriff",
        "primary_location": "Johnson Park",
        "home": {"x": 23, "y": 65},
    },
    "Isabella Rodriguez": {
        "role": "resident",
        "job": "cafe owner",
        "primary_location": "Hobbs Cafe",
        "home": {"x": 77, "y": 14},
    },
    "Klaus Mueller": {
        "role": "resident",
        "job": "college student",
        "primary_location": "Oak Hill College",
        "home": {"x": 126, "y": 46},
    },
    "Maria Lopez": {
        "role": "resident",
        "job": "market/pharmacy clerk",
        "primary_location": "The Willows Market and Pharmacy",
        "home": {"x": 93, "y": 18},
    },
    "Sam Moore": {
        "role": "resident",
        "job": "pub owner/bartender",
        "primary_location": "The Rose and Crown Pub",
        "home": {"x": 54, "y": 16},
    },
    "Jane Moreno": {
        "role": "resident",
        "job": "park gardener/groundskeeper",
        "primary_location": "Johnson Park",
        "home": {"x": 78, "y": 74},
    },
    "Mei Lin": {
        "role": "resident",
        "job": "college librarian/researcher",
        "primary_location": "Oak Hill College",
        "home": {"x": 107, "y": 62},
    },
}

AMBIENT_RESIDENT_SPRITES = [
    "Abigail Chen",
    "Adam Smith",
    "Ayesha Khan",
    "Carlos Gomez",
    "Carmen Ortiz",
    "Eddy Lin",
    "Francisco Lopez",
    "Giorgio Rossi",
    "Hailey Johnson",
    "Jennifer Moore",
    "John Lin",
    "Latoya Williams",
    "Rajiv Patel",
    "Ryan Park",
    "Tamara Taylor",
    "Tom Moreno",
    "Wolfgang Schulz",
    "Yuriko Yamamoto",
]

AMBIENT_RESIDENT_DISPLAY_NAMES = {
    "Abigail Chen": "阿比盖尔·陈",
    "Adam Smith": "亚当·史密斯",
    "Ayesha Khan": "艾莎·汗",
    "Carlos Gomez": "卡洛斯·戈麦斯",
    "Carmen Ortiz": "卡门·奥尔蒂斯",
    "Eddy Lin": "林艾迪",
    "Francisco Lopez": "弗朗西斯科·洛佩兹",
    "Giorgio Rossi": "乔治奥·罗西",
    "Hailey Johnson": "海莉·约翰逊",
    "Jennifer Moore": "詹妮弗·摩尔",
    "John Lin": "林约翰",
    "Latoya Williams": "拉托娅·威廉姆斯",
    "Rajiv Patel": "拉吉夫·帕特尔",
    "Ryan Park": "莱恩·帕克",
    "Tamara Taylor": "塔玛拉·泰勒",
    "Tom Moreno": "汤姆·莫雷诺",
    "Wolfgang Schulz": "沃尔夫冈·舒尔茨",
    "Yuriko Yamamoto": "山本百合子",
}


def display_name_for_person(name):
    return CHARACTER_DISPLAY_NAMES.get(
        name,
        AMBIENT_RESIDENT_DISPLAY_NAMES.get(name, name),
    )

# Sheriff area metadata: Crow's office/home plus two prison rooms with anchor points.
# Each room lists multiple walkable anchor points for NPC/Crow positioning.
SHERIFF_AREA = {
    "sheriff_office": {
        "name": "警长办公室",
        "anchor_points": [(23, 65), (24, 65), (23, 66)],
    },
    "prison_cell_1": {
        "name": "监狱牢房1",
        "anchor_points": [(31, 66), (31, 67), (31, 68)],
    },
    "prison_cell_2": {
        "name": "监狱牢房2",
        "anchor_points": [(38, 65), (38, 66), (38, 67)],
    },
}

def validate_world_config():
    """
    Validates that:
    1. There are exactly 8 active characters.
    2. Crow is the only detective.
    3. All resident primary locations are valid public landmarks.
    4. Ambient sprites list does not contain any of the active characters.
    5. SHERIFF_AREA contains at least three rooms with multiple anchor points each.
    """
    assert len(ACTIVE_CHARACTERS) == 8, f"Expected exactly 8 active characters, got {len(ACTIVE_CHARACTERS)}"

    detectives = [name for name, char in ACTIVE_CHARACTERS.items() if char["role"] == "detective"]
    assert detectives == ["Crow"], f"Expected only Crow to be the detective, found: {detectives}"

    for name, character in ACTIVE_CHARACTERS.items():
        if character["role"] != "detective":
            assert character["role"] == "resident", f"Character {name} has invalid role: {character['role']}"
            assert character["primary_location"] in PUBLIC_LANDMARKS, \
                f"Resident {name} primary location '{character['primary_location']}' is not in PUBLIC_LANDMARKS"

    active_names_set = set(ACTIVE_CHARACTERS.keys())
    ambient_names_set = set(AMBIENT_RESIDENT_SPRITES)
    overlap = active_names_set.intersection(ambient_names_set)
    assert not overlap, f"Active characters overlap with ambient sprites: {overlap}"

    for name in AMBIENT_RESIDENT_SPRITES:
        display_name = AMBIENT_RESIDENT_DISPLAY_NAMES.get(name)
        assert display_name and display_name != name, f"Missing ambient display name for {name}"

    # Validate SHERIFF_AREA has the required rooms with multiple anchor points
    assert "sheriff_office" in SHERIFF_AREA, "SHERIFF_AREA missing sheriff_office"
    assert "prison_cell_1" in SHERIFF_AREA, "SHERIFF_AREA missing prison_cell_1"
    assert "prison_cell_2" in SHERIFF_AREA, "SHERIFF_AREA missing prison_cell_2"
    for room_key, room_data in SHERIFF_AREA.items():
        assert isinstance(room_data, dict), f"SHERIFF_AREA.{room_key} must be a dict"
        assert "name" in room_data, f"SHERIFF_AREA.{room_key} missing 'name'"
        assert "anchor_points" in room_data, f"SHERIFF_AREA.{room_key} missing 'anchor_points'"
        assert len(room_data["anchor_points"]) >= 2, \
            f"SHERIFF_AREA.{room_key} needs at least 2 anchor points, got {len(room_data['anchor_points'])}"
        for pt in room_data["anchor_points"]:
            assert isinstance(pt, (list, tuple)) and len(pt) == 2, \
                f"SHERIFF_AREA.{room_key} anchor point {pt} must be (x,y)"

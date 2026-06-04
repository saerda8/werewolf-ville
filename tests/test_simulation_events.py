from simulation_events import BodyRecord, ClueRecord, undelivered_clues_for

def test_pending_clue_remains_until_delivered():
    clue = ClueRecord(
        clue_id="clue_1",
        clue_type="footprint",
        summary="Found a footprint near the lake",
        source="Sheriff",
        related_person="John Doe",
        location="Lake",
        created_day=1,
        delivered_to_crow=False
    )
    clues = [clue]
    
    # A pending clue remains (delivered_to_crow is False)
    undelivered = undelivered_clues_for(clues, "Sheriff")
    assert len(undelivered) == 1
    assert undelivered[0].clue_id == "clue_1"
    
    # Once marked as delivered (delivered_to_crow is True), it should not be returned
    clue.delivered_to_crow = True
    undelivered_after = undelivered_clues_for(clues, "Sheriff")
    assert len(undelivered_after) == 0

def test_body_serialization_includes_sprite_key_and_alive_false():
    body = BodyRecord(
        body_id="body_1",
        victim_name="Ayesha Khan",
        location="Forest",
        x=12,
        y=34,
        created_day=2,
        discovered=False
    )
    
    status = body.to_status()
    
    # Assert standard fields are preserved in the serialized dict
    assert status["body_id"] == "body_1"
    assert status["victim_name"] == "Ayesha Khan"
    assert status["location"] == "Forest"
    assert status["x"] == 12
    assert status["y"] == 34
    assert status["created_day"] == 2
    assert status["discovered"] is False
    assert status["burying"] is False
    assert status["burial_target_x"] == 0
    assert status["burial_target_y"] == 0
    
    # Assert extra generated fields
    assert status["sprite_key"] == "Ayesha_Khan"
    assert status["alive"] is False

def test_filtering_does_not_return_another_source_clue():
    clue_sheriff = ClueRecord(
        clue_id="clue_1",
        clue_type="rumor",
        summary="Heard something strange",
        source="Sheriff",
        related_person="Jane",
        location="Tavern",
        created_day=1,
        delivered_to_crow=False
    )
    clue_villager = ClueRecord(
        clue_id="clue_2",
        clue_type="murder_weapon",
        summary="Found a bloody knife",
        source="Villager",
        related_person="Bob",
        location="Barn",
        created_day=1,
        delivered_to_crow=False
    )
    
    clues = [clue_sheriff, clue_villager]
    
    # Check that we only get the Sheriff's clue when filtering for "Sheriff"
    undelivered_sheriff = undelivered_clues_for(clues, "Sheriff")
    assert len(undelivered_sheriff) == 1
    assert undelivered_sheriff[0].clue_id == "clue_1"
    
    # Check that we only get the Villager's clue when filtering for "Villager"
    undelivered_villager = undelivered_clues_for(clues, "Villager")
    assert len(undelivered_villager) == 1
    assert undelivered_villager[0].clue_id == "clue_2"
    
    # Check that an unrelated source returns nothing
    undelivered_none = undelivered_clues_for(clues, "Doctor")
    assert len(undelivered_none) == 0

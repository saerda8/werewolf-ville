from engine_observation import ObservationEvent, filter_observable_events


def _event(event_id: str, **overrides) -> ObservationEvent:
    values = {
        "event_id": event_id,
        "event_type": "action_start",
        "subject": "Arthur Burton",
        "text": f"Event {event_id}",
        "x": 5,
        "y": 5,
        "day": 1,
        "game_hour": 9.0,
        "timestamp": 100.0,
    }
    values.update(overrides)
    return ObservationEvent(**values)


def test_observation_event_serializes_witnesses_in_stable_order():
    event = _event(
        "obs_serialized",
        object="inventory",
        public=True,
        hidden=True,
        witnesses={"Mei Lin", "Crow"},
        source="npc",
    )

    assert event.to_dict() == {
        "event_id": "obs_serialized",
        "event_type": "action_start",
        "subject": "Arthur Burton",
        "text": "Event obs_serialized",
        "x": 5,
        "y": 5,
        "day": 1,
        "game_hour": 9.0,
        "timestamp": 100.0,
        "object": "inventory",
        "public": True,
        "hidden": True,
        "witnesses": ["Crow", "Mei Lin"],
        "source": "npc",
    }


def test_observation_event_deserializes_serialized_payload():
    original = _event(
        "obs_round_trip",
        witnesses={"Crow", "Mei Lin"},
        source="conversation",
    )

    restored = ObservationEvent.from_dict(original.to_dict())

    assert restored == original
    assert restored.witnesses == {"Crow", "Mei Lin"}


def test_observation_radius_10_includes_nearby_event():
    event = ObservationEvent(
        event_id="obs_1",
        event_type="action_start",
        subject="Arthur Burton",
        text="Arthur starts checking inventory.",
        x=5,
        y=5,
        day=1,
        game_hour=9.0,
        timestamp=100.0,
    )

    visible = filter_observable_events(
        events=[event],
        observer_name="Isabella Rodriguez",
        observer_x=12,
        observer_y=8,
        now=110.0,
        radius=10,
    )

    assert [item.event_id for item in visible] == ["obs_1"]


def test_default_radius_includes_event_at_boundary_and_excludes_event_beyond_it():
    boundary = _event("obs_boundary", x=10, y=0)
    beyond = _event("obs_beyond", x=10, y=1)

    visible = filter_observable_events(
        events=[boundary, beyond],
        observer_name="Isabella Rodriguez",
        observer_x=0,
        observer_y=0,
        now=110.0,
    )

    assert [item.event_id for item in visible] == ["obs_boundary"]


def test_observation_filter_excludes_far_private_event():
    event = ObservationEvent(
        event_id="obs_2",
        event_type="speech",
        subject="Sam Moore",
        text="Sam speaks quietly.",
        x=30,
        y=30,
        day=1,
        game_hour=9.0,
        timestamp=100.0,
    )

    visible = filter_observable_events(
        events=[event],
        observer_name="Isabella Rodriguez",
        observer_x=12,
        observer_y=8,
        now=110.0,
        radius=10,
    )

    assert visible == []


def test_public_event_ignores_radius():
    event = ObservationEvent(
        event_id="obs_3",
        event_type="public_announcement",
        subject="Crow",
        text="Crow announces the dusk meeting.",
        x=99,
        y=99,
        day=1,
        game_hour=18.0,
        timestamp=100.0,
        public=True,
    )

    visible = filter_observable_events(
        events=[event],
        observer_name="Mei Lin",
        observer_x=0,
        observer_y=0,
        now=110.0,
        radius=10,
    )

    assert [item.event_id for item in visible] == ["obs_3"]


def test_hidden_event_requires_explicit_witness():
    event = ObservationEvent(
        event_id="obs_4",
        event_type="hidden_fact",
        subject="Arthur Burton",
        text="Arthur is a werewolf.",
        x=5,
        y=5,
        day=1,
        game_hour=9.0,
        timestamp=100.0,
        hidden=True,
        witnesses={"Crow"},
    )

    visible_for_crow = filter_observable_events(
        events=[event],
        observer_name="Crow",
        observer_x=5,
        observer_y=5,
        now=110.0,
        radius=10,
    )
    visible_for_sam = filter_observable_events(
        events=[event],
        observer_name="Sam Moore",
        observer_x=5,
        observer_y=5,
        now=110.0,
        radius=10,
    )

    assert [item.event_id for item in visible_for_crow] == ["obs_4"]
    assert visible_for_sam == []


def test_observation_ttl_excludes_old_event():
    event = ObservationEvent(
        event_id="obs_5",
        event_type="action_complete",
        subject="Jane Moreno",
        text="Jane finished pruning flowers.",
        x=1,
        y=1,
        day=1,
        game_hour=9.0,
        timestamp=100.0,
    )

    visible = filter_observable_events(
        events=[event],
        observer_name="Mei Lin",
        observer_x=1,
        observer_y=1,
        now=401.0,
        ttl_seconds=300.0,
    )

    assert visible == []


def test_observation_filter_preserves_event_order():
    events = [
        _event("obs_first", x=99, y=99, public=True),
        _event("obs_hidden", hidden=True, witnesses={"Someone Else"}),
        _event("obs_second", x=1, y=0),
        _event("obs_third", x=2, y=0, witnesses={"Mei Lin"}),
    ]

    visible = filter_observable_events(
        events=events,
        observer_name="Mei Lin",
        observer_x=0,
        observer_y=0,
        now=110.0,
    )

    assert [item.event_id for item in visible] == [
        "obs_first",
        "obs_second",
        "obs_third",
    ]

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ObservationEvent:
    event_id: str
    event_type: str
    subject: str
    text: str
    x: int
    y: int
    day: int
    game_hour: float
    timestamp: float
    object: str = ""
    public: bool = False
    hidden: bool = False
    witnesses: set[str] = field(default_factory=set)
    source: str = "world"

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "subject": self.subject,
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "day": self.day,
            "game_hour": self.game_hour,
            "timestamp": self.timestamp,
            "object": self.object,
            "public": self.public,
            "hidden": self.hidden,
            "witnesses": sorted(self.witnesses),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ObservationEvent:
        return cls(
            event_id=str(payload["event_id"]),
            event_type=str(payload["event_type"]),
            subject=str(payload["subject"]),
            text=str(payload["text"]),
            x=int(payload["x"]),
            y=int(payload["y"]),
            day=int(payload["day"]),
            game_hour=float(payload["game_hour"]),
            timestamp=float(payload["timestamp"]),
            object=str(payload.get("object", "")),
            public=bool(payload.get("public", False)),
            hidden=bool(payload.get("hidden", False)),
            witnesses={str(name) for name in payload.get("witnesses", [])},
            source=str(payload.get("source", "world")),
        )


def manhattan_distance(x1: int, y1: int, x2: int, y2: int) -> int:
    return abs(int(x1) - int(x2)) + abs(int(y1) - int(y2))


def filter_observable_events(
    events: Iterable[ObservationEvent],
    observer_name: str,
    observer_x: int,
    observer_y: int,
    now: float,
    radius: int = 10,
    ttl_seconds: float = 300.0,
) -> list[ObservationEvent]:
    visible: list[ObservationEvent] = []
    for event in events:
        if now - event.timestamp > ttl_seconds:
            continue
        if event.hidden and observer_name not in event.witnesses:
            continue
        if event.public or observer_name in event.witnesses:
            visible.append(event)
            continue
        if manhattan_distance(observer_x, observer_y, event.x, event.y) <= radius:
            visible.append(event)
    return visible

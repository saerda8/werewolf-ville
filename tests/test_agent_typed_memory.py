"""Tests for Agent typed memory system: visibility (public/private/witnessed),
evidence list handling, legacy memory_index fallback, and retrieval integrity."""
import json as _json
import os
import sys
import time as _time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent import Agent


# ---------------------------------------------------------------------------
# Shared helper: create an Agent with all file I/O mocked (no persona/ writes)
# ---------------------------------------------------------------------------

def _make_mocked_agent(monkeypatch):
    """Return an Agent instance with all filesystem I/O mocked.

    Prevents writes to personas/ (directory creation, MD appends, JSON saves).
    Captures typed_memory_index writes into agent._typed_store for verification.
    """
    # Prevent directory creation under personas/
    monkeypatch.setattr(os, "makedirs", lambda *a, **kw: None)

    agent = Agent("TestNPC", "villager")

    # Capture typed memory index writes
    typed_store = []

    def _save_typed(index):
        typed_store.clear()
        typed_store.extend(index)

    def _load_typed():
        return list(typed_store)

    # Mock all file I/O
    monkeypatch.setattr(agent, "_load_memory_index", lambda: [])
    monkeypatch.setattr(agent, "_save_memory_index", lambda: None)
    monkeypatch.setattr(agent, "_load_typed_memory_index", _load_typed)
    monkeypatch.setattr(agent, "_save_typed_memory_index", _save_typed)
    monkeypatch.setattr(agent, "_load_scratch", lambda: agent._default_scratch())
    monkeypatch.setattr(agent, "_load_spatial_memory", lambda: {})
    monkeypatch.setattr(agent, "_append_md", lambda *a, **kw: None)

    # Expose typed_store for assertion
    agent._typed_store = typed_store
    return agent


# ===================================================================
# Visibility: public / private / witnessed
# ===================================================================

class TestTypedMemoryVisibility:
    """add_typed_memory must support public, private, and witnessed visibility."""

    def test_visibility_public(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        mid = agent.add_typed_memory(
            type="event", day=1, text="A public announcement", visibility="public"
        )
        assert agent._typed_store[0]["visibility"] == "public"
        assert agent._typed_store[0]["id"] == mid

    def test_visibility_private(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="thought", day=1, text="Internal monologue", visibility="private"
        )
        assert agent._typed_store[0]["visibility"] == "private"

    def test_visibility_witnessed(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=2, text="Saw something suspicious", visibility="witnessed"
        )
        assert agent._typed_store[0]["visibility"] == "witnessed"

    def test_visibility_defaults_to_private(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="event", day=1, text="No visibility given")
        assert agent._typed_store[0]["visibility"] == "private"

    def test_invalid_visibility_falls_back_to_private(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="Secret visibility typo", visibility="secret"
        )
        assert agent._typed_store[0]["visibility"] == "private"


# ===================================================================
# Evidence list
# ===================================================================

class TestTypedMemoryEvidence:
    """add_typed_memory must normalize evidence to a list of strings."""

    def test_evidence_list_single(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="Found a clue", evidence=["bloody knife"]
        )
        assert agent._typed_store[0]["evidence"] == ["bloody knife"]

    def test_evidence_list_multiple(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="Multiple clues",
            evidence=["footprint", "hair strand", "torn fabric"]
        )
        assert agent._typed_store[0]["evidence"] == [
            "footprint", "hair strand", "torn fabric"
        ]

    def test_evidence_string_becomes_list(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="String evidence", evidence="bloodstain"
        )
        assert agent._typed_store[0]["evidence"] == ["bloodstain"]

    def test_evidence_none_becomes_empty_list(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="No evidence", evidence=None
        )
        assert agent._typed_store[0]["evidence"] == []

    def test_evidence_default_empty_list(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="event", day=1, text="Evidence omitted")
        assert agent._typed_store[0]["evidence"] == []

    def test_evidence_empty_string_ignored(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="Empty string evidence", evidence=""
        )
        assert agent._typed_store[0]["evidence"] == []


# ===================================================================
# Legacy memory_index fallback & retrieval
# ===================================================================

class TestTypedMemoryLegacyFallback:
    """add_typed_memory must also populate self.memory_index so that
    retrieve_memories (legacy retrieval) continues to work."""

    def test_legacy_index_populated(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=2, text="Important event", importance=7
        )
        assert len(agent.memory_index) == 1
        entry = agent.memory_index[0]
        assert entry["day"] == 2
        assert entry["event"] == "Important event"
        assert entry["importance"] == 7
        assert entry["type"] == "event"

    def test_legacy_index_has_timestamp(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="event", day=3, text="Timestamped")
        assert "timestamp" in agent.memory_index[0]
        assert agent.memory_index[0]["timestamp"] > 0

    def test_retrieve_memories_finds_typed_entry(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="Werewolf attack at midnight", importance=10
        )
        agent.add_typed_memory(
            type="chat", day=1, text="Talked with Crow about safety", importance=5
        )
        results = agent.retrieve_memories("werewolf", top_k=5)
        assert len(results) >= 1
        assert any("Werewolf" in r["event"] for r in results)

    def test_retrieve_memories_empty_query_returns_all(self, monkeypatch):
        """Empty query should still return scored results (recency + importance)."""
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="event", day=1, text="Event A", importance=8)
        agent.add_typed_memory(type="event", day=1, text="Event B", importance=3)
        results = agent.retrieve_memories("", top_k=10)
        assert len(results) == 2

    def test_multiple_typed_entries_in_legacy_index(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="event", day=1, text="Event 1")
        agent.add_typed_memory(type="chat", day=1, text="Chat 1")
        agent.add_typed_memory(type="thought", day=2, text="Thought 1")
        assert len(agent.memory_index) == 3

    def test_legacy_retrieval_top_k_respected(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        for i in range(20):
            agent.add_typed_memory(type="event", day=1, text=f"Event {i}")
        results = agent.retrieve_memories("Event", top_k=5)
        assert len(results) <= 5

    def test_get_retrieved_memory_text_returns_string(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="Important evidence found", importance=10
        )
        # Mock read_memory for fallback
        monkeypatch.setattr(agent, "read_memory", lambda: "fallback memory content")
        text = agent.get_retrieved_memory_text("evidence", max_chars=500)
        assert isinstance(text, str)
        assert len(text) > 0


# ===================================================================
# Memory types: event / chat / thought / plan
# ===================================================================

class TestTypedMemoryTypes:
    """add_typed_memory must accept and validate type field."""

    def test_type_event(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="event", day=1, text="Event memory")
        assert agent._typed_store[0]["type"] == "event"

    def test_type_chat(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="chat", day=1, text="Chat memory")
        assert agent._typed_store[0]["type"] == "chat"

    def test_type_thought(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="thought", day=1, text="Thought memory")
        assert agent._typed_store[0]["type"] == "thought"

    def test_type_plan(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="plan", day=1, text="Plan memory")
        assert agent._typed_store[0]["type"] == "plan"

    def test_invalid_type_falls_back_to_event(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="invalid", day=1, text="Bad type")
        assert agent._typed_store[0]["type"] == "event"

    def test_memory_type_param_alternative(self, monkeypatch):
        """memory_type kwarg is accepted as alternative to type."""
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(memory_type="chat", day=1, text="Using memory_type")
        assert agent._typed_store[0]["type"] == "chat"


# ===================================================================
# Keywords handling
# ===================================================================

class TestTypedMemoryKeywords:
    """add_typed_memory must normalize keywords to a list of strings."""

    def test_keywords_list(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="Keywords", keywords=["wolf", "night"]
        )
        assert agent._typed_store[0]["keywords"] == ["wolf", "night"]

    def test_keywords_string_wrapped(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="String kw", keywords="wolf"
        )
        assert agent._typed_store[0]["keywords"] == ["wolf"]

    def test_keywords_none_empty(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="No kw", keywords=None
        )
        assert agent._typed_store[0]["keywords"] == []

    def test_keywords_default_empty(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="event", day=1, text="Default kw")
        assert agent._typed_store[0]["keywords"] == []


# ===================================================================
# Entry structure completeness
# ===================================================================

class TestTypedMemoryStructure:
    """Every add_typed_memory entry must carry all required fields."""

    REQUIRED_FIELDS = [
        "id", "type", "created_at", "day", "game_hour",
        "subject", "predicate", "object", "text",
        "importance", "keywords", "evidence", "source", "visibility",
    ]

    def test_entry_has_all_required_fields(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="Full entry",
            subject="Arthur", predicate="found", object="clue",
            source="observation", game_hour=14.5,
        )
        entry = agent._typed_store[0]
        for field in self.REQUIRED_FIELDS:
            assert field in entry, f"Missing field: {field}"

    def test_id_is_unique_per_call(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        id1 = agent.add_typed_memory(type="event", day=1, text="First")
        id2 = agent.add_typed_memory(type="event", day=1, text="Second")
        assert id1 != id2
        assert len(id1) > 0
        assert len(id2) > 0

    def test_importance_bounded_1_to_10(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="event", day=1, text="Test", importance=99)
        assert 1 <= agent._typed_store[0]["importance"] <= 10

    def test_importance_auto_scored_when_none(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="A murder happened last night", importance=None
        )
        imp = agent._typed_store[0]["importance"]
        assert 1 <= imp <= 10

    def test_subject_predicate_object_stored(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="SPO test",
            subject="Isabella", predicate="talked to", object="Crow",
        )
        entry = agent._typed_store[0]
        assert entry["subject"] == "Isabella"
        assert entry["predicate"] == "talked to"
        assert entry["object"] == "Crow"

    def test_source_field_stored(self, monkeypatch):
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(
            type="event", day=1, text="Source test", source="direct_observation"
        )
        assert agent._typed_store[0]["source"] == "direct_observation"

    def test_empty_text_still_creates_entry(self, monkeypatch):
        """Even with empty text, an entry should be created (with metadata)."""
        agent = _make_mocked_agent(monkeypatch)
        agent.add_typed_memory(type="event", day=1, text="")
        assert len(agent._typed_store) == 1
        assert agent._typed_store[0]["text"] == ""

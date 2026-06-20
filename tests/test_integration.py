"""
Mirror Brain v1.0 — Integration test.
Creates real entities: Julián, Romina, Mirror Brain, c0, Florería.
Tests EntityRegistry, EntityCriteria, and the full create/resolve/alias pipeline.
"""
import sys
import os
import tempfile

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mirror_brain.registry import EntityRegistry
from mirror_brain.criteria import EntityCriteria


def test_criteria():
    """Test the entity creation decision rules."""
    criteria = EntityCriteria()

    # ALWAYS_ENTITY_TYPES → create on first mention
    assert criteria.should_create_entity("Romina", "person", 1) == (True, "type 'person' is an always-entity type (mention 1)")
    assert criteria.should_create_entity("Mirror Brain", "project", 1) == (True, "type 'project' is an always-entity type (mention 1)")
    assert criteria.should_create_entity("Docker", "tool", 1) == (True, "type 'tool' is an always-entity type (mention 1)")

    # NEVER_ENTITY → never create
    assert criteria.should_create_entity("frustración", "emotion", 5)[0] is False
    assert criteria.should_create_entity("el deploy", "event", 3)[0] is False

    # Recurrence → create on 2nd mention (using type NOT in ALWAYS_ENTITY_TYPES)
    # "concept" is not always-entity, so needs recurrence
    assert criteria.should_create_entity("café de la esquina", "place", 1) == (True, "type 'place' is an always-entity type (mention 1)")
    # For non-always types, recurrence matters:
    assert criteria.should_create_entity("idea recurrente", "concept", 2) == (True, "mention_count=2 >= 2")

    # Parent entity → no create
    assert criteria.should_create_entity("API key", "attribute", 1, parent_entity="DeepSeek")[0] is False

    # LLM high confidence → create
    assert criteria.should_create_entity("algo raro", "concept", 1, llm_confidence=0.92) == (True, "llm_confidence=0.92 > 0.85")

    # Insufficient signal → skip
    assert criteria.should_create_entity("algo raro", "concept", 1, llm_confidence=0.5) == (False, "no criteria met (type='concept', mention_count=1, llm_confidence=0.5)")

    print("✅ Criteria tests passed")


def test_registry():
    """Test the full EntityRegistry pipeline."""
    db_path = os.path.join(tempfile.gettempdir(), "mirror_brain_test.db")
    reg = EntityRegistry(db_path)

    # ── Create entities ─────────────────────────────────────────
    uuid_julian, c0_julian = reg.create("Gustavo Julian Barrios Borja", "person")
    uuid_romina, c0_romina = reg.create("Romina González", "person")
    uuid_mb, c0_mb = reg.create("Mirror Brain", "project")
    uuid_c0, c0_c0 = reg.create("c0", "tool")
    uuid_floreria, c0_floreria = reg.create("Florería GJB", "place")

    assert len(uuid_julian) == 36  # UUID4
    assert c0_julian.startswith("ent_")
    assert len(c0_julian) == 12  # ent_ + 8 hex chars

    # ── Resolve by canonical name ───────────────────────────────
    assert reg.resolve("Romina González") == uuid_romina
    assert reg.resolve("Mirror Brain") == uuid_mb

    # ── Add aliases ─────────────────────────────────────────────
    reg.add_alias("Julián", uuid_julian, source="manual", confidence=1.0)
    reg.add_alias("Julian", uuid_julian, source="fuzzy", confidence=0.95)
    reg.add_alias("Romi", uuid_romina, source="llm", confidence=0.91)
    reg.add_alias("MB", uuid_mb, source="llm", confidence=0.88)
    reg.add_alias("la florería", uuid_floreria, source="llm", confidence=0.93)

    # ── Resolve by alias ────────────────────────────────────────
    assert reg.resolve("Julián") == uuid_julian
    assert reg.resolve("Romi") == uuid_romina
    assert reg.resolve("MB") == uuid_mb
    assert reg.resolve("la florería") == uuid_floreria

    # ── Get entity info ─────────────────────────────────────────
    julian_info = reg.get(uuid_julian)
    assert julian_info["canonical_name"] == "Gustavo Julian Barrios Borja"
    assert julian_info["type"] == "person"
    assert julian_info["status"] == "active"

    # ── Get aliases ─────────────────────────────────────────────
    aliases = reg.get_aliases(uuid_julian)
    alias_names = {a["alias"] for a in aliases}
    assert "Gustavo Julian Barrios Borja" in alias_names  # canonical
    assert "Julián" in alias_names
    assert "Julian" in alias_names

    # ── Search ──────────────────────────────────────────────────
    results = reg.search("Romina")
    assert any(r["canonical_name"] == "Romina González" for r in results)

    results = reg.search("flor")
    assert any(r["canonical_name"] == "Florería GJB" for r in results)

    # ── List by type ────────────────────────────────────────────
    persons = reg.list_by_type("person")
    assert len(persons) == 2
    projects = reg.list_by_type("project")
    assert len(projects) == 1
    assert projects[0]["canonical_name"] == "Mirror Brain"

    # ── Ingest with full decision pipeline ──────────────────────
    # New person → should be created
    uuid_new, c0_new, reason = reg.ingest("DeepSeek", "tool", mention_count=1)
    assert uuid_new is not None
    assert "created" in reason

    # Duplicate (resolved by alias "Romi") → should resolve
    uuid_existing, c0_existing, reason = reg.ingest("Romi", "person", mention_count=1)
    assert uuid_existing == uuid_romina
    assert reason == "resolved_existing"

    # Emotion → should be skipped
    uuid_skip, c0_skip, reason = reg.ingest("alegría", "emotion", mention_count=1)
    assert uuid_skip is None
    assert "skipped" in reason

    # ── Reasoning trail ─────────────────────────────────────────
    reg.log_decision("create_entity", uuid_julian, confidence=1.0,
                     reasoning="Root entity — the user.", source="manual")
    reg.log_decision("add_alias", uuid_romina, confidence=0.91,
                     reasoning="LLM detected diminutive: 'Romi' ≈ 'Romina González'",
                     evidence="Text: 'Romi me dijo que...'", source="llm")

    print("✅ Registry tests passed")

    # Cleanup
    reg.db.close()
    os.unlink(db_path)


if __name__ == "__main__":
    test_criteria()
    test_registry()
    print("\n🎉 All tests passed!")

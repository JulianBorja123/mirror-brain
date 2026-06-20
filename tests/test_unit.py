"""
Mirror Brain v1.0 — Unit tests (25+).
Each test is independent. Uses MockLLM for controlled LLM output.
Python 3.11+ stdlib only. No pytest. Temp DB per test via tempfile.
"""

import sys
import os
import tempfile
import json
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mirror_brain.schema import init_db
from mirror_brain.criteria import EntityCriteria
from mirror_brain.registry import EntityRegistry
from mirror_brain.models import (
    Entity, Alias, DailySummary, ReasoningRecord, Relation, Note,
)
from mirror_brain.note_constructor import NoteConstructor, NOTE_CONSTRUCTOR_PROMPT
from mirror_brain.context_fetcher import ContextFetcher
from mirror_brain.link_evolution import LinkEvolution, LINK_EVOLUTION_PROMPT


# ═══════════════════════════════════════════════════════════════════
# Mock LLM — returns controlled JSON
# ═══════════════════════════════════════════════════════════════════

class MockLLM:
    """Returns a fixed response string for testing LLM-dependent code."""

    def __init__(self, response: str):
        self.response = response
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def make_temp_db() -> str:
    """Create a temp SQLite file path."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="mb_test_")
    os.close(fd)
    return path


def clean_db(db_path: str, conn: sqlite3.Connection | None = None):
    """Close connection and remove temp DB."""
    if conn:
        try:
            conn.close()
        except Exception:
            pass
    try:
        os.unlink(db_path)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
# 1. SCHEMA TESTS (3)
# ═══════════════════════════════════════════════════════════════════

def test_schema_creates_five_tables():
    """init_db should create exactly 7 tables."""
    db_path = make_temp_db()
    conn = None
    try:
        conn = init_db(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        expected = ["aliases", "daily_index", "entities", "raw_texts", "reasoning_trail", "relations", "weekly_summaries"]
        assert tables == expected, f"Expected {expected}, got {tables}"
        print("PASS: test_schema_creates_five_tables")
    finally:
        clean_db(db_path, conn)


def test_schema_foreign_key_enforcement():
    """FK on aliases.entity_uuid -> entities.uuid must reject orphan inserts."""
    db_path = make_temp_db()
    conn = None
    try:
        conn = init_db(db_path)
        try:
            conn.execute(
                "INSERT INTO aliases (alias, entity_uuid, source, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("orphan_alias", "non-existent-uuid", "manual", 1.0, "2025-01-01T00:00:00"),
            )
            conn.commit()
            row = conn.execute(
                "SELECT alias FROM aliases WHERE entity_uuid = 'non-existent-uuid'"
            ).fetchone()
            if row is not None:
                print("FAIL: test_schema_foreign_key_enforcement - FK not enforced")
                return
            print("PASS: test_schema_foreign_key_enforcement")
        except sqlite3.IntegrityError:
            print("PASS: test_schema_foreign_key_enforcement")
    finally:
        clean_db(db_path, conn)


def test_schema_idempotent():
    """init_db called twice should not raise errors."""
    db_path = make_temp_db()
    conn = None
    try:
        conn = init_db(db_path)
        conn2 = init_db(db_path)
        cursor = conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        assert len(tables) == 7, f"Expected 7 tables, got {len(tables)}: {tables}"
        conn2.close()
        print("PASS: test_schema_idempotent")
    finally:
        clean_db(db_path, conn)


# ═══════════════════════════════════════════════════════════════════
# 2. CRITERIA TESTS — 6 rules (7 tests)
# ═══════════════════════════════════════════════════════════════════

def test_criteria_always_entity():
    """Rule 1: ALWAYS_ENTITY_TYPES create on first mention."""
    c = EntityCriteria()
    for etype in ["person", "project", "tool", "place", "organization"]:
        should, reason = c.should_create_entity("TestName", etype, 1)
        assert should is True, f"Expected True for '{etype}', got {should}"
        assert f"'{etype}' is an always-entity" in reason
    print("PASS: test_criteria_always_entity")


def test_criteria_never_entity():
    """Rule 2: NEVER_ENTITY types never create."""
    c = EntityCriteria()
    for etype in ["emotion", "event", "attribute", "quantity", "date", "action"]:
        should, reason = c.should_create_entity("SomeName", etype, 5)
        assert should is False, f"Expected False for '{etype}', got {should}"
        assert "' is in NEVER_ENTITY" in reason
    print("PASS: test_criteria_never_entity")


def test_criteria_recurrence():
    """Rule 3: Non-always types need mention_count >= 2."""
    c = EntityCriteria()
    should, reason = c.should_create_entity("IdeaX", "concept", 2)
    assert should is True, f"Expected True, got {should}"
    assert "mention_count=2 >= 2" in reason
    print("PASS: test_criteria_recurrence")


def test_criteria_parent_entity():
    """Rule 4: parent_entity suppresses creation (sub-entity)."""
    c = EntityCriteria()
    should, reason = c.should_create_entity("SubThing", "person", 1, parent_entity="ParentEntity")
    assert should is False, f"Expected False, got {should}"
    assert "sub-entity" in reason
    print("PASS: test_criteria_parent_entity")


def test_criteria_confidence():
    """Rule 5: High llm_confidence (>0.85) triggers creation."""
    c = EntityCriteria()
    should, reason = c.should_create_entity("WeirdConcept", "concept", 1, llm_confidence=0.92)
    assert should is True, f"Expected True, got {should}"
    assert "llm_confidence=0.92 > 0.85" in reason
    print("PASS: test_criteria_confidence")


def test_criteria_insufficient():
    """Rule 6: No criteria met -> skip."""
    c = EntityCriteria()
    should, reason = c.should_create_entity("FleetingIdea", "concept", 1, llm_confidence=0.3)
    assert should is False, f"Expected False, got {should}"
    assert "no criteria met" in reason
    print("PASS: test_criteria_insufficient")


def test_criteria_boundary_confidence():
    """Confidence exactly 0.85 should NOT trigger (strict >)."""
    c = EntityCriteria()
    should, reason = c.should_create_entity("EdgeCase", "concept", 1, llm_confidence=0.85)
    assert should is False, f"Expected False for exactly 0.85, got {should}"
    print("PASS: test_criteria_boundary_confidence")


# ═══════════════════════════════════════════════════════════════════
# 3. REGISTRY TESTS (14)
# ═══════════════════════════════════════════════════════════════════

def test_registry_create():
    """Create returns (uuid, c0_ref) and entity is resolvable."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid, ref = reg.create("Test Person", "person")
        assert len(uid) == 36
        assert ref.startswith("ent_")
        assert len(ref) == 12
        assert reg.resolve("Test Person") == uid
        print("PASS: test_registry_create")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_resolve_canonical():
    """Resolve by canonical name returns correct UUID."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid_a, _ = reg.create("Alice", "person")
        uid_b, _ = reg.create("Bob", "person")
        assert reg.resolve("Alice") == uid_a
        assert reg.resolve("Bob") == uid_b
        assert reg.resolve("Charlie") is None
        print("PASS: test_registry_resolve_canonical")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_resolve_alias():
    """Resolve by alias returns correct UUID."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid, _ = reg.create("Gustavo Julian Barrios Borja", "person")
        reg.add_alias("Julian", uid, source="manual", confidence=1.0)
        assert reg.resolve("Julian") == uid
        print("PASS: test_registry_resolve_alias")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_add_alias():
    """add_alias stores alias and it appears in get_aliases."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid, _ = reg.create("Mirror Brain", "project")
        reg.add_alias("MB", uid, source="llm", confidence=0.88)
        aliases = reg.get_aliases(uid)
        alias_names = [a["alias"] for a in aliases]
        assert "MB" in alias_names
        # Duplicate insert is harmless (INSERT OR IGNORE)
        reg.add_alias("MB", uid, source="llm", confidence=0.90)
        aliases2 = reg.get_aliases(uid)
        assert len(aliases2) == len(aliases)
        print("PASS: test_registry_add_alias")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_get():
    """get returns full entity dict."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid, _ = reg.create("DeepSeek", "tool")
        info = reg.get(uid)
        assert info is not None
        assert info["canonical_name"] == "DeepSeek"
        assert info["type"] == "tool"
        assert info["status"] == "active"
        assert info["uuid"] == uid
        assert reg.get("nonexistent-uuid") is None
        print("PASS: test_registry_get")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_get_aliases():
    """get_aliases returns all aliases including canonical."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid, _ = reg.create("Floreria GJB", "place")
        reg.add_alias("la floreria", uid, source="llm", confidence=0.93)
        reg.add_alias("la floristeria", uid, source="llm", confidence=0.85)
        aliases = reg.get_aliases(uid)
        assert len(aliases) >= 3
        names = {a["alias"] for a in aliases}
        assert "Floreria GJB" in names
        assert "la floreria" in names
        assert "la floristeria" in names
        for a in aliases:
            assert "alias" in a
            assert "source" in a
            assert "confidence" in a
        print("PASS: test_registry_get_aliases")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_search():
    """search returns matching entities by canonical name or alias."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid_romi, _ = reg.create("Romina Gonzalez", "person")
        reg.add_alias("Romi", uid_romi, source="llm", confidence=0.91)
        reg.create("Mirror Brain", "project")
        results = reg.search("Romi")
        assert any(r["canonical_name"] == "Romina Gonzalez" for r in results)
        results = reg.search("Mirror")
        assert any(r["canonical_name"] == "Mirror Brain" for r in results)
        results = reg.search("zzz_nonexistent")
        assert len(results) == 0
        print("PASS: test_registry_search")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_list_by_type():
    """list_by_type returns active entities of given type."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        reg.create("Alice", "person")
        reg.create("Bob", "person")
        reg.create("MyProject", "project")
        reg.create("VSCode", "tool")
        persons = reg.list_by_type("person")
        assert len(persons) == 2
        names = {p["canonical_name"] for p in persons}
        assert "Alice" in names
        assert "Bob" in names
        projects = reg.list_by_type("project")
        assert len(projects) == 1
        assert projects[0]["canonical_name"] == "MyProject"
        assert reg.list_by_type("place") == []
        print("PASS: test_registry_list_by_type")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_ingest_new():
    """ingest creates new entity when criteria are met."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid, c0_ref, reason = reg.ingest("NewPerson", "person", mention_count=1)
        assert uid is not None
        assert c0_ref.startswith("ent_")
        assert "created" in reason
        assert reg.resolve("NewPerson") == uid
        print("PASS: test_registry_ingest_new")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_ingest_existing():
    """ingest resolves existing entity when name already registered."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid_orig, _ = reg.create("ExistingProject", "project")
        reg.add_alias("EP", uid_orig, source="llm", confidence=0.85)
        uid, c0_ref, reason = reg.ingest("EP", "project", mention_count=1)
        assert uid == uid_orig
        assert reason == "resolved_existing"
        print("PASS: test_registry_ingest_existing")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_ingest_skipped():
    """ingest skips entity when criteria say no."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid, c0_ref, reason = reg.ingest("frustracion", "emotion", mention_count=1)
        assert uid is None
        assert c0_ref == ""
        assert "skipped" in reason
        print("PASS: test_registry_ingest_skipped")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_log_decision():
    """log_decision records an entry in reasoning_trail."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid, _ = reg.create("TestEntity", "concept")
        reg.log_decision(
            action="create_entity",
            entity_uuid=uid,
            confidence=1.0,
            reasoning="Test reasoning",
            evidence="Test evidence",
            source="manual",
        )
        row = reg.db.execute(
            "SELECT action, entity_uuid, confidence, reasoning, evidence, source, reverted "
            "FROM reasoning_trail WHERE entity_uuid = ?",
            (uid,),
        ).fetchone()
        assert row is not None
        assert row[0] == "create_entity"
        assert row[1] == uid
        assert row[2] == 1.0
        assert row[3] == "Test reasoning"
        assert row[4] == "Test evidence"
        assert row[5] == "manual"
        assert row[6] == 0
        print("PASS: test_registry_log_decision")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_revert_decision():
    """revert_decision marks a trail entry as reverted."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid, _ = reg.create("TestRevert", "concept")
        reg.log_decision(
            action="merge_entities",
            entity_uuid=uid,
            confidence=0.75,
            reasoning="Tentative merge",
        )
        row = reg.db.execute(
            "SELECT id, reverted FROM reasoning_trail WHERE entity_uuid = ?",
            (uid,),
        ).fetchone()
        trail_id = row[0]
        assert row[1] == 0
        reg.revert_decision(trail_id)
        row2 = reg.db.execute(
            "SELECT reverted FROM reasoning_trail WHERE id = ?", (trail_id,)
        ).fetchone()
        assert row2[0] == 1
        print("PASS: test_registry_revert_decision")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_registry_create_idempotent():
    """create with same canonical name returns existing entity."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        uid1, ref1 = reg.create("UniqueName", "concept")
        uid2, ref2 = reg.create("UniqueName", "concept")
        assert uid1 == uid2
        assert ref1 == ref2
        print("PASS: test_registry_create_idempotent")
    finally:
        clean_db(db_path, reg.db if reg else None)


# ═══════════════════════════════════════════════════════════════════
# 4. MODELS TESTS — all dataclasses instantiate (6)
# ═══════════════════════════════════════════════════════════════════

def test_model_entity():
    """Entity dataclass instantiates and to_dict works."""
    e = Entity(uuid="abc-123", canonical_name="Test Entity", c0_ref="ent_abc12345",
              type="concept", status="active",
              created_at="2025-01-01T00:00:00", updated_at="2025-01-01T00:00:00")
    d = e.to_dict()
    assert d["uuid"] == "abc-123"
    assert d["canonical_name"] == "Test Entity"
    assert d["type"] == "concept"
    assert d["status"] == "active"
    e2 = Entity(uuid="x", canonical_name="y", c0_ref="ent_00000000", type="person")
    assert e2.status == "active"
    assert e2.merged_into is None
    print("PASS: test_model_entity")


def test_model_alias():
    """Alias dataclass instantiates correctly."""
    a = Alias(alias="nickname", entity_uuid="uuid-123", source="manual",
              confidence=1.0, created_at="2025-01-01")
    assert a.alias == "nickname"
    assert a.entity_uuid == "uuid-123"
    assert a.source == "manual"
    assert a.confidence == 1.0
    a2 = Alias(alias="x", entity_uuid="y")
    assert a2.source == "llm"
    assert a2.confidence == 0.8
    print("PASS: test_model_alias")


def test_model_daily_summary():
    """DailySummary dataclass instantiates with default empty lists."""
    ds = DailySummary(date="2025-06-19")
    assert ds.date == "2025-06-19"
    assert ds.summary == ""
    assert ds.emotional_arc == []
    assert ds.key_entities == []
    assert ds.key_decisions == []
    assert ds.embedding == []
    ds2 = DailySummary(date="2025-06-19", summary="Good day",
                       emotional_arc=[0.3, 0.7], key_entities=["Mirror Brain"],
                       key_decisions=["Deploy v1"], embedding=[0.1, 0.2, 0.3])
    assert ds2.summary == "Good day"
    assert len(ds2.emotional_arc) == 2
    print("PASS: test_model_daily_summary")


def test_model_reasoning_record():
    """ReasoningRecord dataclass instantiates correctly."""
    rr = ReasoningRecord(id=1, timestamp="2025-01-01T00:00:00",
                         action="create_entity", entity_uuid="uuid-1",
                         target_uuid="uuid-2", confidence=0.95,
                         reasoning="Test reasoning", evidence="Test evidence",
                         source="llm", reversible=True, reverted=False)
    assert rr.action == "create_entity"
    assert rr.confidence == 0.95
    assert rr.reversible is True
    assert rr.reverted is False
    rr2 = ReasoningRecord()
    assert rr2.action == ""
    assert rr2.confidence == 0.0
    assert rr2.source == "llm"
    print("PASS: test_model_reasoning_record")


def test_model_relation():
    """Relation dataclass instantiates correctly."""
    r = Relation(id=1, from_uuid="uuid-a", to_uuid="uuid-b",
                 relation_type="mentions", source_text="Original source",
                 created_at="2025-01-01")
    assert r.from_uuid == "uuid-a"
    assert r.to_uuid == "uuid-b"
    assert r.relation_type == "mentions"
    print("PASS: test_model_relation")


def test_model_note():
    """Note dataclass instantiates with defaults."""
    n = Note(content="Test note content")
    assert n.content == "Test note content"
    assert n.keywords == []
    assert n.tags == []
    assert n.context == ""
    assert n.emotional_load == {}
    assert n.temporal_hints == []
    assert n.entities_mentioned == []
    assert n.search_hints == []
    assert n.links == []
    ts = Note.now()
    assert isinstance(ts, str)
    assert "T" in ts
    n2 = Note(content="Full note", timestamp=ts, keywords=["test", "unit"],
              tags=["testing", "dev"], context="Testing context",
              emotional_load={"oxytocin": 0.5}, temporal_hints=["hoy"],
              entities_mentioned=[{"name": "Test", "type": "concept"}],
              search_hints=["find test"], links=[])
    assert n2.keywords == ["test", "unit"]
    assert n2.emotional_load["oxytocin"] == 0.5
    print("PASS: test_model_note")


# ═══════════════════════════════════════════════════════════════════
# 5. NOTE CONSTRUCTOR TESTS (7)
# ═══════════════════════════════════════════════════════════════════

def test_note_constructor_prompt_format():
    """Prompt template includes existing_entities and text placeholders."""
    prompt = NOTE_CONSTRUCTOR_PROMPT
    assert "{existing_entities}" in prompt
    assert "{text}" in prompt
    formatted = prompt.format(existing_entities="test entities", text="test text")
    assert "test entities" in formatted
    assert "test text" in formatted
    print("PASS: test_note_constructor_prompt_format")


def test_note_constructor_parse_valid_json():
    """_parse_response handles clean JSON."""
    result = NoteConstructor._parse_response(
        '{"keywords": ["a"], "context": "ctx", "tags": ["t"]}'
    )
    assert result == {"keywords": ["a"], "context": "ctx", "tags": ["t"]}
    print("PASS: test_note_constructor_parse_valid_json")


def test_note_constructor_parse_markdown_json():
    """_parse_response strips markdown code fences."""
    md = '```json\n{"keywords": ["a"], "context": "ctx"}\n```'
    result = NoteConstructor._parse_response(md)
    assert result == {"keywords": ["a"], "context": "ctx"}
    md2 = '```\n{"x": 1}\n```'
    result2 = NoteConstructor._parse_response(md2)
    assert result2 == {"x": 1}
    print("PASS: test_note_constructor_parse_markdown_json")


def test_note_constructor_parse_empty():
    """_parse_response returns empty dict for empty input."""
    assert NoteConstructor._parse_response("") == {}
    result = NoteConstructor._parse_response("   ")
    assert result.get("_parse_error") is True or result == {}
    print("PASS: test_note_constructor_parse_empty")


def test_note_constructor_parse_malformed():
    """_parse_response handles completely malformed input."""
    result = NoteConstructor._parse_response("This is not JSON at all!")
    assert result.get("_parse_error") is True
    assert result.get("_raw") == "This is not JSON at all!"
    print("PASS: test_note_constructor_parse_malformed")


def test_note_constructor_construct_with_mock_llm():
    """Full construct() pipeline with MockLLM returns a valid Note."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        reg.create("Julian", "person")
        reg.create("c0", "tool")

        mock_response = json.dumps({
            "keywords": ["memoria", "prueba", "c0", "test"],
            "context": "Julian is testing the Mirror Brain note constructor.",
            "tags": ["testing", "proyecto", "tecnico"],
            "emotional_load": {"oxytocin": 0.1, "adrenaline": 0.2,
                               "cortisol": 0.1, "dopamine": 0.8},
            "temporal_hints": ["hoy"],
            "entities_mentioned": [
                {"name": "Julian", "type": "person", "is_new": False,
                 "alias_of": None, "confidence": 1.0},
                {"name": "c0", "type": "tool", "is_new": False,
                 "alias_of": None, "confidence": 0.95},
            ],
            "search_hints": [
                "what was the last c0 status check?",
                "has Julian mentioned testing before?",
            ],
        })

        mock_llm = MockLLM(mock_response)
        nc = NoteConstructor(reg, llm_call=mock_llm)
        note = nc.construct("Estoy probando el constructor de notas con Julian y c0.")

        assert isinstance(note, Note)
        assert note.content == "Estoy probando el constructor de notas con Julian y c0."
        assert "memoria" in note.keywords
        assert len(note.keywords) >= 2
        assert "testing" in note.tags
        assert note.context != ""
        assert note.emotional_load.get("dopamine") == 0.8
        assert "hoy" in note.temporal_hints
        assert len(note.entities_mentioned) == 2
        assert len(note.search_hints) == 2
        assert len(mock_llm.calls) == 1
        assert "Estoy probando" in mock_llm.calls[0]
        print("PASS: test_note_constructor_construct_with_mock_llm")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_note_constructor_parse_json_with_markdown_and_text():
    """_parse_response extracts JSON when mixed with explanatory text."""
    response = (
        'Sure, here is the JSON:\n\n'
        '```json\n{"keywords": ["test"]}\n```\n'
        'Hope that helps!'
    )
    result = NoteConstructor._parse_response(response)
    assert "keywords" in result
    assert result["keywords"] == ["test"]
    print("PASS: test_note_constructor_parse_json_with_markdown_and_text")


# ═══════════════════════════════════════════════════════════════════
# 6. CONTEXT FETCHER TESTS (5)
# ═══════════════════════════════════════════════════════════════════

def test_context_fetcher_classify_hint_temporal():
    """_classify_hint returns 'temporal' for time-related hints."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        cf = ContextFetcher(reg)
        assert cf._classify_hint("cuanto gaste esta semana?") == "temporal"
        assert cf._classify_hint("how much did I spend this week?") == "temporal"
        assert cf._classify_hint("que paso ayer") == "temporal"
        assert cf._classify_hint("what happened yesterday") == "temporal"
        assert cf._classify_hint("resumen de hoy") == "temporal"
        assert cf._classify_hint("el costo del mes pasado") == "temporal"
        print("PASS: test_context_fetcher_classify_hint_temporal")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_context_fetcher_classify_hint_entity():
    """_classify_hint returns 'entity' when hint mentions a known entity."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        reg.create("Julian", "person")
        reg.create("Mirror Brain", "project")
        cf = ContextFetcher(reg)
        assert cf._classify_hint("what is the status of Julian's work?") == "entity"
        assert cf._classify_hint("how is Mirror Brain doing?") == "entity"
        print("PASS: test_context_fetcher_classify_hint_entity")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_context_fetcher_classify_hint_semantic():
    """_classify_hint returns 'semantic' when hint is general."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        cf = ContextFetcher(reg)
        assert cf._classify_hint("what is the meaning of this concept?") == "semantic"
        print("PASS: test_context_fetcher_classify_hint_semantic")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_context_fetcher_extract_dates():
    """_extract_dates returns appropriate date ranges."""
    from datetime import date, timedelta
    today = date.today()
    yesterday = today - timedelta(days=1)

    dates = ContextFetcher._extract_dates("que paso ayer")
    assert yesterday.isoformat() in dates

    dates = ContextFetcher._extract_dates("resumen de hoy")
    assert today.isoformat() in dates

    dates = ContextFetcher._extract_dates("esta semana")
    assert len(dates) == 7

    dates = ContextFetcher._extract_dates("some other query")
    assert len(dates) == 3

    print("PASS: test_context_fetcher_extract_dates")


def test_context_fetcher_fetch_empty_context():
    """fetch on an empty registry returns basic context structure."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        cf = ContextFetcher(reg)
        note = Note(content="test", search_hints=["what is the status of c0?"],
                    entities_mentioned=[])
        ctx = cf.fetch(note)
        assert "daily_summaries" in ctx
        assert "entity_contexts" in ctx
        assert "semantic_results" in ctx
        assert "related_reasoning" in ctx
        assert "summary" in ctx
        print("PASS: test_context_fetcher_fetch_empty_context")
    finally:
        clean_db(db_path, reg.db if reg else None)


# ═══════════════════════════════════════════════════════════════════
# 7. LINK EVOLUTION TESTS (9)
# ═══════════════════════════════════════════════════════════════════

def test_link_evolution_parse_empty():
    """_parse_response returns defaults for empty input."""
    result = LinkEvolution._parse_response("")
    assert result == {"links": [], "evolutions": [], "new_aliases": [],
                      "needs_more_search": []}
    print("PASS: test_link_evolution_parse_empty")


def test_link_evolution_parse_valid_json():
    """_parse_response handles clean JSON with all fields."""
    raw = json.dumps({
        "links": [{"from_entity": "a", "to_entity": "b", "relation": "mentions",
                   "confidence": 0.9, "reasoning": "r"}],
        "evolutions": [], "new_aliases": [], "needs_more_search": [],
    })
    result = LinkEvolution._parse_response(raw)
    assert len(result["links"]) == 1
    assert result["links"][0]["from_entity"] == "a"
    print("PASS: test_link_evolution_parse_valid_json")


def test_link_evolution_parse_missing_keys():
    """_parse_response fills in missing keys with defaults."""
    result = LinkEvolution._parse_response('{"links": [{"from_entity": "x"}]}')
    assert result["links"] is not None
    assert result["evolutions"] == []
    assert result["new_aliases"] == []
    assert result["needs_more_search"] == []
    print("PASS: test_link_evolution_parse_missing_keys")


def test_link_evolution_parse_markdown():
    """_parse_response handles markdown-fenced JSON."""
    md = ('```json\n{"links": [], "evolutions": [], '
          '"new_aliases": [], "needs_more_search": []}\n```')
    result = LinkEvolution._parse_response(md)
    assert result["links"] == []
    assert result["evolutions"] == []
    print("PASS: test_link_evolution_parse_markdown")


def test_link_evolution_parse_malformed():
    """_parse_response handles completely malformed input."""
    result = LinkEvolution._parse_response("not json at all!!!")
    assert result.get("_parse_error") is True
    assert result.get("_raw") == "not json at all!!!"
    assert result["links"] == []
    print("PASS: test_link_evolution_parse_malformed")


def test_link_evolution_prompt_format():
    """LINK_EVOLUTION_PROMPT template has required placeholders."""
    prompt = LINK_EVOLUTION_PROMPT
    for key in ["{note_content}", "{note_context}", "{note_keywords}",
                "{note_tags}", "{note_emotional}", "{note_temporal}",
                "{note_entities}", "{retrieved_context}", "{neighbor_memories}"]:
        assert key in prompt, f"Missing {key} in prompt"
    print("PASS: test_link_evolution_prompt_format")


def test_link_evolution_execute_confidence_gates():
    """execute routes by confidence: auto (>=0.85), flag (>=0.6), skip (<0.6)."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        reg.create("EntityA", "concept")
        reg.create("EntityB", "concept")
        reg.create("EntityC", "concept")
        le = LinkEvolution(reg)

        decisions = {
            "links": [
                {"from_entity": "EntityA", "to_entity": "EntityB",
                 "relation": "relates_to", "confidence": 0.95, "reasoning": "high"},
                {"from_entity": "EntityA", "to_entity": "EntityC",
                 "relation": "mentions", "confidence": 0.70, "reasoning": "med"},
                {"from_entity": "EntityB", "to_entity": "EntityC",
                 "relation": "depends_on", "confidence": 0.30, "reasoning": "low"},
            ],
            "evolutions": [
                {"target": "EntityA", "action": "update_context",
                 "new_context": "Changed", "confidence": 0.90, "reasoning": "hi"},
                {"target": "EntityB", "action": "update_context",
                 "new_context": "Maybe", "confidence": 0.65, "reasoning": "med"},
            ],
            "new_aliases": [
                {"alias": "KnownAlias", "canonical_entity": "EntityA",
                 "confidence": 0.95, "reasoning": "known alias"},
                {"alias": "NewAlias", "canonical_entity": "EntityB",
                 "confidence": 0.55, "reasoning": "too low conf"},
            ],
            "needs_more_search": [],
        }
        note = Note(content="test")
        report = le.execute(decisions, note)

        auto = report["auto_executed"]
        flagged = report["flagged"]
        skipped = report["skipped"]

        assert any("EntityA" in a and "relates_to" in a for a in auto)
        assert any("update_context" in a and "EntityA" in a for a in auto)
        assert any("alias" in a and "KnownAlias" in a for a in auto)
        assert any("EntityA" in f and "mentions" in f for f in flagged)
        assert any("EntityB" in f and "update_context" in f for f in flagged)
        assert any("EntityB" in s and "depends_on" in s for s in skipped)
        assert any("NewAlias" in s and "too low" in s for s in skipped)

        print("PASS: test_link_evolution_execute_confidence_gates")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_link_evolution_decide_with_mock_llm():
    """decide() builds prompt, calls LLM, parses response."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        reg.create("Julian", "person")
        reg.create("c0", "tool")

        mock_response = json.dumps({
            "links": [{"from_entity": "Julian", "to_entity": "c0",
                       "relation": "works_on", "confidence": 0.9,
                       "reasoning": "Julian is actively developing c0."}],
            "evolutions": [], "new_aliases": [], "needs_more_search": [],
        })

        mock_llm = MockLLM(mock_response)
        le = LinkEvolution(reg, llm_call=mock_llm)

        note = Note(
            content="Julian sigue trabajando en c0.",
            context="Julian developing c0",
            keywords=["c0", "desarrollo", "Julian"],
            tags=["tecnico", "proyecto"],
            emotional_load={}, temporal_hints=[],
            entities_mentioned=[
                {"name": "Julian", "type": "person", "is_new": False},
                {"name": "c0", "type": "tool", "is_new": False},
            ],
            search_hints=[],
        )

        context = {"daily_summaries": [], "entity_contexts": {},
                   "semantic_results": [], "related_reasoning": [],
                   "summary": "no context"}

        decisions = le.decide(note, context, neighbor_memories="")
        assert "links" in decisions
        assert len(decisions["links"]) == 1
        assert decisions["links"][0]["from_entity"] == "Julian"
        assert decisions["links"][0]["to_entity"] == "c0"
        assert decisions["links"][0]["confidence"] == 0.9
        assert len(mock_llm.calls) == 1
        assert "Julian sigue trabajando en c0" in mock_llm.calls[0]
        print("PASS: test_link_evolution_decide_with_mock_llm")
    finally:
        clean_db(db_path, reg.db if reg else None)


def test_link_evolution_execute_skips_unknown_entities():
    """execute should not crash when link targets unknown entities."""
    db_path = make_temp_db()
    reg = None
    try:
        reg = EntityRegistry(db_path)
        le = LinkEvolution(reg)
        decisions = {
            "links": [{"from_entity": "UnknownFrom", "to_entity": "UnknownTo",
                       "relation": "relates_to", "confidence": 0.95,
                       "reasoning": "should be skipped gracefully"}],
            "evolutions": [], "new_aliases": [], "needs_more_search": [],
        }
        note = Note(content="test")
        report = le.execute(decisions, note)
        assert "errors" in report
        print("PASS: test_link_evolution_execute_skips_unknown_entities")
    finally:
        clean_db(db_path, reg.db if reg else None)


# ═══════════════════════════════════════════════════════════════════
# Main runner
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    all_tests = [
        test_schema_creates_five_tables,
        test_schema_foreign_key_enforcement,
        test_schema_idempotent,
        test_criteria_always_entity,
        test_criteria_never_entity,
        test_criteria_recurrence,
        test_criteria_parent_entity,
        test_criteria_confidence,
        test_criteria_insufficient,
        test_criteria_boundary_confidence,
        test_registry_create,
        test_registry_resolve_canonical,
        test_registry_resolve_alias,
        test_registry_add_alias,
        test_registry_get,
        test_registry_get_aliases,
        test_registry_search,
        test_registry_list_by_type,
        test_registry_ingest_new,
        test_registry_ingest_existing,
        test_registry_ingest_skipped,
        test_registry_log_decision,
        test_registry_revert_decision,
        test_registry_create_idempotent,
        test_model_entity,
        test_model_alias,
        test_model_daily_summary,
        test_model_reasoning_record,
        test_model_relation,
        test_model_note,
        test_note_constructor_prompt_format,
        test_note_constructor_parse_valid_json,
        test_note_constructor_parse_markdown_json,
        test_note_constructor_parse_empty,
        test_note_constructor_parse_malformed,
        test_note_constructor_construct_with_mock_llm,
        test_note_constructor_parse_json_with_markdown_and_text,
        test_context_fetcher_classify_hint_temporal,
        test_context_fetcher_classify_hint_entity,
        test_context_fetcher_classify_hint_semantic,
        test_context_fetcher_extract_dates,
        test_context_fetcher_fetch_empty_context,
        test_link_evolution_parse_empty,
        test_link_evolution_parse_valid_json,
        test_link_evolution_parse_missing_keys,
        test_link_evolution_parse_markdown,
        test_link_evolution_parse_malformed,
        test_link_evolution_prompt_format,
        test_link_evolution_execute_confidence_gates,
        test_link_evolution_decide_with_mock_llm,
        test_link_evolution_execute_skips_unknown_entities,
    ]

    passed = 0
    failed = 0

    for test_fn in all_tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {test_fn.__name__} - {e}")
        except Exception as e:
            failed += 1
            import traceback
            print(f"FAIL: {test_fn.__name__} - {type(e).__name__}: {e}")
            traceback.print_exc()

    total = passed + failed
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)

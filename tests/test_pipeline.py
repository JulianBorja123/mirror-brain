"""
Mirror Brain v1.0 — Integration Tests with MockLLM.

Tests the full pipeline: NoteConstructor → ContextFetcher → LinkEvolution,
plus EntityRegistry lifecycle, reasoning trail, and graceful degradation.

Uses a MockLLM instead of real API calls for deterministic, fast tests.
"""

import sys
import os
import json
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mirror_brain.registry import EntityRegistry
from mirror_brain.note_constructor import NoteConstructor
from mirror_brain.context_fetcher import ContextFetcher
from mirror_brain.link_evolution import LinkEvolution
from mirror_brain.models import Note


# ── MockLLM ──────────────────────────────────────────────────────

class MockLLM:
    """Deterministic mock LLM that returns controlled responses based on call index."""

    def __init__(self, responses=None):
        """responses: list of JSON strings to return in order. Cycles if exhausted."""
        self.responses = responses or []
        self.call_count = 0
        self.calls = []  # record of prompts sent

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        if not self.responses:
            return json.dumps({
                "keywords": [], "context": "no mock response configured",
                "tags": [], "emotional_load": {}, "temporal_hints": [],
                "entities_mentioned": [], "search_hints": [],
            })
        idx = self.call_count % len(self.responses)
        self.call_count += 1
        return self.responses[idx]


# ── Helpers ──────────────────────────────────────────────────────

PASS = 0
FAIL = 0

def assert_equal(actual, expected, label=""):
    global PASS, FAIL
    if actual != expected:
        print(f"  FAIL: {label} — expected {expected!r}, got {actual!r}")
        FAIL += 1
        return False
    PASS += 1
    return True

def assert_true(cond, label=""):
    global PASS, FAIL
    if not cond:
        print(f"  FAIL: {label}")
        FAIL += 1
        return False
    PASS += 1
    return True

def assert_in(item, container, label=""):
    global PASS, FAIL
    if item not in container:
        print(f"  FAIL: {label} — {item!r} not in {container!r}")
        FAIL += 1
        return False
    PASS += 1
    return True

def make_temp_db():
    return os.path.join(tempfile.gettempdir(), f"mirror_brain_test_{os.getpid()}_{time.time_ns()}.db")


# ── Valid JSON fixtures ──────────────────────────────────────────

NOTE_VALID_JSON = json.dumps({
    "keywords": ["florería", "ventas", "publicidad", "c0", "DeepSeek"],
    "context": "Romina reportó que las ventas de la florería bajaron; Julián ofrece ayuda con publicidad online.",
    "tags": ["negocio", "técnico", "social", "preocupación"],
    "emotional_load": {"oxytocin": 0.6, "adrenaline": 0.3, "cortisol": 0.5, "dopamine": 0.4},
    "temporal_hints": ["hoy", "este mes"],
    "entities_mentioned": [
        {"name": "Romina", "type": "person", "is_new": False, "alias_of": "Romina González", "confidence": 0.95},
        {"name": "Florería GJB", "type": "place", "is_new": False, "alias_of": None, "confidence": 1.0},
        {"name": "c0", "type": "tool", "is_new": False, "alias_of": None, "confidence": 1.0},
        {"name": "DeepSeek", "type": "tool", "is_new": False, "alias_of": None, "confidence": 0.9},
        {"name": "Publicidad Online", "type": "project", "is_new": True, "alias_of": None, "confidence": 0.88},
    ],
    "search_hints": [
        "ayer qué pasó con la florería",
        "último status de c0 esta semana",
        "gasto reciente en tokens DeepSeek",
    ],
})

LINK_VALID_JSON = json.dumps({
    "links": [
        {"from_entity": "Publicidad Online", "to_entity": "Florería GJB",
         "relation": "concerns", "confidence": 0.92, "reasoning": "publicidad para la florería"},
        {"from_entity": "Romina González", "to_entity": "Florería GJB",
         "relation": "works_at", "confidence": 0.95, "reasoning": "Romina trabaja en la florería"},
        {"from_entity": "c0", "to_entity": "DeepSeek",
         "relation": "used_with", "confidence": 0.65, "reasoning": "c0 usa DeepSeek parcialmente"},
    ],
    "evolutions": [
        {"target": "Florería GJB", "action": "update_context",
         "confidence": 0.90, "reasoning": "ventas bajaron", "new_context": "Ventas bajaron 30% este mes."},
    ],
    "new_aliases": [
        {"alias": "la publicidad", "canonical_entity": "Publicidad Online",
         "confidence": 0.87, "reasoning": "abreviación detectada"},
    ],
    "needs_more_search": [],
})

LINK_MIXED_CONFIDENCE_JSON = json.dumps({
    "links": [
        {"from_entity": "c0", "to_entity": "Mirror Brain",
         "relation": "depends_on", "confidence": 0.95, "reasoning": "c0 is part of Mirror Brain"},
        {"from_entity": "Ollama", "to_entity": "Docker",
         "relation": "runs_in", "confidence": 0.72, "reasoning": "Ollama runs in Docker"},
        {"from_entity": "DeepSeek", "to_entity": "Hermes Agent",
         "relation": "related_to", "confidence": 0.40, "reasoning": "weak connection"},
    ],
    "evolutions": [
        {"target": "c0", "action": "update_context",
         "confidence": 0.50, "reasoning": "too uncertain evolution"},
        {"target": "Docker", "action": "update_tags",
         "confidence": 0.68, "reasoning": "flagged evolution"},
    ],
    "new_aliases": [
        {"alias": "modelo", "canonical_entity": "DeepSeek",
         "confidence": 0.91, "reasoning": "synonym"},
        {"alias": "contenedor", "canonical_entity": "Docker",
         "confidence": 0.68, "reasoning": "flagged alias"},
    ],
    "needs_more_search": [],
})


# ── Seed helpers ─────────────────────────────────────────────────

def seed_entities(reg):
    """Create base entities needed by tests."""
    reg.create("Gustavo Julian Barrios Borja", "person")
    uuid_romina, _ = reg.create("Romina González", "person")
    reg.add_alias("Romi", uuid_romina, source="manual", confidence=1.0)
    reg.create("Mirror Brain", "project")
    reg.add_alias("MB", reg.resolve("Mirror Brain"), source="manual")
    reg.create("c0", "tool")
    reg.create("Florería GJB", "place")
    reg.add_alias("la florería", reg.resolve("Florería GJB"), source="manual", confidence=1.0)
    reg.create("DeepSeek", "tool")
    reg.create("Docker", "tool")
    reg.create("Hermes Agent", "tool")
    reg.create("Ollama", "tool")


def seed_daily_summaries(reg):
    """Insert daily summaries for ContextFetcher tests."""
    from datetime import date, timedelta

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    two_days_ago = (date.today() - timedelta(days=2)).isoformat()

    summaries = [
        (two_days_ago, json.dumps({
            "es": "Julian compiló c0 en Docker. Neo4j corriendo."
        }), json.dumps([0.3, 0.4, 0.7, 0.3]),
         json.dumps(["c0", "Docker", "Neo4j"]),
         json.dumps(["c0 compilado en Docker"])),
        (yesterday, json.dumps({
            "es": "c0 + Ollama funcionando con hybrid search. Gasto $5 USD en tokens DeepSeek."
        }), json.dumps([0.2, 0.6, 0.5, 0.8]),
         json.dumps(["c0", "Ollama", "DeepSeek", "Mirror Brain"]),
         json.dumps(["hybrid search OK", "preocupación tokens DeepSeek"])),
    ]

    for date_val, summary, emotional, entities, decisions in summaries:
        reg.db.execute(
            "INSERT OR REPLACE INTO daily_index (date, summary, emotional_arc, "
            "key_entities, key_decisions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (date_val, summary, emotional, entities, decisions, date_val),
        )
    reg.db.commit()


# ── Test 1: Full pipeline happy path ─────────────────────────────

def test_full_pipeline_happy_path():
    print("\n── Test 1: Full pipeline happy path ──")

    db_path = make_temp_db()
    reg = EntityRegistry(db_path)
    seed_entities(reg)
    seed_daily_summaries(reg)

    mock = MockLLM([NOTE_VALID_JSON, LINK_VALID_JSON])

    nc = NoteConstructor(registry=reg, llm_call=mock)
    fetcher = ContextFetcher(registry=reg)
    le = LinkEvolution(registry=reg, llm_call=mock)

    sample_text = "Hoy Romi me dijo que la florería bajó ventas. c0 anda bien."

    # Step 1: Note constructor
    note = nc.construct(sample_text)
    assert_true(isinstance(note, Note), "note is Note instance")
    assert_true(len(note.keywords) > 0, "keywords populated")
    assert_true(len(note.context) > 0, "context populated")
    assert_true(len(note.entities_mentioned) == 5, "5 entities mentioned")
    assert_in("florería", note.keywords, "keyword 'florería'")

    # Verify entities were processed in registry
    ent_found = reg.resolve("Publicidad Online")
    assert_true(ent_found is not None, "new entity 'Publicidad Online' created")
    ent_found = reg.resolve("Romina González")
    assert_true(ent_found is not None, "existing entity resolved")
    alias_uuid = reg.resolve("Romina")
    assert_true(alias_uuid is not None, "alias 'Romina' registered")

    # Step 2: Context fetcher
    context = fetcher.fetch(note)
    assert_in("summary", context, "context has summary")
    assert_true(len(context.get("daily_summaries", [])) >= 1, "daily summaries found")
    assert_true(len(context.get("entity_contexts", {})) >= 3, "entity contexts found")

    # Step 3: Link evolution
    decisions = le.decide(note, context)
    assert_true(len(decisions.get("links", [])) == 3, "3 links proposed")
    assert_true(len(decisions.get("evolutions", [])) == 1, "1 evolution proposed")
    assert_true(len(decisions.get("new_aliases", [])) == 1, "1 alias proposed")

    # Step 4: Execute decisions
    report = le.execute(decisions, note)
    assert_true(len(report.get("auto_executed", [])) >= 3, "auto-executed items")
    assert_true(len(report.get("errors", [])) == 0, "no execution errors")

    # Verify relations created in DB
    rel_count = reg.db.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
    assert_true(rel_count >= 1, f"relations created in DB (found {rel_count})")

    # Verify reasoning trail entries
    trail_count = reg.db.execute("SELECT COUNT(*) FROM reasoning_trail").fetchone()[0]
    assert_true(trail_count >= 1, f"reasoning trail entries (found {trail_count})")

    reg.db.close()
    os.unlink(db_path)
    return True


# ── Test 2: Empty entities_mentioned → graceful ──────────────────

def test_empty_entities():
    print("\n── Test 2: Empty entities_mentioned → graceful ──")

    db_path = make_temp_db()
    reg = EntityRegistry(db_path)
    seed_entities(reg)

    NOTE_EMPTY_ENTITIES = json.dumps({
        "keywords": ["testing", "reflection"],
        "context": "Just a test note with no entities.",
        "tags": ["test"],
        "emotional_load": {},
        "temporal_hints": [],
        "entities_mentioned": [],
        "search_hints": [],
    })

    mock = MockLLM([NOTE_EMPTY_ENTITIES])
    nc = NoteConstructor(registry=reg, llm_call=mock)

    note = nc.construct("Test note without entities.")
    assert_true(isinstance(note, Note), "note created")
    assert_equal(len(note.entities_mentioned), 0, "zero entities")

    entity_count = reg.db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    initial_count = 9
    assert_equal(entity_count, initial_count, "entity count unchanged")

    reg.db.close()
    os.unlink(db_path)
    return True


# ── Test 3: Bad LLM JSON → graceful degradation ──────────────────

def test_bad_llm_json():
    print("\n── Test 3: Bad LLM JSON → graceful degradation ──")

    db_path = make_temp_db()
    reg = EntityRegistry(db_path)

    mock = MockLLM(["This is not JSON at all! { broken syntax!!!!"])
    nc = NoteConstructor(registry=reg, llm_call=mock)

    try:
        note = nc.construct("some text")
        assert_true(isinstance(note, Note), "note created despite bad JSON")
        assert_true(len(note.keywords) == 0, "keywords default to empty")
        print("  NoteConstructor handled bad JSON gracefully")
    except Exception as e:
        assert_true(False, f"NoteConstructor crashed on bad JSON: {e}")
        reg.db.close()
        os.unlink(db_path)
        return False

    # Test LinkEvolution bad JSON
    seed_entities(reg)
    LE_BAD_JSON = MockLLM(["Not JSON either!!! ``` {unbalanced"])
    le = LinkEvolution(registry=reg, llm_call=LE_BAD_JSON)

    test_note = Note(content="test", timestamp=Note.now(),
                     keywords=[], tags=[], entities_mentioned=[], search_hints=[])

    try:
        decisions = le.decide(test_note, {"summary": "empty", "daily_summaries": [],
                                           "entity_contexts": {}, "related_reasoning": []})
        assert_true(isinstance(decisions, dict), "decisions is dict despite bad JSON")
        assert_equal(len(decisions.get("links", [])), 0, "no links from bad JSON")
        print("  LinkEvolution handled bad JSON gracefully")
    except Exception as e:
        assert_true(False, f"LinkEvolution crashed on bad JSON: {e}")
        reg.db.close()
        os.unlink(db_path)
        return False

    reg.db.close()
    os.unlink(db_path)
    return True


# ── Test 4: ContextFetcher with seeded daily summaries ───────────

def test_context_fetcher():
    print("\n── Test 4: ContextFetcher with seeded daily summaries ──")

    db_path = make_temp_db()
    reg = EntityRegistry(db_path)
    seed_entities(reg)
    seed_daily_summaries(reg)

    fetcher = ContextFetcher(registry=reg)

    note = Note(
        content="Test note about yesterday's work on c0",
        timestamp=Note.now(),
        keywords=["c0", "Docker"],
        tags=["técnico"],
        entities_mentioned=[
            {"name": "c0", "type": "tool", "is_new": False, "alias_of": None, "confidence": 1.0},
            {"name": "Docker", "type": "tool", "is_new": False, "alias_of": None, "confidence": 1.0},
        ],
        search_hints=["qué pasó ayer con c0", "gasto en tokens esta semana"],
    )

    context = fetcher.fetch(note)

    dailies = context.get("daily_summaries", [])
    assert_true(len(dailies) >= 1, f"daily summaries found (got {len(dailies)})")

    entity_ctx = context.get("entity_contexts", {})
    assert_in("c0", entity_ctx, "c0 entity context found")
    assert_in("Docker", entity_ctx, "Docker entity context found")

    c0_ctx = entity_ctx.get("c0", {})
    assert_equal(c0_ctx.get("type"), "tool", "c0 type is tool")
    assert_true("c0_ref" in c0_ctx, "c0_ref present")

    summary = context.get("summary", "")
    assert_true(len(summary) > 0, "summary is non-empty")
    assert_true("daily" in summary.lower() or "entity" in summary.lower(),
                "summary mentions found content")

    reg.db.close()
    os.unlink(db_path)
    return True


# ── Test 5: LinkEvolution execute with mixed confidences ─────────

def test_link_evolution_mixed_confidence():
    print("\n── Test 5: LinkEvolution execute with mixed confidences ──")

    db_path = make_temp_db()
    reg = EntityRegistry(db_path)
    seed_entities(reg)
    seed_daily_summaries(reg)

    mock = MockLLM([LINK_MIXED_CONFIDENCE_JSON])
    le = LinkEvolution(registry=reg, llm_call=mock)

    note = Note(
        content="c0 works with Mirror Brain. Ollama in Docker. DeepSeek related to Hermes.",
        timestamp=Note.now(),
        keywords=["c0", "Ollama", "DeepSeek"],
        tags=["técnico"],
        entities_mentioned=[
            {"name": "c0", "type": "tool", "is_new": False, "alias_of": None, "confidence": 1.0},
            {"name": "Mirror Brain", "type": "project", "is_new": False, "alias_of": None, "confidence": 1.0},
            {"name": "Ollama", "type": "tool", "is_new": False, "alias_of": None, "confidence": 1.0},
            {"name": "Docker", "type": "tool", "is_new": False, "alias_of": None, "confidence": 1.0},
            {"name": "DeepSeek", "type": "tool", "is_new": False, "alias_of": None, "confidence": 1.0},
            {"name": "Hermes Agent", "type": "tool", "is_new": False, "alias_of": None, "confidence": 1.0},
        ],
        search_hints=[],
    )

    context = {"summary": "test", "daily_summaries": [], "entity_contexts": {},
               "related_reasoning": []}

    decisions = le.decide(note, context)
    report = le.execute(decisions, note)

    auto = report.get("auto_executed", [])
    assert_true(any("c0" in a for a in auto), "c0 link auto-executed")
    assert_true(any("modelo" in a for a in auto), "alias 'modelo' auto-executed")

    flagged = report.get("flagged", [])
    assert_true(any("Ollama" in f for f in flagged), "Ollama link flagged")
    assert_true(any("Docker" in f for f in flagged), "Docker evolution flagged")
    assert_true(any("contenedor" in f for f in flagged), "alias 'contenedor' flagged")

    skipped = report.get("skipped", [])
    assert_true(any("DeepSeek" in s and "too low" in s for s in skipped),
                "DeepSeek low-confidence link skipped")
    assert_true(any("c0" in s and "too low" in s for s in skipped),
                "c0 low-confidence evolution skipped")

    print(f"  auto={len(auto)} flagged={len(flagged)} skipped={len(skipped)}")
    assert_true(len(auto) >= 2, f"at least 2 auto-executed (got {len(auto)})")
    assert_true(len(flagged) >= 2, f"at least 2 flagged (got {len(flagged)})")
    assert_true(len(skipped) >= 2, f"at least 2 skipped (got {len(skipped)})")

    reg.db.close()
    os.unlink(db_path)
    return True


# ── Test 6: Entity lifecycle: create→alias→merge→verify ──────────

def test_entity_lifecycle():
    print("\n── Test 6: Entity lifecycle: create→alias→merge→verify ──")

    db_path = make_temp_db()
    reg = EntityRegistry(db_path)

    # CREATE
    uuid_hermes, c0_ref = reg.create("Hermes Agent v1", "tool")
    assert_true(uuid_hermes is not None, "entity created")
    assert_true(len(uuid_hermes) == 36, "UUID4 length")
    assert_true(c0_ref.startswith("ent_"), "c0_ref format")
    info = reg.get(uuid_hermes)
    assert_equal(info["status"], "active", "status is active")

    # ALIAS
    reg.add_alias("HA", uuid_hermes, source="llm", confidence=0.92)
    reg.add_alias("hermes", uuid_hermes, source="fuzzy", confidence=0.85)
    resolved = reg.resolve("HA")
    assert_equal(resolved, uuid_hermes, "resolve by alias 'HA'")
    resolved = reg.resolve("hermes")
    assert_equal(resolved, uuid_hermes, "resolve by alias 'hermes'")

    aliases = reg.get_aliases(uuid_hermes)
    alias_names = {a["alias"] for a in aliases}
    assert_in("HA", alias_names, "HA in aliases")
    assert_in("hermes", alias_names, "hermes in aliases")
    assert_in("Hermes Agent v1", alias_names, "canonical name in aliases")

    # Create a second entity to merge into
    uuid_hermes2, _ = reg.create("Hermes Agent v2", "tool")

    # MERGE: mark v1 as merged into v2
    reg.db.execute(
        "UPDATE entities SET status='merged', merged_into=? WHERE uuid=?",
        (uuid_hermes2, uuid_hermes),
    )
    reg.log_decision("merge_entities", entity_uuid=uuid_hermes,
                     target_uuid=uuid_hermes2, confidence=0.95,
                     reasoning="Hermes Agent v1 merged into v2", source="manual")
    reg.db.commit()

    # VERIFY merge
    info = reg.get(uuid_hermes)
    assert_equal(info["status"], "merged", "status is merged")
    assert_equal(info["merged_into"], uuid_hermes2, "merged_into set correctly")

    info2 = reg.get(uuid_hermes2)
    assert_equal(info2["status"], "active", "merge target still active")

    # VERIFY trail
    trail_rows = reg.db.execute(
        "SELECT action, confidence FROM reasoning_trail WHERE entity_uuid=? AND action='merge_entities'",
        (uuid_hermes,)
    ).fetchall()
    assert_true(len(trail_rows) >= 1, "merge trail record exists")

    reg.db.close()
    os.unlink(db_path)
    return True


# ── Test 7: Reasoning trail: create then revert ──────────────────

def test_reasoning_trail_revert():
    print("\n── Test 7: Reasoning trail: create then revert ──")

    db_path = make_temp_db()
    reg = EntityRegistry(db_path)
    seed_entities(reg)

    reg.log_decision("create_entity", reg.resolve("c0"), confidence=1.0,
                     reasoning="c0 is the graph engine", source="manual")
    reg.log_decision("add_alias", reg.resolve("DeepSeek"), confidence=0.91,
                     reasoning="LLM alias: 'el modelo' → DeepSeek",
                     evidence="Text: 'el modelo de DeepSeek'", source="llm")
    reg.log_decision("create_relation:depends_on", reg.resolve("Mirror Brain"),
                     target_uuid=reg.resolve("c0"), confidence=0.88,
                     reasoning="Mirror Brain depends on c0", source="llm")

    trail_before = reg.db.execute(
        "SELECT id, action, confidence, reverted FROM reasoning_trail ORDER BY id"
    ).fetchall()
    assert_true(len(trail_before) >= 3, f"3+ trail entries (got {len(trail_before)})")

    for row in trail_before:
        assert_equal(row[3], 0, f"entry {row[0]} not reverted initially")

    second_id = trail_before[1][0]
    reg.revert_decision(second_id)

    row = reg.db.execute(
        "SELECT reverted FROM reasoning_trail WHERE id=?", (second_id,)
    ).fetchone()
    assert_equal(row[0], 1, "second entry marked reverted")

    first_id = trail_before[0][0]
    third_id = trail_before[2][0]
    row = reg.db.execute(
        "SELECT reverted FROM reasoning_trail WHERE id=?", (first_id,)
    ).fetchone()
    assert_equal(row[0], 0, "first entry still not reverted")
    row = reg.db.execute(
        "SELECT reverted FROM reasoning_trail WHERE id=?", (third_id,)
    ).fetchone()
    assert_equal(row[0], 0, "third entry still not reverted")

    all_rows = reg.db.execute(
        "SELECT id, action, reverted FROM reasoning_trail ORDER BY id"
    ).fetchall()
    reverted_ids = [r[0] for r in all_rows if r[2] == 1]
    assert_equal(reverted_ids, [second_id], "only the target was reverted")

    reg.db.close()
    os.unlink(db_path)
    return True


# ── Run all tests ────────────────────────────────────────────────

def run_all():
    global PASS, FAIL
    PASS = 0
    FAIL = 0

    print("=" * 65)
    print("Mirror Brain v1.0 — INTEGRATION TESTS (MockLLM)")
    print("=" * 65)

    tests = [
        ("Full pipeline happy path", test_full_pipeline_happy_path),
        ("Empty entities_mentioned → graceful", test_empty_entities),
        ("Bad LLM JSON → graceful degradation", test_bad_llm_json),
        ("ContextFetcher with seeded daily summaries", test_context_fetcher),
        ("LinkEvolution mixed confidences", test_link_evolution_mixed_confidence),
        ("Entity lifecycle: create→alias→merge→verify", test_entity_lifecycle),
        ("Reasoning trail: create then revert", test_reasoning_trail_revert),
    ]

    results = []
    for name, test_fn in tests:
        try:
            ok = test_fn()
            results.append((name, "PASS" if ok else "FAIL"))
        except Exception as e:
            print(f"\n  FAIL: Unhandled exception in '{name}': {e}")
            import traceback
            traceback.print_exc()
            FAIL += 1
            results.append((name, "FAIL"))

    print("\n" + "=" * 65)
    print("RESULTS")
    print("=" * 65)
    for name, status in results:
        marker = "✅" if status == "PASS" else "❌"
        print(f"  {marker} {status}: {name}")

    print(f"\n  Total: {PASS} passed, {FAIL} failed ({len(tests)} tests)")
    print("=" * 65)

    return FAIL == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)

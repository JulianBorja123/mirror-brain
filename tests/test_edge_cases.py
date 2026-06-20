"""
Mirror Brain v1.0 — Edge Case / Robustness Tests.
Each test returns (passed: bool, detail: str). Prints PASS/FAIL per test.
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mirror_brain.registry import EntityRegistry
from mirror_brain.criteria import EntityCriteria
from mirror_brain.models import Note

_passed = 0
_failed = 0


def test(name):
    """Decorator that runs a test and prints PASS/FAIL."""

    def decorator(fn):
        global _passed, _failed
        try:
            ok, detail = fn()
            if ok:
                _passed += 1
                print(f"  PASS  {name}: {detail}")
            else:
                _failed += 1
                print(f"  FAIL  {name}: {detail}")
        except Exception as e:
            _failed += 1
            print(f"  FAIL  {name}: unexpected exception — {e}")
        return fn

    return decorator


def fresh_registry():
    """Create a fresh EntityRegistry in a temp file."""
    db_path = os.path.join(tempfile.gettempdir(), f"mirror_brain_edge_{os.getpid()}.db")
    if os.path.exists(db_path):
        os.unlink(db_path)
    reg = EntityRegistry(db_path)
    return reg, db_path


# ────────────────────────────────────────────────────────────────────
# 1. Empty text → graceful
# ────────────────────────────────────────────────────────────────────
@test("1. Empty text → graceful")
def test_empty_text():
    reg, db_path = fresh_registry()
    try:
        # ingest with empty name — should not raise
        uuid_val, c0_ref, reason = reg.ingest("", "person", mention_count=1)
        # Empty name should be handled: either skipped or created (criteria decides)
        # The important thing: no crash
        ok = True
        detail = f"no crash (uuid={'None' if uuid_val is None else uuid_val[:8]}, reason={reason})"
    finally:
        reg.db.close()
        os.unlink(db_path)
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# 2. 5000 char text → no crash
# ────────────────────────────────────────────────────────────────────
@test("2. 5000 char text → no crash")
def test_5000_char_text():
    reg, db_path = fresh_registry()
    try:
        long_name = "X" * 5000
        uuid_val, c0_ref = reg.create(long_name, "concept")
        # verify it was created and can be retrieved
        info = reg.get(uuid_val)
        ok = info is not None and len(info["canonical_name"]) == 5000
        detail = f"created entity with 5000-char name (uuid={uuid_val[:8]}...)"
    finally:
        reg.db.close()
        os.unlink(db_path)
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# 3. Mixed ES/EN
# ────────────────────────────────────────────────────────────────────
@test("3. Mixed ES/EN")
def test_mixed_es_en():
    reg, db_path = fresh_registry()
    try:
        uuid_val, c0_ref = reg.create("José's Café Project — el mejor lugar", "project")
        uuid2, _ = reg.create("Romina y Julián: Mirror Brain Development", "project")

        reg.add_alias("el café de José", uuid_val, source="llm", confidence=0.9)
        reg.add_alias("José's Coffee Shop", uuid_val, source="fuzzy", confidence=0.85)

        resolved = reg.resolve("el café de José")
        ok = resolved == uuid_val
        detail = f"mixed ES/EN names and aliases resolve correctly"
    finally:
        reg.db.close()
        os.unlink(db_path)
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# 4. Special chars (emoji, ñ, Chinese)
# ────────────────────────────────────────────────────────────────────
@test("4. Special chars (emoji, ñ, Chinese)")
def test_special_chars():
    reg, db_path = fresh_registry()
    try:
        uuid1, _ = reg.create("Proyecto 🧠 Mirror Brain", "project")
        uuid2, _ = reg.create("Señor García-Núñez", "person")
        uuid3, _ = reg.create("镜脑系统", "tool")  # Chinese for "Mirror Brain System"
        uuid4, _ = reg.create("emoji_test_🎉🚀💡", "concept")

        reg.add_alias("🧠 MB", uuid1, source="llm", confidence=0.95)
        reg.add_alias("Señor GN", uuid2, source="fuzzy", confidence=0.9)
        reg.add_alias("镜脑", uuid3, source="manual", confidence=1.0)

        ok = all([
            reg.resolve("🧠 MB") == uuid1,
            reg.resolve("Señor GN") == uuid2,
            reg.resolve("镜脑") == uuid3,
            reg.resolve("emoji_test_🎉🚀💡") == uuid4,
        ])
        detail = "emoji, ñ, and Chinese chars work in names and aliases"
    finally:
        reg.db.close()
        os.unlink(db_path)
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# 5. Duplicate entity → idempotent
# ────────────────────────────────────────────────────────────────────
@test("5. Duplicate entity → idempotent")
def test_duplicate_entity():
    reg, db_path = fresh_registry()
    try:
        uuid1, c01 = reg.create("IdempotentTest", "person")
        uuid2, c02 = reg.create("IdempotentTest", "person")

        # Second create should resolve to existing
        ok = uuid1 == uuid2 and c01 == c02
        detail = f"duplicate create returns same UUID ({uuid1[:8]}...)"
    finally:
        reg.db.close()
        os.unlink(db_path)
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# 6. Alias collision → no duplicate
# ────────────────────────────────────────────────────────────────────
@test("6. Alias collision → no duplicate")
def test_alias_collision():
    reg, db_path = fresh_registry()
    try:
        uuid_a, _ = reg.create("Entity A", "person")
        uuid_b, _ = reg.create("Entity B", "person")

        reg.add_alias("the_shared_alias", uuid_a, source="manual", confidence=1.0)
        # Second add with same alias but different entity → should be INSERT OR IGNORE
        reg.add_alias("the_shared_alias", uuid_b, source="manual", confidence=1.0)

        # The alias should still point to Entity A
        resolved = reg.resolve("the_shared_alias")
        ok = resolved == uuid_a
        detail = f"alias collision → first-write-wins (resolved to {uuid_a[:8]}...)"
    finally:
        reg.db.close()
        os.unlink(db_path)
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# 7. Self-referencing relation
# ────────────────────────────────────────────────────────────────────
@test("7. Self-referencing relation")
def test_self_referencing_relation():
    reg, db_path = fresh_registry()
    try:
        uuid_val, _ = reg.create("SelfRefEntity", "concept")
        reg.db.execute(
            "INSERT INTO relations (from_uuid, to_uuid, relation_type, source_text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uuid_val, uuid_val, "self_refers", "self-referencing test", reg._now()),
        )
        reg.db.commit()

        row = reg.db.execute(
            "SELECT from_uuid, to_uuid, relation_type FROM relations WHERE relation_type = 'self_refers'"
        ).fetchone()
        ok = row is not None and row[0] == row[1] == uuid_val
        detail = "self-referencing relation created and retrievable"
    finally:
        reg.db.close()
        os.unlink(db_path)
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# 8. 200 char entity name
# ────────────────────────────────────────────────────────────────────
@test("8. 200 char entity name")
def test_200_char_name():
    reg, db_path = fresh_registry()
    try:
        name = "N" * 200
        uuid_val, _ = reg.create(name, "concept")
        info = reg.get(uuid_val)
        ok = info is not None and len(info["canonical_name"]) == 200
        detail = f"200-char name stored and retrieved correctly"
    finally:
        reg.db.close()
        os.unlink(db_path)
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# 9. Zero-confidence → all skipped
# ────────────────────────────────────────────────────────────────────
@test("9. Zero-confidence → all skipped")
def test_zero_confidence():
    reg, db_path = fresh_registry()
    try:
        # concept type is not always-entity, mention_count=1, llm_confidence=0.0
        # → criteria says no entity created
        uuid_val, c0_ref, reason = reg.ingest("NoConfidenceConcept", "concept",
                                              mention_count=1, llm_confidence=0.0)
        ok = uuid_val is None and "skipped" in reason
        detail = f"zero-confidence correctly skipped (reason: {reason})"
    finally:
        reg.db.close()
        os.unlink(db_path)
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# 10. Empty daily_index → graceful
# ────────────────────────────────────────────────────────────────────
@test("10. Empty daily_index → graceful")
def test_empty_daily_index():
    reg, db_path = fresh_registry()
    try:
        count = reg.db.execute("SELECT COUNT(*) FROM daily_index").fetchone()[0]
        rows = reg.db.execute("SELECT * FROM daily_index").fetchall()
        ok = count == 0 and rows == []
        detail = "empty daily_index table queries without crash"
    finally:
        reg.db.close()
        os.unlink(db_path)
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# 11. No c0 client → no crash
# ────────────────────────────────────────────────────────────────────
@test("11. No c0 client → no crash")
def test_no_c0_client():
    # EntityRegistry does not depend on c0 — it's fully standalone
    reg, db_path = fresh_registry()
    try:
        uuid_val, _ = reg.create("WorksWithoutC0", "person")
        info = reg.get(uuid_val)
        ok = info is not None and info["canonical_name"] == "WorksWithoutC0"
        detail = "registry works fine without c0 client (as designed)"
    finally:
        reg.db.close()
        os.unlink(db_path)
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# 12. Unicode keywords/tags
# ────────────────────────────────────────────────────────────────────
@test("12. Unicode keywords/tags")
def test_unicode_keywords_tags():
    # Note model holds keywords and tags; validate Unicode round-trips
    try:
        note = Note(
            content="Testing unicode keywords and tags",
            keywords=["español", "日本語", "한국어", "emoji🎯", "café"],
            tags=["Müller", "Straße", "中文标签", "русский", "🚀production"],
            context="Unicode context test — ñ, ü, 中文, 한글",
        )
        # Serialize via to_dict-style round-trip (just validate the fields)
        ok = (
            len(note.keywords) == 5
            and "español" in note.keywords
            and "日本語" in note.keywords
            and "emoji🎯" in note.keywords
            and len(note.tags) == 5
            and "Müller" in note.tags
            and "中文标签" in note.tags
            and "🚀production" in note.tags
        )
        detail = f"unicode keywords ({len(note.keywords)}) and tags ({len(note.tags)}) round-trip"
    except Exception as e:
        ok = False
        detail = f"exception: {e}"
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# 13. 100% confidence → all auto
# ────────────────────────────────────────────────────────────────────
@test("13. 100% confidence → all auto")
def test_100_percent_confidence():
    reg, db_path = fresh_registry()
    try:
        # concept type: not always-entity, but llm_confidence=1.0 > 0.85 → creates
        uuid_val, c0_ref, reason = reg.ingest("HighConfidenceConcept", "concept",
                                              mention_count=1, llm_confidence=1.0)
        ok = uuid_val is not None and "created" in reason
        detail = f"100% confidence → auto-created (uuid={uuid_val[:8]}..., reason={reason})"

        # Also test with always-entity type at 100% confidence
        uuid2, _, reason2 = reg.ingest("Person100", "person",
                                       mention_count=1, llm_confidence=1.0)
        ok = ok and uuid2 is not None
        detail += f"; person type also auto-created ({uuid2[:8]}...)"
    finally:
        reg.db.close()
        os.unlink(db_path)
    return ok, detail


# ────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────
def main():
    print("Mirror Brain — Edge Case / Robustness Tests\n" + "=" * 54)
    # Tests are already executed by the @test decorator; we just import/reference them
    # to trigger execution. All functions above are defined and decorated.
    global _passed, _failed

    # Run all tests explicitly
    test_empty_text()
    test_5000_char_text()
    test_mixed_es_en()
    test_special_chars()
    test_duplicate_entity()
    test_alias_collision()
    test_self_referencing_relation()
    test_200_char_name()
    test_zero_confidence()
    test_empty_daily_index()
    test_no_c0_client()
    test_unicode_keywords_tags()
    test_100_percent_confidence()

    total = _passed + _failed
    print("\n" + "=" * 54)
    print(f"Results: {_passed}/{total} PASSED, {_failed}/{total} FAILED")
    if _failed == 0:
        print("🎉 All edge case tests PASSED!")
    else:
        print(f"❌ {_failed} test(s) FAILED")


if __name__ == "__main__":
    main()

"""
Mirror Brain v1.0 — Stress / Load Tests.
Creates heavy data volume and verifies correctness under load.
"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mirror_brain.registry import EntityRegistry


def _progress(i, total, label=""):
    """Print '.' every 50 items, plus a summary at the end."""
    if (i + 1) % 50 == 0:
        print(".", end="", flush=True)
    if i + 1 == total:
        if total % 50 != 0:
            print(".", end="", flush=True)
        print(f"  done ({label})")


def main():
    db_path = os.path.join(tempfile.gettempdir(), "mirror_brain_load_test.db")
    if os.path.exists(db_path):
        os.unlink(db_path)

    reg = EntityRegistry(db_path)
    entity_uuids = []

    # ────────────────────────────────────────────────────────────────
    # 1. Create 500 entities of mixed types
    # ────────────────────────────────────────────────────────────────
    print("Creating 500 entities...", end="", flush=True)
    types_cycle = ["person", "project", "tool", "place", "concept"]
    for i in range(500):
        t = types_cycle[i % 5]
        name = f"Entity_{i:04d}_{t}"
        uuid_str, c0 = reg.create(name, t)
        entity_uuids.append(uuid_str)
        _progress(i, 500, "entities")

    assert len(entity_uuids) == 500
    print("  ✅ 500 entities created")

    # ────────────────────────────────────────────────────────────────
    # 2. Add 1000+ aliases
    # ────────────────────────────────────────────────────────────────
    print("Adding 1000+ aliases...", end="", flush=True)
    alias_count = 0
    for i, uuid_str in enumerate(entity_uuids):
        base = f"Entity_{i:04d}"
        t = types_cycle[i % 5]

        reg.add_alias(f"{base}_short", uuid_str, source="fuzzy", confidence=0.9)
        alias_count += 1

        reg.add_alias(f"{t}_{base}", uuid_str, source="llm", confidence=0.85)
        alias_count += 1

        if i % 3 == 0:
            reg.add_alias(f"Alias_{i:04d}", uuid_str, source="manual", confidence=1.0)
            alias_count += 1

        _progress(i, 500, "aliases")

    assert alias_count > 1000, f"Expected >1000 aliases, got {alias_count}"
    print(f"  ✅ {alias_count} aliases added")

    # ────────────────────────────────────────────────────────────────
    # 3. Create 300+ relations
    # ────────────────────────────────────────────────────────────────
    print("Creating 300+ relations...", end="", flush=True)
    relation_types = ["relates_to", "depends_on", "mentions", "works_on",
                      "visited", "concerns", "updates_status", "talked_with"]
    rel_count = 0
    n = min(len(entity_uuids) - 1, 350)
    for i in range(n):
        from_uuid = entity_uuids[i]
        to_uuid = entity_uuids[i + 1]
        rt = relation_types[i % len(relation_types)]
        reg.db.execute(
            "INSERT INTO relations (from_uuid, to_uuid, relation_type, source_text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (from_uuid, to_uuid, rt, f"test relation {i}", reg._now()),
        )
        rel_count += 1

        if i % 5 == 0 and i + 5 < len(entity_uuids):
            cross_uuid = entity_uuids[i + 5]
            reg.db.execute(
                "INSERT INTO relations (from_uuid, to_uuid, relation_type, source_text, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (cross_uuid, from_uuid, "relates_to", f"cross relation {i}", reg._now()),
            )
            rel_count += 1

        _progress(i, n, "relations")

    reg.db.commit()
    assert rel_count >= 300, f"Expected >=300 relations, got {rel_count}"
    print(f"  ✅ {rel_count} relations created")

    # ────────────────────────────────────────────────────────────────
    # 4. Seed 90 daily summaries
    # ────────────────────────────────────────────────────────────────
    print("Seeding 90 daily summaries...", end="", flush=True)
    import json
    for i in range(90):
        date = f"2026-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}"
        summary = f"Day {i+1}: Mirror Brain stress test daily summary entry."
        emotional_arc = json.dumps([0.3, 0.5, 0.7] if i % 3 == 0 else [0.2, 0.4, 0.6])
        key_entities = json.dumps([entity_uuids[i % 500][:8], entity_uuids[(i + 1) % 500][:8]])
        key_decisions = json.dumps([f"Decision {i}", f"Decision {i+1}"])
        embedding = json.dumps([0.1 * j for j in range(10)])
        reg.db.execute(
            "INSERT OR IGNORE INTO daily_index (date, summary, emotional_arc, key_entities, key_decisions, embedding, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (date, summary, emotional_arc, key_entities, key_decisions, embedding, reg._now()),
        )
        _progress(i, 90, "summaries")

    reg.db.commit()
    daily_count = reg.db.execute("SELECT COUNT(*) FROM daily_index").fetchone()[0]
    assert daily_count == 90, f"Expected 90 daily summaries, got {daily_count}"
    print(f"  ✅ {daily_count} daily summaries seeded")

    # ────────────────────────────────────────────────────────────────
    # 5. Log 200+ reasoning trail entries
    # ────────────────────────────────────────────────────────────────
    print("Logging 200+ reasoning trail entries...", end="", flush=True)
    actions = ["create_entity", "add_alias", "create_relation", "merge_alias",
               "evolution:update_context", "evolution:merge_entities"]
    for i in range(220):
        uuid_str = entity_uuids[i % 500]
        target_uuid = entity_uuids[(i + 1) % 500] if i % 3 == 0 else ""
        action = actions[i % len(actions)]
        confidence = 0.5 + (i % 50) / 100.0
        reg.log_decision(
            action=action,
            entity_uuid=uuid_str,
            target_uuid=target_uuid,
            confidence=confidence,
            reasoning=f"Reasoning entry #{i}: {action} with confidence {confidence:.2f}",
            evidence=f"Evidence from test load #{i}",
            source="test",
        )
        _progress(i, 220, "reasoning")

    trail_count = reg.db.execute("SELECT COUNT(*) FROM reasoning_trail").fetchone()[0]
    assert trail_count >= 200, f"Expected >=200 reasoning entries, got {trail_count}"
    print(f"  ✅ {trail_count} reasoning trail entries logged")

    # ────────────────────────────────────────────────────────────────
    # 6. After load: verify search, resolve, list_by_type
    # ────────────────────────────────────────────────────────────────
    print("\n--- Post-load verification ---")

    # Entity_0000 is person (index 0 % 5 = 0)
    results = reg.search("Entity_0000_person")
    assert len(results) >= 1, f"search for Entity_0000_person returned {len(results)} results"
    assert results[0]["type"] == "person"
    print(f"  ✅ search works: found '{results[0]['canonical_name']}'")

    resolved = reg.resolve("Alias_0000")
    assert resolved is not None, "resolve('Alias_0000') returned None"
    assert resolved == entity_uuids[0], "resolve('Alias_0000') should match entity_uuids[0]"
    print(f"  ✅ resolve works: Alias_0000 -> {resolved[:8]}...")

    unknown = reg.resolve("DefinitelyNotAnEntityXYZ")
    assert unknown is None
    print("  ✅ resolve unknown -> None")

    persons = reg.list_by_type("person")
    projects = reg.list_by_type("project")
    tools = reg.list_by_type("tool")
    places = reg.list_by_type("place")
    concepts = reg.list_by_type("concept")
    assert len(persons) == 100, f"Expected 100 persons, got {len(persons)}"
    assert len(projects) == 100
    assert len(tools) == 100
    assert len(places) == 100
    assert len(concepts) == 100
    total_listed = len(persons) + len(projects) + len(tools) + len(places) + len(concepts)
    assert total_listed == 500
    print(f"  ✅ list_by_type: 100 of each type ({total_listed} total)")

    # ────────────────────────────────────────────────────────────────
    # 7. Measure DB file size
    # ────────────────────────────────────────────────────────────────
    reg.db.close()
    db_size = os.path.getsize(db_path)
    kb_size = db_size / 1024
    mb_size = db_size / (1024 * 1024)
    print(f"\n  📊 DB file size: {db_size:,} bytes ({kb_size:.1f} KB / {mb_size:.2f} MB)")

    # ────────────────────────────────────────────────────────────────
    # 8. Spot check no corruption
    # ────────────────────────────────────────────────────────────────
    import sqlite3
    conn = sqlite3.connect(db_path)
    result = conn.execute("PRAGMA integrity_check").fetchone()
    assert result[0] == "ok", f"Integrity check failed: {result[0]}"
    print(f"  ✅ PRAGMA integrity_check: {result[0]}")

    entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    alias_count_db = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
    relation_count_db = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
    summary_count_db = conn.execute("SELECT COUNT(*) FROM daily_index").fetchone()[0]
    trail_count_db = conn.execute("SELECT COUNT(*) FROM reasoning_trail").fetchone()[0]
    print(f"  ✅ Row counts: entities={entity_count}, aliases={alias_count_db}, "
          f"relations={relation_count_db}, summaries={summary_count_db}, trail={trail_count_db}")
    assert entity_count == 500
    assert alias_count_db == alias_count + 500  # +500 canonical aliases from entity creation
    assert relation_count_db == rel_count
    assert summary_count_db == 90
    assert trail_count_db == trail_count
    print("  ✅ All row counts match expected values")

    sample = conn.execute(
        "SELECT canonical_name, type, c0_ref FROM entities WHERE uuid = ?",
        (entity_uuids[42],)
    ).fetchone()
    assert sample is not None
    assert sample[0] == "Entity_0042_tool"
    assert sample[1] == "tool"
    assert sample[2].startswith("ent_")
    print(f"  ✅ Spot check entity: {sample[0]} ({sample[1]}, {sample[2]})")

    dup_aliases = conn.execute(
        "SELECT alias, COUNT(*) FROM aliases GROUP BY alias HAVING COUNT(*) > 1"
    ).fetchall()
    assert len(dup_aliases) == 0, f"Found {len(dup_aliases)} duplicate aliases!"
    print("  ✅ No duplicate aliases found")

    conn.close()
    os.unlink(db_path)
    print(f"\n🎉 All load tests PASSED! DB cleaned up.")


if __name__ == "__main__":
    main()

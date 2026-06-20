"""
Mirror Brain v1.0 — Performance Benchmarks.

Measures speed of core operations with min/avg/max reporting.
All tests use Python 3.11 stdlib. Time measured with time.perf_counter().
"""

import sys
import os
import json
import tempfile
import time
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mirror_brain.registry import EntityRegistry
from mirror_brain.note_constructor import NoteConstructor
from mirror_brain.context_fetcher import ContextFetcher
from mirror_brain.link_evolution import LinkEvolution
from mirror_brain.models import Note
from mirror_brain.criteria import EntityCriteria


# ── Helpers ──────────────────────────────────────────────────────

PASS = 0
FAIL = 0

def print_stats(name, times, threshold=None):
    """Print min/avg/max for a list of timing values in milliseconds."""
    if not times:
        print(f"  {name}: no data")
        return
    ms_times = [t * 1000 for t in times]
    mn = min(ms_times)
    avg = statistics.mean(ms_times)
    mx = max(ms_times)
    print(f"  {name}: min={mn:.3f}ms avg={avg:.3f}ms max={mx:.3f}ms (n={len(times)})")
    if threshold and avg > threshold:
        print(f"    ⚠️  above threshold ({threshold:.1f}ms)")
    return {"min": mn, "avg": avg, "max": mx, "n": len(times)}


def make_temp_db(suffix=""):
    return os.path.join(tempfile.gettempdir(),
                        f"mirror_brain_perf_{os.getpid()}_{time.time_ns()}{suffix}.db")


# ── MockLLM for pipeline benchmarks ─────────────────────────────

class MockLLM:
    """Returns valid note + link JSON for pipeline benchmarks."""

    def __init__(self):
        self.call_count = 0

    def __call__(self, prompt: str) -> str:
        self.call_count += 1
        if self.call_count % 2 == 1:
            # Note JSON
            return json.dumps({
                "keywords": ["test", "benchmark", "entity"],
                "context": "A benchmark test note about entity {n}.".format(n=self.call_count),
                "tags": ["benchmark", "test"],
                "emotional_load": {"oxytocin": 0.1, "adrenaline": 0.2, "cortisol": 0.1, "dopamine": 0.3},
                "temporal_hints": [],
                "entities_mentioned": [
                    {"name": f"Entity_{self.call_count}", "type": "concept", "is_new": True,
                     "alias_of": None, "confidence": 0.9},
                ],
                "search_hints": [],
            })
        else:
            # Link JSON
            return json.dumps({
                "links": [],
                "evolutions": [],
                "new_aliases": [],
                "needs_more_search": [],
            })


# ── Benchmark 1: Create 100 entities, avg time ──────────────────

def bench_create_entities():
    print("\n── Benchmark 1: Create 100 entities ──")

    db_path = make_temp_db("_create")
    reg = EntityRegistry(db_path)
    times = []

    for i in range(100):
        t0 = time.perf_counter()
        reg.create(f"Entity_Bench_{i}", "concept")
        t1 = time.perf_counter()
        times.append(t1 - t0)

    count = reg.db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    print(f"  Entities in DB: {count}")
    stats = print_stats("create()", times)
    reg.db.close()
    os.unlink(db_path)

    assert_true(count == 100, f"all 100 entities created (got {count})")
    assert_true(stats["avg"] < 50, "avg create time < 50ms")
    return stats


# ── Benchmark 2: Resolve 1000 lookups, avg time ──────────────────

def bench_resolve_lookups():
    print("\n── Benchmark 2: Resolve 1000 lookups ──")

    db_path = make_temp_db("_resolve")
    reg = EntityRegistry(db_path)

    # Create 100 entities
    for i in range(100):
        reg.create(f"ResolveEntity_{i}", "concept")
        reg.add_alias(f"RE_{i}", reg.resolve(f"ResolveEntity_{i}"), source="llm")

    times = []

    for _ in range(1000):
        i = _ % 100
        t0 = time.perf_counter()
        result = reg.resolve(f"RE_{i}")
        t1 = time.perf_counter()
        times.append(t1 - t0)
        # Sanity: result should be a UUID string
        if result is None:
            print(f"  WARNING: resolve('RE_{i}') returned None")

    stats = print_stats("resolve()", times)
    reg.db.close()
    os.unlink(db_path)

    assert_true(stats["avg"] < 5, "avg resolve time < 5ms")
    return stats


# ── Benchmark 3: Search 50 queries through 200 entities ──────────

def bench_search():
    print("\n── Benchmark 3: Search 50 queries through 200 entities ──")

    db_path = make_temp_db("_search")
    reg = EntityRegistry(db_path)

    # Create 200 entities
    for i in range(200):
        uuid_, _ = reg.create(f"SearchEntity_{i:04d}", "concept")
        if i < 100:
            reg.add_alias(f"SE_{i:04d}", uuid_, source="llm")

    times = []
    queries = [f"SearchEntity_{i:04d}" for i in range(0, 200, 4)]  # 50 queries

    for q in queries:
        t0 = time.perf_counter()
        results = reg.search(q)
        t1 = time.perf_counter()
        times.append(t1 - t0)
        # Sanity check
        if len(results) == 0:
            print(f"  WARNING: search('{q}') returned 0 results")

    stats = print_stats("search()", times)
    reg.db.close()
    os.unlink(db_path)

    assert_true(stats["avg"] < 10, "avg search time < 10ms")
    return stats


# ── Benchmark 4: Ingest 50 entities ──────────────────────────────

def bench_ingest():
    print("\n── Benchmark 4: Ingest 50 entities ──")

    db_path = make_temp_db("_ingest")
    reg = EntityRegistry(db_path)
    times = []

    types = ["person", "project", "tool", "place", "concept"]

    for i in range(50):
        etype = types[i % len(types)]
        t0 = time.perf_counter()
        uuid_, c0_ref, reason = reg.ingest(
            f"IngestEntity_{i}", etype, mention_count=1, llm_confidence=0.9
        )
        t1 = time.perf_counter()
        times.append(t1 - t0)

    count = reg.db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    print(f"  Entities in DB: {count}")
    stats = print_stats("ingest()", times)
    reg.db.close()
    os.unlink(db_path)

    assert_true(count == 50, f"all 50 entities ingested (got {count})")
    assert_true(stats["avg"] < 50, "avg ingest time < 50ms")
    return stats


# ── Benchmark 5: Parse 100 JSON responses ──────────────────────

def bench_parse_json():
    print("\n── Benchmark 5: Parse 100 JSON responses ──")

    from mirror_brain.note_constructor import NoteConstructor
    from mirror_brain.link_evolution import LinkEvolution

    dummy_reg = None  # parsing doesn't need a real registry

    # NoteConstructor._parse_response
    nc_parse_times = []
    for i in range(50):
        payload = json.dumps({
            "keywords": [f"test_{i}", "benchmark"],
            "context": f"Test context {i}",
            "tags": ["test"],
            "emotional_load": {"oxytocin": 0.1, "adrenaline": 0.2, "cortisol": 0.1, "dopamine": 0.3},
            "temporal_hints": [],
            "entities_mentioned": [{"name": f"E{i}", "type": "concept", "is_new": True, "alias_of": None, "confidence": 0.9}],
            "search_hints": [],
        })
        t0 = time.perf_counter()
        result = NoteConstructor._parse_response(payload)
        t1 = time.perf_counter()
        nc_parse_times.append(t1 - t0)

    # LinkEvolution._parse_response
    le_parse_times = []
    for i in range(50):
        payload = json.dumps({
            "links": [{"from_entity": "E1", "to_entity": "E2", "relation": "relates_to", "confidence": 0.9, "reasoning": "test"}],
            "evolutions": [],
            "new_aliases": [],
            "needs_more_search": [],
        })
        t0 = time.perf_counter()
        result = LinkEvolution._parse_response(payload)
        t1 = time.perf_counter()
        le_parse_times.append(t1 - t0)

    # Also test bad JSON parsing fallback
    fallback_times = []
    for i in range(10):
        bad = f"```json\n{json.dumps({'links': [{'from_entity': f'E{i}', 'to_entity': 'E2', 'relation': 'test', 'confidence': 0.9, 'reasoning': 'test'}], 'evolutions': [], 'new_aliases': [], 'needs_more_search': []})}\n```"
        t0 = time.perf_counter()
        result = LinkEvolution._parse_response(bad)
        t1 = time.perf_counter()
        fallback_times.append(t1 - t0)

    all_times = nc_parse_times + le_parse_times + fallback_times

    print_stats("NoteConstructor.parse_response (50)", nc_parse_times)
    print_stats("LinkEvolution.parse_response (50)", le_parse_times)
    print_stats("Markdown fence fallback (10)", fallback_times)
    stats = print_stats("parse_json TOTAL (110)", all_times)

    assert_true(stats["avg"] < 5, "avg parse time < 5ms")
    return stats


# ── Benchmark 6: Full pipeline mock 10 times ────────────────────

def bench_full_pipeline():
    print("\n── Benchmark 6: Full pipeline mock 10 times ──")

    times = []

    for run in range(10):
        db_path = make_temp_db(f"_pipeline_{run}")
        reg = EntityRegistry(db_path)

        # Seed entities
        reg.create("Gustavo Julian Barrios Borja", "person")
        uuid_romina, _ = reg.create("Romina González", "person")
        reg.add_alias("Romi", uuid_romina, source="manual", confidence=1.0)
        reg.create("Mirror Brain", "project")
        reg.create("c0", "tool")
        reg.create("Florería GJB", "place")
        reg.create("DeepSeek", "tool")
        reg.create("Docker", "tool")
        reg.create("Hermes Agent", "tool")
        reg.create("Ollama", "tool")

        mock = MockLLM()
        nc = NoteConstructor(registry=reg, llm_call=mock)
        fetcher = ContextFetcher(registry=reg)
        le = LinkEvolution(registry=reg, llm_call=mock)

        t0 = time.perf_counter()

        # Step 1
        note = nc.construct(f"Pipeline benchmark run {run} for Mirror Brain with c0 and Ollama.")

        # Step 2
        context = fetcher.fetch(note)

        # Step 3
        decisions = le.decide(note, context)

        # Step 4
        report = le.execute(decisions, note)

        t1 = time.perf_counter()
        times.append(t1 - t0)

        reg.db.close()
        os.unlink(db_path)

    stats = print_stats("full pipeline (mock)", times)
    assert_true(stats["avg"] < 500, "avg full pipeline time < 500ms")
    return stats


# ── Benchmark 7: DB size after 1000 entities ────────────────────

def bench_db_size():
    print("\n── Benchmark 7: DB size after 1000 entities ──")

    db_path = make_temp_db("_size")
    reg = EntityRegistry(db_path)

    # Create 1000 entities with aliases
    for i in range(1000):
        uuid_, _ = reg.create(f"SizeEntity_{i:06d}", "concept")
        if i % 3 == 0:
            reg.add_alias(f"SE_{i:06d}", uuid_, source="llm")

    reg.db.commit()

    # Get DB file size
    size_bytes = os.path.getsize(db_path)
    size_kb = size_bytes / 1024
    size_mb = size_bytes / (1024 * 1024)

    # Get entity/alias/trail counts
    entity_count = reg.db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    alias_count = reg.db.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]

    print(f"  Entities: {entity_count}")
    print(f"  Aliases:  {alias_count}")
    print(f"  DB size:  {size_bytes:,} bytes ({size_kb:.1f} KB / {size_mb:.2f} MB)")

    # Also measure with vacuum (compact)
    t0 = time.perf_counter()
    reg.db.execute("VACUUM")
    t1 = time.perf_counter()
    vacuum_time = (t1 - t0) * 1000

    size_after_vacuum = os.path.getsize(db_path)
    size_after_kb = size_after_vacuum / 1024
    print(f"  After VACUUM: {size_after_vacuum:,} bytes ({size_after_kb:.1f} KB)")
    print(f"  VACUUM time: {vacuum_time:.2f}ms")

    reg.db.close()
    os.unlink(db_path)

    # DB should be reasonably small (< 2 MB for 1000 entities)
    assert_true(size_mb < 2.0, f"DB size < 2MB (got {size_mb:.2f} MB)")
    assert_true(entity_count == 1000, f"1000 entities created (got {entity_count})")

    return {"size_bytes": size_bytes, "size_mb": size_mb, "entity_count": entity_count,
            "alias_count": alias_count, "vacuum_time_ms": vacuum_time}


# ── Helpers ──────────────────────────────────────────────────────

def assert_true(cond, label=""):
    global PASS, FAIL
    if not cond:
        print(f"  FAIL: {label}")
        FAIL += 1
        return False
    PASS += 1
    return True


# ── Run all benchmarks ───────────────────────────────────────────

def run_all():
    global PASS, FAIL
    PASS = 0
    FAIL = 0

    print("=" * 65)
    print("Mirror Brain v1.0 — PERFORMANCE BENCHMARKS")
    print("=" * 65)
    print(f"  Python: {sys.version}")
    print(f"  Platform: {sys.platform}")

    t_total_start = time.perf_counter()

    benchmarks = [
        ("Create 100 entities", bench_create_entities),
        ("Resolve 1000 lookups", bench_resolve_lookups),
        ("Search 50 queries through 200 entities", bench_search),
        ("Ingest 50 entities", bench_ingest),
        ("Parse 100 JSON responses", bench_parse_json),
        ("Full pipeline mock 10 times", bench_full_pipeline),
        ("DB size after 1000 entities", bench_db_size),
    ]

    results = []
    for name, bench_fn in benchmarks:
        try:
            stats = bench_fn()
            results.append((name, "PASS", stats))
        except Exception as e:
            print(f"\n  FAIL: Unhandled exception in '{name}': {e}")
            import traceback
            traceback.print_exc()
            FAIL += 1
            results.append((name, "FAIL", None))

    t_total_end = time.perf_counter()
    total_time = (t_total_end - t_total_start) * 1000

    print("\n" + "=" * 65)
    print("RESULTS")
    print("=" * 65)
    for name, status, stats in results:
        marker = "✅" if status == "PASS" else "❌"
        print(f"  {marker} {status}: {name}")
        if stats:
            if isinstance(stats, dict) and "avg" in stats:
                print(f"       avg={stats['avg']:.3f}ms, min={stats['min']:.3f}ms, max={stats['max']:.3f}ms (n={stats['n']})")
            elif isinstance(stats, dict) and "size_mb" in stats:
                print(f"       {stats['entity_count']} entities, {stats['size_mb']:.2f} MB")

    print(f"\n  Total: {PASS} passed, {FAIL} failed ({len(benchmarks)} benchmarks)")
    print(f"  Total wall time: {total_time:.1f}ms")
    print("=" * 65)

    return FAIL == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)

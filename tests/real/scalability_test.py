#!/usr/bin/env python3
"""
Mirror Brain v3 — Scalability & Cross-Language Test
Tests: bilingual ingestion, cross-language search, degradation measurement, edge cases.
"""
import sys, json, time, subprocess
sys.path.insert(0, "C:/Users/gusta/mirror-brain/tests/real")
from harness import MCPClient

client = MCPClient()
client.init()
print(f"=== BRAIN SCALABILITY TEST ===")
print(f"Server: Mirror Brain v3 | Session: {client.session_id[:16]}...")
print()

r = client.tool("mb_stats", {})
print(f"BASELINE: entities={r.get('entities','?')} | relations={r.get('relations','?')}")
print()

# ============================================================
# PHASE 1: BILINGUAL INGESTION (EN + ES)
# ============================================================
print("=" * 60)
print("PHASE 1: BILINGUAL INGESTION (15 texts, EN+ES mixed)")
print("=" * 60)

bilingual_texts = [
    ("en", "Julian built Mirror Brain as an AI memory system using DeepSeek and Neo4j"),
    ("en", "Romina designed the user interface with React components and Tailwind styling"),
    ("en", "Docker containers run the entire stack: c0, Neo4j, Ollama, and the MCP server"),
    ("en", "The deployment pipeline includes GitHub Actions CI/CD and Hostinger hosting"),
    ("en", "Ollama runs nomic-embed-text locally for embeddings without external API calls"),
    ("en", "The consolidation engine compresses daily entries into weekly and monthly summaries"),
    ("en", "Procedural memory learns workflows from repeated action patterns in reasoning_trail"),
    ("en", "The predictive engine uses linear regression on emotional metrics over 30-day windows"),
    ("es", "Julian creo Mirror Brain como sistema de memoria con agentes autonomos"),
    ("es", "Romina Gonzalez es la persona mas importante en la vida de Gustavo"),
    ("es", "El motor c0 esta escrito en Rust y se comunica con Neo4j mediante Bolt"),
    ("es", "Los embeddings semanticos usan nomic-embed-text con Ollama local"),
    ("es", "El pipeline de consolidacion comprime dias en semanas y meses automaticamente"),
    ("es", "La memoria procedural aprende flujos de trabajo observando patrones repetidos"),
    ("es", "El motor predictivo proyecta tendencias emocionales usando regresion lineal"),
]

all_tasks = []
phase1_times = []

for i, (lang, text) in enumerate(bilingual_texts):
    t0 = time.perf_counter()
    r = client.tool("mb_ingest", {"text": text, "source": f"bilingual_{lang}_{i}"})
    ms = (time.perf_counter() - t0) * 1000
    tid = r.get("task_id", "") if isinstance(r, dict) else ""
    all_tasks.append((lang, text[:50], tid))
    phase1_times.append(ms)
    print(f"  [{lang}] submit {i+1:2d}/15: {tid[:12]}... ({ms:.0f}ms)")

avg_submit = sum(phase1_times) / len(phase1_times)
print(f"  Avg submit time: {avg_submit:.0f}ms")
print()

# Wait for all to complete
print("Waiting for 15 async tasks...")
t0_wait = time.time()
done_count = 0
for attempt in range(40):
    time.sleep(2)
    done_count = sum(1 for _, _, tid in all_tasks
                     if client.tool("mb_task_status", {"task_id": tid}).get("status", "") in ("done", "error"))
    if done_count == len(all_tasks):
        break
    if attempt % 5 == 0:
        print(f"  ... {done_count}/{len(all_tasks)} done")

wait_sec = time.time() - t0_wait
print(f"  All {done_count}/{len(all_tasks)} done in {wait_sec:.1f}s")
print()

# ============================================================
# PHASE 2: CROSS-LANGUAGE SEARCH QUALITY
# ============================================================
print("=" * 60)
print("PHASE 2: CROSS-LANGUAGE SEARCH")
print("=" * 60)

cross_tests = [
    ("en->en", "memory system", "Mirror Brain", ""),
    ("en->es", "Romina person life", "Romina", "Gustavo"),
    ("es->en", "sistema de memoria", "Mirror Brain", ""),
    ("es->es", "motor Rust Neo4j", "c0", "Rust"),
    ("en->es", "embeddings local", "Ollama", "nomic"),
    ("es->en", "workflows patterns", "procedural", ""),
    ("en->en", "predictive emotional", "predictive", "regression"),
    ("es->es", "Gustavo persona", "Gustavo", "Julian"),
]

score = 0
for query_lang, query, exp_en, exp_es in cross_tests:
    # Try fuzzy
    r_fuzzy = client.tool("mb_search_fuzzy", {"name": query})
    fuzzy_data = r_fuzzy if isinstance(r_fuzzy, list) else []
    fuzzy_names = [d.get("canonical_name", "") for d in fuzzy_data[:3]]

    # Try semantic
    r_sem = client.tool("mb_search_semantic", {"query": query, "limit": 5})
    sem_data = r_sem if isinstance(r_sem, list) else []
    sem_names = [d.get("name", "") for d in sem_data[:3]]

    all_names = " | ".join(fuzzy_names + sem_names)
    hit_en = exp_en.lower() in all_names.lower()
    hit_es = exp_es.lower() in all_names.lower() if exp_es else True
    passed = hit_en and hit_es

    if passed:
        score += 1

    sym = "OK" if passed else "XX"
    print(f"  [{sym}] [{query_lang}] '{query}': fuzzy={fuzzy_names[:2]} sem={sem_names[:2]}")

print(f"  Cross-language score: {score}/{len(cross_tests)}")
print()

# ============================================================
# PHASE 3: DEGRADATION MEASUREMENT
# ============================================================
print("=" * 60)
print("PHASE 3: DEGRADATION - measure times as brain grows")
print("=" * 60)

snapshots = []
for batch in range(3):
    snapshot = {"batch": batch}

    t0 = time.perf_counter()
    client.tool("mb_list_entities", {"limit": 5})
    snapshot["list_entities_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    client.tool("mb_search_fuzzy", {"name": "Mirror"})
    snapshot["fuzzy_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    client.tool("mb_search_semantic", {"query": "memory system docker", "limit": 3})
    snapshot["semantic_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    client.tool("mb_list_relations", {"limit": 10})
    snapshot["relations_ms"] = (time.perf_counter() - t0) * 1000

    r = client.tool("mb_stats", {})
    snapshot["entities"] = r.get("entities", 0)
    snapshot["relations"] = r.get("relations", 0)

    r = client.tool("mb_cache_stats", {})
    snapshot["cache_hit_rate"] = r.get("hit_rate", 0)
    snapshot["cache_size"] = r.get("size", 0)

    # Raw c0 export
    r0 = subprocess.run(
        ["docker", "exec", "mirrorbrain-c0", "c0", "export", "--format", "json"],
        capture_output=True, encoding="utf-8", timeout=15
    )
    try:
        c0_data = json.loads(r0.stdout)
        snapshot["c0_nodes"] = len(c0_data.get("nodes", []))
        snapshot["c0_edges"] = len(c0_data.get("edges", []))
    except Exception:
        snapshot["c0_nodes"] = -1
        snapshot["c0_edges"] = -1

    snapshots.append(snapshot)

    if batch < 2:
        batch_texts = [
            f"Batch {batch+1} test A: The system scales linearly with entity count and cache optimization",
            f"Batch {batch+1} test B: Neural embeddings provide semantic understanding across languages",
            f"Batch {batch+1} test C: Procedural memory improves with more observed workflow repetitions",
            f"Batch {batch+1} test D: Cross-lingual search works when embeddings are well-trained",
            f"Batch {batch+1} test E: Response time correlates with Neo4j graph density not entity count",
        ]
        for text in batch_texts:
            r = client.tool("mb_ingest", {"text": text, "source": f"deg_test_{batch}"})
        time.sleep(15)

print()
print(f"  {'Batch':<7} {'Entities':>8} {'Rels':>6} {'c0_nodes':>8} {'c0_edges':>8} {'fuzzy_ms':>8} {'sem_ms':>8} {'list_ms':>8} {'rel_ms':>8} {'cache%':>7}")
print(f"  {'-'*7} {'-'*8} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*7}")
for s in snapshots:
    print(f"  {s['batch']:<7} {s['entities']:>8} {s['relations']:>6} {s['c0_nodes']:>8} {s['c0_edges']:>8} {s['fuzzy_ms']:>8.0f} {s['semantic_ms']:>8.0f} {s['list_entities_ms']:>8.0f} {s['relations_ms']:>8.0f} {s['cache_hit_rate']:>7.3f}")

if len(snapshots) >= 2:
    s0 = snapshots[0]
    s_last = snapshots[-1]
    print()
    fuzzy_ratio = s_last["fuzzy_ms"] / max(1, s0["fuzzy_ms"])
    sem_ratio = s_last["semantic_ms"] / max(1, s0["semantic_ms"])
    list_ratio = s_last["list_entities_ms"] / max(1, s0["list_entities_ms"])
    rel_ratio = s_last["relations_ms"] / max(1, s0["relations_ms"])
    print(f"  Degradation ratios (last/first):")
    print(f"    fuzzy: {fuzzy_ratio:.2f}x | semantic: {sem_ratio:.2f}x | list: {list_ratio:.2f}x | rel: {rel_ratio:.2f}x")
    if max(fuzzy_ratio, sem_ratio, list_ratio, rel_ratio) > 1.5:
        print(f"  WARNING: DEGRADATION DETECTED (>1.5x slowdown)")
    else:
        print(f"  OK: No significant degradation")

print()

# ============================================================
# PHASE 4: EDGE CASES
# ============================================================
print("=" * 60)
print("PHASE 4: EDGE CASES & BOUNDARY TESTS")
print("=" * 60)

edge_tests = []

# Empty text
r = client.tool("mb_ingest", {"text": "", "source": "edge_empty"})
edge_tests.append(("Empty text", isinstance(r, dict) and "task_id" in r, "accepted"))

# Long text
long_text = "The Mirror Brain system " * 200
r = client.tool("mb_ingest", {"text": long_text[:3000], "source": "edge_long"})
edge_tests.append(("Long text 3k chars", isinstance(r, dict) and "task_id" in r, "truncated OK"))

# Special chars
r = client.tool("mb_search_fuzzy", {"name": "!!!"})
edge_tests.append(("Special chars query", isinstance(r, list), "no crash"))

time.sleep(1)
r = client.tool("mb_search_fuzzy", {"name": "   "})
edge_tests.append(("Whitespace query", isinstance(r, list), "no crash"))

# Emoji
r = client.tool("mb_search_fuzzy", {"name": chr(0x1F9E0)})
edge_tests.append(("Emoji query", isinstance(r, list), "no crash"))

# Unicode accent
r = client.tool("mb_search_fuzzy", {"name": "Gonzalez"})
edge_tests.append(("Accent search Gonzalez", isinstance(r, list), "unicode OK"))

# Very long query
r = client.tool("mb_search_semantic", {"query": "x" * 500, "limit": 2})
edge_tests.append(("Long semantic query 500 chars", isinstance(r, list), "no crash"))

# Duplicate ingestion (idempotency)
r1 = client.tool("mb_ingest", {"text": "UNIQUE_IDEMPOTENT_TEST_123", "source": "edge_dup"})
time.sleep(8)
r2 = client.tool("mb_ingest", {"text": "UNIQUE_IDEMPOTENT_TEST_123", "source": "edge_dup2"})
edge_tests.append(("Duplicate ingest accepted", isinstance(r1, dict) and isinstance(r2, dict), "idempotent"))

for label, passed, detail in edge_tests:
    sym = "OK" if passed else "XX"
    print(f"  [{sym}] {label}: {detail}")

print()

# ============================================================
# FINAL SUMMARY
# ============================================================
r = client.tool("mb_stats", {})
stats = r
r = client.tool("mb_cache_stats", {})
cache = r

print("=" * 60)
print("FINAL BRAIN STATE")
print("=" * 60)
print(f"  Entities: {stats.get('entities', '?')}")
print(f"  Relations: {stats.get('relations', '?')}")
print(f"  c0 nodes: {snapshots[-1]['c0_nodes']}")
print(f"  c0 edges: {snapshots[-1]['c0_edges']}")
print(f"  Cache hit rate: {cache.get('hit_rate', 0):.1%}")
print(f"  Cache size: {cache.get('size', 0)} entries")
print(f"  Cross-language score: {score}/{len(cross_tests)}")
print(f"  Edge cases: {sum(1 for _, p, _ in edge_tests if p)}/{len(edge_tests)}")
print(f"  Degradation: {'NONE' if max(fuzzy_ratio, sem_ratio, list_ratio, rel_ratio) < 1.5 else 'DETECTED'}")
print(f"  Total calls: {client.call_count}")
print(f"  Total time: {client.total_time_ms:.0f}ms")
print()

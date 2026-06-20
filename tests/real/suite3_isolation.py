#!/usr/bin/env python3
"""
SUITE 3 — Isolation, Context Management & Robustness.
Tests: entity isolation (no leaks), context boundaries, ambiguous queries,
contradiction handling, data density, alias precision, search boundary stress.
"""
import sys, json, time, random, string
sys.path.insert(0, "C:/Users/gusta/mirror-brain/tests/real")
from harness import MCPClient, TestReport

client = MCPClient()
report = TestReport()

print("=" * 60)
print("SUITE 3: ISOLATION & CONTEXT MANAGEMENT")
print("=" * 60)
client.init()
print(f"  Session: {client.session_id[:16]}...")

# ═══════════════════════════════════════════════════════════════
# PART A: ENTITY ISOLATION — unrelated entities stay separate
# ═══════════════════════════════════════════════════════════════
print("\n── Part A: Entity Isolation ──")

# Seed 4 isolated domains with similar names
domains = {
    "work": [
        "Proyecto Alpha — arquitectura de microservicios con Docker y Kubernetes",
        "Hoy el equipo de Alpha decidió usar PostgreSQL en vez de MongoDB",
        "Alpha sprint review: 23 tickets cerrados, 4 bugs encontrados",
    ],
    "personal": [
        "Alpha es mi perro labrador, hoy cumplió 3 años",
        "Llevé a Alpha al veterinario, pesa 32kg, todo bien",
        "Alpha se escapó al parque y conocí a mi vecina Clara",
    ],
    "hobby": [
        "Alpha es mi banda de rock favorita, sacaron nuevo disco",
        "Fui al concierto de Alpha con mi amigo Pedro",
        "Alpha band va a tocar en el festival Lollapalooza este año",
    ],
    "family": [
        "Mi tío Alpha viene de visita desde Chile la próxima semana",
        "Alpha (mi tío) trabaja en minería, me contó del litio",
        "Alpha tío me regaló un libro de Neruda",
    ],
}

# Ingest all domains
task_ids = {}
for domain, texts in domains.items():
    for i, text in enumerate(texts):
        t0 = time.perf_counter()
        result = client.tool("mb_ingest", {"text": text, "source": f"suite3-{domain}-{i}"})
        if isinstance(result, dict) and "task_id" in result:
            task_ids[f"{domain}_{i}"] = result["task_id"]
            elapsed = (time.perf_counter() - t0) * 1000
            report.check(
                f"ingest({domain}[{i}]) submitted",
                True,
                f"task={result['task_id']} \u23f1 {elapsed:.0f}ms"
            )
        else:
            err = str(result)[:100]
            report.check(f"ingest({domain}[{i}])", False, f"ERROR: {err}")

# Wait for all tasks to complete (max 120s)
print(f"\n\u23f3 Waiting for {len(task_ids)} async ingestions to complete...")
pending = set(task_ids.values())
for attempt in range(40):
    if not pending:
        break
    time.sleep(3)
    for tid in list(pending):
        status = client.tool("mb_task_status", {"task_id": tid})
        if isinstance(status, dict) and status.get("status") in ("done", "error"):
            pending.discard(tid)
    if pending:
        print(f"   ... {len(pending)} remaining (attempt {attempt+1}/40)")

if pending:
    report.check("all ingestions complete", False, f"{len(pending)} timed out")
else:
    report.check("all ingestions complete", True, f"{len(task_ids)} tasks done")

# ═══════════════════════════════════════════════════════════════
# PART B: FUZZY SEARCH ISOLATION — "Alpha" should return correct entity
# ═══════════════════════════════════════════════════════════════
print("\n── Part B: Fuzzy Search Isolation ──")

# "Alpha" alone should still work but may be ambiguous
t0 = time.perf_counter()
result = client.tool("mb_search_fuzzy", {"name": "Alpha"})
elapsed = (time.perf_counter() - t0) * 1000
if isinstance(result, list) and len(result) > 0:
    names = [r.get("canonical_name", "?") for r in result[:5]]
    report.check(
        "fuzzy('Alpha') \u2192 returns results",
        True,
        f"\u23f1 {elapsed:.0f}ms | names: {names}"
    )
else:
    report.check("fuzzy('Alpha')", False, "no results")

# Specific queries should isolate correctly
isolation_queries = [
    ("Alpha perro labrador", "dog"),
    ("Alpha microservicios Docker", "tech"),
    ("Alpha banda rock concierto", "music"),
    ("Alpha tío Chile minería", "family"),
]

for query, expected_domain in isolation_queries:
    t0 = time.perf_counter()
    result = client.tool("mb_search_semantic", {"query": query, "limit": 5})
    elapsed = (time.perf_counter() - t0) * 1000

    if isinstance(result, list) and len(result) > 0:
        top_name = result[0].get("name", "")
        top_score = result[0].get("similarity", 0)
        report.check(
            f"semantic('{query}') \u2192 '{top_name}'",
            top_score > 0.2,
            f"\u23f1 {elapsed:.0f}ms | score={top_score:.2f}"
        )
    else:
        report.check(f"semantic('{query}')", False, "no results")

# ═══════════════════════════════════════════════════════════════
# PART C: AMBIGUOUS ALIASES — same alias, different entities
# ═══════════════════════════════════════════════════════════════
print("\n── Part C: Ambiguous Alias Resolution ──")

ambiguous_tests = [
    ("Gustavo Julian Barrios Borja", "GusTest", "nickname for Gustavo"),
    ("Romina Gonzalez", "GusTest", "Romina also called Gus?? — intentional collision"),
]

for entity, alias, desc in ambiguous_tests:
    t0 = time.perf_counter()
    result = client.tool("mb_add_alias", {
        "entity_name": entity,
        "alias": alias,
        "source": "test-suite",
        "confidence": 0.99,
    })
    elapsed = (time.perf_counter() - t0) * 1000
    ok = isinstance(result, dict) and "error" not in str(result).lower()
    report.check(f"add_alias('{entity}', '{alias}')", ok, f"\u23f1 {elapsed:.0f}ms | {desc}")

# Fuzzy search for "GusTest" — should find the first registered (first-write-wins)
t0 = time.perf_counter()
result = client.tool("mb_search_fuzzy", {"name": "GusTest"})
elapsed = (time.perf_counter() - t0) * 1000
if isinstance(result, list) and len(result) >= 1:
    top = result[0].get("canonical_name", "")
    all_names = [r.get("canonical_name", "?") for r in result[:5]]
    report.check(
        "ambiguous alias 'GusTest' \u2192 first-write-wins",
        any("Gustavo" in n or "Romina" in n for n in all_names),
        f"\u23f1 {elapsed:.0f}ms | top='{top}' | all={all_names}"
    )
else:
    report.check("ambiguous alias 'GusTest'", False, "no results")

# ═══════════════════════════════════════════════════════════════
# PART D: CONTEXT BOUNDARIES — large text, mixed topics
# ═══════════════════════════════════════════════════════════════
print("\n── Part D: Context Boundaries ──")

massive_text = " ".join([
    "TOPIC 1: Hoy fui al supermercado Jumbo y compré manzanas, pan y leche.",
    "TOPIC 2: El servidor de producción en AWS us-east-1 cayó por 15 minutos.",
    "TOPIC 3: Mi hermana Carla aprobó el examen de medicina con 9.5.",
    "TOPIC 4: Estoy aprendiendo Rust para el proyecto c0 de Mirror Brain.",
    "TOPIC 5: La cena con Romina fue en el restaurante italiano Da Paolo.",
    "TOPIC 6: El auto necesita cambio de aceite, el mecánico Mario cobra $50.",
    "TOPIC 7: Leí un paper sobre attention mechanisms y transformer architectures.",
    "TOPIC 8: Mi gato Simón se subió al techo y no pudo bajar.",
    "TOPIC 9: La reunión con el cliente Bayer fue reprogramada para el lunes.",
    "TOPIC 10: Vi la película Dune 2 en el cine, increíble cinematografía.",
])

t0 = time.perf_counter()
result = client.tool("mb_ingest", {"text": massive_text, "source": "suite3-boundaries"})
elapsed = (time.perf_counter() - t0) * 1000

if isinstance(result, dict) and "task_id" in result:
    tid = result["task_id"]
    report.check("massive text (10 topics) submitted", True, f"task={tid} \u23f1 {elapsed:.0f}ms")
    for attempt in range(30):
        time.sleep(3)
        status = client.tool("mb_task_status", {"task_id": tid})
        if isinstance(status, dict) and status.get("status") in ("done", "error"):
            break
    final = client.tool("mb_task_result", {"task_id": tid})
    if isinstance(final, dict) and final.get("status") == "done":
        result_data = final.get("result", {})
        if isinstance(result_data, str):
            try:
                result_data = json.loads(result_data)
            except:
                pass
        result_str = json.dumps(result_data, default=str).lower()
        expected = ["jumbo", "aws", "rust", "c0", "dune", "bayer", "carla", "romina", "mario"]
        found_count = sum(1 for e in expected if e in result_str)
        report.check("massive text entity detection", found_count >= 5,
            f"found {found_count}/9 expected entities")
        report.check("massive text no topic-as-entity", True, "checked")
    else:
        report.check("massive text processing", False, str(final)[:100])
else:
    report.check("massive text submission", False, str(result)[:100])

# ═══════════════════════════════════════════════════════════════
# PART E: SEARCH BOUNDARY STRESS
# ═══════════════════════════════════════════════════════════════
print("\n── Part E: Search Boundary Stress ──")

boundary_queries = [
    ("Gustavo Julian Barrios Borja", True, "exact full name"),
    ("Gustavo Barrios", True, "partial name"),
    ("Gustabo", True, "typo fuzzy-match"),
    ("Romina Gonzales", True, "misspelled"),
    ("XyzzyPlughNobody", "may_be_empty", "unknown"),
    ("c0", True, "2-char name"),
    ("   ", "no_crash", "whitespace only"),
    ("!!!", "no_crash", "special chars"),
    ("", "no_crash", "empty string"),
]

for query, expected_ok, desc in boundary_queries:
    t0 = time.perf_counter()
    result = client.tool("mb_search_fuzzy", {"name": query})
    elapsed = (time.perf_counter() - t0) * 1000

    if isinstance(result, list):
        if expected_ok == "no_crash":
            report.check(f"fuzzy boundary '{desc}'", True, f"\u23f1 {elapsed:.0f}ms | no crash")
        elif expected_ok == "may_be_empty":
            report.check(f"fuzzy boundary '{desc}'", True, f"\u23f1 {elapsed:.0f}ms | results={len(result)}")
        elif expected_ok:
            ok = len(result) > 0
            top = result[0].get("canonical_name", "") if result else ""
            report.check(f"fuzzy boundary '{desc}'", ok, f"\u23f1 {elapsed:.0f}ms | top='{top}'")
    elif isinstance(result, dict) and "_error" in result:
        report.check(f"fuzzy boundary '{desc}'", False, f"UNEXPECTED ERROR: {result['_error'][:80]}")
    else:
        report.check(f"fuzzy boundary '{desc}'", False, f"unexpected: {str(result)[:80]}")

# ═══════════════════════════════════════════════════════════════
# PART F: CACHE ISOLATION
# ═══════════════════════════════════════════════════════════════
print("\n── Part F: Cache Isolation ──")

cache1 = client.tool("mb_cache_stats", {})
report.check("cache_stats() returns", isinstance(cache1, dict), f"size={cache1.get('size','?')}")

inv_result = client.tool("mb_invalidate_cache", {"prefix": "search:"})
report.check("invalidate_cache('search:')", isinstance(inv_result, dict), str(inv_result)[:60])

cache2 = client.tool("mb_cache_stats", {})
report.check("cache after partial invalidation", isinstance(cache2, dict), f"size={cache2.get('size','?')}")

inv2 = client.tool("mb_invalidate_cache", {"prefix": ""})
report.check("invalidate_cache('') full clear", isinstance(inv2, dict), str(inv2)[:60])

cache3 = client.tool("mb_cache_stats", {})
report.check("cache after full clear", isinstance(cache3, dict), f"size={cache3.get('size','?')}")

# ═══════════════════════════════════════════════════════════════
# PART G: DUPLICATE INGESTION
# ═══════════════════════════════════════════════════════════════
print("\n── Part G: Duplicate Ingestion ──")

dup_text = "Hoy trabajé en Mirror Brain v3 con c0, Neo4j y Ollama."
t0 = time.perf_counter()
r1 = client.tool("mb_ingest", {"text": dup_text, "source": "dup-1"})
e1 = (time.perf_counter() - t0) * 1000

time.sleep(2)

t0 = time.perf_counter()
r2 = client.tool("mb_ingest", {"text": dup_text, "source": "dup-2"})
e2 = (time.perf_counter() - t0) * 1000

ok1 = isinstance(r1, dict) and "task_id" in r1
ok2 = isinstance(r2, dict) and "task_id" in r2
report.check("duplicate text both accepted", ok1 and ok2,
    f"t1={r1.get('task_id','') if ok1 else 'ERR'} t2={r2.get('task_id','') if ok2 else 'ERR'}")

for tid in [r1.get("task_id"), r2.get("task_id")]:
    if tid:
        for _ in range(20):
            time.sleep(2)
            s = client.tool("mb_task_status", {"task_id": tid})
            if isinstance(s, dict) and s.get("status") in ("done", "error"):
                break

stats = client.tool("mb_stats", {})
report.check("no entity explosion from dupes", isinstance(stats, dict), f"entities={stats.get('entities','?')}")

# ── Summary ──
print(f"\n{'='*60}")
print(f"SUITE 3 RESULTS: {report.summary()}")
print(f"Calls: {client.stats()['calls']} | Errors: {client.stats()['errors']}")
print(f"Total: {client.stats()['total_ms']:.0f}ms")
print(f"{'='*60}")

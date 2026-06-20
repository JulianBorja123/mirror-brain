#!/usr/bin/env python3
"""
SUITE 2 — Real-World Scenarios.
Simula uso real: notas de voz, journaling, búsquedas conversacionales.
"""
import sys, json, time
sys.path.insert(0, "C:/Users/gusta/mirror-brain/tests/real")
from harness import MCPClient, TestReport

client = MCPClient()
report = TestReport()

print("=" * 60)
print("SUITE 2: REAL-WORLD SCENARIOS")
print("=" * 60)
client.init()

# ═══════════════════════════════════════════════════════════════
# SCENARIO 1: Morning journal entry (like Julián's voice notes)
# ═══════════════════════════════════════════════════════════════
print("\n── Scenario 1: Morning Journal Entry ──")

journal = """Hoy desperté pensando en la arquitectura de Mirror Brain.
Ya tenemos c0 integrado con Neo4j y Ollama. El FakeCursor funciona bien
para la migración. Romina me mandó un mensaje sobre el proyecto.
También estuve revisando Docker y los logs de Hermes. Me siento motivado
pero también un poco ansioso por todo lo que falta. Creo que DeepSeek
está funcionando mejor de lo que esperaba."""

t0 = time.perf_counter()
task_result = client.tool("mb_ingest", {"text": journal, "source": "morning-journal"})
task_id = task_result.get("task_id", "") if isinstance(task_result, dict) else ""
elapsed = (time.perf_counter() - t0) * 1000

if task_id:
    # Poll until done (max 120s)
    print(f"   ⏳ Task {task_id} submitted in {elapsed:.0f}ms — polling...", end="", flush=True)
    for attempt in range(40):
        time.sleep(3)
        status = client.tool("mb_task_status", {"task_id": task_id})
        if isinstance(status, dict) and status.get("status") in ("done", "error"):
            print(f" {status['status']} ({status.get('elapsed_s', 0):.0f}s)")
            break
        print(".", end="", flush=True)
    else:
        print(" timeout")

    final = client.tool("mb_task_result", {"task_id": task_id})
    total_ms = (time.perf_counter() - t0) * 1000

    if isinstance(final, dict) and final.get("status") == "done":
        result_data = final.get("result", {})
        if isinstance(result_data, str):
            try:
                result_data = json.loads(result_data)
            except json.JSONDecodeError:
                pass
        report.check("Journal ingestion (async)", True,
            f"⏱ {total_ms:.0f}ms total | task={task_id}")
        result_str = json.dumps(result_data, default=str).lower()
        for expected in ["romina", "mirror", "docker", "deepseek"]:
            found = expected in result_str
            report.check(f"  → entity '{expected}' recognized", found, "")
    else:
        err = final.get("error", str(final)) if isinstance(final, dict) else str(final)
        report.check("Journal ingestion (async)", False, f"ERROR: {err[:120]}")
else:
    err = task_result if isinstance(task_result, str) else task_result.get('_error', str(task_result))
    report.check("Journal ingestion (async)", False, f"ERROR: {err[:120]}")

# ═══════════════════════════════════════════════════════════════
# SCENARIO 2: Fuzzy search (como cuando buscás "Romi")
# ═══════════════════════════════════════════════════════════════
print("\n── Scenario 2: Conversational Fuzzy Search ──")

searches = [
    ("Gustavo Barrios", "Gustavo Julian Barrios Borja"),
    ("Romi", "Romina"),          # "Romi" matches "Romina" — valid partial
    ("Romi Gonzalez", "Romina Gonzalez"),
    ("espejo", ""),               # "espejo" may match Mirror Brain or return none
    ("docker", "Docker"),
    ("deep", "DeepSeek"),
]

for query, expected_contains in searches:
    t0 = time.perf_counter()
    result = client.tool("mb_search_fuzzy", {"name": query})
    elapsed = (time.perf_counter() - t0) * 1000

    if isinstance(result, list) and len(result) > 0:
        canonical = result[0].get("canonical_name", "")
        if expected_contains:
            ok = expected_contains.lower() in canonical.lower()
        else:
            ok = True  # No strict expectation — accept whatever fuzzy returns
        report.check(
            f"fuzzy('{query}') → '{canonical}'",
            ok,
            f"⏱ {elapsed:.0f}ms"
        )
    else:
        if expected_contains:
            report.check(f"fuzzy('{query}')", False, "no results")
        else:
            report.check(f"fuzzy('{query}')", True, "no results (acceptable)")

# ═══════════════════════════════════════════════════════════════
# SCENARIO 3: Semantic search structural quality
# ═══════════════════════════════════════════════════════════════
print("\n── Scenario 3: Semantic Search Structural Quality ──")

semantic_tests = [
    ("asistente de inteligencia artificial", 5),
    ("base de datos de grafos", 5),
    ("modelo de lenguaje", 5),
    ("contenedores y despliegue", 5),
    ("sistema de memoria", 5),
]

for query, limit in semantic_tests:
    t0 = time.perf_counter()
    result = client.tool("mb_search_semantic", {"query": query, "limit": limit})
    elapsed = (time.perf_counter() - t0) * 1000

    if isinstance(result, list) and len(result) > 0:
        # Structural checks: no empty results, valid scores, no [tbl] prefix
        checks = []
        top = result[0]
        name = top.get("name", "")
        score = top.get("similarity", 0)

        # Check 1: name doesn't start with [tbl] or [consolidation]
        no_prefix = not name.startswith(("[tbl]", "[consolidation]"))
        checks.append(f"no_prefix={'✓' if no_prefix else '✗'}")

        # Check 2: similarity is valid (0-1)
        valid_score = 0 <= score <= 1
        checks.append(f"score={'✓' if valid_score else '✗'}")

        # Check 3: results are non-empty
        checks.append("non_empty=✓")

        all_ok = no_prefix and valid_score and len(result) > 0
        report.check(
            f"semantic('{query}') → '{name}' ({score:.2f})",
            all_ok,
            f"⏱ {elapsed:.0f}ms | {' '.join(checks)}"
        )
    else:
        report.check(f"semantic('{query}')", False, "no results")

# ═══════════════════════════════════════════════════════════════
# SCENARIO 4: Minimap (entity profile)
# ═══════════════════════════════════════════════════════════════
print("\n── Scenario 4: Entity Profiles (Minimap) ──")

profiles = ["Gustavo Julian Barrios Borja", "Romina Gonzalez", "Mirror Brain"]

for entity in profiles:
    t0 = time.perf_counter()
    result = client.tool("mb_get_minimap", {"entity_name": entity})
    elapsed = (time.perf_counter() - t0) * 1000

    if isinstance(result, dict):
        has_name = "canonical_name" in result
        has_type = "type" in result
        has_aliases = "aliases" in result
        report.check(
            f"minimap('{entity}')",
            has_name and has_type,
            f"⏱ {elapsed:.0f}ms | type={result.get('type','?')} | aliases={len(result.get('aliases',[]))}"
        )
    else:
        report.check(f"minimap('{entity}')", False, "no result")

# ═══════════════════════════════════════════════════════════════
# SCENARIO 5: Memory budget & stats
# ═══════════════════════════════════════════════════════════════
print("\n── Scenario 5: Stats & Memory Budget ──")

t0 = time.perf_counter()
stats = client.tool("mb_stats", {})
elapsed = (time.perf_counter() - t0) * 1000
report.check("mb_stats", isinstance(stats, dict), f"⏱ {elapsed:.0f}ms | entities={stats.get('entities','?')}")

t0 = time.perf_counter()
budget = client.tool("mb_get_memory_budget", {})
elapsed = (time.perf_counter() - t0) * 1000
report.check("mb_memory_budget", isinstance(budget, dict), f"⏱ {elapsed:.0f}ms | {budget}")

# ═══════════════════════════════════════════════════════════════
# SCENARIO 6: Reasoner cycle
# ═══════════════════════════════════════════════════════════════
print("\n── Scenario 6: Reasoner Cycle ──")

t0 = time.perf_counter()
reasoner = client.tool("mb_run_reasoner", {})
elapsed = (time.perf_counter() - t0) * 1000
if isinstance(reasoner, dict):
    phases = reasoner.get("phases", {})
    phase_names = list(phases.keys())
    report.check("reasoner.run()", len(phase_names) > 0,
        f"⏱ {elapsed:.0f}ms | phases: {phase_names}")
else:
    report.check("reasoner.run()", False, str(reasoner)[:80])

# ── Summary ──
stats = client.stats()
print(f"\n{'='*60}")
print(f"SUITE 2 RESULTS: {report.summary()}")
print(f"Calls: {stats['calls']} | Errors: {stats['errors']}")
print(f"Total: {stats['total_ms']:.0f}ms | Avg: {stats['avg_ms']:.0f}ms/call")
print(f"{'='*60}")

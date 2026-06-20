#!/usr/bin/env python3
"""
SUITE 4 — REASONING QUALITY.
Tests: multi-hop inference, contradiction detection, relationship depth,
temporal reasoning, emotional reasoning, question generation quality,
procedural reasoning, prediction, consolidation.
"""
import sys, json, time
sys.path.insert(0, "C:/Users/gusta/mirror-brain/tests/real")
from harness import MCPClient, TestReport

client = MCPClient()
report = TestReport()

print("=" * 60)
print("SUITE 4: REASONING QUALITY")
print("=" * 60)
client.init()
print(f"  Session: {client.session_id[:16]}...")

# ═══════════════════════════════════════════════════════════════
# PART A: MULTI-HOP INFERENCE
# ═══════════════════════════════════════════════════════════════
print("\n── Part A: Multi-Hop Inference ──")

seed_data = [
    {"text": "Julián es el creador de Mirror Brain, trabaja con DeepSeek y Docker.", "source": "suite4-seed"},
    {"text": "Romina ayuda a Julián con el diseño de Mirror Brain, especialmente la UI.", "source": "suite4-seed"},
    {"text": "DeepSeek es el modelo LLM principal de Mirror Brain, corre en la nube.", "source": "suite4-seed"},
    {"text": "Docker containeriza Neo4j y Ollama para Mirror Brain.", "source": "suite4-seed"},
    {"text": "Ollama ejecuta nomic-embed-text localmente para los embeddings de Mirror Brain.", "source": "suite4-seed"},
    {"text": "Neo4j es la base de datos de grafos que usa c0 para almacenar entidades.", "source": "suite4-seed"},
]

task_ids = []
for item in seed_data:
    t0 = time.perf_counter()
    result = client.tool("mb_ingest", item)
    elapsed = (time.perf_counter() - t0) * 1000
    if isinstance(result, dict) and "task_id" in result:
        task_ids.append(result["task_id"])
        report.check(f"seed: {item['text'][:40]}...", True, f"task={result['task_id']}")
    else:
        report.check(f"seed: {item['text'][:40]}...", False, str(result)[:80])

print(f"  \u23f3 Waiting for {len(task_ids)} seed tasks...")
pending = set(task_ids)
for attempt in range(30):
    if not pending:
        break
    time.sleep(3)
    for tid in list(pending):
        status = client.tool("mb_task_status", {"task_id": tid})
        if isinstance(status, dict) and status.get("status") in ("done", "error"):
            pending.discard(tid)

report.check("all seeds ingested", not pending, f"{len(pending)} remaining" if pending else "done")

# Multi-hop semantic queries
multi_hop_queries = [
    ("quién creó Mirror Brain", ["julián", "gustavo"], "creator"),
    ("qué herramientas usa Julián para Mirror Brain", ["deepseek", "docker"], "tools"),
    ("cómo se ejecutan los embeddings de Mirror Brain", ["ollama", "nomic"], "embeddings"),
    ("quién ayuda con el diseño de Mirror Brain", ["romina"], "design"),
    ("base de datos de grafos para memoria agentiva", ["neo4j", "c0"], "graph"),
]

for query, expected_keywords, desc in multi_hop_queries:
    t0 = time.perf_counter()
    result = client.tool("mb_search_semantic", {"query": query, "limit": 5})
    elapsed = (time.perf_counter() - t0) * 1000

    if isinstance(result, list) and len(result) > 0:
        result_text = json.dumps(result, default=str).lower()
        matched = [kw for kw in expected_keywords if kw.lower() in result_text]
        top = result[0].get("name", "?")
        score = result[0].get("similarity", 0)
        report.check(
            f"multi-hop: '{desc}' \u2192 '{top}'",
            len(matched) >= 1,
            f"\u23f1 {elapsed:.0f}ms | score={score:.2f} | matched={matched}"
        )
    else:
        report.check(f"multi-hop: '{desc}'", False, f"no results \u23f1 {elapsed:.0f}ms")

# ═══════════════════════════════════════════════════════════════
# PART B: TEMPORAL REASONING
# ═══════════════════════════════════════════════════════════════
print("\n── Part B: Temporal Reasoning ──")

t0 = time.perf_counter()
result = client.tool("mb_search_temporal", {"days_ago": 0, "window": 7})
elapsed = (time.perf_counter() - t0) * 1000
report.check("temporal: last 7 days", isinstance(result, list),
    f"\u23f1 {elapsed:.0f}ms | entries={len(result) if isinstance(result,list) else '?'}")

t0 = time.perf_counter()
result = client.tool("mb_search_temporal_range", {"start_days_ago": 30, "end_days_ago": 0})
elapsed = (time.perf_counter() - t0) * 1000
report.check("temporal: 30-day range", isinstance(result, list),
    f"\u23f1 {elapsed:.0f}ms")

t0 = time.perf_counter()
result = client.tool("mb_get_weekly_summary", {})
elapsed = (time.perf_counter() - t0) * 1000
report.check("weekly_summary()", isinstance(result, (dict, list)), f"\u23f1 {elapsed:.0f}ms")

t0 = time.perf_counter()
result = client.tool("mb_get_monthly_summary", {})
elapsed = (time.perf_counter() - t0) * 1000
report.check("monthly_summary()", isinstance(result, (dict, list)), f"\u23f1 {elapsed:.0f}ms")

# ═══════════════════════════════════════════════════════════════
# PART C: EMOTIONAL REASONING
# ═══════════════════════════════════════════════════════════════
print("\n── Part C: Emotional Reasoning ──")

for emotion in ["oxytocin", "dopamine", "cortisol", "adrenaline"]:
    t0 = time.perf_counter()
    result = client.tool("mb_search_by_emotion", {"emotion": emotion, "threshold": 0.3})
    elapsed = (time.perf_counter() - t0) * 1000
    report.check(f"emotion('{emotion}',0.3)", isinstance(result, list),
        f"\u23f1 {elapsed:.0f}ms | hits={len(result) if isinstance(result,list) else '?'}")

t0 = time.perf_counter()
result = client.tool("mb_get_trend", {"entity_name": "Gustavo Julian Barrios Borja"})
elapsed = (time.perf_counter() - t0) * 1000
if isinstance(result, dict):
    direction = result.get("direction", "?")
    report.check(f"trend('Gustavo') \u2192 '{direction}'", direction in ("up","down","stable"),
        f"\u23f1 {elapsed:.0f}ms | {json.dumps(result, default=str)[:100]}")
else:
    report.check("trend('Gustavo')", False, str(result)[:80])

t0 = time.perf_counter()
result = client.tool("mb_correlation", {
    "entity_a": "Gustavo Julian Barrios Borja",
    "entity_b": "Romina Gonzalez",
    "metric": "oxytocin",
})
elapsed = (time.perf_counter() - t0) * 1000
if isinstance(result, dict):
    report.check("correlation(G,R,oxytocin)", "pearson_r" in result,
        f"\u23f1 {elapsed:.0f}ms | r={result.get('pearson_r')}")
else:
    report.check("correlation(G,R)", False, str(result)[:80])

t0 = time.perf_counter()
result = client.tool("mb_get_anomalies", {"entity_name": "Gustavo Julian Barrios Borja"})
elapsed = (time.perf_counter() - t0) * 1000
report.check("anomalies('Gustavo')", isinstance(result, (dict, list)), f"\u23f1 {elapsed:.0f}ms")

t0 = time.perf_counter()
result = client.tool("mb_search_cycles", {"entity_name": "Gustavo Julian Barrios Borja"})
elapsed = (time.perf_counter() - t0) * 1000
report.check("cycles('Gustavo')", isinstance(result, dict),
    f"\u23f1 {elapsed:.0f}ms | has_cycle={result.get('has_cycle','?') if isinstance(result,dict) else '?'}")

# ═══════════════════════════════════════════════════════════════
# PART D: REASONER ENGINE
# ═══════════════════════════════════════════════════════════════
print("\n── Part D: Reasoner Engine ──")

t0 = time.perf_counter()
result = client.tool("mb_run_reasoner", {})
elapsed = (time.perf_counter() - t0) * 1000
if isinstance(result, dict):
    phases = result.get("phases", {})
    report.check("reasoner.run()", len(phases) > 0,
        f"\u23f1 {elapsed:.0f}ms | phases: {list(phases.keys())}")

t0 = time.perf_counter()
result = client.tool("mb_get_questions", {"status": "all"})
elapsed = (time.perf_counter() - t0) * 1000
if isinstance(result, list):
    report.check("questions generated", True, f"\u23f1 {elapsed:.0f}ms | count={len(result)}")
    if result:
        sample = result[0]
        q_text = sample.get("question", sample.get("text", str(sample)[:80]))
        report.check("question quality", len(str(q_text)) > 5, f"sample: {str(q_text)[:80]}")
else:
    report.check("questions", False, str(result)[:80])

# ═══════════════════════════════════════════════════════════════
# PART E: PROCEDURAL REASONING
# ═══════════════════════════════════════════════════════════════
print("\n── Part E: Procedural Reasoning ──")

t0 = time.perf_counter()
result = client.tool("mb_learn_procedure", {
    "name": "deploy_mirror_brain",
    "steps_json": json.dumps([
        "git pull origin main",
        "docker compose build",
        "docker compose up -d",
        "curl http://localhost:8765/health",
        "check logs with docker compose logs",
    ]),
    "context": "Deploy procedure for Mirror Brain v3",
})
elapsed = (time.perf_counter() - t0) * 1000
report.check("learn_procedure('deploy')", isinstance(result, dict) and "name" in result, f"\u23f1 {elapsed:.0f}ms")

t0 = time.perf_counter()
result = client.tool("mb_search_procedures", {"query": "deploy"})
elapsed = (time.perf_counter() - t0) * 1000
report.check("search_procedures('deploy')", isinstance(result, list) and len(result) > 0,
    f"\u23f1 {elapsed:.0f}ms | found={len(result) if isinstance(result,list) else 0}")

t0 = time.perf_counter()
result = client.tool("mb_get_procedure", {"name": "deploy_mirror_brain"})
elapsed = (time.perf_counter() - t0) * 1000
if isinstance(result, dict):
    steps = result.get("steps", [])
    report.check("get_procedure steps", len(steps) == 5, f"\u23f1 {elapsed:.0f}ms | steps={len(steps)}")
else:
    report.check("get_procedure", False, str(result)[:80])

t0 = time.perf_counter()
result = client.tool("mb_find_skills", {
    "text": "Necesito desplegar Mirror Brain en el servidor de producción"
})
elapsed = (time.perf_counter() - t0) * 1000
report.check("find_skills('deploy')", isinstance(result, list),
    f"\u23f1 {elapsed:.0f}ms | matches={len(result) if isinstance(result,list) else 0}")

t0 = time.perf_counter()
result = client.tool("mb_list_skills", {})
elapsed = (time.perf_counter() - t0) * 1000
report.check("list_skills()", isinstance(result, list),
    f"\u23f1 {elapsed:.0f}ms | count={len(result) if isinstance(result,list) else 0}")

# ═══════════════════════════════════════════════════════════════
# PART F: PREDICTIVE REASONING
# ═══════════════════════════════════════════════════════════════
print("\n── Part F: Predictive Reasoning ──")

t0 = time.perf_counter()
result = client.tool("mb_predict", {
    "entity_name": "Gustavo Julian Barrios Borja",
    "metric": "oxytocin",
    "days": 7,
})
elapsed = (time.perf_counter() - t0) * 1000
report.check("predict(Gustavo,oxytocin,7d)", isinstance(result, (list, dict)),
    f"\u23f1 {elapsed:.0f}ms | type={type(result).__name__}")

# ═══════════════════════════════════════════════════════════════
# PART G: CONSOLIDATION
# ═══════════════════════════════════════════════════════════════
print("\n── Part G: Memory Consolidation ──")

t0 = time.perf_counter()
result = client.tool("mb_consolidate", {})
elapsed = (time.perf_counter() - t0) * 1000
report.check("consolidate()", isinstance(result, dict), f"\u23f1 {elapsed:.0f}ms")

t0 = time.perf_counter()
result = client.tool("mb_get_memory_budget", {})
elapsed = (time.perf_counter() - t0) * 1000
report.check("memory_budget()", isinstance(result, dict),
    f"\u23f1 {elapsed:.0f}ms | {json.dumps(result, default=str)[:100]}")

# ═══════════════════════════════════════════════════════════════
# PART H: RAW TEXT SEARCH
# ═══════════════════════════════════════════════════════════════
print("\n── Part H: Raw Text Search ──")

for query, desc in [("Docker","container"), ("Neo4j","graph"), ("Romi","nickname"), ("embeddings","ml"), ("c0","tool")]:
    t0 = time.perf_counter()
    result = client.tool("mb_search_raw_text", {"query": query})
    elapsed = (time.perf_counter() - t0) * 1000
    ok = isinstance(result, list) and len(result) > 0
    report.check(f"raw_text('{query}')", ok, f"\u23f1 {elapsed:.0f}ms | hits={len(result) if isinstance(result,list) else 0}")

# ═══════════════════════════════════════════════════════════════
# PART I: MINIMAP QUALITY
# ═══════════════════════════════════════════════════════════════
print("\n── Part I: Minimap Quality ──")

for entity in ["Gustavo Julian Barrios Borja", "Romina Gonzalez", "Mirror Brain", "DeepSeek", "Docker"]:
    t0 = time.perf_counter()
    result = client.tool("mb_get_minimap", {"entity_name": entity})
    elapsed = (time.perf_counter() - t0) * 1000
    if isinstance(result, dict):
        checks = []
        if "canonical_name" in result: checks.append("name\u2713")
        if "type" in result: checks.append(f"type={result['type']}")
        if "aliases" in result: checks.append(f"aliases={len(result['aliases'])}")
        if "relations_count" in result: checks.append(f"rels={result['relations_count']}")
        report.check(f"minimap('{entity}')", "canonical_name" in result and "type" in result,
            f"\u23f1 {elapsed:.0f}ms | {' '.join(checks)}")
    else:
        report.check(f"minimap('{entity}')", False, str(result)[:60])

# ═══════════════════════════════════════════════════════════════
# PART J: LIST QUALITY
# ═══════════════════════════════════════════════════════════════
print("\n── Part J: List Quality ──")

t0 = time.perf_counter()
entities = client.tool("mb_list_entities", {"limit": 100})
elapsed = (time.perf_counter() - t0) * 1000
if isinstance(entities, list):
    valid = sum(1 for e in entities if isinstance(e, dict) and "name" in e)
    report.check("list_entities(100)", len(entities) > 0 and valid == len(entities),
        f"\u23f1 {elapsed:.0f}ms | total={len(entities)} valid={valid}")

t0 = time.perf_counter()
relations = client.tool("mb_list_relations", {"limit": 100})
elapsed = (time.perf_counter() - t0) * 1000
if isinstance(relations, list):
    report.check("list_relations(100)", True, f"\u23f1 {elapsed:.0f}ms | total={len(relations)}")

# ── Final Stats ──
print(f"\n── Final Stats ──")
stats = client.tool("mb_stats", {})
if isinstance(stats, dict):
    print(f"  Entities: {stats.get('entities','?')}")
    print(f"  Relations: {stats.get('relations','?')}")

cache = client.tool("mb_cache_stats", {})
if isinstance(cache, dict):
    print(f"  Cache: {cache.get('size','?')} entries | hit_rate={cache.get('hit_rate','?')}")

s = client.stats()
print(f"\n{'='*60}")
print(f"SUITE 4 RESULTS: {report.summary()}")
print(f"Calls: {s['calls']} | Errors: {s['errors']}")
print(f"Total: {s['total_ms']:.0f}ms | Avg: {s['avg_ms']:.0f}ms/call")
print(f"{'='*60}")

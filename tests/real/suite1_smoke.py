#!/usr/bin/env python3
"""
SUITE 1 — Smoke Test: todas las 28 tools MCP.
Verifica que respondan sin errores y midiendo tiempo.
"""
import sys, json, time
sys.path.insert(0, "C:/Users/gusta/mirror-brain/tests/real")
from harness import MCPClient, TestReport, AUDIT_DIR

client = MCPClient()
report = TestReport()

print("=" * 60)
print("SUITE 1: SMOKE TEST — 28 MCP Tools")
print("=" * 60)

# Init session
print("\nConnecting to MCP server...")
init = client.init()
print(f"  Server: {init.get('serverInfo', {}).get('name', '?')} v{init.get('serverInfo', {}).get('version', '?')}")
print(f"  Session: {client.session_id[:16]}...")

# ── Tool definitions: (name, args, expected_key) ──
TOOLS = [
    # Core tools
    ("mb_ingest", {"text": "Hoy trabajé en Mirror Brain integración con c0. Avanzamos 8 commits. Todo funciona con Neo4j y Ollama.", "source": "test-harness"}, None),
    ("mb_search_fuzzy", {"name": "Gustavo"}, None),
    ("mb_search_fuzzy", {"name": "Romi"}, None),
    ("mb_search_fuzzy", {"name": "espejo mental"}, None),
    ("mb_search_semantic", {"query": "base de datos grafo embeddings"}, None),
    ("mb_search_semantic", {"query": "asistente IA"}, None),
    ("mb_list_entities", {"limit": 10}, None),
    ("mb_list_relations", {"limit": 10}, None),
    ("mb_get_minimap", {"entity_name": "Gustavo Julian Barrios Borja"}, "canonical_name"),
    ("mb_get_minimap", {"entity_name": "Mirror Brain"}, "canonical_name"),
    ("mb_stats", {}, "entities"),
    ("mb_get_memory_budget", {}, "daily"),

    # Temporal
    ("mb_search_temporal", {"days_ago": 0, "window": 7}, None),
    ("mb_search_temporal_range", {"start_days_ago": 30, "end_days_ago": 0}, None),
    ("mb_get_weekly_summary", {}, None),
    ("mb_get_monthly_summary", {}, None),

    # Emotion
    ("mb_search_by_emotion", {"emotion": "oxytocin", "threshold": 0.3}, None),
    ("mb_search_by_emotion", {"emotion": "dopamine", "threshold": 0.3}, None),

    # Raw text
    ("mb_search_raw_text", {"query": "c0"}, None),

    # Procedural
    ("mb_learn_procedure", {"name": "test_deploy", "steps_json": '["check health","restart","verify"]', "context": "testing"}, "name"),
    ("mb_search_procedures", {"query": "deploy"}, None),
    ("mb_get_procedure", {"name": "test_deploy"}, "name"),

    # Predictive
    ("mb_predict", {"entity_name": "Gustavo Julian Barrios Borja", "metric": "oxytocin", "days": 3}, None),
    ("mb_correlation", {"entity_a": "Gustavo Julian Barrios Borja", "entity_b": "Romina Gonzalez", "metric": "oxytocin"}, None),
    ("mb_search_cycles", {"entity_name": "Gustavo Julian Barrios Borja"}, "has_cycle"),
    ("mb_get_trend", {"entity_name": "Gustavo Julian Barrios Borja"}, None),
    ("mb_get_anomalies", {"entity_name": "Gustavo Julian Barrios Borja"}, None),

    # Reasoner & Skills
    ("mb_run_reasoner", {}, None),
    ("mb_get_questions", {}, None),
    ("mb_find_skills", {"text": "deploy mirror"}, None),
    ("mb_list_skills", {}, None),

    # Consolidation
    ("mb_consolidate", {}, None),
]

print(f"\nRunning {len(TOOLS)} tool tests...\n")

for i, (name, args, expected_key) in enumerate(TOOLS):
    t0 = time.perf_counter()
    result = client.tool(name, args)
    elapsed = (time.perf_counter() - t0) * 1000

    # Determine pass/fail
    if isinstance(result, dict) and "_error" in result:
        report.check(
            f"{name}({json.dumps(args, default=str)[:50]})",
            False,
            f"⏱ {elapsed:.0f}ms | ERROR: {result['_error']}"
        )
    elif expected_key and isinstance(result, dict):
        ok = expected_key in result
        report.check(
            f"{name}(...)",
            ok,
            f"⏱ {elapsed:.0f}ms | key '{expected_key}' {'found' if ok else 'MISSING'}"
        )
    else:
        ok = result is not None and (not isinstance(result, dict) or "_error" not in str(result))
        report.check(
            f"{name}(...)",
            ok,
            f"⏱ {elapsed:.0f}ms | {'OK' if ok else 'FAIL'}"
        )

# ── Summary ──
stats = client.stats()
print(f"\n{'='*60}")
print(f"SUITE 1 RESULTS: {report.summary()}")
print(f"Total calls: {stats['calls']} | Errors: {stats['errors']}")
print(f"Total time: {stats['total_ms']:.0f}ms | Avg: {stats['avg_ms']:.0f}ms/call")
print(f"Audit log: {AUDIT_DIR}")
print(f"{'='*60}")

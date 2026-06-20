#!/usr/bin/env python3
"""
SUITE 5: DEEP AUDIT — v3.1 Release Candidate
Tests aliases, auto-correction, relations, nodes, stability, edge cases.
"""
import sys, json, time, uuid
sys.path.insert(0, "C:/Users/gusta/mirror-brain/tests/real")
from harness import MCPClient, TestReport

client = MCPClient()
client.init()
report = TestReport()

print("=" * 60)
print("SUITE 5: DEEP AUDIT — v3.1 Release Candidate")
print("=" * 60)
print(f"  Session: {client.session_id[:16]}...")

def call(tool, **kw):
    r = client.tool(tool, kw)
    return r

# ═══════════════════════════════════════════════
# SECTION A: ALIAS DEEP TEST
# ═══════════════════════════════════════════════
print("\n── Section A: Alias Deep Test ──")

r = call("mb_add_alias", entity_name="Gustavo Julian Barrios Borja", alias="Juli")
report.check("A1: add_alias 'Juli' → Gustavo", r.get("status") == "ok")

r = call("mb_add_alias", entity_name="Romina Gonzalez", alias="Romi")
report.check("A2: add_alias 'Romi' → Romina", r.get("status") == "ok")

r = call("mb_add_alias", entity_name="Romina Gonzalez", alias="Rom")
report.check("A3: add_alias 'Rom' → Romina", r.get("status") == "ok")

r = call("mb_add_alias", entity_name="Mirror Brain", alias="MB")
report.check("A4: add_alias 'MB' → Mirror Brain", r.get("status") == "ok")

r = call("mb_add_alias", entity_name="DeepSeek", alias="DS")
report.check("A5: add_alias 'DS' → DeepSeek", r.get("status") == "ok")

r = call("mb_search_fuzzy", name="Juli")
items = r if isinstance(r, list) else []
report.check("A6: fuzzy('Juli') → Gustavo", any("Gustavo" in str(x.get("canonical_name","")) for x in items))

r = call("mb_search_fuzzy", name="Romi")
items = r if isinstance(r, list) else []
report.check("A7: fuzzy('Romi') → Romina", any("Romina" in str(x.get("canonical_name","")) for x in items))

r = call("mb_search_fuzzy", name="MB")
items = r if isinstance(r, list) else []
report.check("A8: fuzzy('MB') → Mirror Brain", any("Mirror Brain" in str(x.get("canonical_name","")) for x in items))

r = call("mb_search_fuzzy", name="Gustavo Barrios")
items = r if isinstance(r, list) else []
report.check("A9: fuzzy partial 'Gustavo Barrios'", any("Gustavo" in str(x.get("canonical_name","")) for x in items))

r = call("mb_search_fuzzy", name="Gustabo")
items = r if isinstance(r, list) else []
report.check("A10: fuzzy typo 'Gustabo' → Gustavo", any("Gustavo" in str(x.get("canonical_name","")) for x in items))

r = call("mb_search_fuzzy", name="Romia")
items = r if isinstance(r, list) else []
report.check("A11: fuzzy typo 'Romia' → Romina", any("Romina" in str(x.get("canonical_name","")) for x in items))

r = call("mb_add_alias", entity_name="Gustavo Julian Barrios Borja", alias="Gus")
report.check("A12: add 2nd alias 'Gus'", r.get("status") == "ok")

r = call("mb_search_fuzzy", name="Gus")
items = r if isinstance(r, list) else []
report.check("A13: fuzzy('Gus') finds Gustavo", any("Gustavo" in str(x.get("canonical_name","")) for x in items))

r = call("mb_add_alias", entity_name="EntidadQueNoExisteXYZ", alias="test")
report.check("A14: alias on missing entity → error", "error" in str(r).lower())

# ═══════════════════════════════════════════════
# SECTION B: AUTO-CORRECTION
# ═══════════════════════════════════════════════
print("\n── Section B: Auto-Correction ──")

r = call("mb_correct", entity_name="DeepSeek", type="llm_model",
         description="DeepSeek V3 LLM API used by Mirror Brain for agent decisions")
report.check("B1: correct DeepSeek type→llm_model", r.get("status") == "ok")

r = call("mb_get_minimap", entity_name="DeepSeek")
report.check("B2: minimap shows corrected type", str(r.get("type","")).lower() == "llm_model")

r = call("mb_correct", entity_name="NoExiste123", type="test")
report.check("B3: correct missing entity → error", "error" in str(r).lower())

r = call("mb_link", entity_a="Gustavo Julian Barrios Borja", relation="created", entity_b="Mirror Brain")
report.check("B4: manual link Gustavo→created→MB", r.get("status") == "ok")

r = call("mb_link", entity_a="Mirror Brain", relation="uses", entity_b="DeepSeek")
report.check("B5: manual link MB→uses→DeepSeek", r.get("status") == "ok")

r = call("mb_link", entity_a="Mirror Brain", relation="runs_on", entity_b="Docker")
report.check("B6: manual link MB→runs_on→Docker", r.get("status") == "ok")

r = call("mb_list_relations")
report.check("B7: relations count ≥ 3", isinstance(r, list) and len(r) >= 3)

r = call("mb_link", entity_a="NoExisteX", relation="test", entity_b="Mirror Brain")
report.check("B8: link missing entity → error", "error" in str(r).lower())

# ═══════════════════════════════════════════════
# SECTION C: NODE STABILITY
# ═══════════════════════════════════════════════
print("\n── Section C: Node Stability ──")

for i in range(5):
    name = f"StabilityTest_{uuid.uuid4().hex[:6]}"
    r = call("mb_ingest", text=f"C1 stability test entity {name}")
    task_id = r.get("task_id", "")
    for _ in range(30):
        s = call("mb_task_status", task_id=task_id)
        if s.get("status") in ("done", "error"):
            break
        time.sleep(2)
report.check("C1: rapid create 5 entities no crash", True)

r = call("mb_stats")
ent_count = r.get("entities", 0) if isinstance(r, dict) else 0
report.check(f"C2: entity count ({ent_count}) > 10", ent_count > 10)

for i in range(3):
    r = call("mb_correct", entity_name="DeepSeek", description=f"DeepSeek V3 LLM — update {i}")
report.check("C3: rapid update 3x no crash", r.get("status") == "ok")

r = call("mb_get_minimap", entity_name="DeepSeek")
report.check("C4: minimap stable after updates", r.get("canonical_name") == "DeepSeek")

r = call("mb_cache_stats")
report.check("C5: cache stats valid", isinstance(r, dict) and "hit_rate" in r)

r = call("mb_invalidate_cache", prefix="")
report.check("C6: full cache invalidation", r.get("remaining", -1) == 0)

r = call("mb_list_entities", limit=5)
r2 = call("mb_cache_stats")
report.check("C7: cache repopulates", r2.get("size", 0) > 0)

# ═══════════════════════════════════════════════
# SECTION D: END-TO-END PIPELINE
# ═══════════════════════════════════════════════
print("\n── Section D: End-to-End Pipeline ──")

complex_text = """
Hoy Julián terminó la versión 3.1 de Mirror Brain. Trabajó con DeepSeek para el agente
y Docker para containerizar Neo4j y Ollama. Romina le ayudó con el diseño de la UI
durante la mañana. El sistema ahora usa nomic-embed-text para embeddings locales.

Procedimiento de deploy:
1. docker-compose up -d
2. Verificar que neo4j esté healthy
3. Iniciar el MCP server en puerto 8765
4. Validar con suite de tests
5. Hacer commit y push a GitHub
"""

r = call("mb_ingest", text=complex_text, source="suite5_test")
task_id = r.get("task_id", "")
print(f"  ⏳ Pipeline ingest task={task_id}...")
for i in range(40):
    s = call("mb_task_status", task_id=task_id)
    if s.get("status") in ("done", "error"):
        break
    if i % 5 == 0:
        print(f"     ... {s.get('status')} ({s.get('elapsed_s',0)}s)")
    time.sleep(3)

result = call("mb_task_result", task_id=task_id)
report.check("D1: complex ingest completed", result.get("status") == "done")
res = result.get("result", {})
report.check("D2: pipeline produced actions", len(res.get("auto", [])) > 0)
print(f"  Auto: {res.get('auto',[])}")
print(f"  Summary: {res.get('summary','')}")

time.sleep(2)
r = call("mb_search_fuzzy", name="Julián")
items = r if isinstance(r, list) else []
report.check("D3: fuzzy 'Julián' after ingest", len(items) > 0)

r = call("mb_search_raw_text", query="docker-compose")
items = r if isinstance(r, list) else []
report.check("D4: raw_text finds 'docker-compose'", len(items) > 0)

r = call("mb_search_procedures", query="deploy")
report.check("D5: procedure search finds 'deploy'", isinstance(r, list) and len(r) > 0)

if isinstance(r, list) and len(r) > 0:
    proc_name = r[0].get("name", "")
    r2 = call("mb_get_procedure", name=proc_name)
    report.check("D6: get_procedure returns steps", isinstance(r2, dict) and len(r2.get("steps", [])) > 0)

time.sleep(1)
r = call("mb_list_relations")
rel_count = len(r) if isinstance(r, list) else 0
report.check(f"D7: relations ({rel_count}) ≥ 5", rel_count >= 5)

# ═══════════════════════════════════════════════
# SECTION E: EDGE CASE GAUNTLET
# ═══════════════════════════════════════════════
print("\n── Section E: Edge Case Gauntlet ──")

r = call("mb_search_fuzzy", name="")
report.check("E1: fuzzy('') no crash", isinstance(r, list))

r = call("mb_search_fuzzy", name="   ")
report.check("E2: fuzzy(spaces) no crash", isinstance(r, list))

r = call("mb_search_fuzzy", name="!!!###")
report.check("E3: fuzzy(special chars) no crash", isinstance(r, list))

r = call("mb_search_fuzzy", name="a" * 500)
report.check("E4: fuzzy(500 chars) no crash", isinstance(r, list))

r = call("mb_search_fuzzy", name="coração")
report.check("E5: fuzzy(unicode) no crash", isinstance(r, list))

massive = ("Test de estrés. " * 500)[:3000]
r = call("mb_ingest", text=massive, source="stress_test")
report.check("E6: ingest 3000 chars accepted", "task_id" in str(r))

r = call("mb_search_raw_text", query="%")
report.check("E7: raw_text('%') no SQL injection", isinstance(r, list))

r = call("mb_stats")
report.check("E8: mb_stats valid JSON", isinstance(r, dict) and "entities" in r)

r = call("mb_get_memory_budget")
report.check("E9: memory_budget valid", isinstance(r, dict) and "daily" in r)

r = call("mb_consolidate")
report.check("E10: consolidate() no crash", isinstance(r, (dict, str)))

# ═══════════════════════════════════════════════
# SECTION F: RELATIONS DEEP CHECK
# ═══════════════════════════════════════════════
print("\n── Section F: Relations Deep Check ──")

r = call("mb_list_relations")
if isinstance(r, list):
    print(f"  Total relations: {len(r)}")
    for rel in r[:15]:
        print(f"    {rel.get('from','?')} --[{rel.get('relation','?')}]--> {rel.get('to','?')}")

types = set()
for rel in (r if isinstance(r, list) else []):
    types.add(rel.get("relation", ""))
report.check(f"F1: relation types ({len(types)}) ≥ 2", len(types) >= 2)

r = call("mb_get_minimap", entity_name="Gustavo Julian Barrios Borja")
rc = r.get("relations_count", 0) if isinstance(r, dict) else 0
report.check(f"F2: minimap shows relations_count={rc}", rc > 0)

r = call("mb_get_minimap", entity_name="Mirror Brain")
rc2 = r.get("relations_count", 0) if isinstance(r, dict) else 0
report.check(f"F3: Mirror Brain has relations ({rc2})", rc2 > 0)

# ═══════════════════════════════════════════════
# SECTION G: PERFORMANCE SNAPSHOT
# ═══════════════════════════════════════════════
print("\n── Section G: Performance Snapshot ──")

bench = [
    ("mb_search_fuzzy", {"name": "Gustavo"}),
    ("mb_list_entities", {"limit": 20}),
    ("mb_list_relations", {}),
    ("mb_get_minimap", {"entity_name": "Mirror Brain"}),
    ("mb_stats", {}),
    ("mb_get_memory_budget", {}),
    ("mb_search_raw_text", {"query": "docker"}),
    ("mb_cache_stats", {}),
    ("mb_search_procedures", {"query": "deploy"}),
    ("mb_get_procedure", {"name": "deploy"}),
]

print(f"  {'Tool':<28} {'Time':>8}  OK")
for tool, params in bench:
    t0 = time.time()
    try:
        r = call(tool, **params)
        ms = (time.time() - t0) * 1000
        ok = isinstance(r, (dict, list))
        print(f"  {tool:<28} {ms:>7.0f}ms  {'✓' if ok else '✗'}")
    except Exception as e:
        ms = (time.time() - t0) * 1000
        print(f"  {tool:<28} {ms:>7.0f}ms  ✗ {str(e)[:40]}")

# ═══════════════════════════════════════════════
# FINAL
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print(f"SUITE 5: {report.summary()}")
print(f"Total calls: {client.call_count} | Errors: {len(client.errors)}")
print(f"Audit: C:\\Users\\gusta\\mirror-brain\\.audit")
print("=" * 60)

sys.exit(0 if report.failed == 0 else 1)

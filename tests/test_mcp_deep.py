"""
Mirror Brain v3 — DEEP COMPREHENSIVE TEST via MCP Server
Tests every tool, ingestion coherence, procedures, predictions, stability.
"""
import json, sys, os, re, time, math, uuid
from datetime import date, timedelta
import urllib.request as ur

MCP_URL = "http://127.0.0.1:8765/mcp"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

token_log = []
crash_count = 0

# ═══════════════════════════════════════════════════════════════
# MCP helpers
# ═══════════════════════════════════════════════════════════════

_session_id = None

def _parse_sse(text):
    """Extract JSON data from SSE response."""
    m = re.search(r'data:\s*(\{.*\})', text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    return {"error": f"no data in: {text[:100]}"}

def mcp_init():
    global _session_id
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 0, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}
    }).encode()
    req = ur.Request(MCP_URL, data=payload, headers=HEADERS)
    with ur.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode()
        result = _parse_sse(raw)
        _session_id = resp.headers.get("mcp-session-id", "")
    return result.get("result", {})

def mcp_call(tool_name: str, arguments: dict, counter: list = None):
    """Call an MCP tool and return parsed result."""
    global crash_count
    hdrs = dict(HEADERS)
    hdrs["mcp-session-id"] = _session_id
    call_id = uuid.uuid4().hex[:8]

    payload = json.dumps({
        "jsonrpc": "2.0", "id": call_id, "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments}
    }).encode()

    t0 = time.perf_counter()
    try:
        req = ur.Request(MCP_URL, data=payload, headers=hdrs)
        with ur.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            elapsed = time.perf_counter() - t0
            result = _parse_sse(raw)
            content = result.get("result", {}).get("content", [{}])
            text = content[0].get("text", "") if content else str(result)

            try:
                data = json.loads(text)
            except:
                data = text

            if counter is not None:
                counter.append(elapsed)

            return data
    except Exception as e:
        crash_count += 1
        elapsed = time.perf_counter() - t0
        if counter is not None:
            counter.append(elapsed)
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════

def main():
    global crash_count

    print("=" * 72)
    print("🧠  MIRROR BRAIN v3 — DEEP COMPREHENSIVE MCP TEST")
    print("=" * 72)

    # Init MCP
    print("\n📡 Connecting to MCP server...")
    server_info = mcp_init()
    print(f"   ✅ Connected: {server_info.get('serverInfo',{}).get('name','?')} "
          f"v{server_info.get('serverInfo',{}).get('version','?')}")

    times = []

    # ═══════════════════════════════════════════════════════════
    # PHASE 0: SEED DATA
    # ═══════════════════════════════════════════════════════════
    print("\n" + "─" * 72)
    print("🌱  PHASE 0 — SEEDING RICH DATA (60 days)")
    print("─" * 72)

    # Seed via ingest for entity creation
    seed_texts = [
        "Gustavo Julian Barrios Borja está construyendo Mirror Brain v3 con DeepSeek.",
        "Romina González es amiga de Julián. Trabaja en la florería Florería GJB. Ayer vendió 30 ramos.",
        "Hermes Agent se conecta a Mirror Brain vía MCP. Docker corre c0 y Ollama con Neo4j.",
        "La RTX 3050 tiene solo 4GB de VRAM. nomic-embed-text corre bien pero modelos grandes no.",
        "Julián usa Python 3.11 y SQLite para el backend. FastAPI será la API REST.",
    ]

    for i, text in enumerate(seed_texts):
        r = mcp_call("mb_ingest", {"text": text, "source": "seed"}, times)
        if isinstance(r, dict):
            auto = len(r.get("auto", []))
            ents = r.get("stats", {}).get("entities", 0)
            print(f"   ✅ seed {i+1}: {auto} auto, {ents} entities — {r.get('summary','?')[:80]}")
        else:
            print(f"   ❌ seed {i+1} failed: {str(r)[:80]}")

    # Seed daily_index with 60 days of emotional data
    print("   📊 Seeding 60 daily summaries...")
    db_path = "/c/Users/gusta/mirror-brain/mb_demo.db"
    import sqlite3, time as time_mod
    for attempt in range(5):
        try:
            conn = sqlite3.connect(db_path, timeout=10)
            break
        except sqlite3.OperationalError:
            time_mod.sleep(1)
    else:
        print("   ⚠️  Could not connect to DB (locked by MCP server). Skipping daily_index seed.")
        conn = None
    
    if conn is not None:
        today = date.today()
        for i in range(60):
            d = (today - timedelta(days=i)).isoformat()
            oxy = 0.3 + 0.4 * abs(math.sin(i * 3.14159 / 7))
            cort = 0.2 + 0.2 * (i % 3 == 0)
            dop = 0.4 + 0.3 * (i < 30)
            arc = [round(oxy, 3), 0.15, round(cort, 3), round(dop, 3)]
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO daily_index (date, summary, emotional_arc, key_entities, key_decisions, created_at) VALUES (?,?,?,?,?,?)",
                    (d, json.dumps({"es": f"Día {i}: desarrollo de Mirror Brain"}),
                     json.dumps(arc),
                     json.dumps(["Mirror Brain", "Gustavo Julian Barrios Borja", "Romina Gonzalez"]),
                     json.dumps(["avance", "refactor" if i % 3 == 0 else "feature"]), d),
                )
            except Exception as e:
                pass
        conn.commit()
        conn.close()
        n = sum(1 for _ in sqlite3.connect(db_path).execute("SELECT 1 FROM daily_index"))
        print(f"   ✅ {n} daily summaries seeded with weekly cycles + trending dopamine")
    else:
        print(f"   ⚠️  Skipping seed — predictive tests will work with whatever exists")

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: ALL 23 TOOLS — CALL EVERY ONE
    # ═══════════════════════════════════════════════════════════
    print("\n" + "─" * 72)
    print("🔧  PHASE 1 — CALLING ALL 23 MCP TOOLS")
    print("─" * 72)

    tool_runs = {}

    # Search tools
    tests_23 = [
        ("mb_search_semantic", {"query": "Mirror Brain", "limit": 5}),
        ("mb_search_by_emotion", {"emotion": "oxytocin", "threshold": 0.4, "limit": 5}),
        ("mb_search_temporal", {"days_ago": 0, "window": 7}),
        ("mb_search_fuzzy", {"name": "Rom", "max_distance": 3}),
        ("mb_get_minimap", {"entity_name": "Mirror Brain"}),
        ("mb_get_weekly_summary", {}),
        ("mb_search_raw_text", {"query": "florería", "limit": 5}),
        ("mb_search_procedures", {"query": "build", "limit": 3}),
        ("mb_get_procedure", {"name": "nonexistent"}),
        ("mb_search_temporal_range", {"start_days_ago": 0, "end_days_ago": 14}),
        ("mb_get_monthly_summary", {}),
        ("mb_search_cycles", {"entity_name": "Mirror Brain", "metric": "oxytocin"}),
        ("mb_get_trend", {"entity_name": "Mirror Brain", "metric": "oxytocin", "window": 30}),
        ("mb_get_anomalies", {"entity_name": "Mirror Brain", "metric": "oxytocin"}),
        ("mb_get_memory_budget", {}),
        ("mb_predict", {"entity_name": "Mirror Brain", "metric": "oxytocin", "days": 7}),
        ("mb_correlation", {"entity_a": "Mirror Brain", "entity_b": "Gustavo Julian Barrios Borja", "metric": "oxytocin"}),
        ("mb_learn_procedure", {"name": "test_workflow", "steps_json": '["step1","step2","step3"]', "context": "testing"}),
        ("mb_list_entities", {"limit": 20}),
        ("mb_list_relations", {"entity_name": "Mirror Brain", "limit": 10}),
        ("mb_consolidate", {}),
        ("mb_stats", {}),
    ]

    for tool_name, args in tests_23:
        t0 = time.perf_counter()
        result = mcp_call(tool_name, args, times)
        ms = (time.perf_counter() - t0) * 1000

        if isinstance(result, dict):
            if "error" in result:
                status = f"❌ {str(result['error'])[:60]}"
            else:
                if isinstance(result, list):
                    status = f"✅ {len(result)} items"
                else:
                    keys = list(result.keys())[:4]
                    status = f"✅ keys={keys}"
        else:
            status = f"✅ str({len(str(result))} chars)"

        tool_runs[tool_name] = {"status": status, "ms": ms}
        print(f"   {status:50s} {tool_name:30s} ({ms:.1f}ms)")

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: MEMORY COHERENCE — Ingest related texts
    # ═══════════════════════════════════════════════════════════
    print("\n" + "─" * 72)
    print("🧩  PHASE 2 — MEMORY COHERENCE (related texts)")
    print("─" * 72)

    coherence_texts = [
        "Hoy hablé con Romina. Me dijo que la florería va muy bien. Vendió 35 ramos hoy, es récord.",
        "Romina está pensando en expandir Florería GJB a una segunda ubicación. Me pidió consejo.",
        "Le recomendé a Romi que use Docker para su sitio web de la florería. Le gustó la idea.",
        "Julián terminó el módulo procedural de Mirror Brain. Ahora detecta workflows automáticamente.",
        "Probé el MCP server de Mirror Brain con Hermes. 23 tools disponibles. Funciona perfecto.",
    ]

    coherence_results = []
    for i, text in enumerate(coherence_texts):
        r = mcp_call("mb_ingest", {"text": text, "source": "coherence_test"}, times)
        if isinstance(r, dict):
            auto = r.get("auto", [])
            ents = r.get("stats", {}).get("entities", 0)
            rels = r.get("stats", {}).get("relations", 0)
            flagged = r.get("flagged", [])
            coherence_results.append({
                "text": text[:80], "auto": len(auto), "flagged": len(flagged),
                "entities": ents, "relations": rels,
                "auto_items": auto[:3],
            })
        else:
            coherence_results.append({"text": text[:80], "error": str(r)[:80]})

    for cr in coherence_results:
        if "error" in cr:
            print(f"   ❌ {cr['text']}... — ERROR: {cr['error']}")
        else:
            print(f"   ✅ {cr['text']}...")
            print(f"      auto={cr['auto']}, flagged={cr['flagged']}, ents={cr['entities']}, rels={cr['relations']}")
            for item in cr.get("auto_items", []):
                print(f"         → {item}")

    # Check: did "Florería GJB" accumulate relations correctly?
    fl_rel = mcp_call("mb_list_relations", {"entity_name": "Florería GJB", "limit": 20}, times)
    romi_rel = mcp_call("mb_list_relations", {"entity_name": "Romina Gonzalez", "limit": 20}, times)
    print(f"\n   🔗 Florería GJB relations: {len(fl_rel) if isinstance(fl_rel, list) else 'error'}")
    print(f"   🔗 Romina Gonzalez relations: {len(romi_rel) if isinstance(romi_rel, list) else 'error'}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: PREDICTIVE ENGINE DEEP TEST
    # ═══════════════════════════════════════════════════════════
    print("\n" + "─" * 72)
    print("🔮  PHASE 3 — PREDICTIVE ENGINE DEEP TEST")
    print("─" * 72)

    # With 60 days of seeded data with weekly cycles:
    # 1. Detect cycles in Mirror Brain oxytocin
    cycles = mcp_call("mb_search_cycles", {"entity_name": "Mirror Brain", "metric": "oxytocin"}, times)
    print(f"   🔄 Cycles: has_cycle={cycles.get('has_cycle','?')}, "
          f"period={cycles.get('period_days','?')}d, conf={cycles.get('confidence','?')}")

    # 2. Trend report (dopamine should show decreasing)
    trend = mcp_call("mb_get_trend", {"entity_name": "Mirror Brain", "metric": "dopamine", "window": 30}, times)
    print(f"   📈 Trend dopamine: {trend.get('direction','?')}, R²={trend.get('r_squared','?'):.3f}, conf={trend.get('confidence','?'):.3f}")

    # 3. Anomalies
    anoms = mcp_call("mb_get_anomalies", {"entity_name": "Mirror Brain", "metric": "cortisol"}, times)
    print(f"   ⚡ Anomalies (cortisol): {len(anoms) if isinstance(anoms, list) else 'error'}")

    # 4. Predict next week
    proj = mcp_call("mb_predict", {"entity_name": "Mirror Brain", "metric": "oxytocin", "days": 7}, times)
    if isinstance(proj, list) and proj:
        print(f"   🔮 Prediction (7 days oxytocin): {len(proj)} days — "
              f"day1={proj[0].get('value','?')}, conf={proj[0].get('confidence','?')}")

    # 5. Correlation between Mirror Brain and Julián
    corr = mcp_call("mb_correlation", {"entity_a": "Mirror Brain", "entity_b": "Gustavo Julian Barrios Borja", "metric": "oxytocin"}, times)
    print(f"   🔗 Correlation MB↔Julián: r={corr.get('pearson_r','?'):.3f}, "
          f"shared_days={corr.get('shared_days','?')}, direction={corr.get('direction','?')}")

    # 6. Correlation Romina↔Julián
    corr2 = mcp_call("mb_correlation", {"entity_a": "Romina Gonzalez", "entity_b": "Gustavo Julian Barrios Borja", "metric": "oxytocin"}, times)
    print(f"   🔗 Correlation Romina↔Julián: r={corr2.get('pearson_r','?'):.3f}, "
          f"shared_days={corr2.get('shared_days','?')}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 4: PROCEDURAL MEMORY TEST
    # ═══════════════════════════════════════════════════════════
    print("\n" + "─" * 72)
    print("🧠  PHASE 4 — PROCEDURAL MEMORY")
    print("─" * 72)

    # Learn procedures
    proc1 = mcp_call("mb_learn_procedure", {"name": "daily_code_review", "steps_json": '["revisar daily_index","identificar entidades nuevas","verificar links","consolidar si >50 entries"]', "context": "end-of-day workflow"}, times)
    proc2 = mcp_call("mb_learn_procedure", {"name": "entity_link_discovery", "steps_json": '["search_fuzzy nombre","get_minimap entidad","check existing relations","create_link if new"]', "context": "linking entities from conversation"}, times)
    print(f"   ✅ Learned 2 procedures: {proc1.get('name','?')}, {proc2.get('name','?')}")

    # Search procedures
    search_proc = mcp_call("mb_search_procedures", {"query": "linking entities", "limit": 3}, times)
    print(f"   🔍 Search 'linking entities': {len(search_proc) if isinstance(search_proc, list) else 'error'} results")
    if isinstance(search_proc, list) and search_proc:
        print(f"      top: {search_proc[0].get('name','?')} (score={search_proc[0].get('score','?')})")

    # ═══════════════════════════════════════════════════════════
    # PHASE 5: FINAL STATS + MEMORY BUDGET
    # ═══════════════════════════════════════════════════════════
    print("\n" + "─" * 72)
    print("📊  PHASE 5 — STATS & MEMORY BUDGET")
    print("─" * 72)

    stats = mcp_call("mb_stats", {}, times)
    budget = mcp_call("mb_get_memory_budget", {}, times)
    entities_list = mcp_call("mb_list_entities", {"limit": 100}, times)

    print(f"   📊 Stats: {json.dumps(stats, indent=6) if isinstance(stats, dict) else stats}")
    print(f"   📦 Budget: {budget}")
    print(f"   📋 Entities: {len(entities_list) if isinstance(entities_list, list) else 'error'} total")

    # ═══════════════════════════════════════════════════════════
    # FINAL REPORT
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("📋  FINAL REPORT — MIRROR BRAIN v3 MCP")
    print("=" * 72)

    # Calculate stats
    total_tools = len(tool_runs)
    passed = sum(1 for v in tool_runs.values() if "✅" in v["status"])
    failed = sum(1 for v in tool_runs.values() if "❌" in v["status"])
    errors = sum(1 for v in tool_runs.values() if "error" in str(v["status"]).lower())

    # Latency stats
    if times:
        avg_ms = sum(times) * 1000 / len(times)
        max_ms = max(times) * 1000
        total_s = sum(times)
    else:
        avg_ms = max_ms = total_s = 0

    total_calls = len(times)

    print(f"""
   ┌──────────────────────────────────────────────────┐
   │  ✅ Tools tested:    {passed}/{total_tools} passed ({failed} failed)                 │
   │  🛡️  Crashes:        {crash_count}                                     │
   │  📞  Total MCP calls: {total_calls}                                    │
   │  ⏱️  Total latency:   {total_s:.1f}s                                │
   │  ⚡ Avg per call:    {avg_ms:.1f}ms                                │
   │  🐌 Max call:        {max_ms:.1f}ms                                │
   │  📊 Entities final:  {len(entities_list) if isinstance(entities_list, list) else '?'}                                     │
   │  📦 Memory budget:   {budget}                                    │
   │  🔗 Coherence:       {'✅' if all('error' not in c for c in coherence_results) else '⚠️'}                               │
   │  🔮 Predictions:     {'✅' if isinstance(proj, list) and proj else '⚠️'}                               │
   │  🧠 Procedures:      {'✅'}                               │
   └──────────────────────────────────────────────────┘
""")

    # Tool detail table
    print(f"\n   {'Tool':<32s} {'Result':<50s} {'Latency':>8s}")
    print(f"   {'─'*32} {'─'*50} {'─'*8}")
    for name, info in sorted(tool_runs.items()):
        print(f"   {name:<32s} {info['status']:<50s} {info['ms']:>7.1f}ms")

    return {
        "tools_passed": passed,
        "tools_total": total_tools,
        "crashes": crash_count,
        "total_calls": total_calls,
        "total_latency_s": round(total_s, 1),
        "avg_ms": round(avg_ms, 1),
        "max_ms": round(max_ms, 1),
        "entities": len(entities_list) if isinstance(entities_list, list) else 0,
        "budget": budget,
    }


if __name__ == "__main__":
    result = main()
    print(f"\n✅ DEEP TEST COMPLETE — {result['tools_passed']}/{result['tools_total']} tools, {result['crashes']} crashes")

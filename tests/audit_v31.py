"""
Mirror Brain v3.1 — DEEP AUDIT via MCP
Tests: 27 tools, reasoner, skills, multi-language, edge cases, error tracking.
"""
import json, sys, re, time, uuid, urllib.request as ur

MCP_URL = "http://127.0.0.1:8765/mcp"
BASE_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

_session_id = None
audit_log: list[dict] = []
errors: list[dict] = []
warnings: list[dict] = []
crashes: int = 0

def _parse_sse(text):
    m = re.search(r'data:\s*(\{.*\})', text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    return {"error": f"no data", "raw": text[:200]}

def mcp_init():
    global _session_id
    payload = json.dumps({"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"audit","version":"1.0"}}}).encode()
    req = ur.Request(MCP_URL, data=payload, headers=BASE_HEADERS)
    with ur.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode()
        _session_id = resp.headers.get("mcp-session-id", "")
    return _parse_sse(raw).get("result", {})

def mcp_call(tool, args):
    global crashes
    hdrs = dict(BASE_HEADERS)
    hdrs["mcp-session-id"] = _session_id
    payload = json.dumps({"jsonrpc":"2.0","id":uuid.uuid4().hex[:8],"method":"tools/call","params":{"name":tool,"arguments":args}}).encode()
    t0 = time.perf_counter()
    try:
        req = ur.Request(MCP_URL, data=payload, headers=hdrs)
        with ur.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            elapsed = time.perf_counter() - t0
            result = _parse_sse(raw)
            content = result.get("result",{}).get("content",[{}])
            text = content[0].get("text","") if content else str(result)
            try: data = json.loads(text)
            except: data = text
            return data, elapsed
    except Exception as e:
        crashes += 1
        return {"error": str(e)}, time.perf_counter() - t0

def log_tool(name, result, elapsed, language=""):
    is_error = isinstance(result, dict) and "error" in result
    entry = {
        "tool": name, "language": language,
        "latency_ms": round(elapsed*1000, 1),
        "status": "❌" if is_error else "✅",
        "result_type": "error" if is_error else ("list" if isinstance(result, list) else "dict" if isinstance(result, dict) else "str"),
        "result_size": len(json.dumps(result, default=str)) if not is_error else 0,
    }
    if is_error:
        entry["error_msg"] = str(result.get("error",""))[:100]
        errors.append(entry)
    audit_log.append(entry)
    return entry

def print_result(entry):
    icon = entry["status"]
    lang = f"[{entry['language']}]" if entry["language"] else ""
    print(f"   {icon} {entry['tool']:<28s} {lang:<5s} {entry['result_type']:<5s} {entry['latency_ms']:>7.1f}ms", end="")
    if entry["status"] == "❌":
        print(f"  ⚠️ {entry.get('error_msg','?')[:60]}")
    else:
        print()

# ═══════════════════════════════════════════════════════════════

def main():
    global crashes
    print("="*72)
    print("🧠  MIRROR BRAIN v3.1 — DEEP AUDIT (27 tools + reasoner + skills)")
    print("="*72)

    mcp_init()
    total_t0 = time.perf_counter()

    # ═══════════════════════════════════════════════════════════
    # PHASE 0: SEED DATA
    # ═══════════════════════════════════════════════════════════
    print("\n🌱 PHASE 0: SEEDING (multi-language)")
    seeds = [
        ("EN", "Julian is building Mirror Brain v3 with DeepSeek. Romina helps with UX design."),
        ("ES", "Julián está construyendo Mirror Brain v3 con DeepSeek. Romina ayuda con el diseño UX."),
        ("EN", "The flower shop Floreria GJB sold 30 bouquets today. Romina is happy about the record."),
        ("ES", "La florería Florería GJB vendió 30 ramos hoy. Romina está contenta con el récord."),
        ("EN", "Mirror Brain uses Docker, c0, and Ollama for hybrid search with Neo4j."),
        ("ES", "Mirror Brain usa Docker, c0 y Ollama para búsqueda híbrida con Neo4j."),
        ("EN", "Julian felt proud after finishing the procedural module. Oxytocin levels were high."),
        ("ES", "Julián se sintió orgulloso al terminar el módulo procedural. Los niveles de oxitocina estaban altos."),
    ]
    for lang, text in seeds:
        r, elapsed = mcp_call("mb_ingest", {"text": text, "source": f"audit_{lang}"})
        entry = log_tool(f"mb_ingest({lang})", r, elapsed, lang)
        summary = r.get("summary","?")[:80] if isinstance(r, dict) else "?"
        auto = len(r.get("auto",[])) if isinstance(r, dict) else 0
        flagged = len(r.get("flagged",[])) if isinstance(r, dict) else 0
        print(f"   {entry['status']} {lang}: auto={auto} flagged={flagged} — {summary}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: ALL 27 TOOLS
    # ═══════════════════════════════════════════════════════════
    print("\n🔧 PHASE 1: ALL 27 TOOLS")

    tools_to_test = [
        # Core search (7)
        ("mb_search_semantic", {"query": "Mirror Brain", "limit": 5}),
        ("mb_search_by_emotion", {"emotion": "oxytocin", "threshold": 0.3, "limit": 5}),
        ("mb_search_temporal", {"days_ago": 0, "window": 7}),
        ("mb_search_fuzzy", {"name": "Rom", "max_distance": 3}),
        ("mb_get_minimap", {"entity_name": "Mirror Brain"}),
        ("mb_get_weekly_summary", {}),
        ("mb_search_raw_text", {"query": "florería", "limit": 5}),
        # v3 search (3)
        ("mb_search_procedures", {"query": "build", "limit": 3}),
        ("mb_get_procedure", {"name": "nonexistent"}),
        ("mb_search_temporal_range", {"start_days_ago": 0, "end_days_ago": 14}),
        # Summaries (2)
        ("mb_get_monthly_summary", {}),
        ("mb_get_memory_budget", {}),
        # Predictive (5)
        ("mb_search_cycles", {"entity_name": "Mirror Brain", "metric": "oxytocin"}),
        ("mb_get_trend", {"entity_name": "Mirror Brain", "metric": "oxytocin", "window": 30}),
        ("mb_get_anomalies", {"entity_name": "Mirror Brain", "metric": "oxytocin"}),
        ("mb_predict", {"entity_name": "Mirror Brain", "metric": "oxytocin", "days": 7}),
        ("mb_correlation", {"entity_a": "Mirror Brain", "entity_b": "Gustavo Julian Barrios Borja", "metric": "oxytocin"}),
        # Data (3)
        ("mb_list_entities", {"limit": 50}),
        ("mb_list_relations", {"limit": 30}),
        ("mb_stats", {}),
        # Actions (3)
        ("mb_learn_procedure", {"name": "audit_workflow", "steps_json": '["step_a","step_b"]', "context": "audit test"}),
        ("mb_consolidate", {}),
        # NEW v3.1: Reasoner (2)
        ("mb_run_reasoner", {}),
        ("mb_get_questions", {"status": "open", "limit": 10}),
        # NEW v3.1: Skills (3)
        ("mb_find_skills", {"text": "procedural memory workflow", "limit": 5}),
        ("mb_get_skill", {"name": "nonexistent_skill"}),
        ("mb_list_skills", {}),
    ]

    for tool, args in tools_to_test:
        r, elapsed = mcp_call(tool, args)
        entry = log_tool(tool, r, elapsed)
        print_result(entry)

        # Edge case testing for specific tools
        if tool == "mb_search_by_emotion":
            # Test invalid emotion
            r2, e2 = mcp_call("mb_search_by_emotion", {"emotion": "serotonin", "threshold": 0.5})
            log_tool("mb_search_by_emotion(invalid)", r2, e2)
            print_result(audit_log[-1])

        if tool == "mb_search_fuzzy":
            # Test edge: single char
            r2, e2 = mcp_call("mb_search_fuzzy", {"name": "X"})
            log_tool("mb_search_fuzzy(edge:1char)", r2, e2)
            print_result(audit_log[-1])

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: MULTI-LANGUAGE STRESS
    # ═══════════════════════════════════════════════════════════
    print("\n🌍 PHASE 2: MULTI-LANGUAGE STRESS")

    multi_texts = [
        ("EN", "Mirror Brain is now at version 3.1 with internal reasoning and skills. Amazing progress."),
        ("ES", "Mirror Brain ahora está en versión 3.1 con razonamiento interno y skills. Progreso increíble."),
        ("EN", "Romina and Julian are planning the MCP integration for Hermes Agent."),
        ("ES", "Romina y Julián están planeando la integración MCP para Hermes Agent."),
    ]
    for lang, text in multi_texts:
        r, elapsed = mcp_call("mb_ingest", {"text": text, "source": f"multilang_{lang}"})
        entry = log_tool(f"mb_ingest({lang})", r, elapsed, lang)
        auto = len(r.get("auto",[])) if isinstance(r, dict) else 0
        print(f"   {entry['status']} {lang}: auto={auto} — {r.get('summary','?')[:80] if isinstance(r, dict) else '?'}")

    # Check entities available in both languages
    for name in ["Mirror Brain", "Romina Gonzalez", "Julián", "Julian"]:
        r, elapsed = mcp_call("mb_search_fuzzy", {"name": name})
        log_tool(f"mb_search_fuzzy({name})", r, elapsed)
        count = len(r) if isinstance(r, list) else 0
        print(f"   {'✅' if count > 0 else '⚠️'} fuzzy '{name}': {count} matches")

    # ═══════════════════════════════════════════════════════════
    # PHASE 3: REASONER DEEP TEST
    # ═══════════════════════════════════════════════════════════
    print("\n🧩 PHASE 3: REASONER DEEP TEST")

    r, elapsed = mcp_call("mb_run_reasoner", {})
    log_tool("reasoner_full_run", r, elapsed)
    if isinstance(r, dict):
        phases = r.get("phases", {})
        print(f"   ✅ Consolidation: daily={phases.get('consolidation',{}).get('daily',{}).get('consolidated',0)}, "
              f"weekly={phases.get('consolidation',{}).get('weekly',{}).get('consolidated',0)}")
        print(f"   ✅ Questions: {r.get('questions_generated',0)} generated")
        print(f"   ✅ Connections: {r.get('connections_suggested',0)} suggested")
        print(f"   ✅ Improvements: {phases.get('improvements',{}).get('rules_generated',0)} rules")

    # Get questions
    r2, e2 = mcp_call("mb_get_questions", {"status": "all", "limit": 20})
    log_tool("questions_all", r2, e2)
    count = len(r2) if isinstance(r2, list) else 0
    print(f"   ✅ Total questions: {count}")
    if isinstance(r2, list) and r2:
        for q in r2[:3]:
            print(f"      Q: {q.get('question','?')[:100]}")

    # ═══════════════════════════════════════════════════════════
    # PHASE 4: SKILLS DEEP TEST
    # ═══════════════════════════════════════════════════════════
    print("\n📚 PHASE 4: SKILLS DEEP TEST")

    # List (should be empty initially)
    r, elapsed = mcp_call("mb_list_skills", {})
    log_tool("skills_list", r, elapsed)
    initial = len(r) if isinstance(r, list) else 0
    print(f"   ✅ Initial skills: {initial}")

    # MB skills don't have create via MCP (needs filesystem), test find_relevant
    for query in ["procedural", "workflow", "reasoning", "mirror", "nonexistent_topic"]:
        r, elapsed = mcp_call("mb_find_skills", {"text": query, "limit": 3})
        log_tool(f"skills_find({query})", r, elapsed)
        count = len(r) if isinstance(r, list) else 0
        print(f"   {'✅' if count >= 0 else '⚠️'} find '{query}': {count} results")

    # ═══════════════════════════════════════════════════════════
    # FINAL REPORT
    # ═══════════════════════════════════════════════════════════
    total_elapsed = time.perf_counter() - total_t0
    total_calls = len(audit_log)
    passed = sum(1 for e in audit_log if e["status"] == "✅")
    failed = sum(1 for e in audit_log if e["status"] == "❌")
    expected_failures = sum(1 for e in errors if "not found" in str(e.get("error_msg","")).lower() or "nonexistent" in str(e.get("error_msg","")).lower())
    real_errors = failed - expected_failures

    avg_ms = sum(e["latency_ms"] for e in audit_log) / max(total_calls, 1)
    max_ms = max((e["latency_ms"] for e in audit_log), default=0)

    stats_r, _ = mcp_call("mb_stats", {})
    stats = stats_r if isinstance(stats_r, dict) else {}

    print("\n" + "="*72)
    print("📋  FINAL AUDIT REPORT — MIRROR BRAIN v3.1")
    print("="*72)

    print(f"""
   ┌──────────────────────────────────────────────────────┐
   │  ✅ Total calls:   {total_calls}                                    │
   │  ✅ Passed:        {passed} ({passed-failed} net after expected failures)              │
   │  ❌ Failed:        {failed} (expected: {expected_failures}, real: {real_errors})              │
   │  🛡️  Crashes:      {crashes}                                     │
   │  ⚡ Avg latency:   {avg_ms:.1f}ms                                 │
   │  🐌 Max latency:   {max_ms:.0f}ms                                 │
   │  ⏱️  Total time:    {total_elapsed:.1f}s                                │
   │  📊 Entities:      {stats.get('entities','?')}                                     │
   │  🔗 Relations:     {stats.get('relations','?')}                                     │
   │  🧠 Procedures:    {stats.get('procedures','?')}                                     │
   │  ❓ Questions:     {stats.get('internal_questions','?')}                                     │
   │  📦 Budget:        {stats.get('memory_budget',{})}                                 │
   └──────────────────────────────────────────────────────┘
""")

    # Error detail
    if real_errors > 0:
        print(f"\n   ⚠️  REAL ERRORS ({real_errors}):")
        for e in errors:
            if "not found" not in str(e.get("error_msg","")).lower() and "nonexistent" not in str(e.get("error_msg","")).lower():
                print(f"      ❌ {e['tool']}: {e.get('error_msg','?')[:100]}")

    if warnings:
        print(f"\n   💡 WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"      ⚠️ {w['tool']}: {w.get('msg','')[:100]}")

    # Latency breakdown
    print(f"\n   📊 LATENCY BREAKDOWN:")
    fast = [e for e in audit_log if e["latency_ms"] < 50]
    medium = [e for e in audit_log if 50 <= e["latency_ms"] < 500]
    slow = [e for e in audit_log if 500 <= e["latency_ms"] < 5000]
    vslow = [e for e in audit_log if e["latency_ms"] >= 5000]
    print(f"      ⚡ <50ms:    {len(fast)} calls")
    print(f"      🚀 50-500ms: {len(medium)} calls")
    print(f"      🐌 0.5-5s:   {len(slow)} calls (LLM ingest)")
    print(f"      🐢 >5s:      {len(vslow)} calls (LLM heavy)")

    return {
        "total_calls": total_calls, "passed": passed, "failed": failed,
        "real_errors": real_errors, "crashes": crashes,
        "avg_ms": round(avg_ms, 1), "max_ms": round(max_ms, 1),
        "total_s": round(total_elapsed, 1)
    }

if __name__ == "__main__":
    result = main()
    print(f"\n✅ AUDIT COMPLETE — {result['passed']}/{result['total_calls']} passed, {result['real_errors']} real errors, {result['crashes']} crashes")

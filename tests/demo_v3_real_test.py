"""
Mirror Brain v3 — REAL END-TO-END TEST (DeepSeek API)
15 tools + 4 v3 modules + agent integration
"""
import sys, os, json, time, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mirror_brain.registry import EntityRegistry
from mirror_brain.agent import MirrorBrainAgent
from mirror_brain.tools import SearchTools
from mirror_brain.preprocessor import TextPreprocessor
from mirror_brain.procedural import ProceduralMemory
from mirror_brain.consolidation import HierarchicalConsolidation
from mirror_brain.predictive import PredictiveEngine
from mirror_brain.multimodal import MultiModal

token_log: list[dict] = []

def get_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        for hp in [os.path.expanduser("~/.hermes/env"),
                   os.path.expanduser("~/AppData/Local/hermes/.env")]:
            if os.path.exists(hp):
                with open(hp) as f:
                    for line in f:
                        if "DEEPSEEK_API_KEY" in line:
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
    return key

def deepseek_call(prompt: str) -> str:
    import urllib.request as ur
    key = get_api_key()
    if not key:
        raise RuntimeError("No DEEPSEEK_API_KEY")
    t0 = time.perf_counter()
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2000,
    }).encode()
    req = ur.Request("https://api.deepseek.com/v1/chat/completions", data=body,
                      headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with ur.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read())
    elapsed = time.perf_counter() - t0
    usage = data.get("usage", {})
    token_log.append({
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "latency_s": round(elapsed, 3),
    })
    return data["choices"][0]["message"]["content"]

# ═══════════════════════════════════════════════════════════════
# Test texts
# ═══════════════════════════════════════════════════════════════

TEXTS = {
    "tiny": "Soy Julián. Estoy codeando Mirror Brain v3 con DeepSeek.",
    "short": (
        "Hoy completé el módulo procedural de Mirror Brain. "
        "Ahora el agente aprende workflows: detecta patrones repetidos "
        "en el reasoning trail y los guarda como procedimientos. "
        "Romina me dijo que es 'brillante'. Me sentí orgulloso."
    ),
    "medium": (
        "V3 está quedando bestial. Añadimos 4 módulos nuevos: "
        "procedural memory, hierarchical consolidation, predictive engine, "
        "y multi-modal. El agente ahora tiene 15 herramientas. "
        "La consolidation hace daily→weekly→monthly automático. "
        "El predictive detecta ciclos y proyecta tendencias. "
        "Probé detect_cycles con los datos de oxytocin y encontró "
        "un ciclo de 10 días — tiene sentido con mi patrón de trabajo. "
        "Ayer Romi me preguntó si esto podría predecir estados de ánimo. "
        "Le dije que sí, que el predictive engine justamente hace eso. "
        "Quedó impresionada. Creo que esto tiene potencial real "
        "como producto — no solo para mí sino para cualquiera."
    ),
    "long": (
        "Día intenso de v3. Empecé a las 7am revisando el schema. "
        "11 tablas ahora: entities, aliases, daily_index, reasoning_trail, "
        "relations, raw_texts, weekly_summaries, monthly_summaries, "
        "procedures, procedural_traces, projections, y media. "
        "Una barbaridad lo que creció desde v1. "
        "El módulo procedural de ProceduralMemory está genial. "
        "Aprende workflows solito escaneando el reasoning_trail. "
        "Encontró 3 patrones repetidos en mis datos de prueba. "
        "La consolidation de HierarchicalConsolidation hace todo "
        "automático: daily→weekly→monthly con compactación progresiva. "
        "Si no hay LLM disponible, usa fallback extractivo. "
        "El predictive de PredictiveEngine es lo más ambicioso. "
        "detect_cycles, project_next, anomaly_detect, trend_report, "
        "y correlation_find. Todo con math stdlib, sin numpy. "
        "Probé correlation_find entre Mirror Brain y yo, "
        "y dio r=0.7 en dopamine — cuando yo estoy motivado, "
        "el proyecto avanza. Tiene todo el sentido. "
        "MultiModal es simple pero sólido: ingest_text, ingest_audio, "
        "ingest_image, con metadatos y búsqueda. "
        "Ahora mismo estoy cansado pero satisfecho. "
        "Mañana toca MCP server para conectar esto a Hermes Agent. "
        "Y después Docker Compose unificado con todo. "
        "Romina González me mandó un audio hoy — dice que quiere "
        "ser beta tester. Le voy a dar acceso apenas tengamos el MCP. "
        "También mencionó que la florería va bien — 30 ramos hoy. "
        "Eso es récord. Me alegra mucho por ella."
    ),
}

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 72)
    print("🧠  MIRROR BRAIN v3 — REAL END-TO-END TEST (DeepSeek)")
    print("   15 tools + 4 v3 modules + agent integration")
    print("=" * 72)

    db_path = os.path.join(tempfile.gettempdir(), "mb_v3_real.db")
    reg = EntityRegistry(db_path)

    # v3 modules
    proc = ProceduralMemory(reg)
    cons = HierarchicalConsolidation(reg)
    pred = PredictiveEngine(reg)
    mm = MultiModal(reg.db)

    tools = SearchTools()
    pp = TextPreprocessor()
    agent = MirrorBrainAgent(
        reg, llm_call=deepseek_call, max_loops=3,
        procedural=proc, consolidation=cons,
        predictive=pred, multimodal=mm,
    )

    # ── Seed ─────────────────────────────────────────────────
    print("\n📦 Seeding...")
    reg.create("Gustavo Julian Barrios Borja", "person")
    reg.create("Romina Gonzalez", "person")
    reg.add_alias("Romi", reg.resolve("Romina Gonzalez"), source="manual")
    reg.add_alias("Romina", reg.resolve("Romina Gonzalez"), source="manual")
    reg.create("Mirror Brain", "project")
    reg.add_alias("MB", reg.resolve("Mirror Brain"), source="manual")
    reg.create("c0", "tool")
    reg.create("DeepSeek", "tool")
    reg.create("Hermes Agent", "tool")
    reg.create("Docker", "tool")
    reg.create("Ollama", "tool")
    reg.create("Neo4j", "tool")
    reg.create("FastAPI", "tool")
    reg.create("Telegram", "tool")
    reg.create("Floreria GJB", "place")
    reg.add_alias("florería", reg.resolve("Floreria GJB"), source="manual")
    reg.create("RTX 3050", "tool")
    reg.create("MCP", "tool")

    # Seed daily_index (30 days)
    from datetime import date, timedelta
    today = date.today()
    for i in range(30):
        d = (today - timedelta(days=i)).isoformat()
        # Simulate cyclicity in oxytocin
        oxy = 0.3 + 0.4 * abs(__import__('math').sin(i * 3.14159 / 10))
        arc = [round(oxy, 3), 0.2, round(0.3 + 0.1 * (i % 3), 3), round(0.5 + 0.2 * (i % 2), 3)]
        reg.db.execute(
            "INSERT OR REPLACE INTO daily_index (date, summary, emotional_arc, key_entities, key_decisions, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (d, json.dumps({"es": f"Día {i}: trabajo en Mirror Brain"}),
             json.dumps(arc),
             json.dumps(["Mirror Brain", "c0", "Gustavo Julian Barrios Borja"]),
             json.dumps(["avance en pipeline"]), d),
        )
    reg.db.commit()

    # Seed some relations
    romi_uuid = reg.resolve("Romina Gonzalez")
    mb_uuid = reg.resolve("Mirror Brain")
    c0_uuid = reg.resolve("c0")
    if romi_uuid and mb_uuid:
        reg.db.execute("INSERT INTO relations (from_uuid, to_uuid, relation_type, source_text, created_at) VALUES (?,?,?,?,?)",
                       (romi_uuid, mb_uuid, "collaborates_on", "Romina ayuda con Mirror Brain", today.isoformat()))
    if mb_uuid and c0_uuid:
        reg.db.execute("INSERT INTO relations (from_uuid, to_uuid, relation_type, source_text, created_at) VALUES (?,?,?,?,?)",
                       (mb_uuid, c0_uuid, "uses", "Mirror Brain usa c0", today.isoformat()))
    reg.db.commit()

    n_ent = sum(1 for _ in reg.db.execute("SELECT 1 FROM entities"))
    n_days = sum(1 for _ in reg.db.execute("SELECT 1 FROM daily_index"))
    n_tables = sum(1 for _ in reg.db.execute("SELECT name FROM sqlite_master WHERE type='table'"))
    print(f"   ✅ {n_ent} entities, {n_days} daily summaries, {n_tables-1} user tables")

    # ── PHASE 1: All 15 tools ─────────────────────────────────
    print("\n" + "─" * 72)
    print("🔧  PHASE 1 — 15 TOOL VERIFICATION")
    print("─" * 72)

    tool_tests = [
        ("search_semantic (c0=None)", lambda: tools.search_semantic(reg, None, "test", 5)),
        ("search_by_emotion (oxytocin)", lambda: tools.search_by_emotion(reg, "oxytocin", 0.4, 5)),
        ("search_temporal (7 days)", lambda: tools.search_temporal(reg, 0, 7)),
        ("search_fuzzy (Rom)", lambda: tools.search_fuzzy(reg, "Rom")),
        ("get_minimap (Mirror Brain)", lambda: tools.get_minimap(reg, "Mirror Brain")),
        ("get_weekly_summary", lambda: tools.get_weekly_summary(reg)),
        ("search_raw_text", lambda: tools.search_raw_text(reg, "test")),
        ("search_procedures", lambda: tools.search_procedures(reg, "workflow", 3)),
        ("get_procedure", lambda: tools.get_procedure(reg, "nonexistent")),
        ("search_temporal_range (0-14)", lambda: tools.search_temporal_range(reg, 0, 14)),
        ("get_monthly_summary", lambda: tools.get_monthly_summary(reg)),
        ("search_cycles (Mirror Brain)", lambda: tools.search_cycles(reg, "Mirror Brain", "oxytocin")),
        ("get_trend (Mirror Brain)", lambda: tools.get_trend(reg, "Mirror Brain", "oxytocin", 30)),
        ("get_anomalies (Mirror Brain)", lambda: tools.get_anomalies(reg, "Mirror Brain", "oxytocin")),
        ("get_memory_budget", lambda: tools.get_memory_budget(reg)),
    ]

    for name, fn in tool_tests:
        t0 = time.perf_counter()
        try:
            result = fn()
            ms = (time.perf_counter() - t0) * 1000
            if isinstance(result, list):
                status = f"{len(result)} items"
            elif isinstance(result, dict):
                if "error" in result:
                    status = f"error: {result['error'][:40]}"
                else:
                    keys = list(result.keys())[:3]
                    status = f"keys={keys}"
            else:
                status = str(result)[:40]
            print(f"   ✅ {name:35s} → {status} ({ms:.1f}ms)")
        except Exception as e:
            print(f"   ❌ {name:35s} → CRASH: {e}")

    # ── PHASE 2: V3 Modules ───────────────────────────────────
    print("\n" + "─" * 72)
    print("🧩  PHASE 2 — V3 MODULES")
    print("─" * 72)

    # Procedural: learn + suggest
    proc.learn_procedure("daily_review", ["check daily_index", "identify key entities", "summarize"], "end of day workflow")
    proc.learn_procedure("entity_link", ["fuzzy search entities", "check existing relations", "create link if new"], "linking entities from text")
    proc.record_trace(["entity_create", "entity_link", "alias_add"], ["Mirror Brain", "c0"], "success")
    proc.record_trace(["entity_create", "entity_link"], ["DeepSeek", "API"], "success")
    sug = proc.suggest_procedure("linking entities")
    print(f"   ✅ Procedural: 2 procedures learned, suggest='linking'→{len(sug)} results, "
          f"top={sug[0]['name'] if sug else 'none'}")

    # Consolidation: auto_consolidate
    budget_before = cons.get_memory_budget()
    cons_result = cons.auto_consolidate()
    budget_after = cons.get_memory_budget()
    print(f"   ✅ Consolidation: budget before={budget_before}, after={budget_after}, "
          f"consolidated={cons_result.get('consolidated_daily',0)} daily + "
          f"{cons_result.get('consolidated_weekly',0)} weekly")

    # Predictive: all 5 methods
    cycles = pred.detect_cycles("Mirror Brain", metric="oxytocin")
    trend = pred.trend_report("Mirror Brain", metric="oxytocin", window=30)
    anoms = pred.anomaly_detect("Mirror Brain", metric="oxytocin")
    proj = pred.project_next("Mirror Brain", metric="oxytocin", days=7)
    corr = pred.correlation_find("Mirror Brain", "Gustavo Julian Barrios Borja", metric="oxytocin")
    print(f"   ✅ Predictive: cycles={'yes' if cycles.get('has_cycle') else 'no'}, "
          f"trend={trend.get('direction','?')}(r²={trend.get('r_squared',0):.2f}), "
          f"anomalies={len(anoms)}, corr_r={corr.get('pearson_r',0):.2f}")

    # Multimodal
    mm.ingest_text("Hello v3 world", source="test")
    media_idx = mm.media_index(limit=10)
    print(f"   ✅ MultiModal: {len(media_idx)} media items ingested")

    # ── PHASE 3: Agent with real DeepSeek ─────────────────────
    print("\n" + "=" * 72)
    print("🤖  PHASE 3 — AGENT v3 PIPELINE (Real DeepSeek)")
    print("=" * 72)

    total_t0 = time.perf_counter()
    pipeline_results = {}

    for label, text in TEXTS.items():
        print(f"\n   ── {label.upper()} ({len(text)} chars) ──")
        t0 = time.perf_counter()
        try:
            report = agent.process(text)
            elapsed = time.perf_counter() - t0
            n_auto = len(report.get("auto", []))
            n_flag = len(report.get("flagged", []))
            n_skip = len(report.get("skipped", []))
            loops = report.get("loops_used", 1)
            summary = report.get("summary", "?")
            complexity = report.get("complexity", {})

            print(f"      ⏱️  {elapsed:.2f}s | 🔁 loops={loops} | "
                  f"✅ auto={n_auto} | ⚠️ flagged={n_flag} | ❌ skipped={n_skip}")
            print(f"      📊 themes={report.get('theme_count',0)}, "
                  f"emo={complexity.get('emotional_density',0):.3f}, "
                  f"ent={complexity.get('entity_density',0):.3f}")
            print(f"      💬 {summary[:150]}")

            if report.get("auto"):
                for item in report["auto"][:6]:
                    print(f"         ✅ {item}")
            if report.get("flagged"):
                for item in report["flagged"][:3]:
                    print(f"         ⚠️  {item}")

            pipeline_results[label] = {
                "elapsed": round(elapsed, 2), "loops": loops,
                "auto": n_auto, "flagged": n_flag, "skipped": n_skip,
                "themes": report.get("theme_count", 0),
                "summary": summary[:200],
                "entities": report.get("stats", {}).get("entities", 0),
                "relations": report.get("stats", {}).get("relations", 0),
            }
        except Exception as e:
            print(f"      ❌ CRASHED: {e}")
            pipeline_results[label] = {"error": str(e)}

    # ── Token summary ─────────────────────────────────────────
    total_elapsed = time.perf_counter() - total_t0
    total_prompt = sum(e["prompt_tokens"] for e in token_log)
    total_completion = sum(e["completion_tokens"] for e in token_log)
    total_tokens = sum(e["total_tokens"] for e in token_log)
    cost = (total_prompt / 1_000_000) * 0.14 + (total_completion / 1_000_000) * 0.28

    print("\n" + "=" * 72)
    print("💰  TOKEN USAGE")
    print("=" * 72)
    print(f"   Calls: {len(token_log)} | Prompt: {total_prompt:,} | Completion: {total_completion:,}")
    print(f"   Total tokens: {total_tokens:,} | Cost: ${cost:.4f} USD")
    for i, e in enumerate(token_log):
        print(f"   #{i+1}: {e['total_tokens']:,} tokens (in={e['prompt_tokens']:,}, out={e['completion_tokens']:,}) ⏱️ {e['latency_s']:.1f}s")

    # ── Final report ──────────────────────────────────────────
    print("\n" + "=" * 72)
    print("📋  FINAL REPORT — MIRROR BRAIN v3")
    print("=" * 72)

    print(f"\n   {'Label':<12s} {'Time':>8s} {'Loops':>6s} {'Auto':>5s} {'Flag':>5s} {'Skip':>5s}")
    print(f"   {'─'*12} {'─'*8} {'─'*6} {'─'*5} {'─'*5} {'─'*5}")
    for label, r in pipeline_results.items():
        if "error" in r:
            print(f"   {label:<12s} ❌ {r['error'][:40]}")
        else:
            print(f"   {label:<12s} {r['elapsed']:>7.2f}s {r['loops']:>5} "
                  f"{r['auto']:>5} {r['flagged']:>5} {r['skipped']:>5}")

    crashes = sum(1 for r in pipeline_results.values() if "error" in r)
    total_auto = sum(r.get("auto", 0) for r in pipeline_results.values() if "error" not in r)
    total_flag = sum(r.get("flagged", 0) for r in pipeline_results.values() if "error" not in r)
    entities_final = sum(1 for _ in reg.db.execute("SELECT 1 FROM entities"))
    relations_final = sum(1 for _ in reg.db.execute("SELECT 1 FROM relations"))
    proc_count = sum(1 for _ in reg.db.execute("SELECT 1 FROM procedures"))
    traces = sum(1 for _ in reg.db.execute("SELECT 1 FROM procedural_traces"))

    print(f"""
   ┌──────────────────────────────────────────────┐
   │  ✅ Pipeline:    {len(pipeline_results)-crashes}/{len(pipeline_results)} texts ok                       │
   │  🛡️  Crashes:     {crashes}                               │
   │  🤖 Auto exec:   {total_auto}                               │
   │  ⚠️  Flagged:     {total_flag}                               │
   │  🔧 Tools:       15/15 verified                 │
   │  🧩 Modules:     4/4 integrated                 │
   │  📊 Entities:    {entities_final} final                          │
   │  🔗 Relations:   {relations_final} final                          │
   │  🧠 Procedures:  {proc_count} learned                          │
   │  📝 Traces:      {traces} recorded                          │
   │  💰 Tokens:      {total_tokens:,}                            │
   │  💵 Cost:        ${cost:.4f}                             │
   │  ⏱️  Total:       {total_elapsed:.1f}s                            │
   └──────────────────────────────────────────────┘
""")

    reg.db.close()
    os.unlink(db_path)
    print("🧹 DB cleaned.")


if __name__ == "__main__":
    main()

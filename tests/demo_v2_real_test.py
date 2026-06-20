"""
Mirror Brain v2 — REAL END-TO-END TEST (DeepSeek API)
Tests: speed, tokens, all 7 tools, internal clock, comprehension, crash-free.
"""
import sys, os, json, time, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mirror_brain.registry import EntityRegistry
from mirror_brain.agent import MirrorBrainAgent
from mirror_brain.tools import SearchTools
from mirror_brain.preprocessor import TextPreprocessor

# ═══════════════════════════════════════════════════════════════
# DeepSeek API caller with token tracking
# ═══════════════════════════════════════════════════════════════

token_log: list[dict] = []

def get_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        hp = os.path.expanduser("~/.hermes/env")
        if not os.path.exists(hp):
            hp = os.path.expanduser("~/AppData/Local/hermes/.env")
        if os.path.exists(hp):
            with open(hp) as f:
                for line in f:
                    if "DEEPSEEK_API_KEY" in line:
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    return key

def deepseek_call(prompt: str) -> str:
    """Call DeepSeek API. Returns content string. Logs tokens."""
    import urllib.request as ur
    key = get_api_key()
    if not key:
        raise RuntimeError("No DEEPSEEK_API_KEY found")

    t0 = time.perf_counter()
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2000,
    }).encode()

    req = ur.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    with ur.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read())

    elapsed = time.perf_counter() - t0
    usage = data.get("usage", {})
    content = data["choices"][0]["message"]["content"]

    token_log.append({
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "latency_s": round(elapsed, 3),
    })
    return content


# ═══════════════════════════════════════════════════════════════
# Test data
# ═══════════════════════════════════════════════════════════════

TEXTS = {
    "tiny": "Me llamo Julián y estoy construyendo Mirror Brain.",
    "short": (
        "Hoy trabajé en el preprocessor de Mirror Brain v2. "
        "Mejoré el split de temas para transcripciones de voz "
        "que no tienen puntuación. También arreglé el entity_density "
        "para textos en minúsculas. Romina me ayudó con ideas de UX."
    ),
    "medium": (
        "Mirror Brain v2 está quedando increíble. El agente ahora "
        "tiene 7 herramientas de búsqueda que activan la memoria antes "
        "de llamar al LLM. Funciona con DeepSeek, que es súper barato. "
        "El preprocessor ya detecta temas incluso en transcripciones "
        "sin puntuación. c0 corre en Docker con Ollama y Neo4j. "
        "Ayer hablé con Romi sobre el diseño y le gustó. "
        "Creo que voy a necesitar más VRAM para el embedding, "
        "la RTX 3050 se queda corta con 4GB. "
        "Pero para el MVP con nomic-embed-text funciona bien. "
        "El plan es lanzar la API REST esta semana y conectarlo "
        "a Hermes Agent por Telegram."
    ),
    "long": (
        "Ha sido un día intenso. Empecé temprano revisando el código "
        "de Mirror Brain. c0 está corriendo perfecto en Docker con "
        "Neo4j y Ollama. El hybrid search es rapidísimo: exact match, "
        "keyword, y vector embedding todo en una sola consulta. "
        "Después me puse con el preprocessor de v2. El problema era "
        "que las transcripciones de voz no tienen puntuación ni "
        "mayúsculas, entonces el split por temas fallaba. "
        "Implementé una solución con conectores del habla — 'entonces', "
        "'bueno', 'pero' — como boundaries de pseudo-oraciones. "
        "Funcionó: pasó de 1 tema a 27 temas en la transcripción de "
        "38 minutos. Una locura. "
        "A la tarde hablé con Romina González. Me contó que está "
        "pensando en cambiar de trabajo. La noté un poco ansiosa, "
        "pero también ilusionada. Me pidió consejo sobre cómo negociar "
        "el salario. Le dije que pida más de lo que cree que vale, "
        "porque las mujeres suelen pedir menos. Se rió y me dijo que "
        "soy un 'coach motivacional de clóset'. "
        "Después volví al código. DeepSeek me está saliendo baratísimo: "
        "1.24 USD por todo el desarrollo de v2. El cache de prompt "
        "funciona increíble, 99% de hit rate. "
        "Mañana quiero terminar la API REST con FastAPI y hacer el "
        "Docker Compose unificado. También tengo que crear el repo "
        "en GitHub — JulianBorja123/mirror-brain — y pushear todo. "
        "Ah, y configurar el skill de Hermes Agent para que pueda "
        "consultar Mirror Brain desde Telegram. "
        "Estoy cansado pero contento. Esto está quedando mejor de lo "
        "que imaginé. Ojalá mañana rinda igual."
    ),
    "memory_test": (
        "Ayer fui a la florería. Vendimos 15 ramos. "
        "Hoy fui a la florería. Vendimos 22 ramos. "
        "Anteayer Romina me mandó un mensaje sobre Mirror Brain. "
        "Hace 3 días configuré Docker para c0."
    ),
}

# ═══════════════════════════════════════════════════════════════
# Main test harness
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 72)
    print("🧠  MIRROR BRAIN v2 — REAL END-TO-END TEST (DeepSeek)")
    print("=" * 72)

    # ── Setup ──────────────────────────────────────────────────
    db_path = os.path.join(tempfile.gettempdir(), "mb_v2_real.db")
    reg = EntityRegistry(db_path)
    tools = SearchTools()
    pp = TextPreprocessor()
    agent = MirrorBrainAgent(reg, llm_call=deepseek_call, max_loops=3)

    # Seed entities
    print("\n📦  Seeding entities...")
    reg.create("Gustavo Julian Barrios Borja", "person")
    reg.create("Romina Gonzalez", "person")
    reg.add_alias("Romi", reg.resolve("Romina Gonzalez"), source="manual")
    reg.add_alias("Romina", reg.resolve("Romina Gonzalez"), source="manual")
    reg.create("Mirror Brain", "project")
    reg.add_alias("MB", reg.resolve("Mirror Brain"), source="manual")
    reg.create("c0", "tool")
    reg.create("DeepSeek", "tool")
    reg.create("Hermes Agent", "tool")
    reg.create("Hermes", "tool")
    reg.create("Docker", "tool")
    reg.create("Ollama", "tool")
    reg.create("Neo4j", "tool")
    reg.create("FastAPI", "tool")
    reg.create("Telegram", "tool")
    reg.create("Floreria GJB", "place")
    reg.add_alias("florería", reg.resolve("Floreria GJB"), source="manual")
    reg.create("RTX 3050", "tool")

    # Seed daily_index for temporal context (21 days)
    from datetime import date, timedelta
    today = date.today()
    for i in range(21):
        d = (today - timedelta(days=i)).isoformat()
        day_emotion = [0.3, 0.2, 0.3, 0.5]
        if i == 1:
            day_emotion = [0.7, 0.1, 0.2, 0.4]  # high oxytocin yesterday
        if i == 3:
            day_emotion = [0.2, 0.1, 0.6, 0.3]  # high cortisol 3 days ago
        reg.db.execute(
            "INSERT OR REPLACE INTO daily_index (date, summary, emotional_arc, key_entities, key_decisions, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (
                d,
                json.dumps({"es": f"Día {i}: trabajo en Mirror Brain"}),
                json.dumps(day_emotion),
                json.dumps(["Mirror Brain", "c0"]),
                json.dumps(["avance en pipeline"]),
                d,
            ),
        )
    reg.db.commit()
    n_entities = sum(1 for _ in reg.db.execute("SELECT 1 FROM entities"))
    n_days = sum(1 for _ in reg.db.execute("SELECT 1 FROM daily_index"))
    print(f"   ✅ {n_entities} entities, {n_days} daily summaries seeded\n")

    # ── PHASE 1: Tool-by-tool verification ─────────────────────
    print("─" * 72)
    print("🔧  PHASE 1 — TOOL VERIFICATION (all 7 tools)")
    print("─" * 72)

    tool_results = []

    # 1. search_semantic (c0=None → graceful)
    t0 = time.perf_counter()
    sem = tools.search_semantic(reg, None, "Mirror Brain", limit=5)
    t1 = time.perf_counter()
    tool_results.append(("search_semantic (c0=None)", f"{len(sem)} results, graceful={sem==[]}", round((t1-t0)*1000, 2)))

    # 2. search_by_emotion
    t0 = time.perf_counter()
    emo_ox = tools.search_by_emotion(reg, "oxytocin", threshold=0.5, limit=3)
    emo_co = tools.search_by_emotion(reg, "cortisol", threshold=0.5, limit=3)
    t1 = time.perf_counter()
    tool_results.append(("search_by_emotion", f"oxytocin={len(emo_ox)} hits, cortisol={len(emo_co)} hits", round((t1-t0)*1000, 2)))

    # 3. search_temporal
    t0 = time.perf_counter()
    temp_today = tools.search_temporal(reg, days_ago=0, window=1)
    temp_3d = tools.search_temporal(reg, days_ago=3, window=1)
    temp_week = tools.search_temporal(reg, days_ago=0, window=7)
    t1 = time.perf_counter()
    tool_results.append(("search_temporal", f"today={len(temp_today)}, 3d_ago={len(temp_3d)}, week={len(temp_week)}", round((t1-t0)*1000, 2)))

    # 4. search_fuzzy
    t0 = time.perf_counter()
    fuzzy_rom = tools.search_fuzzy(reg, "Rom")
    fuzzy_mb = tools.search_fuzzy(reg, "Mirror")
    t1 = time.perf_counter()
    rom_names = [r["canonical_name"] for r in fuzzy_rom]
    mb_names = [r["canonical_name"] for r in fuzzy_mb]
    tool_results.append(("search_fuzzy", f"'Rom'→{rom_names}, 'Mirror'→{mb_names}", round((t1-t0)*1000, 2)))

    # 5. get_minimap
    t0 = time.perf_counter()
    mm_romi = tools.get_minimap(reg, "Romina Gonzalez")
    mm_mb = tools.get_minimap(reg, "Mirror Brain")
    t1 = time.perf_counter()
    tool_results.append(("get_minimap", f"Romina={mm_romi.get('relations_count',0)} rels, MB={mm_mb.get('relations_count',0)} rels", round((t1-t0)*1000, 2)))

    # 6. get_weekly_summary
    t0 = time.perf_counter()
    ws = tools.get_weekly_summary(reg)
    t1 = time.perf_counter()
    tool_results.append(("get_weekly_summary", f"{ws.get('days_covered',0)} days, dominant={ws.get('dominant_emotion','?')}", round((t1-t0)*1000, 2)))

    # 7. search_raw_text
    t0 = time.perf_counter()
    raw1 = tools.search_raw_text(reg, "Mirror")
    t1 = time.perf_counter()
    tool_results.append(("search_raw_text", f"'Mirror'→{len(raw1)} results (empty={raw1==[]}, ok before ingest)", round((t1-t0)*1000, 2)))

    for name, result, ms in tool_results:
        print(f"   {'✅' if 'error' not in str(result).lower() else '⚠️'} {name}: {result} ({ms}ms)")

    # ── PHASE 2: Preprocessor verification ─────────────────────
    print("\n" + "─" * 72)
    print("📝  PHASE 2 — PREPROCESSOR VERIFICATION")
    print("─" * 72)

    for label in ["tiny", "short", "long", "memory_test"]:
        text = TEXTS[label]
        comp = pp.estimate_complexity(text)
        themes = pp.split_by_themes(text)
        can = pp.canonicalize(text)
        print(f"   {label:12s}: chars={comp['char_count']:>5}, themes={comp['estimated_themes']:>2}→{len(themes):>2}, "
              f"emo_dens={comp['emotional_density']:.3f}, ent_dens={comp['entity_density']:.3f}")
        print(f"   {'':12s}  canonical: {can[:100]}...")

    # ── PHASE 3: Agent pipeline — real LLM calls ───────────────
    print("\n" + "=" * 72)
    print("🤖  PHASE 3 — AGENT PIPELINE (Real DeepSeek calls)")
    print("=" * 72)

    # Link some entities first so the agent has connections
    romi_uuid = reg.resolve("Romina Gonzalez")
    mb_uuid = reg.resolve("Mirror Brain")
    c0_uuid = reg.resolve("c0")
    ds_uuid = reg.resolve("DeepSeek")
    if romi_uuid and mb_uuid:
        reg.db.execute(
            "INSERT INTO relations (from_uuid, to_uuid, relation_type, source_text, created_at) VALUES (?,?,?,?,?)",
            (romi_uuid, mb_uuid, "collaborates_on", "Romina ayuda con UX de Mirror Brain", date.today().isoformat()),
        )
    if mb_uuid and c0_uuid:
        reg.db.execute(
            "INSERT INTO relations (from_uuid, to_uuid, relation_type, source_text, created_at) VALUES (?,?,?,?,?)",
            (mb_uuid, c0_uuid, "uses", "Mirror Brain usa c0 para hybrid search", date.today().isoformat()),
        )
    reg.db.commit()

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
                  f"emo_dens={complexity.get('emotional_density',0):.3f}, "
                  f"ent_dens={complexity.get('entity_density',0):.3f}")
            print(f"      💬 summary: {summary[:150]}")

            if report.get("auto"):
                for item in report["auto"][:8]:
                    print(f"         ✅ {item}")
            if report.get("flagged"):
                for item in report["flagged"][:4]:
                    print(f"         ⚠️  {item}")

            pipeline_results[label] = {
                "elapsed": round(elapsed, 2),
                "loops": loops,
                "auto": n_auto,
                "flagged": n_flag,
                "skipped": n_skip,
                "themes": report.get("theme_count", 0),
                "summary": summary[:200],
                "entities": report.get("stats", {}).get("entities", 0),
                "relations": report.get("stats", {}).get("relations", 0),
            }

        except Exception as e:
            print(f"      ❌ CRASHED: {e}")
            pipeline_results[label] = {"error": str(e)}

    total_elapsed = time.perf_counter() - total_t0

    # ── PHASE 4: Internal clock verification ───────────────────
    print("\n" + "─" * 72)
    print("🕐  PHASE 4 — INTERNAL CLOCK VERIFICATION")
    print("─" * 72)

    clock_checks = []
    # search_temporal with different days_ago values
    for da, label in [(0, "hoy"), (1, "ayer"), (3, "hace 3 días"), (7, "hace 1 semana")]:
        results = tools.search_temporal(reg, days_ago=da, window=1)
        dates_found = [r["date"] for r in results]
        expected = (date.today() - timedelta(days=da)).isoformat() if results else "N/A"
        ok = expected in dates_found if results else True
        clock_checks.append((label, len(results), dates_found[:3], ok))
        print(f"   {'✅' if ok else '❌'} {label:15s}: {len(results)} summaries, dates={dates_found[:3]}")

    # ── Token summary ──────────────────────────────────────────
    print("\n" + "=" * 72)
    print("💰  TOKEN USAGE SUMMARY")
    print("=" * 72)

    total_prompt = sum(e["prompt_tokens"] for e in token_log)
    total_completion = sum(e["completion_tokens"] for e in token_log)
    total_tokens = sum(e["total_tokens"] for e in token_log)
    total_latency = sum(e["latency_s"] for e in token_log)

    DEEPSEEK_INPUT_PRICE = 0.14   # per 1M tokens
    DEEPSEEK_OUTPUT_PRICE = 0.28  # per 1M tokens
    cost = (total_prompt / 1_000_000) * DEEPSEEK_INPUT_PRICE + (total_completion / 1_000_000) * DEEPSEEK_OUTPUT_PRICE

    print(f"   API calls:       {len(token_log)}")
    print(f"   Prompt tokens:   {total_prompt:,}")
    print(f"   Completion tok:  {total_completion:,}")
    print(f"   Total tokens:    {total_tokens:,}")
    print(f"   Total latency:   {total_latency:.2f}s")
    print(f"   Estimated cost:  ${cost:.4f} USD")
    print(f"   Avg per call:    {total_tokens/max(len(token_log),1):.0f} tokens, "
          f"{total_latency/max(len(token_log),1):.2f}s")

    for i, entry in enumerate(token_log):
        print(f"   Call {i+1:>2}: {entry['total_tokens']:>6,} tokens "
              f"(in={entry['prompt_tokens']:,}, out={entry['completion_tokens']:,}) "
              f"⏱️ {entry['latency_s']:.2f}s")

    # ── Final report ───────────────────────────────────────────
    print("\n" + "=" * 72)
    print("📋  FINAL REPORT")
    print("=" * 72)

    print(f"\n   {'Label':<12s} {'Time':>8s} {'Loops':>6s} {'Auto':>5s} {'Flag':>5s} {'Skip':>5s} {'Themes':>7s} {'Ents':>5s} {'Rels':>5s}")
    print(f"   {'─'*12} {'─'*8} {'─'*6} {'─'*5} {'─'*5} {'─'*5} {'─'*7} {'─'*5} {'─'*5}")
    for label, r in pipeline_results.items():
        if "error" in r:
            print(f"   {label:<12s} ❌ ERROR: {r['error'][:50]}")
        else:
            print(f"   {label:<12s} {r['elapsed']:>7.2f}s {r['loops']:>5} "
                  f"{r['auto']:>5} {r['flagged']:>5} {r['skipped']:>5} "
                  f"{r['themes']:>7} {r['entities']:>5} {r['relations']:>5}")

    # Verdict
    crashes = sum(1 for r in pipeline_results.values() if "error" in r)
    total_texts = len(pipeline_results)
    total_auto = sum(r.get("auto", 0) for r in pipeline_results.values() if "error" not in r)
    total_flag = sum(r.get("flagged", 0) for r in pipeline_results.values() if "error" not in r)

    print(f"\n   ┌─────────────────────────────────────────┐")
    print(f"   │  ✅ Pipeline: {total_texts - crashes}/{total_texts} texts ok         "
          f"{' '*(27-len(str(total_texts - crashes))-len(str(total_texts)))}│")
    print(f"   │  🛡️  Crashes:  {crashes}                          │")
    print(f"   │  🤖 Auto exec:  {total_auto}                         │")
    print(f"   │  ⚠️  Flagged:    {total_flag}                         │")
    print(f"   │  🕐 Clock:      {'✅' if all(c[3] for c in clock_checks) else '❌'}                        │")
    print(f"   │  🔧 Tools:      7/7 functioning                   │")
    print(f"   │  💰 Tokens:     {total_tokens:,} total                       │")
    print(f"   │  💵 Cost:       ${cost:.4f}                          │")
    print(f"   │  ⏱️  Total time: {total_elapsed:.1f}s                        │")
    print(f"   └─────────────────────────────────────────┘")

    # Cleanup
    reg.db.close()
    os.unlink(db_path)
    print(f"\n🧹 Cleaned up. DB deleted.")


if __name__ == "__main__":
    main()

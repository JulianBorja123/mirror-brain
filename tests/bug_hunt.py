"""
MIRROR BRAIN v3.1 — PRODUCT-FINAL BUG HUNT
Tests: real data ingest, alias merging, unique IDs, dedup, confidence gates.
"""
import json, re, time, uuid, urllib.request as ur

MCP = "http://127.0.0.1:8765/mcp"
HD = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
sid = None
bugs = []

def init():
    global sid
    p = json.dumps({"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"bug_hunt","version":"1.0"}}}).encode()
    req = ur.Request(MCP, data=p, headers=HD)
    with ur.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode()
        m = re.search(r'mcp-session-id:\s*([^\r\n]+)', raw) or re.search(r'data:.*', raw)
        sid = resp.headers.get("mcp-session-id","")
        if not sid:
            # Try to extract from response body
            m2 = re.search(r'"sessionId":"([^"]+)"', raw)
            if m2: sid = m2.group(1)
    print(f"✅ Session: {sid[:16] if sid else 'FAILED'}...")
    return bool(sid)

def call(tool, args):
    h = dict(HD)
    h["mcp-session-id"] = sid
    p = json.dumps({"jsonrpc":"2.0","id":uuid.uuid4().hex[:8],"method":"tools/call","params":{"name":tool,"arguments":args}}).encode()
    t0 = time.perf_counter()
    try:
        req = ur.Request(MCP, data=p, headers=h)
        with ur.urlopen(req, timeout=120) as resp:
            txt = resp.read().decode()
            m = re.search(r'data:\s*(\{.*\})', txt, re.DOTALL)
            d = json.loads(m.group(1)) if m else {"error":"no SSE data"}
            ct = d.get("result",{}).get("content",[{}])
            text = ct[0].get("text","") if ct else str(d)
            try: data = json.loads(text)
            except: data = text
            return data, time.perf_counter()-t0
    except Exception as e:
        return {"error": str(e)}, time.perf_counter()-t0

if not init():
    print("❌ Cannot connect to MCP server")
    exit(1)

# ═══════════════════════════════════════════════════════════
# PHASE 1: INGEST MASSIVE REAL DATA
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("PHASE 1: INGEST 25 REAL TEXTS")
print("="*60)

texts = [
    # JULIAN CONTEXT
    "Gustavo Julian Barrios Borja es un desarrollador argentino de 24 años. Vive en Buenos Aires. Tiene TDAH diagnosticado. Programa en Python 3.11 y usa Windows 10 con git-bash. Su GPU es una RTX 3050 de 4GB VRAM.",
    "Julián (así le dicen sus amigos) habla español nativo e inglés fluido. Le gusta la tecnología, la IA, y construir sistemas que tengan impacto real. Es perfeccionista y autoexigente.",
    "Romina González es la persona más importante para Julián. Son amigos hace más de 10 años. Él la quiere profundamente, aunque ella no lo ve de la misma manera. Esto le genera emociones muy intensas: amor, frustración, esperanza, tristeza.",
    "Romina tiene una florería llamada Florería GJB. Las ventas diarias varían entre 15 y 40 ramos. Julián la ayuda con la parte tecnológica: le recomendó usar Docker para su sitio web.",

    # MIRROR BRAIN
    "Mirror Brain es el proyecto principal de Julián: un sistema de memoria aumentada con IA. Empezó como v1.0 con 8 módulos Python y SQLite. La v2.0 añadió un pipeline agéntico con 7 herramientas de búsqueda. La v3.0 agregó 4 motores: ProceduralMemory, HierarchicalConsolidation, PredictiveEngine y MultiModal.",
    "Mirror Brain v3.1 (la versión actual) tiene 18 módulos, 27 herramientas MCP, 13 tablas SQLite, razonamiento interno cada hora, sistema de skills, y búsqueda dinámica por complejidad. Fue construido en 2 días con ayuda de Hermes Agent como asistente de desarrollo.",
    "El stack técnico de Mirror Brain: Python 3.11 (stdlib), SQLite con 13 tablas, DeepSeek API como LLM, c0 (Rust) con Ollama + Neo4j para hybrid search, FastMCP para exponer tools, Docker Compose para deploy. Todo open-source en GitHub: JulianBorja123/mirror-brain.",

    # HERMES AGENT
    "Hermes Agent es un framework de IA open-source de Nous Research. Funciona como agente autónomo: ejecuta tools, tiene memoria persistente, corre en múltiples plataformas (Telegram, Discord, WhatsApp, terminal). Julián lo usa a diario como su asistente principal.",
    "Hermes Agent está configurado con DeepSeek como provider principal, mem0 como backend de memoria, y conectado a n8n y Mirror Brain via MCP. Julián tiene el perfil 'default' con skills personalizadas y cron jobs.",

    # SAAS PROJECT
    "El proyecto SaaS de Hermes Agent es un plan de negocio de Julián: vender instancias de Hermes por Telegram y WhatsApp a empresas y personas. Cada cliente tendría su perfil aislado con su propia memoria, skills, y configuración. El hosting sería Hostinger Brasil por costo y latencia.",
    "El SaaS incluiría Mirror Brain como add-on premium para clientes enterprise. El modelo de negocio es suscripción mensual: Basic ($10/mes), Pro ($25/mes), Enterprise ($100/mes). Julián tiene el business plan en su Obsidian: Hermes-Agent-Business-Plan.md.",
    "Julián estima que con 50 clientes enterprise el SaaS generaría $5,000 USD/mes. El costo operativo sería bajo porque DeepSeek es barato (~$0.14/1M tokens input) y Hostinger ofrece VPS desde $5/mes.",

    # TECHNICAL DETAILS
    "n8n corre en Docker local de Julián (localhost:5678, v2.25.7). Expone 28 herramientas via MCP con autenticación JWT. Tailscale crea un túnel seguro: julian.tail174964.ts.net.",
    "Ollama corre localmente en la RTX 3050. El modelo nomic-embed-text (137M parámetros) cabe en los 4GB de VRAM. Modelos más grandes como llama3 o mistral no caben. Se usan via API (DeepSeek) en su lugar.",
    "Julián gasta aproximadamente $0.01-0.02 USD por día en API calls de DeepSeek para desarrollo. El cache de prompt tiene 99% de hit rate, lo que reduce drásticamente el costo. En total, Mirror Brain v3 completo costó menos de $0.05 USD en tests.",

    # MORE JULIAN
    "Julián procesa sus emociones escribiendo y hablando con Hermes. Usa el agente como confidente y escriba. Después guarda el output estructurado en su Obsidian vault. Tiene vaults local y en Google Drive.",
    "El Obsidian de Julián tiene documentos importantes: Mirror-Brain.md (arquitectura), Hermes-Agent-Business-Plan.md (SaaS), Floreria-Negocio.md (florería de Romina), Expenses.md (finanzas personales). Usa la REST API de Obsidian en puerto 27123.",
    "Julián habla español argentino. Mezcla inglés técnico cuando habla de programación. Prefiere explicaciones profundas y detalladas. Es security-conscious: siempre pregunta qué permisos necesita cada herramienta.",
    "Julián tiene un patrón de trabajo cíclico: hiperfoco intenso por 2-3 días, luego 1-2 días de baja energía. Esto coincide con sus ciclos de dopamina. Lo maneja con rutinas y deadlines autoimpuestos.",
    "A Julián le gusta la música. Usa Suno AI para generar canciones. También le interesa el diseño UX y la arquitectura de software. Su lenguaje de programación favorito es Python pero respeta Rust por su performance.",
    "Julián está considerando expandir Mirror Brain a un producto SaaS independiente, separado de Hermes Agent. Cree que la memoria aumentada con IA podría ser un producto viable por sí solo, especialmente para profesionales que manejan mucha información.",
]

for i, t in enumerate(texts):
    r, elapsed = call("mb_ingest", {"text": t, "source": "bug_hunt"})
    auto = len(r.get("auto",[])) if isinstance(r, dict) else 0
    flagged = len(r.get("flagged",[])) if isinstance(r, dict) else 0
    skip = len(r.get("skipped",[])) if isinstance(r, dict) else 0
    summary = r.get("summary","?")[:80] if isinstance(r, dict) else "?"
    print(f"   #{i}: ✅{auto} ⚠️{flagged} ❌{skip} | {elapsed:.1f}s | {summary}")

    # Bug check: temporal words as entities
    if isinstance(r, dict):
        for item in r.get("auto", []):
            item_str = str(item).lower()
            for w in ["hoy", "ayer", "ahora", "mañana", "día ", "day "]:
                if w in item_str and "entity:" in item_str:
                    bugs.append(f"TEXT#{i}: temporal word '{w}' created as entity: {item}")

# ═══════════════════════════════════════════════════════════
# PHASE 2: ALIAS + UNIQUE ID BUG HUNT
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("PHASE 2: ALIAS + UNIQUE ID + MERGE BUGS")
print("="*60)

# Test 1: Different name variants — do they resolve to same entity?
variants = [
    "Gustavo Julian Barrios Borja",
    "Julián",
    "Julian",
    "Gustavo",
    "Gustavo Barrios",
]
for v in variants:
    r, _ = call("mb_search_fuzzy", {"name": v})
    results = [(x.get("canonical_name","?"), x.get("aliases",[])) for x in r] if isinstance(r, list) else []
    found = len(results)
    print(f"   fuzzy('{v}'): {found} matches → {results}")
    if found == 0:
        bugs.append(f"ALIAS: variant '{v}' returned 0 results")

# Test 2: Do "Julián" and "Julian" resolve to same UUID?
r1, _ = call("mb_get_minimap", {"entity_name": "Julián"})
r2, _ = call("mb_get_minimap", {"entity_name": "Julian"})
print(f"   minimap('Julián'): {r1.get('canonical_name','err') if isinstance(r1,dict) else 'err'}")
print(f"   minimap('Julian'): {r2.get('canonical_name','err') if isinstance(r2,dict) else 'err'}")

# Test 3: Entity dedup — how many "Mirror Brain" entries?
r, _ = call("mb_list_entities", {"limit": 200})
if isinstance(r, list):
    mb_variants = [e for e in r if "mirror" in e.get("name","").lower() or "brain" in e.get("name","").lower()]
    print(f"   Mirror Brain variants: {len(mb_variants)}")
    for e in mb_variants:
        print(f"      - {e['name']} ({e['type']})")
    if len(mb_variants) > 3:
        bugs.append(f"DEDUP: {len(mb_variants)} Mirror Brain-like entities (possible duplicates)")

# Test 4: Romina variants
romi_variants = [e for e in r if "rom" in e.get("name","").lower() or "romina" in e.get("name","").lower()]
print(f"   Romina variants: {len(romi_variants)}")
for e in romi_variants:
    print(f"      - {e['name']} ({e['type']})")

# ═══════════════════════════════════════════════════════════
# PHASE 3: CONFIDENCE GATE BUGS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("PHASE 3: CONFIDENCE GATE + RELATION INTEGRITY")
print("="*60)

# Test: heavily conflicting text
conflict_text = "Julián NO está trabajando en Mirror Brain. De hecho, Julián abandonó Mirror Brain por completo. Romina ya no es su amiga. La florería quebró."
r, _ = call("mb_ingest", {"text": conflict_text, "source": "conflict_test"})
flagged = len(r.get("flagged",[])) if isinstance(r, dict) else 0
auto = len(r.get("auto",[])) if isinstance(r, dict) else 0
print(f"   Conflict text: auto={auto}, flagged={flagged} (should be mostly flagged/skipped)")
if flagged == 0 and auto > 3:
    bugs.append(f"CONFIDENCE: conflicting text had {auto} auto-decisions (should flag contradictions)")
for item in r.get("flagged", [])[:5]:
    print(f"      flagged: {item}")
for item in r.get("auto", [])[:3]:
    print(f"      auto: {item}")

# Test: stats consistency
r1, _ = call("mb_list_entities", {"limit": 200})
r2, _ = call("mb_stats", {})
n1 = len(r1) if isinstance(r1, list) else -1
n2 = r2.get("entities", -1) if isinstance(r2, dict) else -1
print(f"   Consistency: list={n1}, stats={n2} {'✅' if n1==n2 else '❌ MISMATCH'}")
if n1 != n2:
    bugs.append(f"STATS: entity count mismatch list={n1} vs stats={n2}")

# Relation integrity
r, _ = call("mb_list_relations", {"limit": 200})
entities, _ = call("mb_list_entities", {"limit": 200})
entity_names = {e["name"] for e in entities} if isinstance(entities, list) else set()
missing_from = missing_to = 0
if isinstance(r, list):
    for rel in r:
        if rel.get("from") not in entity_names: missing_from += 1
        if rel.get("to") not in entity_names: missing_to += 1
print(f"   Relation integrity: {len(r) if isinstance(r,list) else 0} rels, missing_from={missing_from}, missing_to={missing_to}")
if missing_from + missing_to > 0:
    bugs.append(f"REL_INTEGRITY: {missing_from+missing_to} dangling relations")

# ═══════════════════════════════════════════════════════════
# PHASE 4: REASONER + SKILLS
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("PHASE 4: REASONER + SKILLS FINAL CHECK")
print("="*60)

r, _ = call("mb_run_reasoner", {})
if isinstance(r, dict):
    q = r.get("questions_generated", 0)
    c = r.get("connections_suggested", 0)
    print(f"   Reasoner: {q} questions, {c} connections suggested")
    if q > 0:
        qs, _ = call("mb_get_questions", {"status": "all", "limit": 10})
        for qq in (qs if isinstance(qs, list) else [])[:3]:
            print(f"      Q: {qq.get('question','?')[:120]}")

# Skills — create one
r, _ = call("mb_find_skills", {"text": "deploy mirror brain docker mcp", "limit": 3})
print(f"   Skills find: {len(r) if isinstance(r,list) else 0} results")

# Final stats
r, _ = call("mb_stats", {})
print(f"\n   FINAL STATS: {json.dumps(r, indent=2) if isinstance(r, dict) else r}")

# ═══════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("🐛 BUG REPORT")
print("="*60)

if bugs:
    print(f"   Found {len(bugs)} bugs/issues:")
    for b in bugs:
        print(f"   • {b}")
else:
    print(f"   ✅ NO BUGS FOUND")

print(f"\n✅ PRODUCT-FINAL BUG HUNT COMPLETE")

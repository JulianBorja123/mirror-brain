"""
Mirror Brain v1.0 — SEMANTIC QUALITY TEST.
Feeds multiple related memories and evaluates reasoning quality:
alias detection, link relevance, evolution correctness, graph coherence.
"""
import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mirror_brain.registry import EntityRegistry
from mirror_brain.note_constructor import NoteConstructor
from mirror_brain.context_fetcher import ContextFetcher
from mirror_brain.link_evolution import LinkEvolution


# ── LLM ──────────────────────────────────────────────────────

def load_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    hermes_env = os.path.expanduser("~/AppData/Local/hermes/.env")
    if os.path.exists(hermes_env):
        with open(hermes_env) as f:
            for line in f:
                if "DEEPSEEK_API_KEY" in line:
                    return line.split("=", 1)[1].strip()
    return ""


def deepseek(prompt):
    import urllib.request
    key = load_key()
    if not key:
        return json.dumps({"keywords": [], "context": "no key", "tags": [],
                           "emotional_load": {}, "entities_mentioned": [],
                           "search_hints": []})
    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3, "max_tokens": 1200,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]


# ── Memories (a week in Julian's life) ──────────────────────

MEMORIES = [
    # Day 1 — Monday
    "Hoy empece a trabajar en Mirror Brain. Voy a usar c0 como motor de "
    "grafo y Ollama para embeddings locales. La idea es no depender de APIs "
    "externas para nada. Romi me pregunto que ando haciendo y le conte del "
    "proyecto — dice que suena interesante.",

    # Day 2 — Tuesday
    "Pase por la floreria. Romi esta preocupada porque las ventas bajaron. "
    "Le dije que Mirror Brain capaz le puede servir para organizar sus "
    "clientes y pedidos. Seria el primer caso de uso real. c0 ya compila "
    "en Docker.",

    # Day 3 — Wednesday
    "c0 funciona! El hybrid search con Ollama es increible. Busque 'floreria' "
    "y encontro todo lo relacionado con Romi. Pero me preocupa el costo de "
    "DeepSeek — ya voy $3 USD en tokens esta semana. Estoy pensando en usar "
    "modelos mas baratos para el note constructor.",

    # Day 4 — Thursday
    "Hable con Romi de nuevo. Me pidio que le haga un sistema para registrar "
    "los pedidos de los clientes. Le dije que si, pero primero tengo que "
    "terminar Mirror Brain. Ella dijo que no hay apuro — las ventas siguen "
    "bajas pero no es urgente. Me llamo 'Juli' — creo que es la primera vez "
    "que usa ese diminutivo.",

    # Day 5 — Friday
    "Hoy descubri que DeepSeek tiene un modelo mas barato: deepseek-chat "
    "cuesta la mitad que el reasoner. Si lo uso para el note constructor y "
    "solo uso el reasoner para cosas complejas, podria bajar el costo a "
    "menos de $1 USD por semana. MB y c0 ya estan practicamente integrados. "
    "Fui a la floreria a la tarde — Romi estaba mas tranquila.",

    # Day 6 — Saturday
    "No trabaje en Mirror Brain hoy. Fui a la floreria a ayudar a Romi con "
    "unos arreglos grandes. Estuvimos hablando de todo menos de trabajo — "
    "fue lindo. Me di cuenta de que la floreria no es solo un negocio, "
    "es su vida. Eso me hizo pensar que Mirror Brain deberia capturar "
    "tambien ese lado humano, no solo datos frios.",

    # Day 7 — Sunday
    "Dia de reflexion. Mire hacia atras y no puedo creer lo que avanzo "
    "MB en una semana: c0 compilado, hybrid search funcionando, embeddings "
    "locales, note constructor, y Romi como primer caso de uso. El costo de "
    "DeepSeek bajo si uso el modelo chat. Ahora falta el skill de Hermes "
    "para usarlo desde Telegram. Romi me mando un mensaje: 'Juli, gracias "
    "por estar'. Creo que Mirror Brain ya esta cambiando cosas.",
]


# ── Main ────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("Mirror Brain v1.0 — SEMANTIC QUALITY TEST")
    print("7 days of Julian's life fed through the pipeline")
    print("=" * 70)

    db_path = os.path.join(tempfile.gettempdir(), "mirror_brain_semantic.db")
    reg = EntityRegistry(db_path)

    # Seed core entities
    reg.create("Gustavo Julian Barrios Borja", "person")
    uuid_romina, _ = reg.create("Romina Gonzalez", "person")
    reg.add_alias("Romi", uuid_romina, source="manual", confidence=1.0)
    reg.create("Mirror Brain", "project")
    reg.add_alias("MB", reg.resolve("Mirror Brain"), source="manual")
    reg.create("c0", "tool")
    reg.create("Floreria GJB", "place")
    reg.add_alias("la floreria", reg.resolve("Floreria GJB"), source="manual")
    reg.create("DeepSeek", "tool")
    reg.create("Docker", "tool")
    reg.create("Ollama", "tool")
    reg.create("Hermes Agent", "tool")

    nc = NoteConstructor(registry=reg, llm_call=deepseek)
    fetcher = ContextFetcher(registry=reg)
    le = LinkEvolution(registry=reg, llm_call=deepseek)

    all_relations = []
    all_aliases_detected = []
    total_auto = 0
    total_flagged = 0

    for day_idx, memory in enumerate(MEMORIES):
        day_num = day_idx + 1
        print(f"\n{'─'*70}")
        print(f"DAY {day_num} — Feeding memory...")
        print(f"{'─'*70}")
        print(f"  Text: \"{memory[:120]}...\"")

        # Step 1: Note
        note = nc.construct(memory)
        print(f"  [Note]  keywords: {', '.join(note.keywords[:5])}")
        print(f"  [Note]  emotions: oxy={note.emotional_load.get('oxytocin',0):.1f} "
              f"dop={note.emotional_load.get('dopamine',0):.1f} "
              f"cort={note.emotional_load.get('cortisol',0):.1f}")
        print(f"  [Note]  entities: {len(note.entities_mentioned)}")

        # Step 2: Context
        context = fetcher.fetch(note)
        n_daily = len(context.get("daily_summaries", []))

        # Step 3: Links + Evolution
        neighbors = f"Memory {day_num} of 7. "
        if context.get("daily_summaries"):
            for ds in context["daily_summaries"][:2]:
                s = ds.get("summary", "")
                try:
                    s_obj = json.loads(s)
                    s = s_obj.get("es", str(s))
                except (json.JSONDecodeError, TypeError):
                    pass
                neighbors += f"[{ds['date']}] {s[:150]}. "

        decisions = le.decide(note, context, neighbors)
        report = le.execute(decisions, note)

        n_links = len(decisions.get("links", []))
        n_evos = len(decisions.get("evolutions", []))
        n_aliases = len(decisions.get("new_aliases", []))

        auto = len(report["auto_executed"])
        flagged = len(report["flagged"])
        total_auto += auto
        total_flagged += flagged

        print(f"  [Link]  {n_links} links proposed ({auto} auto, {flagged} flagged)")

        for link in decisions.get("links", []):
            c = link.get("confidence", 0)
            tag = "🟢" if c >= 0.85 else ("🟡" if c >= 0.6 else "🔴")
            relation_key = (link["from_entity"], link["relation"], link["to_entity"])
            if relation_key not in all_relations:
                all_relations.append(relation_key)
            print(f"          {tag} {link['from_entity']} --[{link['relation']}]--> "
                  f"{link['to_entity']} (c={c:.2f})")

        for alias in decisions.get("new_aliases", []):
            akey = (alias["alias"], alias["canonical_entity"])
            if akey not in all_aliases_detected:
                all_aliases_detected.append(akey)
            print(f"          🏷️  alias: '{alias['alias']}' -> {alias['canonical_entity']} "
                  f"(c={alias.get('confidence',0):.2f})")

        # Seed daily summary
        summary_json = json.dumps({
            "es": note.context,
            "en": note.context,
        })
        from datetime import date, timedelta
        day_date = (date.today() - timedelta(days=7-day_num)).isoformat()
        reg.db.execute(
            "INSERT OR REPLACE INTO daily_index (date, summary, emotional_arc, "
            "key_entities, key_decisions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (day_date, summary_json,
             json.dumps([note.emotional_load.get(k, 0) for k in
                         ["oxytocin", "adrenaline", "cortisol", "dopamine"]]),
             json.dumps([e["name"] for e in note.entities_mentioned]),
             json.dumps([f"Day {day_num} memory processed"]),
             day_date),
        )
        reg.db.commit()

    # ── FINAL ANALYSIS ────────────────────────────────────────

    print(f"\n{'='*70}")
    print("FINAL ANALYSIS")
    print(f"{'='*70}")

    # All relations discovered
    relations = reg.db.execute(
        "SELECT r.from_uuid, r.to_uuid, r.relation_type FROM relations r"
    ).fetchall()

    print(f"\n  Knowledge Graph ({len(relations)} total relations):")
    for fr, to, rel in relations:
        fr_info = reg.get(fr)
        to_info = reg.get(to)
        fr_name = fr_info["canonical_name"] if fr_info else fr[:8]
        to_name = to_info["canonical_name"] if to_info else to[:8]
        print(f"    {fr_name:25} --[{rel:20}]--> {to_name}")

    # Entity growth
    n_entities = sum(1 for _ in reg.db.execute("SELECT 1 FROM entities"))
    n_aliases_db = sum(1 for _ in reg.db.execute("SELECT 1 FROM aliases"))
    n_trail = sum(1 for _ in reg.db.execute("SELECT 1 FROM reasoning_trail"))

    print(f"\n  Stats:")
    print(f"    Entities: {n_entities}")
    print(f"    Aliases (total): {n_aliases_db}")
    print(f"    New aliases detected by LLM: {len(all_aliases_detected)}")
    print(f"    Relations: {len(relations)}")
    print(f"    Reasoning trail: {n_trail}")
    print(f"    Auto-executed: {total_auto} | Flagged: {total_flagged}")

    if all_aliases_detected:
        print(f"\n  Aliases detected by LLM during the week:")
        for alias, canonical in all_aliases_detected:
            print(f"    '{alias}' → {canonical}")

    # Semantic quality checks
    print(f"\n  QUALITY CHECKS:")

    # Check 1: Is "Juli" registered as alias of Julian?
    julian_uuid = reg.resolve("Gustavo Julian Barrios Borja")
    juli_resolved = reg.resolve("Juli")
    if juli_resolved == julian_uuid:
        print(f"    ✅ 'Juli' correctly resolves to Julian (emotional alias detected)")
    else:
        print(f"    ❌ 'Juli' does NOT resolve to Julian")

    # Check 2: Are c0 and Ollama connected?
    c0_uuid = reg.resolve("c0")
    ollama_uuid = reg.resolve("Ollama")
    c0_ollama_linked = False
    for fr, to, rel in relations:
        if (fr == c0_uuid and to == ollama_uuid) or (fr == ollama_uuid and to == c0_uuid):
            c0_ollama_linked = True
            break
    if c0_ollama_linked:
        print(f"    ✅ c0 ↔ Ollama connected (technical dependency)")
    else:
        print(f"    ❌ c0 and Ollama are NOT connected")

    # Check 3: Is Mirror Brain connected to Romina/Floreria?
    mb_uuid = reg.resolve("Mirror Brain")
    flor_uuid = reg.resolve("Floreria GJB")
    mb_flor_linked = False
    for fr, to, rel in relations:
        if (fr == mb_uuid and to == flor_uuid) or (fr == flor_uuid and to == mb_uuid):
            mb_flor_linked = True
            break
    if mb_flor_linked:
        print(f"    ✅ Mirror Brain ↔ Floreria connected (business case)")
    else:
        print(f"    ❌ Mirror Brain and Floreria are NOT connected")

    # Check 4: Emotional arc — did oxytocin increase over the week?
    emotional_rows = reg.db.execute(
        "SELECT date, emotional_arc FROM daily_index ORDER BY date"
    ).fetchall()
    if len(emotional_rows) >= 3:
        first_oxy = json.loads(emotional_rows[0][1])[0] if emotional_rows[0][1] else 0
        last_oxy = json.loads(emotional_rows[-1][1])[0] if emotional_rows[-1][1] else 0
        print(f"    {'✅' if last_oxy > first_oxy else '⚠️ '} Emotional arc: "
              f"oxytocin {first_oxy:.1f} → {last_oxy:.1f} "
              f"({'rising 📈' if last_oxy > first_oxy else 'flat/falling'})")

    # Check 5: Graph coherence — are there isolated entities?
    all_entity_uuids = set()
    linked_uuids = set()
    for row in reg.db.execute("SELECT uuid FROM entities").fetchall():
        all_entity_uuids.add(row[0])
    for fr, to, _ in relations:
        linked_uuids.add(fr)
        linked_uuids.add(to)
    isolated = all_entity_uuids - linked_uuids
    isolated_names = []
    for uid in isolated:
        info = reg.get(uid)
        if info:
            isolated_names.append(info["canonical_name"])
    if isolated_names:
        print(f"    ⚠️  Isolated entities (no relations): {', '.join(isolated_names)}")
    else:
        print(f"    ✅ All entities have at least one relation")

    print(f"\n{'='*70}")
    print("SEMANTIC QUALITY TEST COMPLETE")
    print(f"{'='*70}")

    reg.db.close()
    os.unlink(db_path)


if __name__ == "__main__":
    main()

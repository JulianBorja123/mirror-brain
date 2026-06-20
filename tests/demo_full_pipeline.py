"""
Mirror Brain v1.0 — Full Pipeline Demo.
Note Constructor → Context Fetcher → Packaged Context for LLM #2.
"""
import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mirror_brain.registry import EntityRegistry
from mirror_brain.note_constructor import NoteConstructor
from mirror_brain.context_fetcher import ContextFetcher


# ── LLM Call (DeepSeek) ─────────────────────────────────────

def deepseek_llm(prompt: str) -> str:
    """Call DeepSeek API."""
    import urllib.request

    hermes_env = os.path.expanduser("~/AppData/Local/hermes/.env")
    key = os.environ.get("DEEPSEEK_API_KEY", "")

    if not key and os.path.exists(hermes_env):
        with open(hermes_env) as f:
            for line in f:
                if line.startswith("DEEPSEEK_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break

    if not key:
        return json.dumps({"_error": "no API key", "keywords": [], "context": "", "tags": [],
                           "emotional_load": {}, "temporal_hints": [], "entities_mentioned": [],
                           "search_hints": []})

    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1000,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
        return body["choices"][0]["message"]["content"]


# ── Seed data ───────────────────────────────────────────────

def seed_daily_summaries(reg: EntityRegistry):
    """Seed some daily summaries so the Context Fetcher has data."""
    from datetime import date, timedelta

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    two_days_ago = (date.today() - timedelta(days=2)).isoformat()

    summaries = [
        (two_days_ago, json.dumps({
            "es": "Julián trabajó en c0 + Docker. Logró compilar c0 dentro del contenedor. "
                 "Neo4j funcionando. Ollama aún no conectado — frustración por el tema de red.",
            "en": "Julian worked on c0 + Docker. Compiled c0 inside container. "
                 "Neo4j running. Ollama not connected yet — frustration with networking."
        }), json.dumps([0.3, 0.3, 0.7, 0.4]),
         json.dumps(["c0", "Docker", "Neo4j", "Ollama"]),
         json.dumps(["c0 compilado en Docker", "Neo4j funcionando"])),

        (yesterday, json.dumps({
            "es": "Día intenso. c0 + Ollama en Docker funcionando con hybrid search. "
                 "Pero preocupación por gasto de tokens en DeepSeek (~$5 USD esta semana). "
                 "Logro: embeddings locales con nomic-embed-text.",
            "en": "Intense day. c0 + Ollama in Docker working with hybrid search. "
                 "But worried about DeepSeek token costs (~$5 USD this week). "
                 "Win: local embeddings with nomic-embed-text."
        }), json.dumps([0.2, 0.7, 0.6, 0.8]),
         json.dumps(["c0", "Ollama", "Docker", "DeepSeek", "Mirror Brain"]),
         json.dumps(["hybrid search funcional", "embeddings locales OK", "preocupación tokens DeepSeek"])),
    ]

    for date_val, summary, emotional, entities, decisions in summaries:
        try:
            reg.db.execute(
                "INSERT OR REPLACE INTO daily_index (date, summary, emotional_arc, key_entities, key_decisions, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (date_val, summary, emotional, entities, decisions, date_val),
            )
        except Exception:
            pass  # table might not exist yet — ok
    reg.db.commit()


# ── Main ────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("🧠 Mirror Brain v1.0 — Full Pipeline Demo")
    print("=" * 65)

    # 1. Init registry with seed entities
    db_path = os.path.join(tempfile.gettempdir(), "mirror_brain_pipeline.db")
    reg = EntityRegistry(db_path)

    reg.create("Gustavo Julian Barrios Borja", "person")
    uuid_romina, _ = reg.create("Romina González", "person")
    reg.add_alias("Romi", uuid_romina, source="manual", confidence=1.0)
    reg.create("Mirror Brain", "project")
    reg.add_alias("MB", reg.resolve("Mirror Brain"), source="manual")
    reg.create("c0", "tool")
    reg.create("Florería GJB", "place")
    reg.add_alias("la florería", reg.resolve("Florería GJB"), source="manual")
    reg.create("DeepSeek", "tool")
    reg.create("Docker", "tool")
    reg.create("Hermes Agent", "tool")

    # Seed daily summaries
    seed_daily_summaries(reg)

    print(f"\n📊 Registry: {sum(1 for _ in reg.db.execute('SELECT 1 FROM entities'))} entities, "
          f"{sum(1 for _ in reg.db.execute('SELECT 1 FROM daily_index'))} daily summaries\n")

    # 2. Create components
    nc = NoteConstructor(registry=reg, llm_call=deepseek_llm)
    fetcher = ContextFetcher(registry=reg)  # no c0 for now — SQLite only

    # 3. Sample text — continuation of the story
    sample = (
        "Hoy estuve en la florería otra vez con Romi. Me dijo que las ventas "
        "están bajando esta semana. Mientras tanto, c0 ya funciona perfecto "
        "con los embeddings locales — ya no gasto en DeepSeek para eso. "
        "Pero ahora la preocupación es otra: ¿cómo integro todo esto con "
        "Hermes Agent para usarlo desde Telegram? Creo que necesito un skill. "
        "También me preocupa el costo de DeepSeek para el modelo principal."
    )

    print(f"📝 INPUT TEXT:\n  \"{sample}\"\n")
    print("─" * 65)
    print("🔄 STEP 1: Note Constructor (DeepSeek → structured note)")
    print("─" * 65)

    note = nc.construct(sample)

    print(f"  Keywords:   {', '.join(note.keywords)}")
    print(f"  Context:    {note.context}")
    print(f"  Tags:       {', '.join(note.tags)}")
    emotion = note.emotional_load
    print(f"  Emotions:   oxy={emotion.get('oxytocin',0):.1f} adr={emotion.get('adrenaline',0):.1f} "
          f"cort={emotion.get('cortisol',0):.1f} dop={emotion.get('dopamine',0):.1f}")
    print(f"  Temporal:   {', '.join(note.temporal_hints) if note.temporal_hints else '(none)'}")
    print(f"  Entities:   {len(note.entities_mentioned)} mentioned")
    for e in note.entities_mentioned[:5]:
        alias = f" → {e.get('alias_of')}" if e.get('alias_of') else ""
        print(f"    - [{e.get('type','?')}] {e['name']}{alias}")
    if len(note.entities_mentioned) > 5:
        print(f"    ... and {len(note.entities_mentioned) - 5} more")
    print(f"  Hints:      {len(note.search_hints)} generated")
    for h in note.search_hints:
        print(f"    - {h}")

    print(f"\n{'─'*65}")
    print("🔍 STEP 2: Context Fetcher (search hints → real data)")
    print(f"{'─'*65}")

    context = fetcher.fetch(note)

    print(f"  Summary: {context['summary']}")

    if context.get("daily_summaries"):
        print(f"\n  📅 Daily Summaries found:")
        for ds in context["daily_summaries"][:3]:
            # Parse JSON summary field
            summary = ds.get("summary", "")
            try:
                summary_obj = json.loads(summary)
                summary_text = summary_obj.get("es", summary_obj.get("en", summary))
            except (json.JSONDecodeError, TypeError):
                summary_text = summary
            print(f"    [{ds['date']}] {summary_text[:120]}...")

    if context.get("entity_contexts"):
        print(f"\n  🧩 Entity Contexts:")
        for name, ectx in list(context["entity_contexts"].items())[:5]:
            aliases = ectx.get("aliases", [])
            alias_str = f" (aliases: {', '.join(aliases)})" if aliases else ""
            print(f"    [{ectx.get('type','?')}] {ectx['canonical_name']}{alias_str}")

    if context.get("related_reasoning"):
        print(f"\n  📜 Related Past Decisions: {len(context['related_reasoning'])}")
        for r in context["related_reasoning"][:3]:
            print(f"    [{r['action']}] {r.get('reasoning','')[:100]}")

    print(f"\n{'─'*65}")
    print("📦 PACKAGED CONTEXT (ready for LLM #2)")
    print(f"{'─'*65}")

    # Show a compact version of what LLM #2 would receive
    package = {
        "note": {
            "content": note.content[:200] + "...",
            "context": note.context,
            "keywords": note.keywords,
            "tags": note.tags,
            "emotional_load": note.emotional_load,
            "temporal_hints": note.temporal_hints,
            "entities_mentioned": note.entities_mentioned,
            "search_hints": note.search_hints,
        },
        "fetched_context": {
            "summary": context["summary"],
            "daily_count": len(context.get("daily_summaries", [])),
            "entity_count": len(context.get("entity_contexts", {})),
            "reasoning_count": len(context.get("related_reasoning", [])),
        }
    }
    print(json.dumps(package, indent=2, ensure_ascii=False))

    print(f"\n{'='*65}")
    print("✅ Full pipeline: Text → Note → Context → LLM #2 ready")
    print(f"{'='*65}")

    reg.db.close()
    os.unlink(db_path)


if __name__ == "__main__":
    main()

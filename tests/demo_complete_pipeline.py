"""
Mirror Brain v1.0 — Complete Pipeline Demo.
All 3 steps: Note Constructor → Context Fetcher → Link Evolution.
DeepSeek real API calls for both LLM steps.
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


# ── LLM Call (DeepSeek) ─────────────────────────────────────

def load_deepseek_key():
    """Load DeepSeek API key from env or .env file."""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    hermes_env = os.path.expanduser("~/AppData/Local/hermes/.env")
    if os.path.exists(hermes_env):
        with open(hermes_env) as f:
            for line in f:
                if "DEEPSEEK_API_KEY" in line:
                    key = line.split("=", 1)[1].strip()
                    break
    return key


def deepseek_llm(prompt):
    """Call DeepSeek API."""
    import urllib.request
    key = load_deepseek_key()
    if not key:
        return json.dumps({"keywords": [], "context": "no API key", "tags": [],
                           "emotional_load": {}, "temporal_hints": [],
                           "entities_mentioned": [], "search_hints": []})
    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1200,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        body = json.loads(resp.read())
        return body["choices"][0]["message"]["content"]


# ── Seed data ───────────────────────────────────────────────

def seed_data(reg):
    """Seed entities and daily summaries."""
    from datetime import date, timedelta

    # Entities
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
    reg.create("Hermes Agent", "tool")
    reg.create("Ollama", "tool")

    # Pre-existing links
    uuid_mb = reg.resolve("Mirror Brain")
    uuid_c0 = reg.resolve("c0")
    uuid_docker = reg.resolve("Docker")
    now = date.today().isoformat()
    if uuid_mb and uuid_c0:
        reg.db.execute(
            "INSERT INTO relations (from_uuid, to_uuid, relation_type, source_text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uuid_mb, uuid_c0, "depends_on", "c0 is the graph engine for Mirror Brain", now),
        )
    if uuid_c0 and uuid_docker:
        reg.db.execute(
            "INSERT INTO relations (from_uuid, to_uuid, relation_type, source_text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uuid_c0, uuid_docker, "runs_in", "c0 is containerized in Docker", now),
        )

    # Daily summaries
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    two_days_ago = (date.today() - timedelta(days=2)).isoformat()

    summaries = [
        (two_days_ago, json.dumps({
            "es": "Julian compilo c0 en Docker. Neo4j corriendo. Ollama aun sin conectar."
        }), json.dumps([0.3, 0.4, 0.7, 0.3]),
         json.dumps(["c0", "Docker", "Neo4j", "Ollama"]),
         json.dumps(["c0 compilado en Docker"])),
        (yesterday, json.dumps({
            "es": "c0 + Ollama funcionando con hybrid search. Logro: embeddings locales "
                 "gratis. Pero $5 USD en tokens DeepSeek esta semana."
        }), json.dumps([0.2, 0.6, 0.5, 0.8]),
         json.dumps(["c0", "Ollama", "DeepSeek", "Mirror Brain"]),
         json.dumps(["hybrid search OK", "preocupacion tokens DeepSeek"])),
    ]

    for date_val, summary, emotional, entities, decisions in summaries:
        reg.db.execute(
            "INSERT OR REPLACE INTO daily_index (date, summary, emotional_arc, "
            "key_entities, key_decisions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (date_val, summary, emotional, entities, decisions, date_val),
        )
    reg.db.commit()


# ── Main ────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("Mirror Brain v1.0 -- COMPLETE PIPELINE DEMO")
    print("=" * 70)

    # Init
    db_path = os.path.join(tempfile.gettempdir(), "mirror_brain_complete.db")
    reg = EntityRegistry(db_path)
    seed_data(reg)

    nc = NoteConstructor(registry=reg, llm_call=deepseek_llm)
    fetcher = ContextFetcher(registry=reg)
    le = LinkEvolution(registry=reg, llm_call=deepseek_llm)

    n_ent = sum(1 for _ in reg.db.execute("SELECT 1 FROM entities"))
    n_day = sum(1 for _ in reg.db.execute("SELECT 1 FROM daily_index"))
    n_rel = sum(1 for _ in reg.db.execute("SELECT 1 FROM relations"))
    print(f"\nSeeded: {n_ent} entities, {n_day} days, {n_rel} relations")

    # ── STEP 1: Note Constructor ───────────────────────────

    sample = (
        "Hoy Romi me dijo que la floreria esta complicada -- las ventas bajaron "
        "un 30% este mes. Me pidio ayuda para hacer publicidad online. "
        "Mientras tanto, c0 ya esta listo. El hybrid search funciona con "
        "Ollama local. Ya no dependo de DeepSeek para embeddings. "
        "Pero el costo del modelo principal de DeepSeek sigue siendo un tema. "
        "Creo que Mirror Brain puede ayudar a Romi tambien -- un sistema de "
        "memoria para sus clientes y pedidos. Seria el primer caso de uso real."
    )

    print(f"\n{'─'*70}")
    print("STEP 1: Note Constructor (LLM #1)")
    print(f"{'─'*70}")
    print(f'  Input: "{sample[:120]}..."')
    print("  Calling DeepSeek...")

    note = nc.construct(sample)

    print(f"  Keywords: {', '.join(note.keywords)}")
    print(f"  Context:  {note.context}")
    e = note.emotional_load
    print(f"  Emotions: oxy={e.get('oxytocin',0):.1f} adr={e.get('adrenaline',0):.1f} "
          f"cort={e.get('cortisol',0):.1f} dop={e.get('dopamine',0):.1f}")
    print(f"  Entities: {len(note.entities_mentioned)} detected")
    print(f"  Hints:    {len(note.search_hints)} generated")

    # ── STEP 2: Context Fetcher ─────────────────────────────

    print(f"\n{'─'*70}")
    print("STEP 2: Context Fetcher")
    print(f"{'─'*70}")

    context = fetcher.fetch(note)
    print(f"  {context['summary']}")

    if context.get("daily_summaries"):
        for ds in context["daily_summaries"][:2]:
            s = ds.get("summary", "")
            try:
                s_obj = json.loads(s)
                s = s_obj.get("es", str(s))
            except (json.JSONDecodeError, TypeError):
                pass
            print(f"     [{ds['date']}] {s[:130]}...")

    # ── STEP 3: Link + Evolution (LLM #2) ────────────────────

    print(f"\n{'─'*70}")
    print("STEP 3: Link Generation + Memory Evolution (LLM #2)")
    print(f"{'─'*70}")

    # Build neighbor context
    neighbors = "Recent events:\n"
    if context.get("daily_summaries"):
        for ds in context["daily_summaries"][:3]:
            s = ds.get("summary", "")
            try:
                s_obj = json.loads(s)
                s = s_obj.get("es", str(s))
            except (json.JSONDecodeError, TypeError):
                pass
            neighbors += f"- [{ds['date']}] {s[:200]}\n"

    print("  Calling DeepSeek...")
    decisions = le.decide(note, context, neighbors)

    n_links = len(decisions.get("links", []))
    n_evos = len(decisions.get("evolutions", []))
    n_aliases = len(decisions.get("new_aliases", []))
    n_more = len(decisions.get("needs_more_search", []))

    print(f"  Links:      {n_links} proposed")
    print(f"  Evolutions: {n_evos} proposed")
    print(f"  Aliases:    {n_aliases} detected")
    print(f"  More search:{n_more} requested")

    print(f"\n  DECISIONS:")
    for link in decisions.get("links", [])[:6]:
        c = link.get("confidence", 0)
        tag = "GREEN" if c >= 0.85 else ("YELLOW" if c >= 0.6 else "RED")
        reason = link.get("reasoning", "")[:80]
        print(f"    [{tag}] {link['from_entity']} --[{link['relation']}]--> "
              f"{link['to_entity']} (conf={c:.2f})")
        if reason:
            print(f"          {reason}")

    for evo in decisions.get("evolutions", [])[:3]:
        c = evo.get("confidence", 0)
        tag = "GREEN" if c >= 0.85 else ("YELLOW" if c >= 0.6 else "RED")
        reason = evo.get("reasoning", "")[:80]
        print(f"    [{tag}] evolve: {evo.get('action','?')} on "
              f"{evo.get('target','?')} (conf={c:.2f})")
        if reason:
            print(f"          {reason}")

    for alias in decisions.get("new_aliases", [])[:3]:
        c = alias.get("confidence", 0)
        tag = "GREEN" if c >= 0.85 else ("YELLOW" if c >= 0.6 else "RED")
        print(f"    [{tag}] alias: '{alias['alias']}' -> "
              f"{alias['canonical_entity']} (conf={c:.2f})")

    if decisions.get("needs_more_search"):
        print(f"\n  Needs more context:")
        for q in decisions["needs_more_search"]:
            print(f"    - {q}")

    # ── EXECUTE ────────────────────────────────────────────

    print(f"\n{'─'*70}")
    print("EXECUTION (confidence gates)")
    print(f"{'─'*70}")

    report = le.execute(decisions, note)

    print(f"  Auto-executed ({len(report['auto_executed'])}):")
    for item in report["auto_executed"]:
        print(f"    [OK] {item[:120]}")

    if report["flagged"]:
        print(f"\n  Flagged for review ({len(report['flagged'])}):")
        for item in report["flagged"]:
            print(f"    [FLAG] {item[:120]}")

    if report["skipped"]:
        print(f"\n  Skipped ({len(report['skipped'])}):")
        for item in report["skipped"]:
            print(f"    [SKIP] {item[:120]}")

    # ── FINAL STATE ────────────────────────────────────────

    print(f"\n{'='*70}")
    print("FINAL BRAIN STATE")
    print(f"{'='*70}")

    n_ent_f = sum(1 for _ in reg.db.execute("SELECT 1 FROM entities"))
    n_rel_f = sum(1 for _ in reg.db.execute("SELECT 1 FROM relations"))
    n_al_f = sum(1 for _ in reg.db.execute("SELECT 1 FROM aliases"))
    n_tr_f = sum(1 for _ in reg.db.execute("SELECT 1 FROM reasoning_trail"))

    print(f"  Entities: {n_ent_f} | Relations: {n_rel_f} | "
          f"Aliases: {n_al_f} | Reasoning: {n_tr_f}")

    # Show all relations
    relations = reg.db.execute(
        "SELECT r.from_uuid, r.to_uuid, r.relation_type FROM relations r"
    ).fetchall()
    if relations:
        print(f"\n  All relations in brain:")
        for fr, to, rel in relations:
            fr_info = reg.get(fr)
            to_info = reg.get(to)
            fr_name = fr_info["canonical_name"] if fr_info else fr[:8]
            to_name = to_info["canonical_name"] if to_info else to[:8]
            print(f"    {fr_name} --[{rel}]--> {to_name}")

    print(f"\n{'='*70}")
    print("PIPELINE COMPLETE: Text -> Brain -> Links -> Evolution")
    print(f"{'='*70}")

    reg.db.close()
    os.unlink(db_path)


if __name__ == "__main__":
    main()

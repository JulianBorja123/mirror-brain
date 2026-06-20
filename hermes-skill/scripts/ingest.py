#!/usr/bin/env python3
"""
Mirror Brain — Ingest Script.
Run the full pipeline on a text string: Note Construction → Context Fetch → Link Evolution → Execute.

Usage:
    python scripts/ingest.py "Hoy trabajé en integrar c0 con Mirror Brain"
    python scripts/ingest.py --file notes.txt
    python scripts/ingest.py --dry-run "test text"   # LLM only, no DB writes
"""

import sys
import os
import json
from pathlib import Path

# Ensure the mirror-brain package is importable
REPO_SRC = os.path.expanduser("~/mirror-brain/src")
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from mirror_brain.registry import EntityRegistry
from mirror_brain.note_constructor import NoteConstructor
from mirror_brain.context_fetcher import ContextFetcher
from mirror_brain.link_evolution import LinkEvolution

# Default DB path
DB_PATH = os.path.expanduser("~/mirror_brain.db")


# ── LLM Call (DeepSeek) ─────────────────────────────────────

def load_deepseek_key() -> str:
    """Load DeepSeek API key from env or .env file."""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key

    env_paths = [
        os.path.expanduser("~/AppData/Local/hermes/.env"),
        os.path.expanduser("~/.hermes/.env"),
    ]
    for env_path in env_paths:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if "DEEPSEEK_API_KEY" in line:
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if key:
                            return key
    return ""


def deepseek_llm(prompt: str) -> str:
    """Call DeepSeek API."""
    import urllib.request

    key = load_deepseek_key()
    if not key:
        return json.dumps({
            "keywords": [], "context": "no API key configured",
            "tags": [], "emotional_load": {},
            "temporal_hints": [], "entities_mentioned": [],
            "search_hints": [],
        })

    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1200,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read())
            return body["choices"][0]["message"]["content"]
    except Exception as exc:
        return json.dumps({
            "keywords": [], "context": f"API error: {exc}",
            "tags": [], "emotional_load": {},
            "temporal_hints": [], "entities_mentioned": [],
            "search_hints": [],
        })


# ── Pipeline ────────────────────────────────────────────────

def run_ingest_pipeline(
    text: str,
    registry: EntityRegistry,
    dry_run: bool = False,
) -> dict:
    """Run the full Mirror Brain pipeline on a text string.

    Returns a dict with: note, context, decisions, report, stats.
    """
    # Initialize components
    nc = NoteConstructor(registry=registry, llm_call=deepseek_llm)
    fetcher = ContextFetcher(registry=registry)  # SQLite-only; c0 is optional
    le = LinkEvolution(registry=registry, llm_call=deepseek_llm)

    result = {}

    # ── Step 1: Note Construction (LLM #1) ──────────────────
    print("🔄 STEP 1: Note Constructor (calling DeepSeek)...", file=sys.stderr)
    note = nc.construct(text)
    result["note"] = {
        "content": note.content[:500] + ("..." if len(note.content) > 500 else ""),
        "timestamp": note.timestamp,
        "keywords": note.keywords,
        "context": note.context,
        "tags": note.tags,
        "emotional_load": note.emotional_load,
        "temporal_hints": note.temporal_hints,
        "entities_mentioned": note.entities_mentioned,
        "search_hints": note.search_hints,
    }

    # ── Step 2: Context Fetch ────────────────────────────────
    print("🔍 STEP 2: Context Fetcher...", file=sys.stderr)
    context = fetcher.fetch(note)
    result["context"] = {
        "summary": context.get("summary", ""),
        "daily_count": len(context.get("daily_summaries", [])),
        "entity_count": len(context.get("entity_contexts", {})),
        "semantic_count": len(context.get("semantic_results", [])),
        "reasoning_count": len(context.get("related_reasoning", [])),
    }

    # ── Step 3: Link + Evolution (LLM #2) ───────────────────
    print("🧬 STEP 3: Link Evolution (calling DeepSeek)...", file=sys.stderr)

    # Build neighbor context string
    neighbors = "Recent events:\n"
    dailies = context.get("daily_summaries", [])
    if dailies:
        for ds in dailies[:3]:
            s = ds.get("summary", "")
            if isinstance(s, dict):
                s = s.get("es", str(s))
            neighbors += f"- [{ds.get('date', '?')}] {str(s)[:200]}\n"
    else:
        neighbors += "(no recent daily summaries)\n"

    decisions = le.decide(note, context, neighbors)
    result["decisions"] = {
        "links_proposed": len(decisions.get("links", [])),
        "evolutions_proposed": len(decisions.get("evolutions", [])),
        "new_aliases": len(decisions.get("new_aliases", [])),
        "needs_more_search": len(decisions.get("needs_more_search", [])),
        "links": decisions.get("links", []),
        "evolutions": decisions.get("evolutions", []),
        "aliases_detected": decisions.get("new_aliases", []),
        "more_search_requests": decisions.get("needs_more_search", []),
    }

    # ── Step 4: Execute ──────────────────────────────────────
    if dry_run:
        print("⚠️  DRY RUN — skipping execution", file=sys.stderr)
        result["report"] = {"dry_run": True, "auto_executed": [], "flagged": [], "skipped": []}
    else:
        print("⚡ STEP 4: Execution (confidence gates)...", file=sys.stderr)
        report = le.execute(decisions, note)
        result["report"] = {
            "auto_executed": len(report.get("auto_executed", [])),
            "flagged": len(report.get("flagged", [])),
            "skipped": len(report.get("skipped", [])),
            "errors": len(report.get("errors", [])),
            "auto_executed_items": report.get("auto_executed", []),
            "flagged_items": report.get("flagged", []),
            "skipped_items": report.get("skipped", []),
        }

    # ── Stats ────────────────────────────────────────────────
    n_ent = sum(1 for _ in registry.db.execute("SELECT 1 FROM entities"))
    n_rel = sum(1 for _ in registry.db.execute("SELECT 1 FROM relations"))
    n_al = sum(1 for _ in registry.db.execute("SELECT 1 FROM aliases"))
    n_tr = sum(1 for _ in registry.db.execute("SELECT 1 FROM reasoning_trail"))
    result["brain_stats"] = {
        "entities": n_ent,
        "relations": n_rel,
        "aliases": n_al,
        "reasoning_trail": n_tr,
    }

    return result


# ── Formatting ──────────────────────────────────────────────

def format_pipeline_result(result: dict) -> str:
    """Format pipeline result for human-readable display."""
    lines = ["=" * 65]
    lines.append("🧠 Mirror Brain — Ingest Complete")
    lines.append("=" * 65)

    # Note
    note = result.get("note", {})
    lines.append("")
    lines.append("📝 Constructed Note:")
    lines.append(f"  Context:    {note.get('context', '')}")
    lines.append(f"  Keywords:   {', '.join(note.get('keywords', []))}")
    lines.append(f"  Tags:       {', '.join(note.get('tags', []))}")
    e = note.get("emotional_load", {})
    lines.append(f"  Emotions:   oxy={e.get('oxytocin',0):.1f} adr={e.get('adrenaline',0):.1f} "
                 f"cort={e.get('cortisol',0):.1f} dop={e.get('dopamine',0):.1f}")
    lines.append(f"  Temporal:   {', '.join(note.get('temporal_hints', [])) or '(none)'}")
    entities = note.get("entities_mentioned", [])
    lines.append(f"  Entities:   {len(entities)} mentioned")
    for ent in entities[:10]:
        alias = f" → {ent.get('alias_of')}" if ent.get('alias_of') else ""
        is_new = " (new)" if ent.get('is_new') else ""
        lines.append(f"    - [{ent.get('type','?')}] {ent['name']}{alias}{is_new}")
    if len(entities) > 10:
        lines.append(f"    ... and {len(entities) - 10} more")
    hints = note.get("search_hints", [])
    if hints:
        lines.append(f"  Search Hints:")
        for h in hints:
            lines.append(f"    - {h}")

    # Context
    ctx = result.get("context", {})
    lines.append(f"\n🔍 Context Fetched:")
    lines.append(f"  {ctx.get('summary', '')}")

    # Decisions
    dec = result.get("decisions", {})
    lines.append(f"\n🧬 Link Evolution Decisions:")
    lines.append(f"  Links proposed:      {dec.get('links_proposed', 0)}")
    lines.append(f"  Evolutions proposed: {dec.get('evolutions_proposed', 0)}")
    lines.append(f"  New aliases:         {dec.get('new_aliases', 0)}")
    lines.append(f"  More search needed:  {dec.get('needs_more_search', 0)}")

    # Show proposed links
    for link in dec.get("links", [])[:5]:
        conf = link.get("confidence", 0)
        tag = "✓" if conf >= 0.85 else ("⚠" if conf >= 0.6 else "✗")
        reason = link.get("reasoning", "")[:100]
        lines.append(f"  [{tag}] {link.get('from_entity','?')} "
                     f"--[{link.get('relation','?')}]--> "
                     f"{link.get('to_entity','?')} (conf={conf:.2f})")
        if reason:
            lines.append(f"       {reason}")
    if len(dec.get("links", [])) > 5:
        lines.append(f"       ... and {len(dec['links']) - 5} more")

    # Show evolutions
    for evo in dec.get("evolutions", [])[:3]:
        conf = evo.get("confidence", 0)
        tag = "✓" if conf >= 0.85 else ("⚠" if conf >= 0.6 else "✗")
        lines.append(f"  [{tag}] evolve: {evo.get('action','?')} on "
                     f"{evo.get('target','?')} (conf={conf:.2f})")

    # Show new aliases
    for alias in dec.get("aliases_detected", [])[:3]:
        conf = alias.get("confidence", 0)
        tag = "✓" if conf >= 0.85 else ("⚠" if conf >= 0.6 else "✗")
        lines.append(f"  [{tag}] alias: '{alias.get('alias','?')}' -> "
                     f"{alias.get('canonical_entity','?')} (conf={conf:.2f})")

    # Execution report
    rep = result.get("report", {})
    lines.append(f"\n⚡ Execution Report:")
    if rep.get("dry_run"):
        lines.append("  DRY RUN — no changes written to brain")
    else:
        lines.append(f"  Auto-executed: {rep.get('auto_executed', 0)}")
        lines.append(f"  Flagged:       {rep.get('flagged', 0)}")
        lines.append(f"  Skipped:       {rep.get('skipped', 0)}")
        for item in rep.get("auto_executed_items", [])[:5]:
            lines.append(f"    [OK] {item[:120]}")
        for item in rep.get("flagged_items", [])[:5]:
            lines.append(f"    [FLAG] {item[:120]}")
        for item in rep.get("skipped_items", [])[:5]:
            lines.append(f"    [SKIP] {item[:120]}")

    # Brain stats
    stats = result.get("brain_stats", {})
    lines.append(f"\n📊 Brain State:")
    lines.append(f"  Entities:       {stats.get('entities', 0)}")
    lines.append(f"  Relations:      {stats.get('relations', 0)}")
    lines.append(f"  Aliases:        {stats.get('aliases', 0)}")
    lines.append(f"  Reasoning Trail:{stats.get('reasoning_trail', 0)}")

    lines.append("\n" + "=" * 65)
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Mirror Brain — Ingest text into the memory system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s "Hoy trabajé en integrar c0 con Mirror Brain"
  %(prog)s --file notes.txt
  %(prog)s --dry-run "test text"    # preview only, no writes
  %(prog)s --json "test text"       # machine-readable output""",
    )
    parser.add_argument(
        "text", nargs="?", default=None,
        help="Text to ingest into Mirror Brain"
    )
    parser.add_argument(
        "--file", "-f", type=str, default=None,
        help="Read text from a file instead of command line"
    )
    parser.add_argument(
        "--db", type=str, default=DB_PATH,
        help=f"Path to mirror_brain.db (default: {DB_PATH})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run LLM steps only — do not write to the database"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON instead of formatted text"
    )

    args = parser.parse_args()

    # Get text
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read().strip()
    elif args.text:
        text = args.text
    else:
        print("Error: No text provided. Use --text or --file.", file=sys.stderr)
        sys.exit(1)

    if not text:
        print("Error: Empty text.", file=sys.stderr)
        sys.exit(1)

    # Check DB
    if not os.path.exists(args.db) and not args.dry_run:
        print(f"Warning: DB not found at {args.db} — initializing...", file=sys.stderr)

    # Check API key
    key = load_deepseek_key()
    if not key:
        print("Error: DEEPSEEK_API_KEY not found in env or ~/AppData/Local/hermes/.env",
              file=sys.stderr)
        print("Set DEEPSEEK_API_KEY=sk-... or add it to the .env file.", file=sys.stderr)
        sys.exit(1)

    print(f"Ingesting: \"{text[:100]}{'...' if len(text) > 100 else ''}\"", file=sys.stderr)

    # Load registry
    registry = EntityRegistry(args.db)

    try:
        result = run_ingest_pipeline(text, registry, dry_run=args.dry_run)
    except Exception as exc:
        print(f"Pipeline error: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        registry.db.close()
        sys.exit(1)

    registry.db.close()

    # Output
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(format_pipeline_result(result))


if __name__ == "__main__":
    main()

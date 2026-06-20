#!/usr/bin/env python3
"""
Mirror Brain — Query Script.
Search the memory system: entities, aliases, relations, daily summaries, and reasoning trail.

Usage:
    python scripts/query.py "c0"
    python scripts/query.py "what happened this week?"
    python scripts/query.py --entity "DeepSeek"
    python scripts/query.py --recent 7
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

# Default DB path
DB_PATH = os.path.expanduser("~/mirror_brain.db")


def load_registry(db_path: str = DB_PATH) -> EntityRegistry:
    """Load the entity registry, creating the DB if needed."""
    return EntityRegistry(db_path)


def search_entities(registry: EntityRegistry, query: str) -> list[dict]:
    """Search entities by name or alias. Returns enriched results with aliases."""
    results = registry.search(query)
    enriched = []
    for r in results:
        aliases = registry.get_aliases(r["uuid"])
        enriched.append({
            **r,
            "aliases": [a["alias"] for a in aliases if a["alias"] != r["canonical_name"]],
        })
    return enriched


def get_recent_daily_summaries(registry: EntityRegistry, days: int = 7) -> list[dict]:
    """Get recent daily summaries from the daily_index table."""
    from datetime import date, timedelta

    today = date.today()
    results = []
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        row = registry.db.execute(
            "SELECT date, summary, emotional_arc, key_entities, key_decisions "
            "FROM daily_index WHERE date = ?",
            (d,),
        ).fetchone()
        if row:
            try:
                summary = json.loads(row[1]) if row[1] else row[1]
            except (json.JSONDecodeError, TypeError):
                summary = row[1]
            try:
                key_entities = json.loads(row[3]) if row[3] else []
            except (json.JSONDecodeError, TypeError):
                key_entities = []
            results.append({
                "date": row[0],
                "summary": summary,
                "key_entities": key_entities,
            })
    return results


def get_entity_detail(registry: EntityRegistry, name: str) -> dict | None:
    """Get full details for a specific entity by name."""
    entity_uuid = registry.resolve(name)
    if not entity_uuid:
        # Try search
        results = registry.search(name)
        if not results:
            return None
        entity_uuid = results[0]["uuid"]

    info = registry.get(entity_uuid)
    aliases = registry.get_aliases(entity_uuid)

    # Get relations
    relations = registry.db.execute(
        "SELECT r.from_uuid, r.to_uuid, r.relation_type, r.source_text "
        "FROM relations r WHERE r.from_uuid = ? OR r.to_uuid = ?",
        (entity_uuid, entity_uuid),
    ).fetchall()

    rel_list = []
    for fr, to, rel_type, source in relations:
        fr_info = registry.get(fr) if fr else None
        to_info = registry.get(to) if to else None
        rel_list.append({
            "from": fr_info["canonical_name"] if fr_info else fr[:8],
            "to": to_info["canonical_name"] if to_info else to[:8],
            "relation": rel_type,
            "direction": "outgoing" if fr == entity_uuid else "incoming",
        })

    return {
        "uuid": entity_uuid,
        "canonical_name": info["canonical_name"] if info else name,
        "type": info["type"] if info else "unknown",
        "status": info["status"] if info else "?",
        "c0_ref": info["c0_ref"] if info else "",
        "aliases": [a["alias"] for a in aliases],
        "relations": rel_list,
        "created_at": info["created_at"] if info else "",
        "updated_at": info["updated_at"] if info else "",
    }


def get_reasoning_trail(registry: EntityRegistry, query: str, limit: int = 10) -> list[dict]:
    """Search the reasoning trail for related decisions."""
    like = f"%{query}%"
    rows = registry.db.execute(
        "SELECT timestamp, action, confidence, reasoning, source "
        "FROM reasoning_trail "
        "WHERE reasoning LIKE ? OR action LIKE ? "
        "ORDER BY timestamp DESC LIMIT ?",
        (like, like, limit),
    ).fetchall()
    return [
        {"timestamp": r[0], "action": r[1], "confidence": r[2],
         "reasoning": r[3], "source": r[4]}
        for r in rows
    ]


def format_entity_list(entities: list[dict]) -> str:
    """Format entity search results for display."""
    if not entities:
        return "  (no entities found)"

    lines = []
    for e in entities:
        line = f"  [{e.get('type', '?')}] {e['canonical_name']}"
        if e.get("aliases"):
            line += f" (aliases: {', '.join(e['aliases'])})"
        line += f" — {e['uuid'][:8]}"
        lines.append(line)
    return "\n".join(lines)


def format_daily_summaries(summaries: list[dict]) -> str:
    """Format daily summaries for display."""
    if not summaries:
        return "  (no daily summaries found)"

    lines = []
    for ds in summaries:
        summary = ds.get("summary", "")
        if isinstance(summary, dict):
            summary = summary.get("es", summary.get("en", str(summary)))
        summary_str = str(summary)[:150]
        entities = ds.get("key_entities", [])
        ent_str = f" [{', '.join(entities)}]" if entities else ""
        lines.append(f"  [{ds['date']}] {summary_str}{ent_str}")
    return "\n".join(lines)


def format_entity_detail(detail: dict) -> str:
    """Format a single entity detail for display."""
    lines = [
        f"Entity: {detail['canonical_name']}",
        f"  UUID:    {detail['uuid']}",
        f"  Type:    {detail['type']}",
        f"  Status:  {detail['status']}",
        f"  c0 ref:  {detail['c0_ref']}",
        f"  Created: {detail['created_at']}",
        f"  Updated: {detail['updated_at']}",
    ]
    if detail.get("aliases"):
        lines.append(f"  Aliases: {', '.join(detail['aliases'])}")
    if detail.get("relations"):
        lines.append("  Relations:")
        for r in detail["relations"]:
            arrow = "→" if r["direction"] == "outgoing" else "←"
            lines.append(f"    {r['from']} --[{r['relation']}]--{arrow} {r['to']}")
    return "\n".join(lines)


def format_reasoning(trail: list[dict]) -> str:
    """Format reasoning trail for display."""
    if not trail:
        return "  (no matching reasoning trail entries)"

    lines = []
    for r in trail:
        lines.append(
            f"  [{r['timestamp'][:19]}] {r['action']} "
            f"(conf={r['confidence']:.2f}) — {r['reasoning'][:120]}"
        )
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Mirror Brain — Query the memory system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s "c0"                  — search entities/aliases matching 'c0'
  %(prog)s "what happened"       — broad search + recent daily summaries
  %(prog)s --entity "DeepSeek"   — full detail on one entity
  %(prog)s --recent 3            — last 3 days of daily summaries
  %(prog)s --reasoning "merge"   — reasoning trail for 'merge' actions""",
    )
    parser.add_argument(
        "query", nargs="?", default="",
        help="Search query for entities and aliases"
    )
    parser.add_argument(
        "--entity", "-e", type=str, default=None,
        help="Show full detail for a specific entity by name"
    )
    parser.add_argument(
        "--recent", "-r", type=int, default=0,
        help="Show recent N days of daily summaries"
    )
    parser.add_argument(
        "--reasoning", type=str, default=None,
        help="Search reasoning trail for matching entries"
    )
    parser.add_argument(
        "--db", type=str, default=DB_PATH,
        help=f"Path to mirror_brain.db (default: {DB_PATH})"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON instead of formatted text"
    )

    args = parser.parse_args()

    # Load registry
    if not os.path.exists(args.db):
        print(f"Error: Database not found at {args.db}", file=sys.stderr)
        print("Run 'EntityRegistry(db_path)' once to initialize.", file=sys.stderr)
        sys.exit(1)

    registry = load_registry(args.db)

    output = {}

    # Entity detail mode
    if args.entity:
        detail = get_entity_detail(registry, args.entity)
        if detail:
            output["entity"] = detail
        else:
            print(f"Entity '{args.entity}' not found.", file=sys.stderr)
            sys.exit(1)

    # Entity search
    if args.query:
        entities = search_entities(registry, args.query)
        output["entities_found"] = len(entities)
        output["entities"] = entities

    # Recent summaries
    if args.recent > 0:
        summaries = get_recent_daily_summaries(registry, args.recent)
        output["daily_summaries"] = summaries

    # Reasoning trail
    if args.reasoning:
        trail = get_reasoning_trail(registry, args.reasoning)
        output["reasoning_trail"] = trail

    # Default: if no args, show overview
    if not any([args.query, args.entity, args.recent > 0, args.reasoning]):
        n_entities = sum(1 for _ in registry.db.execute("SELECT 1 FROM entities"))
        n_aliases = sum(1 for _ in registry.db.execute("SELECT 1 FROM aliases"))
        n_dailies = sum(1 for _ in registry.db.execute("SELECT 1 FROM daily_index"))
        n_relations = sum(1 for _ in registry.db.execute("SELECT 1 FROM relations"))
        n_reasoning = sum(1 for _ in registry.db.execute("SELECT 1 FROM reasoning_trail"))
        output["brain_stats"] = {
            "entities": n_entities,
            "aliases": n_aliases,
            "daily_summaries": n_dailies,
            "relations": n_relations,
            "reasoning_trail": n_reasoning,
        }

    # Output
    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    else:
        if "brain_stats" in output:
            stats = output["brain_stats"]
            print("Mirror Brain — State Overview")
            print(f"  Entities:       {stats['entities']}")
            print(f"  Aliases:        {stats['aliases']}")
            print(f"  Daily Summaries:{stats['daily_summaries']}")
            print(f"  Relations:      {stats['relations']}")
            print(f"  Reasoning Trail:{stats['reasoning_trail']}")

        if "entity" in output:
            print(format_entity_detail(output["entity"]))
            print()

        if "entities" in output:
            print(f"Entity Search ({output['entities_found']} found):")
            print(format_entity_list(output["entities"]))
            print()

        if "daily_summaries" in output:
            print(f"Daily Summaries ({len(output['daily_summaries'])} found):")
            print(format_daily_summaries(output["daily_summaries"]))
            print()

        if "reasoning_trail" in output:
            print(f"Reasoning Trail ({len(output['reasoning_trail'])} found):")
            print(format_reasoning(output["reasoning_trail"]))

    registry.db.close()


if __name__ == "__main__":
    main()

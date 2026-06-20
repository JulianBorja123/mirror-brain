"""
Mirror Brain v1.0 — Context Fetcher.
Takes the search_hints from a Note and fetches relevant context
from c0 (graph) and SQLite (entities, daily summaries, reasoning trail).
"""
import json
import re
from typing import Optional

from .models import Note


class ContextFetcher:
    """Intelligent context retrieval guided by LLM-generated search hints.

    Usage:
        fetcher = ContextFetcher(registry, c0_client)
        context = fetcher.fetch(note)

    Returns a dict ready to inject into LLM Call #2.
    """

    def __init__(self, registry, c0_client=None):
        self.registry = registry
        self.c0 = c0_client

    # ── Public API ──────────────────────────────────────────────

    def fetch(self, note: Note) -> dict:
        """Fetch all relevant context for a note.

        Returns:
            {
                "daily_summaries": [...],
                "entity_contexts": {uuid: {info, aliases, relations, walk}},
                "semantic_results": [...],
                "related_reasoning": [...],
                "summary": "human-readable summary of what was found"
            }
        """
        ctx = {
            "daily_summaries": [],
            "entity_contexts": {},
            "semantic_results": [],
            "related_reasoning": [],
        }

        for hint in note.search_hints:
            search_type = self._classify_hint(hint)
            self._execute_search(hint, search_type, ctx, note)

        # Add entity context for all mentioned entities
        for ent in note.entities_mentioned:
            name = ent.get("name", "")
            alias_of = ent.get("alias_of", "")
            target = alias_of or name
            if target and target not in ctx["entity_contexts"]:
                entity_ctx = self._get_entity_context(target)
                if entity_ctx:
                    ctx["entity_contexts"][target] = entity_ctx

        # Build human-readable summary
        ctx["summary"] = self._summarize(ctx)

        return ctx

    # ── Search execution ────────────────────────────────────────

    def _execute_search(self, hint: str, search_type: str, ctx: dict, note: Note):
        """Execute the appropriate search and append to context."""
        if search_type == "temporal":
            result = self._search_temporal(hint)
            if result:
                ctx["daily_summaries"].extend(result)

        elif search_type == "entity":
            entity_name = self._extract_entity_from_hint(hint)
            if entity_name:
                entity_ctx = self._get_entity_context(entity_name)
                if entity_ctx and entity_name not in ctx["entity_contexts"]:
                    ctx["entity_contexts"][entity_name] = entity_ctx

        elif search_type == "semantic" and self.c0:
            result = self._search_semantic(hint)
            if result:
                ctx["semantic_results"].append({"hint": hint, "results": result})

        # Always check reasoning trail for related decisions
        trail = self._search_reasoning_trail(hint)
        if trail:
            ctx["related_reasoning"].extend(trail)

    # ── Search implementations ──────────────────────────────────

    def _search_temporal(self, hint: str) -> list[dict]:
        """Search daily_index table for time-related queries."""
        dates = self._extract_dates(hint)
        results = []

        for date in dates:
            row = self.registry.db.execute(
                "SELECT date, summary, emotional_arc, key_entities, key_decisions "
                "FROM daily_index WHERE date = ?",
                (date,),
            ).fetchone()

            if row:
                results.append({
                    "date": row[0],
                    "summary": row[1],
                    "emotional_arc": json.loads(row[2]) if row[2] else [],
                    "key_entities": json.loads(row[3]) if row[3] else [],
                    "key_decisions": json.loads(row[4]) if row[4] else [],
                })

        if not results:
            # Fallback: recent days
            rows = self.registry.db.execute(
                "SELECT date, summary, key_entities FROM daily_index "
                "ORDER BY date DESC LIMIT 5"
            ).fetchall()
            results = [
                {"date": r[0], "summary": r[1],
                 "key_entities": json.loads(r[2]) if r[2] else []}
                for r in rows
            ]

        return results

    def _get_entity_context(self, name: str) -> Optional[dict]:
        """Get full context for an entity: registry info + c0 graph."""
        entity_uuid = self.registry.resolve(name)
        if not entity_uuid:
            return None

        info = self.registry.get(entity_uuid)
        aliases = self.registry.get_aliases(entity_uuid)

        ctx = {
            "uuid": entity_uuid,
            "canonical_name": info["canonical_name"] if info else name,
            "type": info["type"] if info else "unknown",
            "aliases": [a["alias"] for a in aliases],
            "c0_ref": info["c0_ref"] if info else "",
        }

        # Try c0 walk if available
        if self.c0:
            try:
                c0_ref = ctx["c0_ref"]
                walk_result = self.c0.walk(c0_ref, depth=1)
                ctx["graph_neighbors"] = walk_result
            except Exception:
                ctx["graph_neighbors"] = []

        return ctx

    def _search_semantic(self, hint: str) -> list[dict]:
        """Search c0 for semantically relevant memories."""
        if not self.c0:
            return []
        try:
            return self.c0.search(hint, limit=5)
        except Exception:
            return []

    def _search_reasoning_trail(self, hint: str) -> list[dict]:
        """Search reasoning_trail for related past decisions."""
        # Extract entity names from hint to filter reasoning
        words = re.findall(r'\b[A-Za-zÁ-Úá-ú][a-zá-ú]{2,}\b', hint)
        results = []

        for word in words[:3]:
            rows = self.registry.db.execute(
                "SELECT timestamp, action, entity_uuid, target_uuid, confidence, "
                "reasoning, source FROM reasoning_trail "
                "WHERE reasoning LIKE ? OR action LIKE ? "
                "ORDER BY timestamp DESC LIMIT 3",
                (f"%{word}%", f"%{word}%"),
            ).fetchall()
            for r in rows:
                results.append({
                    "timestamp": r[0], "action": r[1],
                    "confidence": r[4], "reasoning": r[5],
                    "source": r[6],
                })

        return results

    # ── Hint classification ─────────────────────────────────────

    def _classify_hint(self, hint: str) -> str:
        """Classify a search hint into: temporal, entity, semantic, or mixed."""
        lower = hint.lower()

        # Temporal markers
        temporal_words = [
            "semana", "month", "week", "ayer", "yesterday", "hoy", "today",
            "cuánto gast", "how much", "spend", "costo", "cost",
            "día", "day", "mes", "year", "año",
        ]
        if any(w in lower for w in temporal_words):
            return "temporal"

        # Entity markers — check if hint contains known entity names
        try:
            entities = self.registry.db.execute(
                "SELECT canonical_name FROM entities WHERE status='active'"
            ).fetchall()
            for (name,) in entities:
                if name.lower() in lower:
                    return "entity"
        except Exception:
            pass

        return "semantic"

    def _extract_entity_from_hint(self, hint: str) -> Optional[str]:
        """Extract a known entity name from a hint string."""
        try:
            entities = self.registry.db.execute(
                "SELECT canonical_name FROM entities WHERE status='active'"
            ).fetchall()
            lower_hint = hint.lower()
            for (name,) in entities:
                if name.lower() in lower_hint:
                    return name
        except Exception:
            pass
        return None

    # ── Date extraction ─────────────────────────────────────────

    @staticmethod
    def _extract_dates(hint: str) -> list[str]:
        """Extract date strings from a temporal hint.

        Simplistic: returns an empty list for now (falls back to recent days).
        In production, this would use datetime parsing.
        """
        from datetime import date, timedelta

        lower = hint.lower()
        today = date.today()

        if "ayer" in lower or "yesterday" in lower:
            return [(today - timedelta(days=1)).isoformat()]
        if "hoy" in lower or "today" in lower:
            return [today.isoformat()]
        if "semana" in lower or "week" in lower:
            return [(today - timedelta(days=i)).isoformat() for i in range(7)]

        # Default: recent days
        return [(today - timedelta(days=i)).isoformat() for i in range(3)]

    # ── Summarization ───────────────────────────────────────────

    @staticmethod
    def _summarize(ctx: dict) -> str:
        """Build a human-readable summary of fetched context."""
        parts = []

        n_daily = len(ctx["daily_summaries"])
        if n_daily:
            parts.append(f"{n_daily} daily summaries found")

        n_entities = len(ctx["entity_contexts"])
        if n_entities:
            names = list(ctx["entity_contexts"].keys())
            parts.append(f"{n_entities} entity contexts: {', '.join(names[:5])}")

        n_semantic = len(ctx["semantic_results"])
        if n_semantic:
            parts.append(f"{n_semantic} semantic search results")

        n_reasoning = len(ctx["related_reasoning"])
        if n_reasoning:
            parts.append(f"{n_reasoning} related past decisions")

        return "; ".join(parts) if parts else "no context found"

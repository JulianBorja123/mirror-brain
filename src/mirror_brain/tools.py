"""
Mirror Brain v1.0 — Search Tools for the Agent.
Provides the SearchTools class with typed, fallback-safe search methods
that the LLM agent can invoke to explore memory.
"""

import json
from datetime import date, timedelta
from typing import Optional

# ── Emotion order mapping ──────────────────────────────────────
# The emotional_arc stored in daily_index is a JSON array where
# each index corresponds to a specific emotion.
EMOTION_INDICES: dict[str, int] = {
    "oxytocin":   0,
    "adrenaline": 1,
    "cortisol":   2,
    "dopamine":   3,
}


class SearchTools:
    """Agent-facing search tools for Mirror Brain memory exploration.

    Every method accepts ``registry`` (an EntityRegistry instance) as its
    first positional argument and returns plain dicts / lists of dicts
    that are safe to serialise and pass directly into an LLM context.
    All methods degrade gracefully when no results are found.
    """

    # ── 1. Semantic (c0 hybrid) search ──────────────────────────

    @staticmethod
    def search_semantic(
        registry,            # EntityRegistry
        c0,                  # C0Client | None
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        """Hybrid search via c0 (exact → keyword → vector RRF).

        Returns a list of result dicts, or an empty list on failure.
        """
        if c0 is None:
            return []

        try:
            results = c0.search(query, limit=limit)
            if not results:
                return []
            # Normalise raw-text fallback from c0._parse_list
            normalised = []
            for r in results:
                if "raw" in r and len(r) == 1:
                    normalised.append({"text": r["raw"]})
                else:
                    normalised.append(r)
            return normalised
        except Exception:
            return []

    # ── 2. Emotion search ───────────────────────────────────────

    @staticmethod
    def search_by_emotion(
        registry,              # EntityRegistry
        emotion: str = "oxytocin",
        threshold: float = 0.5,
        limit: int = 10,
    ) -> list[dict]:
        """Return daily summaries where *emotion* exceeds *threshold*.

        Looks up ``emotional_arc`` (JSON array) in the daily_index table.
        Supported emotions: oxytocin, adrenaline, cortisol, dopamine.
        """
        idx = EMOTION_INDICES.get(emotion)
        if idx is None:
            return []

        try:
            rows = registry.db.execute(
                "SELECT date, summary, emotional_arc, key_entities, key_decisions "
                "FROM daily_index "
                "WHERE emotional_arc != '[]' AND emotional_arc != '' "
                "ORDER BY date DESC "
                "LIMIT ?",
                (limit * 3,),  # over-fetch so we can filter in Python
            ).fetchall()
        except Exception:
            return []

        results: list[dict] = []
        for row in rows:
            try:
                arc = json.loads(row[2]) if row[2] else []
            except (json.JSONDecodeError, TypeError):
                continue

            if len(arc) <= idx:
                continue
            if arc[idx] < threshold:
                continue

            results.append({
                "date":          row[0],
                "summary":       row[1],
                "score":         arc[idx],
                "emotional_arc": arc,
                "key_entities":  json.loads(row[3]) if row[3] else [],
                "key_decisions": json.loads(row[4]) if row[4] else [],
            })

            if len(results) >= limit:
                break

        return results

    # ── 3. Temporal search ──────────────────────────────────────

    @staticmethod
    def search_temporal(
        registry,              # EntityRegistry
        days_ago: int = 0,
        window: int = 3,
    ) -> list[dict]:
        """Get daily summaries in a *window*-day band around *days_ago*.

        ``days_ago=0`` means today; ``window=3`` returns today ± 1 day.
        Results are ordered by date ascending.
        """
        today = date.today()
        target = today - timedelta(days=days_ago)
        start = target - timedelta(days=window // 2)
        end = target + timedelta(days=window // 2)

        try:
            rows = registry.db.execute(
                "SELECT date, summary, emotional_arc, key_entities, key_decisions "
                "FROM daily_index "
                "WHERE date >= ? AND date <= ? "
                "ORDER BY date ASC",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        except Exception:
            return []

        return [
            {
                "date":          row[0],
                "summary":       row[1],
                "emotional_arc": json.loads(row[2]) if row[2] else [],
                "key_entities":  json.loads(row[3]) if row[3] else [],
                "key_decisions": json.loads(row[4]) if row[4] else [],
            }
            for row in rows
        ]

    # ── 4. Fuzzy name search ────────────────────────────────────

    @staticmethod
    def search_fuzzy(
        registry,              # EntityRegistry
        name: str,
        max_distance: int = 3,
    ) -> list[dict]:
        """LIKE-based + non-contiguous word search across canonical names and aliases.

        Falls back to multi-word non-contiguous matching when LIKE returns
        no results (e.g., \"Gustavo Barrios\" matching \"Gustavo Julian Barrios Borja\")."
        """
        like = f"%{name}%"
        try:
            rows = registry.db.execute(
                "SELECT DISTINCT e.uuid, e.canonical_name, e.type, e.status "
                "FROM entities e "
                "LEFT JOIN aliases a ON e.uuid = a.entity_uuid "
                "WHERE e.canonical_name LIKE ? "
                "   OR a.alias LIKE ? "
                "ORDER BY e.canonical_name "
                "LIMIT 20",
                (like, like),
            ).fetchall()
        except Exception:
            return []

        # If LIKE found nothing, try non-contiguous word matching
        if not rows:
            words = name.lower().split()
            if len(words) >= 2:
                try:
                    # Fetch all candidate rows and filter in Python
                    all_rows = registry.db.execute(
                        "SELECT DISTINCT e.uuid, e.canonical_name, e.type, e.status "
                        "FROM entities e "
                        "LEFT JOIN aliases a ON e.uuid = a.entity_uuid "
                        "WHERE e.canonical_name LIKE ? OR e.canonical_name LIKE ? "
                        "   OR a.alias LIKE ? OR a.alias LIKE ? "
                        "ORDER BY e.canonical_name LIMIT 100",
                        (f"%{words[0]}%", f"%{words[-1]}%", f"%{words[0]}%", f"%{words[-1]}%"),
                    ).fetchall()
                    # Filter: all words must appear (non-contiguously)
                    for row in all_rows:
                        canon_lower = row[1].lower()
                        # Also check aliases
                        alias_rows = registry.db.execute(
                            "SELECT alias FROM aliases WHERE entity_uuid=?", (row[0],)
                        ).fetchall()
                        aliases_lower = [a[0].lower() for a in alias_rows]
                        search_in = [canon_lower] + aliases_lower
                        if any(all(w in s for w in words) for s in search_in):
                            if row not in rows:
                                rows.append(row)
                except Exception:
                    pass

        if not rows:
            return []

        results: list[dict] = []
        for row in rows:
            uuid_ = row[0]
            aliases = _safe_get_aliases(registry, uuid_)
            results.append({
                "uuid":            uuid_,
                "canonical_name":  row[1],
                "type":            row[2],
                "status":          row[3],
                "aliases":         aliases,
                "max_distance":    max_distance,
            })

        return results

    # ── 5. Entity minimap ───────────────────────────────────────

    @staticmethod
    def get_minimap(
        registry,              # EntityRegistry
        entity_name: str,
    ) -> dict:
        """Return a compact entity overview ready for LLM consumption.

        Includes: canonical_name, type, aliases, relation count,
        recent reasoning activity, and an emotional profile derived
        from daily summaries that mention the entity.
        """
        # Resolve
        entity_uuid = None
        try:
            entity_uuid = registry.resolve(entity_name)
        except Exception:
            pass

        if not entity_uuid:
            return {"error": f"entity '{entity_name}' not found", "entity_name": entity_name}

        info = _safe_get_entity(registry, entity_uuid)
        if not info:
            return {"error": f"entity '{entity_name}' not found", "entity_name": entity_name}

        aliases = _safe_get_aliases(registry, entity_uuid)
        relations_count = _count_relations(registry, entity_uuid)
        recent_activity = _recent_reasoning(registry, entity_uuid)
        emotional_profile = _entity_emotional_profile(registry, info["canonical_name"])

        return {
            "canonical_name":    info["canonical_name"],
            "type":              info["type"],
            "status":            info.get("status", "active"),
            "aliases":           aliases,
            "relations_count":   relations_count,
            "recent_activity":   recent_activity,
            "emotional_profile": emotional_profile,
        }

    # ── 6. Weekly summary ───────────────────────────────────────

    @staticmethod
    def get_weekly_summary(
        registry,              # EntityRegistry
        week_start: Optional[str] = None,
    ) -> dict:
        """Return an aggregated weekly summary.

        If *week_start* is ``None``, uses the most recent Monday.
        Aggregates daily_summaries, counts entities, and averages
        emotional arcs for the 7-day window.
        """
        # Determine week boundaries
        if week_start:
            try:
                start = date.fromisoformat(week_start)
            except (ValueError, TypeError):
                return {"error": f"invalid week_start date: {week_start!r}"}
        else:
            today = date.today()
            start = today - timedelta(days=today.weekday())  # Monday

        end = start + timedelta(days=6)

        try:
            rows = registry.db.execute(
                "SELECT date, summary, emotional_arc, key_entities, key_decisions "
                "FROM daily_index "
                "WHERE date >= ? AND date <= ? "
                "ORDER BY date ASC",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        except Exception:
            return {"week_start": start.isoformat(), "week_end": end.isoformat(), "days": []}

        days = []
        all_entities: set[str] = set()
        all_decisions: set[str] = set()
        arc_sums: list[float] = [0.0, 0.0, 0.0, 0.0]
        arc_count = 0

        for row in rows:
            arc = json.loads(row[2]) if row[2] else []
            entities = json.loads(row[3]) if row[3] else []
            decisions = json.loads(row[4]) if row[4] else []

            days.append({
                "date":          row[0],
                "summary":       row[1],
                "emotional_arc": arc,
                "key_entities":  entities,
                "key_decisions": decisions,
            })
            all_entities.update(entities)
            all_decisions.update(decisions)

            if len(arc) == 4:
                for i in range(4):
                    arc_sums[i] += arc[i]
                arc_count += 1

        avg_arc = (
            [round(s / arc_count, 3) for s in arc_sums]
            if arc_count > 0
            else [0.0, 0.0, 0.0, 0.0]
        )

        # Determine dominant emotion
        emotion_names = ["oxytocin", "adrenaline", "cortisol", "dopamine"]
        dominant = ""
        if arc_count > 0:
            max_idx = max(range(4), key=lambda i: avg_arc[i])
            dominant = emotion_names[max_idx]

        return {
            "week_start":       start.isoformat(),
            "week_end":         end.isoformat(),
            "days_covered":     len(days),
            "dominant_emotion": dominant,
            "average_arc":      {
                name: avg_arc[i] for i, name in enumerate(emotion_names)
            },
            "key_entities":     sorted(all_entities),
            "key_decisions":    sorted(all_decisions),
            "days":             days,
        }

    # ── 7. Raw text search ──────────────────────────────────────

    @staticmethod
    def search_raw_text(
        registry,              # EntityRegistry
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        """LIKE search on the ``raw_texts`` table.

        Falls back gracefully if the table does not exist yet.
        """
        like = f"%{query}%"
        try:
            rows = registry.db.execute(
                "SELECT uuid, content, created_at, source "
                "FROM raw_texts "
                "WHERE content LIKE ? "
                "ORDER BY created_at DESC "
                "LIMIT ?",
                (like, limit),
            ).fetchall()
        except Exception:
            return []

        return [
            {
                "id":        row[0],
                "content":   row[1],
                "timestamp": row[2],
                "source":    row[3] if len(row) > 3 else "",
            }
            for row in rows
        ]

    # ── 8. Procedural memory search ─────────────────────────────

    @staticmethod
    def search_procedures(
        registry,              # EntityRegistry
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        """Fuzzy-match *query* against stored procedures via ProceduralMemory.

        Returns ranked procedure suggestions, or an empty list if the
        ``procedural`` module or ``procedures`` table is unavailable.
        """
        try:
            from .procedural import ProceduralMemory
        except Exception:
            return []
        try:
            pm = ProceduralMemory(registry)
            return pm.suggest_procedure(query, limit=limit)
        except Exception:
            return []

    # ── 9. Procedure detail lookup ──────────────────────────────

    @staticmethod
    def get_procedure(
        registry,              # EntityRegistry
        name: str,
    ) -> dict:
        """Return full details for a named procedure.

        Reads from the ``procedures`` table directly.  Returns a dict
        with ``error`` if the table is missing or the procedure
        is not found.
        """
        try:
            row = registry.db.execute(
                "SELECT name, steps, context, success_count, fail_count, "
                "last_used, created_at "
                "FROM procedures "
                "WHERE name = ?",
                (name,),
            ).fetchone()
        except Exception:
            return {"error": "procedures table unavailable", "name": name}

        if row is None:
            return {"error": f"procedure {name!r} not found", "name": name}

        # Decode steps JSON safely
        try:
            steps = json.loads(row[1]) if row[1] else []
        except (json.JSONDecodeError, TypeError):
            steps = []

        total = row[3] + row[4]
        success_rate = (row[3] / total) if total > 0 else None

        return {
            "name":          row[0],
            "steps":         steps,
            "context":       row[2],
            "success_count": row[3],
            "fail_count":    row[4],
            "success_rate":  round(success_rate, 4) if success_rate is not None else None,
            "last_used":     row[5],
            "created_at":    row[6],
        }

    # ── 10. Temporal range search ───────────────────────────────

    @staticmethod
    def search_temporal_range(
        registry,                # EntityRegistry
        start_days_ago: int,
        end_days_ago: int,
    ) -> list[dict]:
        """Return daily_index entries between *start_days_ago* and *end_days_ago*.

        ``start_days_ago`` must be larger (older) than ``end_days_ago``
        to form a valid range into the past.  Results are ordered by
        date ascending.
        """
        today = date.today()
        # Ensure start is the older date (further in the past)
        if start_days_ago < end_days_ago:
            start_days_ago, end_days_ago = end_days_ago, start_days_ago

        start_date = today - timedelta(days=start_days_ago)
        end_date = today - timedelta(days=end_days_ago)

        try:
            rows = registry.db.execute(
                "SELECT date, summary, emotional_arc, key_entities, key_decisions "
                "FROM daily_index "
                "WHERE date >= ? AND date <= ? "
                "ORDER BY date ASC",
                (start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
        except Exception:
            return []

        return [
            {
                "date":          row[0],
                "summary":       row[1],
                "emotional_arc": json.loads(row[2]) if row[2] else [],
                "key_entities":  json.loads(row[3]) if row[3] else [],
                "key_decisions": json.loads(row[4]) if row[4] else [],
            }
            for row in rows
        ]

    # ── 11. Monthly summary lookup ──────────────────────────────

    @staticmethod
    def get_monthly_summary(
        registry,                  # EntityRegistry
        month_start: Optional[str] = None,
    ) -> dict:
        """Return a monthly_summaries entry.

        If *month_start* is ``None``, returns the most recent month.
        The ``month_start`` must be the first day of the month in ISO
        format (``YYYY-MM-DD``).
        """
        try:
            if month_start is None:
                row = registry.db.execute(
                    "SELECT month_start, summary, emotional_arc, key_entities, "
                    "key_themes, source_weeks, created_at "
                    "FROM monthly_summaries "
                    "ORDER BY month_start DESC "
                    "LIMIT 1"
                ).fetchone()
            else:
                # Normalise to first of month
                try:
                    d = date.fromisoformat(month_start)
                except (ValueError, TypeError):
                    return {"error": f"invalid month_start: {month_start!r}"}
                first = d.replace(day=1)
                row = registry.db.execute(
                    "SELECT month_start, summary, emotional_arc, key_entities, "
                    "key_themes, source_weeks, created_at "
                    "FROM monthly_summaries "
                    "WHERE month_start = ?",
                    (first.isoformat(),),
                ).fetchone()
        except Exception:
            return {"month_start": month_start, "error": "monthly_summaries table unavailable"}

        if row is None:
            return {"month_start": month_start or "latest", "error": "not found"}

        return {
            "month_start":    row[0],
            "summary":        row[1],
            "emotional_arc":  json.loads(row[2]) if row[2] else [],
            "key_entities":   json.loads(row[3]) if row[3] else [],
            "key_themes":     json.loads(row[4]) if row[4] else [],
            "source_weeks":   json.loads(row[5]) if row[5] else [],
            "created_at":     row[6],
        }

    # ── 12. Cycle detection ─────────────────────────────────────

    @staticmethod
    def search_cycles(
        registry,                # EntityRegistry
        entity_name: str,
        metric: str = "oxytocin",
    ) -> dict:
        """Detect periodic cycles via PredictiveEngine.detect_cycles.

        Returns a ``has_cycle`` / ``period_days`` / ``confidence`` dict,
        or a fallback dict on error.
        """
        try:
            from .predictive import PredictiveEngine
        except Exception:
            return {"has_cycle": False, "period_days": 0, "confidence": 0.0,
                    "error": "predictive module unavailable"}
        try:
            pe = PredictiveEngine(registry)
            return pe.detect_cycles(entity_name, metric=metric)
        except Exception:
            return {"has_cycle": False, "period_days": 0, "confidence": 0.0,
                    "error": "cycle detection failed"}

    # ── 13. Trend report ────────────────────────────────────────

    @staticmethod
    def get_trend(
        registry,                # EntityRegistry
        entity_name: str,
        metric: str = "oxytocin",
        window: int = 30,
    ) -> dict:
        """Return a linear-regression trend report via PredictiveEngine.trend_report.

        Returns a ``direction`` / ``slope`` / ``r_squared`` / ``confidence``
        dict, or a fallback on error.
        """
        try:
            from .predictive import PredictiveEngine
        except Exception:
            return {"direction": "stable", "slope": 0.0, "r_squared": 0.0,
                    "confidence": 0.0, "error": "predictive module unavailable"}
        try:
            pe = PredictiveEngine(registry)
            return pe.trend_report(entity_name, metric=metric, window=window)
        except Exception:
            return {"direction": "stable", "slope": 0.0, "r_squared": 0.0,
                    "confidence": 0.0, "error": "trend report failed"}

    # ── 14. Anomaly detection ───────────────────────────────────

    @staticmethod
    def get_anomalies(
        registry,                # EntityRegistry
        entity_name: str,
        metric: str = "oxytocin",
    ) -> list[dict]:
        """Flag outlier days via PredictiveEngine.anomaly_detect.

        Returns a list of ``{date, value, zscore}`` dicts for flagged
        outliers, or an empty list on error.
        """
        try:
            from .predictive import PredictiveEngine
        except Exception:
            return []
        try:
            pe = PredictiveEngine(registry)
            return pe.anomaly_detect(entity_name, metric=metric)
        except Exception:
            return []

    # ── 15. Memory budget ───────────────────────────────────────

    @staticmethod
    def get_memory_budget(
        registry,                # EntityRegistry
    ) -> dict:
        """Return counts at each consolidation tier via HierarchicalConsolidation.

        Returns ``{daily, weekly, monthly}`` counts, or zeros on error.
        """
        try:
            from .consolidation import HierarchicalConsolidation
        except Exception:
            return {"daily": 0, "weekly": 0, "monthly": 0,
                    "error": "consolidation module unavailable"}
        try:
            hc = HierarchicalConsolidation(registry)
            return hc.get_memory_budget()
        except Exception:
            return {"daily": 0, "weekly": 0, "monthly": 0,
                    "error": "memory budget query failed"}


# ── Internal helpers ────────────────────────────────────────────

def _safe_get_entity(registry, uuid_: str) -> Optional[dict]:
    """Safely call registry.get(), returning None on any error."""
    try:
        return registry.get(uuid_)
    except Exception:
        return None


def _safe_get_aliases(registry, uuid_: str) -> list[str]:
    """Safely return alias name strings for an entity UUID."""
    try:
        alias_dicts = registry.get_aliases(uuid_)
        return [a["alias"] for a in alias_dicts]
    except Exception:
        return []


def _count_relations(registry, uuid_: str) -> int:
    """Count relations where *uuid_* is the source or target."""
    try:
        row = registry.db.execute(
            "SELECT COUNT(*) FROM relations "
            "WHERE from_uuid = ? OR to_uuid = ?",
            (uuid_, uuid_),
        ).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def _recent_reasoning(registry, uuid_: str, limit: int = 5) -> list[dict]:
    """Return the most recent reasoning-trail entries for an entity."""
    try:
        rows = registry.db.execute(
            "SELECT timestamp, action, confidence, reasoning, source "
            "FROM reasoning_trail "
            "WHERE entity_uuid = ? OR target_uuid = ? "
            "ORDER BY timestamp DESC "
            "LIMIT ?",
            (uuid_, uuid_, limit),
        ).fetchall()
        return [
            {
                "timestamp":  row[0],
                "action":     row[1],
                "confidence": row[2],
                "reasoning":  row[3],
                "source":     row[4],
            }
            for row in rows
        ]
    except Exception:
        return []


def _entity_emotional_profile(registry, canonical_name: str) -> dict:
    """Build an emotional profile for an entity from daily summaries.

    Averages emotional_arc values across days where the entity appears
    in key_entities.
    """
    try:
        rows = registry.db.execute(
            "SELECT emotional_arc FROM daily_index "
            "WHERE key_entities LIKE ? AND emotional_arc != '[]' AND emotional_arc != ''",
            (f"%{canonical_name}%",),
        ).fetchall()
    except Exception:
        return {}

    if not rows:
        return {}

    sums = [0.0, 0.0, 0.0, 0.0]
    count = 0
    for (arc_str,) in rows:
        try:
            arc = json.loads(arc_str)
        except (json.JSONDecodeError, TypeError):
            continue
        if len(arc) != 4:
            continue
        for i in range(4):
            sums[i] += arc[i]
        count += 1

    if count == 0:
        return {}

    emotion_names = ["oxytocin", "adrenaline", "cortisol", "dopamine"]
    avg = [round(s / count, 3) for s in sums]

    # Determine dominant and top emotions
    dominant_idx = max(range(4), key=lambda i: avg[i])

    return {
        "average":  {name: avg[i] for i, name in enumerate(emotion_names)},
        "dominant": emotion_names[dominant_idx],
        "days_with_mentions": count,
    }

"""
Mirror Brain v3 — Hierarchical Memory Consolidation.
Progressive compaction: daily → weekly → monthly.

Uses LLM when available (callable passed at init), falls back to
extractive compaction (first-N-chars) when no LLM is provided.
Stdlib only — no external dependencies beyond the Python standard library
and Mirror Brain's own registry / tools modules.
"""

import json
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from .tools import SearchTools


# ── LLM prompts ────────────────────────────────────────────────────

DAILY_CONSOLIDATION_PROMPT = """You are a memory consolidation system. Given a daily journal entry,
produce a compact representation.

## Input (daily entry)
Date: {date}
Summary: {summary}
Existing entities: {key_entities}
Existing emotional arc: {emotional_arc}
Key decisions: {key_decisions}

## Task
1. Write a 1-2 sentence summary that captures the essence of the day.
2. List key entities mentioned (people, projects, tools, places, concepts).
3. Rate the emotional arc as [oxytocin, adrenaline, cortisol, dopamine] on a 0.0-1.0 scale.
4. List any key decisions made.

## Output Format (JSON only, no markdown, no explanation)
{{
  "summary": "1-2 sentence compact summary",
  "key_entities": ["entity1", "entity2"],
  "emotional_arc": [0.0, 0.0, 0.0, 0.0],
  "key_decisions": ["decision1"]
}}"""


WEEKLY_CONSOLIDATION_PROMPT = """You are a memory consolidation system. Given 7 daily summaries,
produce a weekly synthesis.

## Input (7 daily summaries)
{daily_summaries}

## Task
1. Write a 2-4 sentence summary capturing the week's themes, progress, and emotional trajectory.
2. List key entities that appeared across the week.
3. Identify 3-5 key themes for the week.
4. Rate the overall emotional arc as [oxytocin, adrenaline, cortisol, dopamine] on a 0.0-1.0 scale.
5. List the source days used.

## Output Format (JSON only, no markdown, no explanation)
{{
  "summary": "2-4 sentence weekly summary",
  "key_entities": ["entity1", "entity2"],
  "key_themes": ["theme1", "theme2", "theme3"],
  "emotional_arc": [0.0, 0.0, 0.0, 0.0],
  "source_days": ["2024-01-01", "2024-01-02"]
}}"""


MONTHLY_CONSOLIDATION_PROMPT = """You are a memory consolidation system. Given weekly summaries
for a month, produce a monthly synthesis.

## Input (weekly summaries)
{weekly_summaries}

## Task
1. Write a 3-5 sentence summary capturing the month's arc, major events, and growth.
2. List key entities that appeared across the month.
3. Identify 3-5 key themes for the month.
4. Rate the overall emotional arc as [oxytocin, adrenaline, cortisol, dopamine] on a 0.0-1.0 scale.
5. List the source weeks used.

## Output Format (JSON only, no markdown, no explanation)
{{
  "summary": "3-5 sentence monthly summary",
  "key_entities": ["entity1", "entity2"],
  "key_themes": ["theme1", "theme2", "theme3"],
  "emotional_arc": [0.0, 0.0, 0.0, 0.0],
  "source_weeks": ["2024-01-01", "2024-01-08"]
}}"""


# ── Helpers ────────────────────────────────────────────────────────

def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _monday_of_week(d: date) -> date:
    """Return the Monday on or before *d*."""
    return d - timedelta(days=d.weekday())


def _first_of_month(d: date) -> date:
    """Return the first day of the month containing *d*."""
    return d.replace(day=1)


def _parse_json_safe(raw: str) -> dict:
    """Parse an LLM response into a dict, with robust fallback."""
    import re

    cleaned = raw.strip()
    # Strip markdown fences
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {}


# ── Extractive fallback functions ──────────────────────────────────

def _extractive_daily(row: tuple, max_chars: int = 200) -> dict:
    """Build a compact daily dict from a daily_index row without LLM.

    *row* is (date, summary, emotional_arc, key_entities, key_decisions).
    """
    date_str, summary, emotional_arc, key_entities, key_decisions = row

    # Compact summary: first N chars, ending at a sentence boundary
    compact = summary[:max_chars].rsplit(".", 1)[0] + "." if len(summary) > max_chars else summary

    # Parse existing JSON fields
    try:
        arc = json.loads(emotional_arc) if emotional_arc else [0.0, 0.0, 0.0, 0.0]
    except (json.JSONDecodeError, TypeError):
        arc = [0.0, 0.0, 0.0, 0.0]
    try:
        entities = json.loads(key_entities) if key_entities else []
    except (json.JSONDecodeError, TypeError):
        entities = []
    try:
        decisions = json.loads(key_decisions) if key_decisions else []
    except (json.JSONDecodeError, TypeError):
        decisions = []

    return {
        "summary": compact,
        "key_entities": entities,
        "emotional_arc": arc,
        "key_decisions": decisions,
    }


def _extractive_weekly(daily_rows: list[tuple], max_chars_per_day: int = 150) -> dict:
    """Build a weekly summary from daily_index rows without LLM.

    Each row is (date, summary, emotional_arc, key_entities, key_decisions).
    """
    if not daily_rows:
        return {
            "summary": "(no daily entries for this week)",
            "key_entities": [],
            "key_themes": [],
            "emotional_arc": [0.0, 0.0, 0.0, 0.0],
            "source_days": [],
        }

    parts: list[str] = []
    all_entities: set[str] = set()
    arc_sums = [0.0, 0.0, 0.0, 0.0]
    arc_count = 0
    source_days: list[str] = []

    for row in daily_rows:
        date_str, summary, emotional_arc, key_entities, _key_decisions = row
        source_days.append(date_str)
        parts.append(f"[{date_str}] {summary[:max_chars_per_day]}")

        try:
            entities = json.loads(key_entities) if key_entities else []
        except (json.JSONDecodeError, TypeError):
            entities = []
        all_entities.update(entities)

        try:
            arc = json.loads(emotional_arc) if emotional_arc else []
        except (json.JSONDecodeError, TypeError):
            arc = []
        if len(arc) == 4:
            for i in range(4):
                arc_sums[i] += arc[i]
            arc_count += 1

    avg_arc = (
        [round(s / arc_count, 3) for s in arc_sums]
        if arc_count > 0
        else [0.0, 0.0, 0.0, 0.0]
    )

    return {
        "summary": " ".join(parts),
        "key_entities": sorted(all_entities),
        "key_themes": [],
        "emotional_arc": avg_arc,
        "source_days": source_days,
    }


def _extractive_monthly(weekly_rows: list[tuple], max_chars_per_week: int = 200) -> dict:
    """Build a monthly summary from weekly_summaries rows without LLM.

    Each row is (week_start, summary, key_entities, key_themes, emotional_arc, source_days).
    """
    if not weekly_rows:
        return {
            "summary": "(no weekly entries for this month)",
            "key_entities": [],
            "key_themes": [],
            "emotional_arc": [0.0, 0.0, 0.0, 0.0],
            "source_weeks": [],
        }

    parts: list[str] = []
    all_entities: set[str] = set()
    all_themes: set[str] = set()
    arc_sums = [0.0, 0.0, 0.0, 0.0]
    arc_count = 0
    source_weeks: list[str] = []

    for row in weekly_rows:
        week_start, summary, key_entities, key_themes, emotional_arc, _source_days = row
        source_weeks.append(week_start)
        parts.append(f"[week {week_start}] {summary[:max_chars_per_week]}")

        try:
            entities = json.loads(key_entities) if key_entities else []
        except (json.JSONDecodeError, TypeError):
            entities = []
        all_entities.update(entities)

        try:
            themes = json.loads(key_themes) if key_themes else []
        except (json.JSONDecodeError, TypeError):
            themes = []
        all_themes.update(themes)

        try:
            arc = json.loads(emotional_arc) if emotional_arc else []
        except (json.JSONDecodeError, TypeError):
            arc = []
        if len(arc) == 4:
            for i in range(4):
                arc_sums[i] += arc[i]
            arc_count += 1

    avg_arc = (
        [round(s / arc_count, 3) for s in arc_sums]
        if arc_count > 0
        else [0.0, 0.0, 0.0, 0.0]
    )

    return {
        "summary": " ".join(parts),
        "key_entities": sorted(all_entities),
        "key_themes": sorted(all_themes),
        "emotional_arc": avg_arc,
        "source_weeks": source_weeks,
    }


# ── Main class ─────────────────────────────────────────────────────

class HierarchicalConsolidation:
    """Progressive memory compaction: daily → weekly → monthly.

    Storage backend: c0 (Neo4j + Ollama) via C0Registry compatibility layer.
    Consolidation entries are stored as c0 concepts with prefix
    ``[consolidation] {tier} {date}`` and the full JSON result as the
    concept description.

    Parameters
    ----------
    registry : C0Registry
        The Mirror Brain entity registry (provides ``.db`` access via
        FakeCursor compatibility layer).
    llm_call : callable, optional
        A function ``llm_call(prompt: str) -> str`` that invokes an LLM.
        When ``None``, all consolidation uses extractive fallback
        (first-N-chars of source text).
    """

    def __init__(self, registry, llm_call: Optional[Callable[[str], str]] = None):
        self.registry = registry
        self.db = registry.db
        self.llm = llm_call

    # ── 1. Daily consolidation ─────────────────────────────────

    def consolidate_daily(self, date_str: str) -> dict:
        """Compact a daily_index entry into a 1-2 sentence summary.

        Reads the existing row, optionally invokes the LLM to produce a
        compact summary + extracted key_entities / emotional_arc, and
        writes the result back to ``daily_index``.

        Returns the compacted dict.
        """
        # Fetch current row
        row = self.db.execute(
            "SELECT date, summary, emotional_arc, key_entities, key_decisions "
            "FROM daily_index WHERE date = ?",
            (date_str,),
        ).fetchone()

        if row is None:
            return {"error": f"no daily_index entry for {date_str!r}", "date": date_str}

        date_val, summary, emotional_arc, key_entities, key_decisions = row

        if self.llm is not None:
            result = self._llm_consolidate_daily(
                date_val, summary, emotional_arc, key_entities, key_decisions
            )
        else:
            result = _extractive_daily(row)

        # Upsert the compacted results
        now = _now_iso()
        self.db.execute(
            """INSERT INTO daily_index (date, summary, emotional_arc, key_entities, key_decisions, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                   summary = excluded.summary,
                   emotional_arc = excluded.emotional_arc,
                   key_entities = excluded.key_entities""",
            (
                date_val,
                result.get("summary", summary),
                json.dumps(result.get("emotional_arc", [])),
                json.dumps(result.get("key_entities", [])),
                json.dumps(result.get("key_decisions", [])),
                now,
            ),
        )
        self.db.commit()

        return {"date": date_val, **result}

    def _llm_consolidate_daily(
        self,
        date_val: str,
        summary: str,
        emotional_arc: str,
        key_entities: str,
        key_decisions: str,
    ) -> dict:
        """Call the LLM to compact a single daily entry."""
        prompt = DAILY_CONSOLIDATION_PROMPT.format(
            date=date_val,
            summary=summary[:2000],
            key_entities=key_entities,
            emotional_arc=emotional_arc,
            key_decisions=key_decisions,
        )
        raw = self.llm(prompt)
        parsed = _parse_json_safe(raw)

        # Extract and validate fields
        compact_summary = parsed.get("summary", summary[:200])
        entities = parsed.get("key_entities", [])
        if not isinstance(entities, list):
            entities = []
        arc = parsed.get("emotional_arc", [0.0, 0.0, 0.0, 0.0])
        if not isinstance(arc, list) or len(arc) != 4:
            arc = [0.0, 0.0, 0.0, 0.0]
        decisions = parsed.get("key_decisions", [])
        if not isinstance(decisions, list):
            decisions = []

        return {
            "summary": compact_summary,
            "key_entities": entities,
            "emotional_arc": [round(float(v), 3) for v in arc],
            "key_decisions": decisions,
        }

    # ── 2. Weekly consolidation ────────────────────────────────

    def consolidate_weekly(self, week_start: str) -> dict:
        """Aggregate 7 daily summaries into one weekly_summaries entry.

        *week_start* must be a Monday date in ISO format (``YYYY-MM-DD``).
        Fetches daily_index rows for Mon–Sun, then runs the LLM (or
        extractive fallback) to produce a compact weekly summary.

        The result is upserted into the ``weekly_summaries`` table.
        """
        try:
            start = date.fromisoformat(week_start)
        except (ValueError, TypeError):
            return {"error": f"invalid week_start date: {week_start!r}"}

        # Ensure Monday
        start = _monday_of_week(start)
        end = start + timedelta(days=6)

        # Fetch the 7 daily summaries for this week
        rows = self.db.execute(
            "SELECT date, summary, emotional_arc, key_entities, key_decisions "
            "FROM daily_index "
            "WHERE date >= ? AND date <= ? "
            "ORDER BY date ASC",
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        if self.llm is not None and rows:
            result = self._llm_consolidate_weekly(rows)
        else:
            result = _extractive_weekly(rows)

        # Upsert into weekly_summaries
        now = _now_iso()
        self.db.execute(
            """INSERT INTO weekly_summaries
               (week_start, summary, key_entities, key_themes, emotional_arc, source_days, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(week_start) DO UPDATE SET
                   summary = excluded.summary,
                   key_entities = excluded.key_entities,
                   key_themes = excluded.key_themes,
                   emotional_arc = excluded.emotional_arc,
                   source_days = excluded.source_days""",
            (
                start.isoformat(),
                result.get("summary", ""),
                json.dumps(result.get("key_entities", [])),
                json.dumps(result.get("key_themes", [])),
                json.dumps(result.get("emotional_arc", [])),
                json.dumps(result.get("source_days", [])),
                now,
            ),
        )
        self.db.commit()

        return {
            "week_start": start.isoformat(),
            "days_covered": len(rows),
            **{k: v for k, v in result.items() if k != "source_days"},
            "source_days": result.get("source_days", []),
        }

    def _llm_consolidate_weekly(self, daily_rows: list[tuple]) -> dict:
        """Call the LLM to produce a weekly summary from daily rows."""
        # Build a text summary of each day
        day_texts: list[str] = []
        for row in daily_rows:
            date_str, summary, _arc, _entities, _decisions = row
            day_texts.append(f"  {date_str}: {summary[:300]}")

        prompt = WEEKLY_CONSOLIDATION_PROMPT.format(
            daily_summaries="\n".join(day_texts),
        )
        raw = self.llm(prompt)
        parsed = _parse_json_safe(raw)

        summary = parsed.get("summary", "")
        entities = parsed.get("key_entities", [])
        if not isinstance(entities, list):
            entities = []
        themes = parsed.get("key_themes", [])
        if not isinstance(themes, list):
            themes = []
        arc = parsed.get("emotional_arc", [0.0, 0.0, 0.0, 0.0])
        if not isinstance(arc, list) or len(arc) != 4:
            arc = [0.0, 0.0, 0.0, 0.0]
        source_days = parsed.get("source_days", [])
        if not isinstance(source_days, list):
            source_days = [row[0] for row in daily_rows]

        return {
            "summary": summary,
            "key_entities": entities,
            "key_themes": themes,
            "emotional_arc": [round(float(v), 3) for v in arc],
            "source_days": source_days,
        }

    # ── 3. Monthly consolidation ───────────────────────────────

    def consolidate_monthly(self, month_start: str) -> dict:
        """Aggregate 4-5 weekly summaries into one monthly_summaries entry.

        *month_start* must be a date in ISO format (``YYYY-MM-DD``). It is
        normalised to the first of the month. Fetches weekly_summaries rows
        whose ``week_start`` falls within that calendar month and runs the
        LLM (or extractive fallback) to produce a monthly synthesis.

        The result is upserted into the ``monthly_summaries`` table.
        """
        try:
            start = date.fromisoformat(month_start)
        except (ValueError, TypeError):
            return {"error": f"invalid month_start date: {month_start!r}"}

        start = _first_of_month(start)

        # End of month: first of next month minus one day
        if start.month == 12:
            end = date(start.year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(start.year, start.month + 1, 1) - timedelta(days=1)

        # Fetch weekly summaries whose week_start falls in this month
        rows = self.db.execute(
            "SELECT week_start, summary, key_entities, key_themes, emotional_arc, source_days "
            "FROM weekly_summaries "
            "WHERE week_start >= ? AND week_start <= ? "
            "ORDER BY week_start ASC",
            (start.isoformat(), end.isoformat()),
        ).fetchall()

        if self.llm is not None and rows:
            result = self._llm_consolidate_monthly(rows)
        else:
            result = _extractive_monthly(rows)

        # Upsert into monthly_summaries
        now = _now_iso()
        self.db.execute(
            """INSERT INTO monthly_summaries
               (month_start, summary, emotional_arc, key_entities, key_themes, source_weeks, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(month_start) DO UPDATE SET
                   summary = excluded.summary,
                   emotional_arc = excluded.emotional_arc,
                   key_entities = excluded.key_entities,
                   key_themes = excluded.key_themes,
                   source_weeks = excluded.source_weeks""",
            (
                start.isoformat(),
                result.get("summary", ""),
                json.dumps(result.get("emotional_arc", [])),
                json.dumps(result.get("key_entities", [])),
                json.dumps(result.get("key_themes", [])),
                json.dumps(result.get("source_weeks", [])),
                now,
            ),
        )
        self.db.commit()

        return {
            "month_start": start.isoformat(),
            "weeks_covered": len(rows),
            **{k: v for k, v in result.items() if k != "source_weeks"},
            "source_weeks": result.get("source_weeks", []),
        }

    def _llm_consolidate_monthly(self, weekly_rows: list[tuple]) -> dict:
        """Call the LLM to produce a monthly summary from weekly rows."""
        week_texts: list[str] = []
        for row in weekly_rows:
            week_start, summary, _entities, _themes, _arc, _source_days = row
            week_texts.append(f"  Week of {week_start}: {summary[:400]}")

        prompt = MONTHLY_CONSOLIDATION_PROMPT.format(
            weekly_summaries="\n".join(week_texts),
        )
        raw = self.llm(prompt)
        parsed = _parse_json_safe(raw)

        summary = parsed.get("summary", "")
        entities = parsed.get("key_entities", [])
        if not isinstance(entities, list):
            entities = []
        themes = parsed.get("key_themes", [])
        if not isinstance(themes, list):
            themes = []
        arc = parsed.get("emotional_arc", [0.0, 0.0, 0.0, 0.0])
        if not isinstance(arc, list) or len(arc) != 4:
            arc = [0.0, 0.0, 0.0, 0.0]
        source_weeks = parsed.get("source_weeks", [])
        if not isinstance(source_weeks, list):
            source_weeks = [row[0] for row in weekly_rows]

        return {
            "summary": summary,
            "key_entities": entities,
            "key_themes": themes,
            "emotional_arc": [round(float(v), 3) for v in arc],
            "source_weeks": source_weeks,
        }

    # ── 4. Auto-consolidate ────────────────────────────────────

    def auto_consolidate(self) -> dict:
        """Consolidate everything that has not yet been compacted.

        Process:
        1. Daily consolidation: compact every daily_index row that has a
           long summary (>300 chars) and is not yet compacted.
        2. Weekly consolidation: group unconsolidated days by week,
           produce a weekly_summaries entry for each week not yet covered.
        3. Monthly consolidation: group unconsolidated weeks by month,
           produce a monthly_summaries entry for each month not yet covered.

        Returns a report of what was done.
        """
        report = {
            "daily": {"consolidated": 0, "errors": []},
            "weekly": {"consolidated": 0, "errors": []},
            "monthly": {"consolidated": 0, "errors": []},
        }

        # ── Step 1: Daily consolidation ──
        # Compact any daily_index row whose summary is long (>300 chars)
        # or where key_entities / emotional_arc are still empty.
        daily_rows = self.db.execute(
            "SELECT date, summary, emotional_arc, key_entities "
            "FROM daily_index"
        ).fetchall()

        for row in daily_rows:
            date_str, summary, emotional_arc, key_entities, *_ = row
            needs_compact = (
                len(summary) > 300
                or emotional_arc in ("", "[]")
                or key_entities in ("", "[]")
            )
            if needs_compact:
                try:
                    self.consolidate_daily(date_str)
                    report["daily"]["consolidated"] += 1
                except Exception as exc:
                    report["daily"]["errors"].append(f"{date_str}: {exc}")

        # ── Step 2: Weekly consolidation ──
        # Find all dates in daily_index that are NOT covered by any
        # weekly_summaries entry, group by their Monday, consolidate.
        done_weeks = set(
            row[0]
            for row in self.db.execute(
                "SELECT week_start FROM weekly_summaries"
            ).fetchall()
        )

        all_dates = [
            row[0]
            for row in self.db.execute(
                "SELECT date FROM daily_index ORDER BY date ASC"
            ).fetchall()
        ]

        weeks_to_do: set[str] = set()
        for d_str in all_dates:
            try:
                d = date.fromisoformat(d_str)
            except (ValueError, TypeError):
                continue
            monday = _monday_of_week(d).isoformat()
            if monday not in done_weeks:
                weeks_to_do.add(monday)

        for monday_str in sorted(weeks_to_do):
            try:
                self.consolidate_weekly(monday_str)
                report["weekly"]["consolidated"] += 1
            except Exception as exc:
                report["weekly"]["errors"].append(f"{monday_str}: {exc}")

        # ── Step 3: Monthly consolidation ──
        # Find all weeks in weekly_summaries that are NOT covered by any
        # monthly_summaries entry, group by their month, consolidate.
        done_months = set(
            row[0]
            for row in self.db.execute(
                "SELECT month_start FROM monthly_summaries"
            ).fetchall()
        )

        all_weeks = [
            row[0]
            for row in self.db.execute(
                "SELECT week_start FROM weekly_summaries ORDER BY week_start ASC"
            ).fetchall()
        ]

        months_to_do: set[str] = set()
        for w_str in all_weeks:
            try:
                w = date.fromisoformat(w_str)
            except (ValueError, TypeError):
                continue
            first = _first_of_month(w).isoformat()
            if first not in done_months:
                months_to_do.add(first)

        for month_str in sorted(months_to_do):
            try:
                self.consolidate_monthly(month_str)
                report["monthly"]["consolidated"] += 1
            except Exception as exc:
                report["monthly"]["errors"].append(f"{month_str}: {exc}")

        return report

    # ── 5. Memory budget ───────────────────────────────────────

    def get_memory_budget(self) -> dict:
        """Return counts of entries at each consolidation tier.

        Returns a dict: ``{"daily": N, "weekly": N, "monthly": N}``.
        """
        daily = self.db.execute(
            "SELECT COUNT(*) FROM daily_index"
        ).fetchone()[0]

        weekly = self.db.execute(
            "SELECT COUNT(*) FROM weekly_summaries"
        ).fetchone()[0]

        monthly = self.db.execute(
            "SELECT COUNT(*) FROM monthly_summaries"
        ).fetchone()[0]

        return {"daily": daily, "weekly": weekly, "monthly": monthly}

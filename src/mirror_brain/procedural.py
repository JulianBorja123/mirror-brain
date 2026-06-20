"""
Mirror Brain v3 — Procedural Memory.
Learns workflows from reasoning_trail and daily_index.
Stores procedures, detects repeated patterns, suggests procedures,
and tracks success rates via procedural traces.
"""

import json
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional


class ProceduralMemory:
    """Learns and recalls procedural workflows from Mirror Brain memory.

    Scans the ``reasoning_trail`` for repeated action sequences, stores
    named procedures in the ``procedures`` table, fuzzy-matches current
    context against stored procedures for ranked suggestions, and logs
    execution outcomes in ``procedural_traces``.
    """

    def __init__(self, registry):
        """Bind to an EntityRegistry for database access.

        Args:
            registry: An ``EntityRegistry`` instance whose ``.db`` attribute
                      points to an open ``sqlite3.Connection``.
        """
        self.registry = registry
        self.db = registry.db

    # ── 1. Detect repeated patterns ─────────────────────────────────

    def detect_repeated_patterns(
        self,
        min_length: int = 2,
        min_repetitions: int = 2,
        limit: int = 20,
    ) -> list[dict]:
        """Find action sequences that repeat across different days.

        Scans ``reasoning_trail``, groups actions by calendar date,
        then looks for subsequences (of at least *min_length* actions)
        that appear on at least *min_repetitions* different days.

        Args:
            min_length: Minimum number of actions in a pattern.
            min_repetitions: Minimum distinct days the pattern must
                             appear on.
            limit: Maximum number of patterns to return.

        Returns:
            List of dicts with keys: ``pattern`` (list of action strings),
            ``length``, ``day_count``, ``days`` (sorted list of date
            strings), ``total_occurrences``.
        """
        try:
            rows = self.db.execute(
                "SELECT timestamp, action FROM reasoning_trail "
                "WHERE reverted = 0 "
                "ORDER BY timestamp ASC"
            ).fetchall()
        except Exception:
            return []

        if not rows:
            return []

        # Group actions by calendar date
        day_actions: dict[str, list[str]] = defaultdict(list)
        for ts, action in rows:
            date_str = ts[:10] if ts else "unknown"
            day_actions[date_str].append(action)

        # Collect every subsequence and track which days it appears on
        pattern_days: dict[tuple[str, ...], set[str]] = defaultdict(set)

        for date_str, actions in day_actions.items():
            seen_today: set[tuple[str, ...]] = set()
            n = len(actions)
            # Cap pattern length at 10 to avoid combinatorial explosion
            max_len = min(n, 10)
            for length in range(min_length, max_len + 1):
                for start in range(n - length + 1):
                    subseq = tuple(actions[start:start + length])
                    if subseq not in seen_today:
                        seen_today.add(subseq)
                        pattern_days[subseq].add(date_str)

        # Filter to patterns that appear on enough distinct days
        results: list[dict] = []
        for pattern, days in pattern_days.items():
            if len(days) < min_repetitions:
                continue

            # Count total occurrences (including multiple per day)
            total_occ = 0
            plen = len(pattern)
            for date_str, actions in day_actions.items():
                for i in range(len(actions) - plen + 1):
                    if tuple(actions[i:i + plen]) == pattern:
                        total_occ += 1

            results.append({
                "pattern": list(pattern),
                "length": plen,
                "day_count": len(days),
                "days": sorted(days),
                "total_occurrences": total_occ,
            })

        # Rank: most days first, then longest pattern, then most occurrences
        results.sort(
            key=lambda r: (r["day_count"], r["length"], r["total_occurrences"]),
            reverse=True,
        )
        return results[:limit]

    # ── 2. Learn procedure ──────────────────────────────────────────

    def learn_procedure(
        self,
        name: str,
        steps: list[str],
        context: str = "",
    ) -> dict:
        """Store a named procedure with its action steps.

        If a procedure with the same *name* already exists, its steps
        and context are updated in-place (the success/fail counters
        are preserved).

        Args:
            name: Unique procedure name.
            steps: Ordered list of action strings (stored as JSON).
            context: Natural-language description of when this
                     procedure applies.

        Returns:
            Dict with ``name``, ``created`` (bool), and ``status``
            (``\"created\"``, ``\"updated\"``, or ``\"error\"``).
        """
        now = datetime.now(timezone.utc).isoformat()
        steps_json = json.dumps(steps)

        try:
            existing = self.db.execute(
                "SELECT name FROM procedures WHERE name = ?", (name,)
            ).fetchone()

            if existing:
                self.db.execute(
                    "UPDATE procedures SET steps = ?, context = ?, "
                    "success_count = ?, fail_count = ?, "
                    "last_used = ? WHERE name = ?",
                    (steps_json, context, 0, 0, now, name),
                )
                self.db.commit()
                return {"name": name, "created": False, "status": "updated"}
            else:
                self.db.execute(
                    "INSERT INTO procedures "
                    "(name, steps, context, success_count, fail_count, "
                    " last_used, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (name, steps_json, context, 0, 0, now, now),
                )
                self.db.commit()
                return {"name": name, "created": True, "status": "created"}
        except Exception as e:
            return {"name": name, "created": False,
                    "status": "error", "error": str(e)}

    # ── 3. Suggest procedure ────────────────────────────────────────

    def suggest_procedure(
        self,
        current_context: str,
        limit: int = 5,
        min_score: float = 0.2,
    ) -> list[dict]:
        """Fuzzy-match *current_context* against stored procedures.

        Uses ``difflib.SequenceMatcher`` to compare the context string
        against each procedure's ``context`` field concatenated with
        its ``steps``. Results are ranked by similarity score
        descending.

        Args:
            current_context: What the user/agent is currently doing
                             (natural language description).
            limit: Maximum suggestions to return.
            min_score: Minimum similarity ratio (0.0–1.0) to include
                       a procedure in results.

        Returns:
            List of dicts with ``name``, ``score``, ``steps``,
            ``context``, ``success_rate``, ``success_count``,
            ``fail_count``, ``last_used``.
        """
        try:
            rows = self.db.execute(
                "SELECT name, steps, context, success_count, fail_count, "
                "last_used FROM procedures ORDER BY last_used DESC"
            ).fetchall()
        except Exception:
            return []

        if not rows:
            return []

        lower_ctx = current_context.lower()
        scored: list[dict] = []

        for name, steps_raw, ctx, succ, fail, last_used in rows:
            # _fetch_module_rows returns steps already parsed from JSON,
            # but direct SQLite would return a JSON string. Handle both.
            if isinstance(steps_raw, list):
                steps = steps_raw
            else:
                try:
                    steps = json.loads(steps_raw) if steps_raw else []
                except (json.JSONDecodeError, TypeError):
                    steps = []

            # Build combined text for fuzzy comparison
            combined = f"{ctx or ''} {' '.join(steps)}".lower()

            score = SequenceMatcher(None, lower_ctx, combined).ratio()

            if score < min_score:
                continue

            total = succ + fail
            success_rate = (succ / total) if total > 0 else None

            scored.append({
                "name": name,
                "score": round(score, 4),
                "steps": steps,
                "context": ctx,
                "success_rate": round(success_rate, 4) if success_rate is not None else None,
                "success_count": succ,
                "fail_count": fail,
                "last_used": last_used,
            })

        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:limit]

    # ── 4. Procedure success rate ───────────────────────────────────

    def procedure_success_rate(self, name: str) -> dict:
        """Compute success rate for a named procedure.

        Reads ``success_count`` and ``fail_count`` from the
        ``procedures`` table.

        Args:
            name: The procedure name to look up.

        Returns:
            Dict with ``name``, ``success_count``, ``fail_count``,
            ``total``, ``rate`` (float 0.0–1.0, or ``None`` if no
            traces exist), and optionally ``error``.
        """
        try:
            row = self.db.execute(
                "SELECT success_count, fail_count FROM procedures "
                "WHERE name = ?",
                (name,),
            ).fetchone()
        except Exception:
            return {"name": name, "success_count": 0, "fail_count": 0,
                    "total": 0, "rate": None, "error": "db_error"}

        if not row:
            return {"name": name, "success_count": 0, "fail_count": 0,
                    "total": 0, "rate": None, "error": "not_found"}

        succ, fail = row
        total = succ + fail
        rate = (succ / total) if total > 0 else None

        return {
            "name": name,
            "success_count": succ,
            "fail_count": fail,
            "total": total,
            "rate": round(rate, 4) if rate is not None else None,
        }

    # ── 5. Record trace ─────────────────────────────────────────────

    def record_trace(
        self,
        action_sequence: list[str],
        entities_involved: list[str],
        outcome: str,
    ) -> dict:
        """Log a procedural trace after executing (or observing) a workflow.

        Also attempts to match the trace against a known procedure and
        update its ``success_count`` or ``fail_count`` accordingly
        (best-effort; failures during the counter update are silently
        ignored so the trace itself is still recorded).

        Args:
            action_sequence: Ordered list of actions performed.
            entities_involved: Entities referenced during the workflow.
            outcome: One of ``'success'``, ``'fail'``, or ``'partial'``.

        Returns:
            Dict with ``id`` (the new trace row id, or ``None`` on
            error), ``timestamp``, and ``status``.
        """
        now = datetime.now(timezone.utc).isoformat()
        actions_json = json.dumps(action_sequence)
        entities_json = json.dumps(entities_involved)

        try:
            cursor = self.db.execute(
                "INSERT INTO procedural_traces "
                "(timestamp, action_sequence, entities_involved, outcome) "
                "VALUES (?, ?, ?, ?)",
                (now, actions_json, entities_json, outcome),
            )
            trace_id = cursor.lastrowid
        except Exception as e:
            return {"id": None, "timestamp": now,
                    "status": "error", "error": str(e)}

        # Best-effort: match against a known procedure and bump counters
        if outcome in ("success", "fail"):
            try:
                proc_rows = self.db.execute(
                    "SELECT name, steps FROM procedures"
                ).fetchall()

                best_match: Optional[str] = None
                best_score = 0.0

                for pname, steps_raw in proc_rows:
                    # Handle both parsed list (from FakeCursor) and JSON string (from SQLite)
                    if isinstance(steps_raw, list):
                        psteps = steps_raw
                    else:
                        try:
                            psteps = json.loads(steps_raw) if steps_raw else []
                        except (json.JSONDecodeError, TypeError):
                            psteps = []
                    if not psteps:
                        continue

                    # Jaccard-like overlap of action sets
                    a_set = set(action_sequence)
                    p_set = set(psteps)
                    overlap = len(a_set & p_set)
                    union = len(a_set | p_set)
                    score = overlap / union if union > 0 else 0.0

                    if score > best_score and score >= 0.5:
                        best_score = score
                        best_match = pname

                if best_match:
                    # Get current counters
                    try:
                        proc_row = self.db.execute(
                            "SELECT success_count, fail_count FROM procedures WHERE name = ?",
                            (best_match,)
                        ).fetchone()
                        if proc_row:
                            succ, fail = int(proc_row[0] or 0), int(proc_row[1] or 0)
                        else:
                            succ, fail = 0, 0
                    except Exception:
                        succ, fail = 0, 0

                    if outcome == "success":
                        succ += 1
                    else:
                        fail += 1

                    self.db.execute(
                        "UPDATE procedures SET success_count = ?, fail_count = ?, "
                        "last_used = ? WHERE name = ?",
                        (succ, fail, now, best_match),
                    )
            except Exception:
                pass  # counter update is best-effort; trace is already saved

        self.db.commit()
        return {"id": trace_id, "timestamp": now, "status": "recorded"}


# ── Module-level helpers ────────────────────────────────────────────

def _safe_json_load(text: str, default=None):
    """Parse a JSON string, returning *default* on any failure."""
    if default is None:
        default = []
    try:
        return json.loads(text) if text else default
    except (json.JSONDecodeError, TypeError):
        return default

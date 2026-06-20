"""
Mirror Brain v3.1 — Internal Reasoner.

Periodic (hourly) self-reflection module that:
  1. Auto-consolidates daily → weekly → monthly memory tiers.
  2. Generates internal questions from gaps and contradictions in the
     reasoning trail.
  3. Suggests new entity connections from co-occurrence patterns.
  4. Suggests self-improvement rules from reverted decisions.

Stores questions in the ``internal_questions`` table and writes a
meta-summary into ``reasoner_runs`` after each run.  Stdlib only.
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional


# ── Helpers ────────────────────────────────────────────────────────────

def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _safe_json_load(text: str, default=None):
    """Parse a JSON string, returning *default* on any failure."""
    if default is None:
        default = []
    try:
        return json.loads(text) if text else default
    except (json.JSONDecodeError, TypeError):
        return default


def _parse_iso(ts: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp, returning None on failure."""
    if not ts:
        return None
    try:
        # Handle 'Z' suffix and other common variants
        ts_clean = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_clean)
    except (ValueError, TypeError):
        return None


# ── Main class ─────────────────────────────────────────────────────────

class InternalReasoner:
    """Hourly self-reflection engine for Mirror Brain.

    Parameters
    ----------
    registry : EntityRegistry
        The Mirror Brain entity registry (provides ``.db`` access).
    llm_call : callable, optional
        A function ``llm_call(prompt: str) -> str`` that invokes an LLM.
        When ``None``, LLM-dependent phases are skipped gracefully.
    """

    def __init__(self, registry, llm_call: Optional[Callable[[str], str]] = None):
        self.registry = registry
        self.db = registry.db
        self.llm = llm_call

    # ── Gate: can this run yet? ────────────────────────────────────

    @staticmethod
    def can_run(last_run_iso: Optional[str]) -> bool:
        """Return True if more than one hour has passed since *last_run_iso*.

        ``last_run_iso`` may be ``None`` (never run), an empty string, or
        an ISO-8601 timestamp.  If it cannot be parsed the method returns
        ``True`` (assume a run is overdue).
        """
        if not last_run_iso:
            return True

        last = _parse_iso(last_run_iso)
        if last is None:
            return True  # unparseable → assume overdue

        elapsed = datetime.now(timezone.utc) - last
        return elapsed > timedelta(hours=1)

    # ── Public entry-point ─────────────────────────────────────────

    def run(self) -> dict:
        """Execute all four reasoning phases and record a meta-summary.

        Returns a dict with keys:
          ``phases`` (dict of per-phase results),
          ``findings_count`` (total flag-worthy findings),
          ``questions_generated`` (questions stored),
          ``run_id`` (reasoner_runs row id).
        """
        run_at = _now_iso()

        # ── Phase 1: Auto-consolidation ──
        consolidation_report = self._phase_consolidate()

        # ── Phase 2: Generate internal questions ──
        questions = self._phase_generate_questions()

        # ── Phase 3: Suggest connections ──
        connections_suggested = self._phase_suggest_connections()

        # ── Phase 4: Suggest improvements ──
        improvements = self._phase_suggest_improvements()

        # Store questions in the internal_questions table
        questions_stored = 0
        for q in questions:
            try:
                self.db.execute(
                    """INSERT INTO internal_questions
                       (question, context, entities_involved, status, created_at)
                       VALUES (?, ?, ?, 'open', ?)""",
                    (
                        q["question"],
                        q.get("context", ""),
                        json.dumps(q.get("entities_involved", [])),
                        run_at,
                    ),
                )
                questions_stored += 1
            except Exception:
                pass  # best-effort storage

        # Optionally store improvement rules as questions too
        for imp in improvements:
            try:
                self.db.execute(
                    """INSERT INTO internal_questions
                       (question, context, entities_involved, status, created_at)
                       VALUES (?, ?, ?, 'open', ?)""",
                    (
                        imp["rule"],
                        imp.get("evidence", ""),
                        json.dumps(imp.get("entities_involved", [])),
                        run_at,
                    ),
                )
                questions_stored += 1
            except Exception:
                pass

        self.db.commit()

        phases_completed = {
            "consolidation": consolidation_report,
            "questions": {
                "low_confidence": len([q for q in questions if q.get("source") == "low_confidence"]),
                "unlinked_cooccurrences": len([q for q in questions if q.get("source") == "unlinked_cooccurrence"]),
                "reverted_decisions": len([q for q in questions if q.get("source") == "reverted_decision"]),
                "total": len(questions),
            },
            "connections_suggested": connections_suggested,
            "improvements": {
                "rules_generated": len(improvements),
            },
        }

        findings_count = questions_stored

        # Write meta-summary row
        run_id = None
        try:
            cursor = self.db.execute(
                """INSERT INTO reasoner_runs
                   (run_at, phases_completed, questions_generated, connections_suggested)
                   VALUES (?, ?, ?, ?)""",
                (
                    run_at,
                    json.dumps(phases_completed),
                    questions_stored,
                    connections_suggested,
                ),
            )
            run_id = cursor.lastrowid
            self.db.commit()
        except Exception:
            pass

        return {
            "phases": phases_completed,
            "findings_count": findings_count,
            "questions_generated": questions_stored,
            "connections_suggested": connections_suggested,
            "run_id": run_id,
            "run_at": run_at,
        }

    # ── Phase 1: Auto-consolidation ────────────────────────────────

    def _phase_consolidate(self) -> dict:
        """Run hierarchical consolidation (daily → weekly → monthly).

        Instantiates ``HierarchicalConsolidation`` internally so this
        module has no hard import-time dependency on the consolidation
        module.
        """
        from .consolidation import HierarchicalConsolidation

        try:
            hc = HierarchicalConsolidation(self.registry, llm_call=self.llm)
            return hc.auto_consolidate()
        except Exception as exc:
            return {"error": str(exc), "daily": {"consolidated": 0},
                    "weekly": {"consolidated": 0}, "monthly": {"consolidated": 0}}

    # ── Phase 2: Generate internal questions ──────────────────────

    def _phase_generate_questions(self) -> list[dict]:
        """Scan the knowledge graph for gaps and produce questions.

        Sources:
          * Low-confidence decisions in ``reasoning_trail`` (confidence < 0.7).
          * Entity pairs that co-occur frequently in ``daily_index`` but
            have no relation in the ``relations`` table.
          * Reverted decisions — ``what should have been done instead?``.
        """
        questions: list[dict] = []

        # 2a. Low-confidence decisions
        questions.extend(self._find_low_confidence_questions())

        # 2b. Unlinked co-occurrences
        questions.extend(self._find_unlinked_cooccurrence_questions())

        # 2c. Reverted decisions
        questions.extend(self._find_reverted_decision_questions())

        return questions

    # ── 2a. Low-confidence decisions ──────────────────────────────

    def _find_low_confidence_questions(self) -> list[dict]:
        """Yield questions for reasoning_trail rows with confidence < 0.7."""
        try:
            rows = self.db.execute(
                """SELECT id, timestamp, action, entity_uuid, confidence,
                          reasoning, reverted
                   FROM reasoning_trail
                   WHERE confidence > 0 AND confidence < 0.7
                     AND reverted = 0
                   ORDER BY confidence ASC
                   LIMIT 30"""
            ).fetchall()
        except Exception:
            return []

        questions: list[dict] = []
        for row in rows:
            trail_id, ts, action, entity_uuid, conf, reasoning, reverted = row

            # Resolve entity name
            entity_name = self._resolve_entity_name(entity_uuid)

            question_text = (
                f"Low-confidence decision ({conf:.2f}): '{action}' "
                f"on entity '{entity_name}'. "
                f"Reasoning was: {reasoning[:200] if reasoning else '(none)'}. "
                f"Should this decision be revisited or reversed?"
            )

            questions.append({
                "question": question_text,
                "context": f"reasoning_trail.id={trail_id}",
                "entities_involved": [entity_name] if entity_name else [],
                "source": "low_confidence",
                "confidence": conf,
                "trail_id": trail_id,
            })

        return questions

    # ── 2b. Unlinked co-occurrences ───────────────────────────────

    def _find_unlinked_cooccurrence_questions(self) -> list[dict]:
        """Find entity pairs that co-occur in daily_index but have no relation."""
        # Collect all entity-name pairs from daily_index.key_entities
        cooccurrences: dict[tuple[str, str], int] = defaultdict(int)

        try:
            rows = self.db.execute(
                "SELECT key_entities FROM daily_index WHERE key_entities != '[]' AND key_entities != ''"
            ).fetchall()
        except Exception:
            return []

        for (ke_json,) in rows:
            entities = _safe_json_load(ke_json, [])
            if not isinstance(entities, list):
                continue
            # Count every unordered pair
            for i in range(len(entities)):
                for j in range(i + 1, len(entities)):
                    a, b = entities[i], entities[j]
                    pair = (a, b) if a < b else (b, a)
                    cooccurrences[pair] += 1

        if not cooccurrences:
            return []

        # Build a fast lookup of existing relations (by canonical name)
        existing_relations: set[tuple[str, str]] = set()
        try:
            rel_rows = self.db.execute(
                """SELECT e1.canonical_name, e2.canonical_name
                   FROM relations r
                   JOIN entities e1 ON r.from_uuid = e1.uuid
                   JOIN entities e2 ON r.to_uuid = e2.uuid"""
            ).fetchall()
            for a, b in rel_rows:
                existing_relations.add((a, b) if a < b else (b, a))
        except Exception:
            pass

        # Find pairs that co-occur enough but have no relation
        MIN_COOCCURRENCE = 2  # appear together on at least 2 different days
        questions: list[dict] = []
        seen_count = 0

        for (a, b), count in sorted(cooccurrences.items(),
                                     key=lambda x: -x[1]):
            if count < MIN_COOCCURRENCE:
                continue
            if (a, b) in existing_relations:
                continue

            question_text = (
                f"Entity '{a}' and '{b}' appear together in "
                f"{count} daily summaries but have no defined relation. "
                f"Should they be linked? What kind of relation exists?"
            )

            questions.append({
                "question": question_text,
                "context": f"cooccurrence_count={count}",
                "entities_involved": [a, b],
                "source": "unlinked_cooccurrence",
                "cooccurrence_count": count,
            })

            seen_count += 1
            if seen_count >= 20:  # limit
                break

        return questions

    # ── 2c. Reverted decisions ────────────────────────────────────

    def _find_reverted_decision_questions(self) -> list[dict]:
        """Ask 'what should have been done instead?' for each reverted decision."""
        try:
            rows = self.db.execute(
                """SELECT id, timestamp, action, entity_uuid, reasoning
                   FROM reasoning_trail
                   WHERE reverted = 1
                   ORDER BY timestamp DESC
                   LIMIT 20"""
            ).fetchall()
        except Exception:
            return []

        questions: list[dict] = []
        for row in rows:
            trail_id, ts, action, entity_uuid, reasoning = row

            entity_name = self._resolve_entity_name(entity_uuid)

            # Build a richer context
            context_lines = [f"Timestamp: {ts}", f"Action: {action}",
                             f"Entity: {entity_name}"]
            if reasoning:
                context_lines.append(f"Original reasoning: {reasoning[:300]}")

            question_text = (
                f"Decision '{action}' on '{entity_name}' was reverted. "
                f"What should have been done instead? "
                f"Original reasoning: {reasoning[:150] if reasoning else '(none)'}"
            )

            questions.append({
                "question": question_text,
                "context": " | ".join(context_lines),
                "entities_involved": [entity_name] if entity_name else [],
                "source": "reverted_decision",
                "trail_id": trail_id,
            })

        return questions

    # ── Phase 3: Suggest connections ──────────────────────────────

    def _phase_suggest_connections(self) -> int:
        """Find entity pairs that co-occur in daily_index often but lack a relation.

        Stores each suggestion as an internal question and returns the
        count of connections suggested.

        This is a deeper scan than phase 2b — it uses a higher co-occurrence
        threshold and also examines the entity types for compatibility hints.
        """
        cooccurrences: dict[tuple[str, str], int] = defaultdict(int)

        try:
            rows = self.db.execute(
                "SELECT key_entities FROM daily_index WHERE key_entities != '[]' AND key_entities != ''"
            ).fetchall()
        except Exception:
            return 0

        for (ke_json,) in rows:
            entities = _safe_json_load(ke_json, [])
            if not isinstance(entities, list):
                continue
            for i in range(len(entities)):
                for j in range(i + 1, len(entities)):
                    a, b = entities[i], entities[j]
                    pair = (a, b) if a < b else (b, a)
                    cooccurrences[pair] += 1

        if not cooccurrences:
            return 0

        # Build existing-relation lookup
        existing_relations: set[tuple[str, str]] = set()
        try:
            rel_rows = self.db.execute(
                """SELECT e1.canonical_name, e2.canonical_name
                   FROM relations r
                   JOIN entities e1 ON r.from_uuid = e1.uuid
                   JOIN entities e2 ON r.to_uuid = e2.uuid"""
            ).fetchall()
            for a, b in rel_rows:
                existing_relations.add((a, b) if a < b else (b, a))
        except Exception:
            pass

        MIN_COOCCURRENCE = 3  # higher threshold for a "suggestion" vs a "question"
        MAX_SUGGESTIONS = 15
        suggested = 0

        for (a, b), count in sorted(cooccurrences.items(),
                                     key=lambda x: -x[1]):
            if count < MIN_COOCCURRENCE:
                break
            if (a, b) in existing_relations:
                continue

            # Try to determine entity types for a richer suggestion
            type_a = self._get_entity_type(a)
            type_b = self._get_entity_type(b)

            suggestion_text = (
                f"Strong co-occurrence ({count} days): "
                f"'{a}' ({type_a}) and '{b}' ({type_b}). "
                f"Consider linking them."
            )

            try:
                self.db.execute(
                    """INSERT INTO internal_questions
                       (question, context, entities_involved, status, created_at)
                       VALUES (?, ?, ?, 'open', ?)""",
                    (
                        suggestion_text,
                        f"cooccurrence_count={count}",
                        json.dumps([a, b]),
                        _now_iso(),
                    ),
                )
                suggested += 1
            except Exception:
                pass

            if suggested >= MAX_SUGGESTIONS:
                break

        self.db.commit()
        return suggested

    # ── Phase 4: Suggest improvements ─────────────────────────────

    def _phase_suggest_improvements(self) -> list[dict]:
        """Analyze reverted decisions and generate improvement rules.

        Groups reverted decisions by their action prefix, identifies
        patterns, and generates concrete improvement rules.

        Returns a list of dicts with keys: ``rule``, ``evidence``,
        ``entities_involved``, ``affected_count``.
        """
        try:
            rows = self.db.execute(
                """SELECT id, action, entity_uuid, confidence, reasoning
                   FROM reasoning_trail
                   WHERE reverted = 1
                   ORDER BY timestamp DESC
                   LIMIT 50"""
            ).fetchall()
        except Exception:
            return []

        if not rows:
            return []

        # Group by action prefix (first word or colon-delimited category)
        action_groups: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            trail_id, action, entity_uuid, confidence, reasoning = row

            # Extract action category
            if ":" in action:
                category = action.split(":")[0]
            else:
                category = action.split()[0] if action else "unknown"

            entity_name = self._resolve_entity_name(entity_uuid)

            action_groups[category].append({
                "trail_id": trail_id,
                "action": action,
                "entity": entity_name,
                "confidence": confidence,
                "reasoning": reasoning or "",
            })

        improvements: list[dict] = []

        for category, items in action_groups.items():
            if len(items) < 2:
                continue  # need at least 2 reverted decisions of same type

            entities_involved = list({it["entity"] for it in items if it["entity"]})

            # Summarise the evidence
            sample_actions = [it["action"] for it in items[:5]]
            sample_reasoning = [it["reasoning"][:100] for it in items[:3] if it["reasoning"]]

            rule = (
                f"Improvement rule for '{category}' actions: "
                f"{len(items)} reverted decisions detected. "
                f"Consider adding a pre-check before executing {category} actions, "
                f"or increasing the confidence threshold for this action type."
            )

            evidence = (
                f"Sample actions: {', '.join(sample_actions)}. "
                f"Sample reasoning: {'; '.join(sample_reasoning) if sample_reasoning else '(none)'}"
            )

            improvements.append({
                "rule": rule,
                "evidence": evidence,
                "entities_involved": entities_involved,
                "affected_count": len(items),
                "category": category,
            })

        # Sort by most-affected first
        improvements.sort(key=lambda x: -x["affected_count"])
        return improvements[:10]

    # ── Helpers ───────────────────────────────────────────────────

    def _resolve_entity_name(self, entity_uuid: str) -> str:
        """Return canonical_name for an entity UUID, or empty string."""
        if not entity_uuid:
            return ""
        try:
            row = self.db.execute(
                "SELECT canonical_name FROM entities WHERE uuid = ?",
                (entity_uuid,),
            ).fetchone()
            return row[0] if row else ""
        except Exception:
            return ""

    def _get_entity_type(self, name: str) -> str:
        """Return the type of an entity by name, defaulting to 'unknown'."""
        if not name:
            return "unknown"
        try:
            row = self.db.execute(
                "SELECT type FROM entities WHERE canonical_name = ?",
                (name,),
            ).fetchone()
            return row[0] if row else "unknown"
        except Exception:
            return "unknown"

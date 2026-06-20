"""
Mirror Brain v1.0 — Link Generation + Memory Evolution (LLM #2).
The final cognitive step: takes the Note + fetched context and decides
what connections to make, what memories to evolve, and what new aliases exist.
"""
import json
import re
from typing import Callable, Optional

from .models import Note


# ── System Prompt ──────────────────────────────────────────────

LINK_EVOLUTION_PROMPT = """You are the Memory Curator of Mirror Brain, an agentic memory system
inspired by A-MEM and the Zettelkasten method.

Your job: given a new memory note AND retrieved context from the brain,
decide what connections to create and what existing memories to evolve.

## Output Format (JSON only)

{{
  "links": [
    {{
      "from_entity": "entity name from note",
      "to_entity": "existing entity name",
      "relation": "relation type (updates_status, mentions, relates_to, depends_on, etc.)",
      "confidence": 0.0-1.0,
      "reasoning": "why this link should exist"
    }}
  ],
  "evolutions": [
    {{
      "target": "entity or daily summary date to update",
      "action": "update_context|update_tags|merge_entities|strengthen_link",
      "new_context": "refined context if updating",
      "new_tags": ["tag1", "tag2"],
      "confidence": 0.0-1.0,
      "reasoning": "why this evolution is needed"
    }}
  ],
  "new_aliases": [
    {{
      "alias": "new alias detected",
      "canonical_entity": "existing entity this refers to",
      "confidence": 0.0-1.0,
      "reasoning": "why this alias was detected"
    }}
  ],
  "needs_more_search": [
    "specific question needing more context"
  ]
}}

## Rules

1. LINKS: Create connections between entities mentioned in the note and
   existing entities. Look at the entity contexts provided — if two entities
   share themes or have related activities, link them.
   Common relations: updates_status, mentions, relates_to, depends_on,
   works_on, talked_with, visited, concerns.

2. EVOLUTIONS: If the new note CHANGES our understanding of an existing
   entity or daily summary, evolve it.
   - update_context: the entity's situation changed (e.g., "c0 ahora funciona")
   - update_tags: new categories apply
   - merge_entities: two entities are actually the same
   - strengthen_link: the relationship between two entities deepened

3. NEW ALIASES: Detect when a new name in the note refers to an existing
   entity. E.g., "MB" -> "Mirror Brain", "la florería" -> "Florería GJB".

4. NEEDS MORE SEARCH: If you feel the context is insufficient to make
   a confident decision, request more specific searches. Keep this
   to 0-2 items only — be frugal.

5. CONFIDENCE:
   - 0.9-1.0: certain — direct evidence in the text
   - 0.7-0.9: probable — strong inference
   - 0.5-0.7: possible — weak inference, flag for review
   - <0.5: don't include — too uncertain

6. Do NOT hallucinate links. Only connect entities that are actually
   related through the note content or context.

## New Memory Note
Content: {note_content}
Context: {note_context}
Keywords: {note_keywords}
Tags: {note_tags}
Emotional Load: {note_emotional}
Temporal Hints: {note_temporal}
Entities Mentioned: {note_entities}

## Retrieved Context from Brain
{retrieved_context}

## Existing Memories (top neighbors)
{neighbor_memories}

Return ONLY valid JSON. No markdown fences, no explanations beyond the reasoning fields."""


# ── Link + Evolution Engine ────────────────────────────────────

class LinkEvolution:
    """LLM #2: Decides links, evolutions, and aliases.

    Usage:
        le = LinkEvolution(registry, llm_call=my_llm)
        decisions = le.decide(note, context)
        le.execute(decisions)  # applies confidence gates
    """

    def __init__(self,
                 registry,
                 llm_call: Optional[Callable[[str], str]] = None,
                 system_prompt: str = LINK_EVOLUTION_PROMPT):
        self.registry = registry
        self.llm_call = llm_call or self._default_llm
        self.system_prompt = system_prompt

    # ── Public API ──────────────────────────────────────────

    def decide(self, note: Note, context: dict, neighbor_memories: str = "") -> dict:
        """Call LLM #2 to get link/evolution/alias decisions.

        Returns parsed JSON with links, evolutions, new_aliases, needs_more_search.
        """
        # Build prompt
        prompt = self.system_prompt.format(
            note_content=note.content[:2000],
            note_context=note.context,
            note_keywords=", ".join(note.keywords),
            note_tags=", ".join(note.tags),
            note_emotional=json.dumps(note.emotional_load),
            note_temporal=", ".join(note.temporal_hints),
            note_entities=json.dumps(note.entities_mentioned, indent=2),
            retrieved_context=json.dumps(self._compact_context(context), indent=2),
            neighbor_memories=neighbor_memories or "(no neighbor memories available)",
        )

        # Call LLM
        raw = self.llm_call(prompt)
        parsed = self._parse_response(raw)

        return parsed

    def execute(self, decisions: dict, note: Note) -> dict:
        """Execute decisions with confidence gates.

        Returns a summary of what was done, flagged, and skipped.
        """
        report = {"auto_executed": [], "flagged": [], "skipped": [], "errors": []}
        confidence_thresholds = {
            "auto": 0.85,
            "flag": 0.60,
        }

        # ── Links ────────────────────────────────────────
        for link in decisions.get("links", []):
            conf = link.get("confidence", 0)
            from_ent = link.get("from_entity", "")
            to_ent = link.get("to_entity", "")
            relation = link.get("relation", "relates_to")
            reasoning = link.get("reasoning", "")

            if conf >= confidence_thresholds["auto"]:
                self._execute_link(from_ent, to_ent, relation, reasoning, conf)
                report["auto_executed"].append(
                    f"link: {from_ent} --[{relation}]--> {to_ent} (conf={conf:.2f})"
                )
            elif conf >= confidence_thresholds["flag"]:
                self._execute_link(from_ent, to_ent, relation, reasoning, conf)
                report["flagged"].append(
                    f"⚠️ link: {from_ent} --[{relation}]--> {to_ent} (conf={conf:.2f})"
                )
            else:
                report["skipped"].append(
                    f"link: {from_ent} --[{relation}]--> {to_ent} (conf={conf:.2f} too low)"
                )

        # ── Evolutions ────────────────────────────────────
        for evo in decisions.get("evolutions", []):
            conf = evo.get("confidence", 0)
            target = evo.get("target", "")
            action = evo.get("action", "")
            reasoning = evo.get("reasoning", "")

            if conf >= confidence_thresholds["auto"]:
                self._execute_evolution(evo)
                report["auto_executed"].append(
                    f"evolution: {action} on {target} (conf={conf:.2f})"
                )
            elif conf >= confidence_thresholds["flag"]:
                self._execute_evolution(evo)
                report["flagged"].append(
                    f"⚠️ evolution: {action} on {target} (conf={conf:.2f})"
                )
            else:
                report["skipped"].append(
                    f"evolution: {action} on {target} (conf={conf:.2f} too low)"
                )

        # ── New Aliases ───────────────────────────────────
        for alias in decisions.get("new_aliases", []):
            conf = alias.get("confidence", 0)
            alias_name = alias.get("alias", "")
            canonical = alias.get("canonical_entity", "")
            reasoning = alias.get("reasoning", "")

            if conf >= confidence_thresholds["auto"]:
                self._execute_alias(alias_name, canonical, conf, reasoning)
                report["auto_executed"].append(
                    f"alias: '{alias_name}' -> {canonical} (conf={conf:.2f})"
                )
            elif conf >= confidence_thresholds["flag"]:
                self._execute_alias(alias_name, canonical, conf, reasoning)
                report["flagged"].append(
                    f"⚠️ alias: '{alias_name}' -> {canonical} (conf={conf:.2f})"
                )
            else:
                report["skipped"].append(
                    f"alias: '{alias_name}' -> {canonical} (conf={conf:.2f} too low)"
                )

        return report

    # ── Execution helpers ──────────────────────────────────

    def _execute_link(self, from_ent: str, to_ent: str, relation: str,
                      reasoning: str, confidence: float):
        """Create a relation in the registry + log reasoning."""
        from_uuid = self.registry.resolve(from_ent)
        to_uuid = self.registry.resolve(to_ent)

        if not from_uuid or not to_uuid:
            return

        # Store relation
        self.registry.db.execute(
            "INSERT INTO relations (from_uuid, to_uuid, relation_type, source_text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (from_uuid, to_uuid, relation, reasoning, Note.now()),
        )

        # Log reasoning trail
        self.registry.log_decision(
            action=f"create_relation:{relation}",
            entity_uuid=from_uuid,
            target_uuid=to_uuid,
            confidence=confidence,
            reasoning=reasoning,
            source="llm",
        )
        self.registry.db.commit()

    def _execute_evolution(self, evo: dict):
        """Apply memory evolution to entities or daily summaries."""
        target = evo.get("target", "")
        action = evo.get("action", "")
        reasoning = evo.get("reasoning", "")
        confidence = evo.get("confidence", 0)
        new_context = evo.get("new_context", "")
        new_tags = evo.get("new_tags", [])

        entity_uuid = self.registry.resolve(target)

        if entity_uuid and action == "update_context" and new_context:
            # Update the entity's context (we store context in the note system,
            # not in the entity table directly — but we log the evolution)
            self.registry.log_decision(
                action=f"evolution:{action}",
                entity_uuid=entity_uuid,
                confidence=confidence,
                reasoning=f"Updated context: {new_context}. {reasoning}",
                source="llm",
            )
            self.registry.db.commit()

        elif entity_uuid and action == "merge_entities":
            # Mark entity as merged
            merge_target = evo.get("merge_into", "")
            merge_uuid = self.registry.resolve(merge_target)
            if merge_uuid:
                self.registry.db.execute(
                    "UPDATE entities SET status='merged', merged_into=? WHERE uuid=?",
                    (merge_uuid, entity_uuid),
                )
                self.registry.log_decision(
                    action="merge_entities",
                    entity_uuid=entity_uuid,
                    target_uuid=merge_uuid,
                    confidence=confidence,
                    reasoning=reasoning,
                    source="llm",
                )
                self.registry.db.commit()

    def _execute_alias(self, alias_name: str, canonical: str,
                       confidence: float, reasoning: str):
        """Register a new alias."""
        target_uuid = self.registry.resolve(canonical)
        if not target_uuid:
            return

        self.registry.add_alias(alias_name, target_uuid, source="llm",
                                confidence=confidence)
        self.registry.log_decision(
            action="add_alias",
            entity_uuid=target_uuid,
            confidence=confidence,
            reasoning=reasoning,
            source="llm",
        )

    # ── Helpers ────────────────────────────────────────────

    @staticmethod
    def _compact_context(context: dict) -> dict:
        """Make context compact enough for the LLM prompt."""
        compact = {
            "summary": context.get("summary", ""),
            "daily_count": len(context.get("daily_summaries", [])),
        }

        # Include recent daily summaries (last 3)
        dailies = context.get("daily_summaries", [])
        if dailies:
            compact["recent_days"] = [
                {"date": d.get("date", ""), "summary": str(d.get("summary", ""))[:300]}
                for d in dailies[:3]
            ]

        # Entity contexts (names only + type)
        entities = context.get("entity_contexts", {})
        if entities:
            compact["entities_found"] = {
                name: {"type": ectx.get("type", "?"), "aliases": ectx.get("aliases", [])[:5]}
                for name, ectx in list(entities.items())[:8]
            }

        return compact

    @staticmethod
    def _parse_response(raw: str) -> dict:
        """Parse LLM response. Robust to markdown fences."""
        if not raw:
            return {"links": [], "evolutions": [], "new_aliases": [], "needs_more_search": []}

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        try:
            parsed = json.loads(cleaned)
            # Ensure all keys exist
            for key in ["links", "evolutions", "new_aliases", "needs_more_search"]:
                if key not in parsed:
                    parsed[key] = []
            return parsed
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            return {"links": [], "evolutions": [], "new_aliases": [],
                    "needs_more_search": [], "_parse_error": True, "_raw": raw}

    @staticmethod
    def _default_llm(prompt: str) -> str:
        raise RuntimeError(
            "No LLM configured. Pass llm_call=your_function to LinkEvolution."
        )

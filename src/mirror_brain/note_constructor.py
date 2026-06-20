"""
Mirror Brain v1.0 — A-MEM Note Constructor.
LLM-driven note construction: keywords, context, tags, emotional load,
entity extraction, and intelligent search hints.
"""
import json
import re
from typing import Callable, Optional

from .models import Note


# ── System Prompt ──────────────────────────────────────────────

NOTE_CONSTRUCTOR_PROMPT = """You are the Note Constructor of Mirror Brain, an agentic memory system
inspired by A-MEM and the Zettelkasten method.

Given a text from Julian (a bilingual ES/EN user), generate a structured note.

## Output Format (JSON only, no markdown, no explanation)

{{
  "keywords": ["3-7 key concepts"],
  "context": "One sentence summary: main topic, key points, purpose",
  "tags": ["3-5 broad categories"],
  "emotional_load": {{
    "oxytocin": 0.0-1.0,
    "adrenaline": 0.0-1.0,
    "cortisol": 0.0-1.0,
    "dopamine": 0.0-1.0
  }},
  "temporal_hints": ["hoy", "ayer", "hace 3 dias", "la semana pasada"],
  "entities_mentioned": [
    {{
      "name": "entity name",
      "type": "person|project|tool|place|concept",
      "is_new": true/false,
      "alias_of": "canonical name or null",
      "confidence": 0.0-1.0
    }}
  ],
  "search_hints": [
    "specific question about what to search in memory"
  ]
}}

## Rules

1. KEYWORDS: 3-7 key concepts (nouns, verbs, tools, emotions). Order by importance.
2. CONTEXT: One sentence. Main topic + key points.
3. TAGS: 3-5 broad categories (proyecto, tecnico, emocional, social, etc).
4. EMOTIONAL_LOAD:
   - oxytocin: connection, love, bonding, social warmth
   - adrenaline: urgency, excitement, intensity, action
   - cortisol: stress, worry, anxiety, concern
   - dopamine: achievement, motivation, reward, progress
   Use 0.0-1.0 scale. Be conservative: only mark high when clearly present.
5. TEMPORAL_HINTS: Time references from text. Empty list if none.
6. ENTITIES_MENTIONED:
   - Only entities EXPLICITLY mentioned in text. Do NOT invent.
   - Emotions, events, attributes are NOT entities (they are tags).
   - If name is clearly an alias of existing entity, set alias_of.
   - Use confidence: 1.0 = certain, 0.7 = probable, 0.5 = unsure.
7. SEARCH_HINTS: 2-4 specific questions that memory (c0 graph + daily summaries)
   could answer. Be concrete:
   GOOD: "what was the last status of c0 before this?"
   GOOD: "how much did Julian spend on DeepSeek tokens this week?"
   BAD: "search for context"

## Existing Entities
{existing_entities}

## Text to Analyze
{text}

Return ONLY valid JSON. No markdown code fences, no explanations."""


# ── Constructor ────────────────────────────────────────────────

class NoteConstructor:
    """A-MEM style note construction via LLM.

    Usage:
        nc = NoteConstructor(registry, llm_call=my_llm_function)
        note = nc.construct("Estuve en la florería con Romi...")
    """

    def __init__(self,
                 registry,  # EntityRegistry
                 llm_call: Optional[Callable[[str], str]] = None,
                 system_prompt: str = NOTE_CONSTRUCTOR_PROMPT):
        self.registry = registry
        self.llm_call = llm_call or self._default_llm
        self.system_prompt = system_prompt

    # ── Public API ──────────────────────────────────────────

    def construct(self, text: str) -> Note:
        """Build a structured Note from raw text.

        Returns a Note with all fields populated, plus entities
        processed through the registry (created or resolved).
        """
        # 1. Build prompt with existing entities
        existing = self._get_existing_entities_summary()
        prompt = self.system_prompt.format(
            existing_entities=existing,
            text=text,
        )

        # 2. Call LLM
        raw_response = self.llm_call(prompt)

        # 3. Parse structured output
        parsed = self._parse_response(raw_response)

        # 4. Build the Note
        note = Note(
            content=text,
            timestamp=Note.now(),
            keywords=parsed.get("keywords", []),
            tags=parsed.get("tags", []),
            context=parsed.get("context", ""),
            emotional_load=parsed.get("emotional_load", {}),
            temporal_hints=parsed.get("temporal_hints", []),
            entities_mentioned=parsed.get("entities_mentioned", []),
            search_hints=parsed.get("search_hints", []),
        )

        # 5. Process entities through registry (create or resolve)
        self._process_entities(note)

        return note

    # ── Private ─────────────────────────────────────────────

    def _get_existing_entities_summary(self) -> str:
        """Build a lightweight summary of existing entities for the prompt."""
        try:
            cursor = self.registry.db.execute(
                "SELECT canonical_name, type FROM entities WHERE status='active'"
                " ORDER BY type, canonical_name"
            )
            rows = cursor.fetchall()
            if not rows:
                return "(no existing entities yet)"

            lines = []
            for name, etype in rows:
                entity_uuid = self.registry.resolve(name)
                aliases = self.registry.get_aliases(entity_uuid or "")
                alias_str = ""
                if aliases:
                    alias_names = [
                        a["alias"] for a in aliases
                        if a["alias"] != name
                    ]
                    if alias_names:
                        alias_str = f" (aliases: {', '.join(alias_names)})"
                lines.append(f"  - [{etype}] {name}{alias_str}")

            return "\n".join(lines)
        except Exception:
            return "(unable to load existing entities)"

    def _process_entities(self, note: Note):
        """Feed entities_mentioned through the registry."""
        for ent in note.entities_mentioned:
            name = ent.get("name", "")
            type_ = ent.get("type", "concept")
            alias_of = ent.get("alias_of")
            confidence = ent.get("confidence", 0.8)
            is_new = ent.get("is_new", True)

            if not name:
                continue

            if alias_of:
                # This is an alias — link to existing entity
                target_uuid = self.registry.resolve(alias_of)
                if target_uuid:
                    self.registry.add_alias(
                        name, target_uuid, source="llm",
                        confidence=min(confidence, 0.95),
                    )
                else:
                    # alias_of target doesn't exist — create as new
                    self.registry.ingest(
                        name, type_, mention_count=1,
                        llm_confidence=confidence,
                    )
            elif is_new:
                # Standalone new entity
                self.registry.ingest(
                    name, type_, mention_count=1,
                    llm_confidence=confidence,
                )
            else:
                # Entity exists but might need alias
                existing_uuid = self.registry.resolve(name)
                if not existing_uuid:
                    self.registry.ingest(
                        name, type_, mention_count=1,
                        llm_confidence=confidence,
                    )

    @staticmethod
    def _parse_response(raw: str) -> dict:
        """Parse LLM response into a dict. Robust to markdown fences."""
        if not raw:
            return {}

        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to extract JSON from the middle of the response
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            return {"_parse_error": True, "_raw": raw}

    @staticmethod
    def _default_llm(prompt: str) -> str:
        """Default no-op LLM — raises if not configured."""
        raise RuntimeError(
            "No LLM configured. Pass llm_call=your_function to NoteConstructor "
            "or set up a provider."
        )

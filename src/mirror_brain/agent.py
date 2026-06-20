"""
Mirror Brain v2 — Agentic Pipeline.
The agent has tools, activates memory, loops if needed, and decides.
"""
import json
import re
from typing import Callable, Optional

from .models import Note
from .registry import EntityRegistry
from .tools import SearchTools
from .preprocessor import TextPreprocessor


AGENT_SYSTEM_PROMPT = """You are the Mirror Brain Agent v2, an agentic memory system.

You have ACCESS TO TOOLS that searched the brain for you. The results are below.
You also have the original text. Your job: decide what to create, link, evolve.

## Retrieved Context from Brain
{retrieved_context}

## Original Text
{text}

## Past Decisions (learn from mistakes)
{past_decisions}

## Instructions

Analyze the text and the retrieved context. Return JSON with:

{{
  "entities": [
    {{
      "name": "entity name",
      "type": "person|project|tool|place|concept",
      "is_new": true/false,
      "alias_of": "canonical name or null",
      "confidence": 0.0-1.0,
      "reasoning": "why"
    }}
  ],
  "links": [
    {{
      "from_entity": "name",
      "to_entity": "name",
      "relation": "relation_type",
      "confidence": 0.0-1.0,
      "reasoning": "why"
    }}
  ],
  "evolutions": [
    {{
      "target": "entity or date",
      "action": "update_context|update_tags|merge",
      "new_context": "refined context",
      "confidence": 0.0-1.0,
      "reasoning": "why"
    }}
  ],
  "new_aliases": [
    {{
      "alias": "new alias",
      "canonical_entity": "existing entity",
      "confidence": 0.0-1.0,
      "reasoning": "why"
    }}
  ],
  "needs_more_search": [
    "specific search request"
  ],
  "summary": "one sentence summary of what was decided"
}}

## Rules
- Only entities EXPLICITLY in the text. Use alias_of if it matches an existing entity.
- Links: connect only when evidence exists in text + retrieved context.
- Evolutions: update context when text changes our understanding.
- needs_more_search: ONLY if truly insufficient context. Max 2 items.
- Confidence: >0.85=auto, 0.6-0.85=flag, <0.6=skip.
- Past decisions with reverted=true: avoid repeating those mistakes.

Return ONLY valid JSON. No markdown fences."""


class MirrorBrainAgent:
    """v2 Agent: tools → activate → decide → loop → execute."""

    def __init__(self, registry: EntityRegistry, llm_call: Callable,
                 c0_client=None, max_loops: int = 3):
        self.registry = registry
        self.llm = llm_call
        self.c0 = c0_client
        self.tools = SearchTools()
        self.preprocessor = TextPreprocessor()
        self.max_loops = max_loops

    def process(self, text: str) -> dict:
        """Full v2 pipeline. Returns execution report."""
        # 0. Save raw text
        self._save_raw_text(text)

        # 0.5. Pre-process: estimate complexity, split themes
        complexity = self.preprocessor.estimate_complexity(text)
        themes = self.preprocessor.split_by_themes(text) if complexity["char_count"] > 500 else [{"theme": "main", "text": text, "start_char": 0, "end_char": len(text)}]

        # 1. ACTIVATION: search brain with tools
        all_context = self._activate(text, themes, complexity)

        # 2. DECIDE: LLM receives text + context + past decisions
        decisions = self._decide(text, all_context)

        # 3. LOOP: if LLM needs more, search again (up to max_loops)
        for loop_i in range(self.max_loops):
            more = decisions.get("needs_more_search", [])
            if not more:
                break
            extra = self._search_more(more)
            if extra:
                all_context["extra_searches"] = extra
            decisions = self._decide(text, all_context)

        # 4. EXECUTE with confidence gates
        report = self._execute(decisions)

        report["complexity"] = complexity
        report["theme_count"] = len(themes)
        report["loops_used"] = loop_i + 1 if decisions.get("needs_more_search") else 1
        report["summary"] = decisions.get("summary", "")

        return report

    # ── Activation ──────────────────────────────────────────

    def _activate(self, text: str, themes: list, complexity: dict) -> dict:
        """Search the brain using multiple tools based on text characteristics."""
        ctx = {
            "temporal_context": [],
            "entity_contexts": {},
            "emotional_matches": [],
            "semantic_matches": [],
            "weekly_summary": None,
            "fuzzy_matches": [],
        }

        # Always: temporal context (default window)
        ctx["temporal_context"] = self.tools.search_temporal(self.registry, days_ago=0, window=21)

        # Always: weekly summary
        ctx["weekly_summary"] = self.tools.get_weekly_summary(self.registry)

        # Extract potential entity names from themes
        entity_names = self._extract_potential_entities(themes)

        for name in entity_names[:10]:  # limit
            minimap = self.tools.get_minimap(self.registry, name)
            if minimap:
                ctx["entity_contexts"][name] = minimap
            fuzzy_results = self.tools.search_fuzzy(self.registry, name)
            if fuzzy_results:
                ctx["fuzzy_matches"].extend(fuzzy_results)

        # Emotional search if text has emotional density
        if complexity.get("emotional_density", 0) > 0.05:
            for emotion in ["oxytocin", "cortisol", "dopamine", "adrenaline"]:
                matches = self.tools.search_by_emotion(self.registry, emotion, threshold=0.4, limit=5)
                if matches:
                    ctx["emotional_matches"].extend(matches)

        # Semantic search on key phrases
        for theme in themes[:3]:
            text_sample = theme["text"][:200]
            if self.c0:
                results = self.tools.search_semantic(self.registry, self.c0, text_sample, limit=5)
                if results:
                    ctx["semantic_matches"].extend(results)

        return ctx

    def _search_more(self, queries: list[str]) -> list:
        """Execute additional searches requested by LLM."""
        extra = []
        for q in queries[:3]:
            # Try fuzzy first
            results = self.tools.search_fuzzy(self.registry, q)
            if results:
                extra.append({"query": q, "type": "fuzzy", "results": results})
            # Also try semantic if c0 available
            if self.c0:
                results = self.tools.search_semantic(self.registry, self.c0, q, limit=3)
                if results:
                    extra.append({"query": q, "type": "semantic", "results": results})
        return extra

    # ── Decision ─────────────────────────────────────────────

    def _decide(self, text: str, context: dict) -> dict:
        """Call LLM with text + context + past decisions."""
        past = self._get_past_decisions(context)
        prompt = AGENT_SYSTEM_PROMPT.format(
            retrieved_context=json.dumps(self._compact_context(context), indent=2),
            text=text[:3000],
            past_decisions=past,
        )
        raw = self.llm(prompt)
        return self._parse_json(raw)

    # ── Execution ────────────────────────────────────────────

    def _execute(self, decisions: dict) -> dict:
        """Execute decisions with confidence gates."""
        report = {"auto": [], "flagged": [], "skipped": [], "stats": {}}

        for ent in decisions.get("entities", []):
            name = ent.get("name", "")
            type_ = ent.get("type", "concept")
            alias_of = ent.get("alias_of")
            conf = ent.get("confidence", 0)
            reasoning = ent.get("reasoning", "")

            if not name:
                continue

            if conf >= 0.85:
                if alias_of:
                    target = self.registry.resolve(alias_of)
                    if not target:
                        results = self.registry.search(alias_of)
                        if results:
                            target = results[0]["uuid"]
                    if target:
                        self.registry.add_alias(name, target, source="llm", confidence=conf)
                        self.registry.log_decision("add_alias", target, confidence=conf, reasoning=reasoning, source="llm")
                        report["auto"].append(f"alias: {name} → {alias_of}")
                else:
                    result = self.registry.ingest(name, type_, llm_confidence=conf)
                    uuid_ = result[0] if result else None
                    if uuid_:
                        report["auto"].append(f"entity: {name} ({type_})")
            elif conf >= 0.6:
                report["flagged"].append(f"entity: {name} (conf={conf:.2f}) — {reasoning[:60]}")
            else:
                report["skipped"].append(f"entity: {name} (conf={conf:.2f})")

        for link in decisions.get("links", []):
            conf = link.get("confidence", 0)
            if conf >= 0.85:
                from_uuid = self.registry.resolve(link["from_entity"]) or (self.registry.search(link["from_entity"]) or [{}])[0].get("uuid")
                to_uuid = self.registry.resolve(link["to_entity"]) or (self.registry.search(link["to_entity"]) or [{}])[0].get("uuid")
                if from_uuid and to_uuid:
                    existing = self.registry.db.execute("SELECT 1 FROM relations WHERE from_uuid=? AND to_uuid=? AND relation_type=?", (from_uuid, to_uuid, link["relation"])).fetchone()
                    if not existing:
                        self.registry.db.execute("INSERT INTO relations (from_uuid, to_uuid, relation_type, source_text, created_at) VALUES (?,?,?,?,?)", (from_uuid, to_uuid, link["relation"], link.get("reasoning", ""), Note.now()))
                        self.registry.log_decision(f"create_relation:{link['relation']}", from_uuid, target_uuid=to_uuid, confidence=conf, reasoning=link.get("reasoning", ""), source="llm")
                        report["auto"].append(f"link: {link['from_entity']} → {link['to_entity']}")
            elif conf >= 0.6:
                report["flagged"].append(f"link: {link['from_entity']} → {link['to_entity']} (conf={conf:.2f})")

        for alias in decisions.get("new_aliases", []):
            conf = alias.get("confidence", 0)
            if conf >= 0.85:
                target = self.registry.resolve(alias["canonical_entity"]) or (self.registry.search(alias["canonical_entity"]) or [{}])[0].get("uuid")
                if target:
                    self.registry.add_alias(alias["alias"], target, source="llm", confidence=conf)
                    report["auto"].append(f"alias: {alias['alias']} → {alias['canonical_entity']}")
            elif conf >= 0.6:
                report["flagged"].append(f"alias: {alias['alias']} → {alias['canonical_entity']} (conf={conf:.2f})")

        for evo in decisions.get("evolutions", []):
            conf = evo.get("confidence", 0)
            if conf >= 0.85:
                target_uuid = self.registry.resolve(evo.get("target", ""))
                if target_uuid:
                    self.registry.log_decision(f"evolution:{evo.get('action','')}", target_uuid, confidence=conf, reasoning=evo.get("reasoning",""), source="llm")
                report["auto"].append(f"evolution: {evo.get('action','')} on {evo.get('target','')}")

        self.registry.db.commit()
        n_ent = sum(1 for _ in self.registry.db.execute("SELECT 1 FROM entities"))
        n_rel = sum(1 for _ in self.registry.db.execute("SELECT 1 FROM relations"))
        report["stats"] = {"entities": n_ent, "relations": n_rel}
        return report

    # ── Helpers ───────────────────────────────────────────────

    def _save_raw_text(self, text: str):
        import uuid
        try:
            self.registry.db.execute(
                "INSERT INTO raw_texts (uuid, content, char_count, source, created_at) VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), text, len(text), "ingest", Note.now()),
            )
            self.registry.db.commit()
        except Exception:
            pass

    def _extract_potential_entities(self, themes: list) -> list[str]:
        """Extract potential entity names from text using simple heuristics."""
        names = set()
        for theme in themes:
            text = theme.get("text", "")
            # Capitalized words that look like proper nouns
            import re
            for match in re.finditer(r'\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,})?\b', text):
                names.add(match.group(0))
            # Also check for known entity mentions
            try:
                rows = self.registry.db.execute("SELECT canonical_name FROM entities WHERE status='active'").fetchall()
                lower_text = text.lower()
                for (name,) in rows:
                    if name.lower() in lower_text:
                        names.add(name)
            except Exception:
                pass
        return list(names)[:15]

    def _get_past_decisions(self, context: dict) -> str:
        """Extract relevant past decisions that were reverted."""
        try:
            rows = self.registry.db.execute(
                "SELECT action, reasoning, reverted FROM reasoning_trail WHERE reverted=1 ORDER BY timestamp DESC LIMIT 5"
            ).fetchall()
            if not rows:
                return "(no past mistakes to learn from)"
            lines = []
            for action, reasoning, _ in rows:
                lines.append(f"- REVERTED: {action}. Reason: {reasoning[:150]}")
            return "\n".join(lines)
        except Exception:
            return "(unable to load past decisions)"

    @staticmethod
    def _compact_context(ctx: dict) -> dict:
        c = {}
        if ctx.get("temporal_context"):
            c["temporal"] = [{"date": d.get("date",""), "summary": str(d.get("summary",""))[:200]} for d in ctx["temporal_context"][:7]]
        if ctx.get("entity_contexts"):
            c["entities"] = {k: {"type": v.get("type","?"), "relations": v.get("relation_count",0), "aliases": v.get("aliases",[])[:5]} for k, v in list(ctx["entity_contexts"].items())[:8]}
        if ctx.get("emotional_matches"):
            c["emotional"] = len(ctx["emotional_matches"])
        if ctx.get("weekly_summary"):
            ws = ctx["weekly_summary"]
            c["weekly"] = {"summary": str(ws.get("summary",""))[:300], "dominant_emotion": ws.get("dominant_emotion","")}
        return c

    @staticmethod
    def _parse_json(raw: str) -> dict:
        cleaned = raw.strip()
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
            return {"entities": [], "links": [], "evolutions": [], "new_aliases": [], "needs_more_search": [], "summary": "parse error"}

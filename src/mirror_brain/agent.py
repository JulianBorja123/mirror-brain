"""
Mirror Brain v3 — Agentic Pipeline with procedural memory, consolidation,
predictive engine, and multi-modal support.
"""
import json
import re
from typing import Callable, Optional

from .models import Note
from .registry import EntityRegistry
from .tools import SearchTools
from .preprocessor import TextPreprocessor


AGENT_SYSTEM_PROMPT = """You are the Mirror Brain Agent v3, an agentic memory system.

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
  "procedures_learned": [
    {{
      "name": "procedure name",
      "steps": ["step 1", "step 2"],
      "context": "when to use this procedure",
      "confidence": 0.0-1.0
    }}
  ],
  "projections": [
    {{
      "entity": "entity name",
      "metric": "emotional|activity|growth",
      "direction": "up|down|stable",
      "horizon": "next week|next month",
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
- Procedures: if the text describes a repeatable workflow, extract it.
- Projections: if trend data is available and text suggests future direction.
- needs_more_search: ONLY if truly insufficient context. Max 2 items.
- Confidence: >0.85=auto, 0.6-0.85=flag, <0.6=skip.
- Past decisions with reverted=true: avoid repeating those mistakes.

Return ONLY valid JSON. No markdown fences."""


class MirrorBrainAgent:
    """v3 Agent: tools → activate → decide → loop → execute → consolidate."""

    def __init__(self, registry: EntityRegistry, llm_call: Callable,
                 c0_client=None, max_loops: int = 3,
                 procedural=None, consolidation=None,
                 predictive=None, multimodal=None):
        self.registry = registry
        self.llm = llm_call
        self.c0 = c0_client
        self.tools = SearchTools()
        self.preprocessor = TextPreprocessor()
        self.max_loops = max_loops

        # v3 modules (optional — gracefully degrade if None)
        self.procedural = procedural
        self.consolidation = consolidation
        self.predictive = predictive
        self.multimodal = multimodal

    def process(self, text: str) -> dict:
        """Full v3 pipeline. Returns execution report."""
        # 0. Save raw text
        self._save_raw_text(text)

        # 0.5. Pre-process: estimate complexity, split themes
        complexity = self.preprocessor.estimate_complexity(text)
        themes = self.preprocessor.split_by_themes(text) if complexity["char_count"] > 500 else [{"theme": "main", "text": text, "start_char": 0, "end_char": len(text)}]

        # 1. ACTIVATION: search brain with tools (v2 + v3)
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

        # 3.5. Process v3-specific decisions
        decisions = self._process_v3_decisions(decisions, all_context)

        # 4. EXECUTE with confidence gates
        report = self._execute(decisions)

        # 5. V3 POST-PROCESS: record procedural trace + auto-consolidate
        self._post_process(report, decisions, text)

        report["complexity"] = complexity
        report["theme_count"] = len(themes)
        report["loops_used"] = loop_i + 1 if decisions.get("needs_more_search") else 1
        report["summary"] = decisions.get("summary", "")

        return report

    # ── Activation ──────────────────────────────────────────

    def _activate(self, text: str, themes: list, complexity: dict) -> dict:
        """Search the brain using tools dynamically selected by text complexity.

        Tool selection strategy:
        - char_count > 2000: include semantic search, full entity extraction
        - emotional_density > 0.03: include emotion search, trend, cycles, anomalies
        - entity_density > 0.02: include minimap + fuzzy for all extracted entities
        - entity_density > 0.05: also include trend/cycles for top entities
        - estimated_themes > 3: include procedures search
        - estimated_themes > 5: include broader temporal range (0-30 days)
        - Always: temporal context (21d window), weekly+monthly summary, memory budget
        """
        ctx = {
            "temporal_context": [],
            "entity_contexts": {},
            "emotional_matches": [],
            "semantic_matches": [],
            "weekly_summary": None,
            "monthly_summary": None,
            "fuzzy_matches": [],
            "trends": {},
            "cycles": {},
            "anomalies": [],
            "memory_budget": None,
            "procedures_suggested": [],
            "tools_used": [],  # track which tools were activated
        }

        char_count = complexity.get("char_count", 0)
        emo_dens = complexity.get("emotional_density", 0)
        ent_dens = complexity.get("entity_density", 0)
        est_themes = complexity.get("estimated_themes", 1)

        # ── ALWAYS ──
        ctx["temporal_context"] = self.tools.search_temporal(self.registry, days_ago=0, window=21)
        ctx["tools_used"].append("search_temporal")
        ctx["weekly_summary"] = self.tools.get_weekly_summary(self.registry)
        ctx["tools_used"].append("get_weekly_summary")
        ctx["monthly_summary"] = self.tools.get_monthly_summary(self.registry)
        ctx["tools_used"].append("get_monthly_summary")
        ctx["memory_budget"] = self.tools.get_memory_budget(self.registry)
        ctx["tools_used"].append("get_memory_budget")

        # ── ENTITY-BASED (scales with entity density) ──
        entity_names = self._extract_potential_entities(themes)

        # How many entities to process: proportional to density
        if ent_dens > 0.05:
            max_entities = min(15, len(entity_names))
        elif ent_dens > 0.02:
            max_entities = min(10, len(entity_names))
        else:
            max_entities = min(5, len(entity_names))

        for name in entity_names[:max_entities]:
            minimap = self.tools.get_minimap(self.registry, name)
            if minimap and not minimap.get("error"):
                ctx["entity_contexts"][name] = minimap
                ctx["tools_used"].append(f"get_minimap({name})")

            fuzzy_results = self.tools.search_fuzzy(self.registry, name)
            if fuzzy_results:
                ctx["fuzzy_matches"].extend(fuzzy_results)
                ctx["tools_used"].append(f"search_fuzzy({name})")

            # Trends + cycles only if entity recognized AND density is high
            if minimap and not minimap.get("error") and ent_dens > 0.03:
                trend = self.tools.get_trend(self.registry, name, metric="oxytocin", window=30)
                if trend and not trend.get("error"):
                    ctx["trends"][name] = trend
                    ctx["tools_used"].append(f"get_trend({name})")
                cycles = self.tools.search_cycles(self.registry, name, metric="oxytocin")
                if cycles and cycles.get("has_cycle"):
                    ctx["cycles"][name] = cycles
                    ctx["tools_used"].append(f"search_cycles({name})")

        # ── EMOTIONAL (triggers when emotional density detected) ──
        if emo_dens > 0.03:
            emotions_to_check = ["oxytocin", "cortisol", "dopamine", "adrenaline"]
            # If very emotional (>8%), check all emotions. Otherwise top 2.
            if emo_dens > 0.08:
                check_emotions = emotions_to_check
            else:
                check_emotions = emotions_to_check[:2]
            for emotion in check_emotions:
                matches = self.tools.search_by_emotion(self.registry, emotion, threshold=0.3, limit=5)
                if matches:
                    ctx["emotional_matches"].extend(matches)
                    ctx["tools_used"].append(f"search_by_emotion({emotion})")

            # Anomalies only for most emotional texts
            if emo_dens > 0.06:
                for name in entity_names[:3]:
                    anoms = self.tools.get_anomalies(self.registry, name, metric="oxytocin")
                    if anoms:
                        ctx["anomalies"].extend([{**a, "entity": name} for a in anoms[:2]])
                        ctx["tools_used"].append(f"get_anomalies({name})")

        # ── SEMANTIC (triggers for long/complex texts) ──
        if char_count > 2000 or est_themes > 3:
            for theme in themes[:min(3, est_themes)]:
                text_sample = theme["text"][:200]
                if self.c0:
                    results = self.tools.search_semantic(self.registry, self.c0, text_sample, limit=5)
                    if results:
                        ctx["semantic_matches"].extend(results)
                        ctx["tools_used"].append("search_semantic")

        # ── PROCEDURAL (triggers for multi-theme texts) ──
        if est_themes > 3 or char_count > 1000:
            procedures = self.tools.search_procedures(self.registry, text[:500], limit=5)
            if procedures:
                ctx["procedures_suggested"] = procedures
                ctx["tools_used"].append("search_procedures")

        # ── BROADER TEMPORAL (triggers for very complex texts) ──
        if est_themes > 5 or char_count > 3000:
            broader = self.tools.search_temporal_range(self.registry, 0, 30)
            if broader:
                ctx["temporal_context"].extend(broader[:10])
                ctx["tools_used"].append("search_temporal_range(0-30d)")

        return ctx

    def _search_more(self, queries: list[str]) -> list:
        """Execute additional searches requested by LLM."""
        extra = []
        for q in queries[:3]:
            results = self.tools.search_fuzzy(self.registry, q)
            if results:
                extra.append({"query": q, "type": "fuzzy", "results": results})
            if self.c0:
                results = self.tools.search_semantic(self.registry, self.c0, q, limit=3)
                if results:
                    extra.append({"query": q, "type": "semantic", "results": results})
            # v3: also search procedures
            proc_results = self.tools.search_procedures(self.registry, q, limit=2)
            if proc_results:
                extra.append({"query": q, "type": "procedures", "results": proc_results})
            # v3: temporal range if date-like
            if re.search(r'\b(?:semana|mes|week|month|last|next)\b', q, re.IGNORECASE):
                range_results = self.tools.search_temporal_range(self.registry, 0, 30)
                if range_results:
                    extra.append({"query": q, "type": "temporal_range", "results": range_results[:5]})
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

    # ── V3 Decision Processing ───────────────────────────────

    def _process_v3_decisions(self, decisions: dict, context: dict) -> dict:
        """Process v3-specific decision fields: procedures_learned, projections."""
        # Handle procedures_learned — the LLM extracted a workflow
        if self.procedural:
            for proc in decisions.get("procedures_learned", []):
                name = proc.get("name", "")
                steps = proc.get("steps", [])
                proc_context = proc.get("context", "")
                conf = proc.get("confidence", 0)
                if name and steps and conf >= 0.7:
                    try:
                        self.procedural.learn_procedure(name, steps, proc_context)
                    except Exception:
                        pass

        # Handle projections — store for later trend comparison
        for proj in decisions.get("projections", []):
            entity = proj.get("entity", "")
            metric = proj.get("metric", "activity")
            direction = proj.get("direction", "stable")
            conf = proj.get("confidence", 0)
            if entity and conf >= 0.6 and self.predictive:
                target_uuid = self.registry.resolve(entity)
                if not target_uuid:
                    search_result = self.registry.search(entity)
                    target_uuid = search_result[0]["uuid"] if search_result else None
                if target_uuid:
                    try:
                        proj_result = self.predictive.project_next(entity, metric=metric, days=7)
                        if proj_result:
                            confidence = proj_result[0].get("confidence", conf) if proj_result else conf
                            self.registry.log_decision(
                                "project",
                                target_uuid,
                                confidence=confidence,
                                reasoning=f"projected {direction} — {proj.get('reasoning','')}",
                                source="predictive_engine",
                            )
                    except Exception:
                        pass

        return decisions

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

    # ── V3 Post-Process ──────────────────────────────────────

    def _post_process(self, report: dict, decisions: dict, text: str):
        """V3 post-processing: record procedural trace, auto-consolidate."""
        # Record procedural trace from this execution
        if self.procedural:
            actions_executed = [a.split(":")[0] if ":" in a else a for a in report.get("auto", [])[:10]]
            entities_involved = []
            for ent in decisions.get("entities", []):
                entities_involved.append(ent.get("name", ""))
            if actions_executed:
                outcome = "success" if report.get("auto") else "no_actions"
                try:
                    self.procedural.record_trace(actions_executed, entities_involved, outcome)
                except Exception:
                    pass

        # Auto-consolidate if memory budget is getting large
        if self.consolidation:
            try:
                budget = self.consolidation.get_memory_budget()
                total_entries = sum(budget.values())
                if total_entries > 50:  # threshold: consolidate when over 50 entries
                    self.consolidation.auto_consolidate()
            except Exception:
                pass

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
            for match in re.finditer(r'\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,})?\b', text):
                names.add(match.group(0))
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
        if ctx.get("monthly_summary"):
            ms = ctx["monthly_summary"]
            c["monthly"] = {"summary": str(ms.get("summary",""))[:300]}
        if ctx.get("trends"):
            c["trends"] = {k: {"direction": v.get("direction","?"), "confidence": v.get("confidence",0)} for k, v in list(ctx["trends"].items())[:5]}
        if ctx.get("cycles"):
            c["cycles"] = {k: {"period_days": v.get("period_days",0), "confidence": v.get("confidence",0)} for k, v in list(ctx["cycles"].items())[:3]}
        if ctx.get("anomalies"):
            c["anomalies_count"] = len(ctx["anomalies"])
        if ctx.get("memory_budget"):
            c["memory_budget"] = ctx["memory_budget"]
        if ctx.get("procedures_suggested"):
            c["procedures"] = [{"name": p.get("name",""), "score": p.get("score",0)} for p in ctx["procedures_suggested"][:5]]
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
            return {"entities": [], "links": [], "evolutions": [], "new_aliases": [],
                    "procedures_learned": [], "projections": [],
                    "needs_more_search": [], "summary": "parse error"}

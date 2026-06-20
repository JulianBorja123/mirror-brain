"""
Mirror Brain v3 — MCP Server
Exposes all 15 tools + agent pipeline as MCP tools for Hermes Agent.
Run: python mcp_server.py --db mirror_brain.db [--port 8765]
"""
from __future__ import annotations

import argparse, json, os, sys
from datetime import date, timedelta
from typing import Callable

# ── Parse CLI args early (before FastMCP creation) ────────────
_parser = argparse.ArgumentParser(description="Mirror Brain v3 MCP Server")
_parser.add_argument("--db", default="mirror_brain.db", help="SQLite database path")
_parser.add_argument("--port", type=int, default=8765, help="HTTP port")
_parser.add_argument("--host", default="127.0.0.1", help="Bind address")
_args = _parser.parse_args()

# Ensure mirror_brain is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from mcp.server import FastMCP
from mirror_brain.c0_client import C0Client
from mirror_brain.c0_registry import C0Registry
from mirror_brain.tools import SearchTools
from mirror_brain.agent import MirrorBrainAgent
from mirror_brain.procedural import ProceduralMemory
from mirror_brain.consolidation import HierarchicalConsolidation
from mirror_brain.predictive import PredictiveEngine
from mirror_brain.multimodal import MultiModal

from mirror_brain.internal_reasoner import InternalReasoner
from mirror_brain.skills import SkillManager

# ═══════════════════════════════════════════════════════════════
# Globals (set during startup)
# ═══════════════════════════════════════════════════════════════

_c0: C0Client | None = None
_registry: C0Registry | None = None
_tools: SearchTools | None = None
_agent: MirrorBrainAgent | None = None
_procedural: ProceduralMemory | None = None
_consolidation: HierarchicalConsolidation | None = None
_predictive: PredictiveEngine | None = None
_multimodal: MultiModal | None = None
_reasoner: InternalReasoner | None = None
_skills: SkillManager | None = None

# ═══════════════════════════════════════════════════════════════
# MCP Server
# ═══════════════════════════════════════════════════════════════

mcp = FastMCP(
    "Mirror Brain v3",
    instructions="Agentic memory system with 15 search tools + predictive engine + procedural learning. Use mb_ingest(text) for the full agent pipeline, or individual mb_search_* tools for targeted queries.",
    host=_args.host,
    port=_args.port,
)


# ── INGEST: Full agent pipeline ──────────────────────────────

@mcp.tool()
def mb_ingest(text: str, source: str = "mcp") -> str:
    """Run the full Mirror Brain v3 agent pipeline on text.

    This is the MAIN tool. Feed it any text (conversation, thought, journal entry,
    code log) and the agent will:
    1. Preprocess: estimate complexity, split into themes
    2. Activate memory: search 15 tools for relevant context
    3. Decide: LLM creates entities, links, evolution, aliases, procedures, projections
    4. Execute: confidence-gated auto/flag/skip decisions
    5. Post-process: record procedural trace, auto-consolidate if needed

    Returns a JSON report with auto-executed decisions, flagged items,
    entity/relation counts, summary, and complexity metrics.
    """
    report = _agent.process(text)
    return json.dumps(report, ensure_ascii=False, indent=2, default=str)


# ── 15 SEARCH TOOLS ──────────────────────────────────────────

@mcp.tool()
def mb_search_semantic(query: str, limit: int = 10) -> str:
    """Hybrid semantic search via c0 (exact → keyword → vector RRF).
    Returns empty if c0 is not running."""
    results = _tools.search_semantic(_registry, _c0, query, limit)
    return json.dumps(results, ensure_ascii=False, default=str)


@mcp.tool()
def mb_search_by_emotion(emotion: str = "oxytocin", threshold: float = 0.5, limit: int = 10) -> str:
    """Find days where an emotion exceeded threshold.
    Supported: oxytocin, adrenaline, cortisol, dopamine."""
    results = _tools.search_by_emotion(_registry, emotion, threshold, limit)
    return json.dumps(results, ensure_ascii=False, default=str)


@mcp.tool()
def mb_search_temporal(days_ago: int = 0, window: int = 3) -> str:
    """Get daily summaries in a window around N days ago.
    days_ago=0 = today, window=7 = ±3 days. Use for 'what happened last week?'"""
    results = _tools.search_temporal(_registry, days_ago, window)
    return json.dumps(results, ensure_ascii=False, default=str)


@mcp.tool()
def mb_search_fuzzy(name: str, max_distance: int = 3) -> str:
    """Fuzzy search across entity names and aliases. 'Rom' → Romina Gonzalez."""
    results = _tools.search_fuzzy(_registry, name, max_distance)
    return json.dumps(results, ensure_ascii=False, default=str)


@mcp.tool()
def mb_get_minimap(entity_name: str) -> str:
    """Get compact entity overview: type, aliases, relation count, recent activity, emotional profile."""
    result = _tools.get_minimap(_registry, entity_name)
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def mb_get_weekly_summary(week_start: str | None = None) -> str:
    """Get aggregated weekly summary: dominant emotion, key entities, daily breakdown. week_start=None → current week."""
    result = _tools.get_weekly_summary(_registry, week_start)
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def mb_search_raw_text(query: str, limit: int = 5) -> str:
    """Search original ingested texts by keyword."""
    results = _tools.search_raw_text(_registry, query, limit)
    return json.dumps(results, ensure_ascii=False, default=str)


@mcp.tool()
def mb_search_procedures(query: str, limit: int = 5) -> str:
    """Find procedures/workflows matching a context description."""
    results = _tools.search_procedures(_registry, query, limit)
    return json.dumps(results, ensure_ascii=False, default=str)


@mcp.tool()
def mb_get_procedure(name: str) -> str:
    """Get details of a specific procedure by name."""
    result = _tools.get_procedure(_registry, name)
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def mb_search_temporal_range(start_days_ago: int = 0, end_days_ago: int = 30) -> str:
    """Get daily summaries in a flexible date range (N days ago to M days ago)."""
    results = _tools.search_temporal_range(_registry, start_days_ago, end_days_ago)
    return json.dumps(results, ensure_ascii=False, default=str)


@mcp.tool()
def mb_get_monthly_summary(month_start: str | None = None) -> str:
    """Get monthly consolidated summary. month_start=None → current month."""
    result = _tools.get_monthly_summary(_registry, month_start)
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def mb_search_cycles(entity_name: str, metric: str = "oxytocin") -> str:
    """Detect repeating temporal patterns for an entity. Returns {has_cycle, period_days, confidence}."""
    result = _tools.search_cycles(_registry, entity_name, metric)
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def mb_get_trend(entity_name: str, metric: str = "oxytocin", window: int = 30) -> str:
    """Get trend direction for an entity: up/down/stable with confidence (R²)."""
    result = _tools.get_trend(_registry, entity_name, metric, window)
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def mb_get_anomalies(entity_name: str, metric: str = "oxytocin") -> str:
    """Detect days where metric deviated >2σ from mean."""
    result = _tools.get_anomalies(_registry, entity_name, metric)
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def mb_get_memory_budget() -> str:
    """Get memory budget: how many entries at daily/weekly/monthly tiers."""
    result = _tools.get_memory_budget(_registry)
    return json.dumps(result, ensure_ascii=False, default=str)


# ── PREDICTIVE ENGINE DIRECT TOOLS ───────────────────────────

@mcp.tool()
def mb_predict(entity_name: str, metric: str = "oxytocin", days: int = 7) -> str:
    """Project future values for an entity based on historical trends.
    Returns list of {day, value, confidence} for next N days."""
    result = _predictive.project_next(entity_name, metric, days)
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def mb_correlation(entity_a: str, entity_b: str, metric: str = "oxytocin") -> str:
    """Calculate Pearson correlation between two entities on a metric.
    Returns {pearson_r, shared_days, direction, confidence}."""
    result = _predictive.correlation_find(entity_a, entity_b, metric)
    return json.dumps(result, ensure_ascii=False, default=str)


# ── PROCEDURAL MEMORY TOOLS ──────────────────────────────────

@mcp.tool()
def mb_learn_procedure(name: str, steps_json: str, context: str = "") -> str:
    """Learn a named procedure with steps (JSON array string).
    Example steps_json: '[\"step1\",\"step2\"]'"""
    try:
        steps = json.loads(steps_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "steps_json must be a valid JSON array string"})
    result = _procedural.learn_procedure(name, steps, context)
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def mb_list_entities(limit: int = 50) -> str:
    """List all entities in the registry."""
    try:
        rows = _registry.db.execute(
            "SELECT canonical_name, type, status FROM entities WHERE status='active' ORDER BY canonical_name LIMIT ?",
            (limit,),
        ).fetchall()
        entities = [{"name": r[0], "type": r[1], "status": r[2]} for r in rows]
        return json.dumps(entities, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def mb_list_relations(entity_name: str | None = None, limit: int = 30) -> str:
    """List relations. If entity_name provided, filters to relations involving that entity."""
    try:
        if entity_name:
            uuid_ = _registry.resolve(entity_name)
            if not uuid_:
                search = _registry.search(entity_name)
                uuid_ = search[0]["uuid"] if search else None
            if not uuid_:
                return json.dumps({"error": f"entity '{entity_name}' not found"})
            rows = _registry.db.execute(
                """SELECT e1.canonical_name, r.relation_type, e2.canonical_name
                   FROM relations r
                   JOIN entities e1 ON r.from_uuid = e1.uuid
                   JOIN entities e2 ON r.to_uuid = e2.uuid
                   WHERE r.from_uuid = ? OR r.to_uuid = ?
                   ORDER BY r.id DESC LIMIT ?""",
                (uuid_, uuid_, limit),
            ).fetchall()
        else:
            rows = _registry.db.execute(
                """SELECT e1.canonical_name, r.relation_type, e2.canonical_name
                   FROM relations r
                   JOIN entities e1 ON r.from_uuid = e1.uuid
                   JOIN entities e2 ON r.to_uuid = e2.uuid
                   ORDER BY r.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        relations = [{"from": r[0], "relation": r[1], "to": r[2]} for r in rows]
        return json.dumps(relations, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def mb_consolidate() -> str:
    """Run auto-consolidation: daily→weekly→monthly compaction."""
    result = _consolidation.auto_consolidate()
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def mb_stats() -> str:
    """Get overall Mirror Brain statistics: entity count, relation count, memory tiers."""
    try:
        n_ent = sum(1 for _ in _registry.db.execute("SELECT 1 FROM entities"))
        n_rel = sum(1 for _ in _registry.db.execute("SELECT 1 FROM relations"))
        n_proc = sum(1 for _ in _registry.db.execute("SELECT 1 FROM procedures"))
        n_traces = sum(1 for _ in _registry.db.execute("SELECT 1 FROM procedural_traces"))
        n_media = sum(1 for _ in _registry.db.execute("SELECT 1 FROM media"))
        n_questions = sum(1 for _ in _registry.db.execute("SELECT 1 FROM internal_questions"))
        budget = _consolidation.get_memory_budget() if _consolidation else {}
        return json.dumps({
            "entities": n_ent,
            "relations": n_rel,
            "procedures": n_proc,
            "procedural_traces": n_traces,
            "media_items": n_media,
            "internal_questions": n_questions,
            "memory_budget": budget,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── V3.1: INTERNAL REASONER ─────────────────────────────────

@mcp.tool()
def mb_run_reasoner() -> str:
    """Run the internal reasoner: consolidate, generate questions, suggest connections, suggest improvements."""
    if _reasoner is None:
        return json.dumps({"error": "reasoner not initialized"})
    result = _reasoner.run()
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def mb_get_questions(status: str = "open", limit: int = 20) -> str:
    """Get internal questions generated by the reasoner. status: open|resolved|all"""
    try:
        if status == "all":
            rows = _registry.db.execute(
                "SELECT id, question, context, entities_involved, status, created_at FROM internal_questions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = _registry.db.execute(
                "SELECT id, question, context, entities_involved, status, created_at FROM internal_questions WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        questions = [{"id": r[0], "question": r[1], "context": r[2], "entities_involved": json.loads(r[3]) if r[3] else [], "status": r[4], "created_at": r[5]} for r in rows]
        return json.dumps(questions, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── V3.1: SKILLS ────────────────────────────────────────────

@mcp.tool()
def mb_find_skills(text: str, limit: int = 5) -> str:
    """Find relevant Mirror Brain skills matching the input text."""
    if _skills is None:
        return json.dumps({"error": "skills manager not initialized"})
    results = _skills.find_relevant(text, limit)
    return json.dumps(results, ensure_ascii=False)


@mcp.tool()
def mb_get_skill(name: str) -> str:
    """Get full content of a Mirror Brain skill by name."""
    if _skills is None:
        return json.dumps({"error": "skills manager not initialized"})
    skill = _skills.get_skill(name)
    return json.dumps(skill, ensure_ascii=False) if skill else json.dumps({"error": f"skill '{name}' not found"})


@mcp.tool()
def mb_list_skills() -> str:
    """List all Mirror Brain skills."""
    if _skills is None:
        return json.dumps({"error": "skills manager not initialized"})
    skills = _skills.list_skills()
    return json.dumps(skills, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# Startup
# ═══════════════════════════════════════════════════════════════

def _get_deepseek_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        for hp in [os.path.expanduser("~/.hermes/env"),
                   os.path.expanduser("~/AppData/Local/hermes/.env")]:
            if os.path.exists(hp):
                with open(hp) as f:
                    for line in f:
                        if "DEEPSEEK_API_KEY" in line:
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
    return key


def _deepseek_llm(prompt: str) -> str:
    import urllib.request as ur
    key = _get_deepseek_key()
    if not key:
        return json.dumps({"entities": [], "links": [], "evolutions": [], "new_aliases": [],
                           "procedures_learned": [], "projections": [],
                           "needs_more_search": [], "summary": "no API key"})
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2000,
    }).encode()
    req = ur.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with ur.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


# ── Init registry and modules (c0-backed) ────────────────────

_c0 = C0Client(namespace="mirrorbrain")
_registry = C0Registry(_c0)

# Seed if empty
all_e = _registry.get_all_entities()
n = len(all_e)
if n == 0:
    print(f"[MB-MCP] Seeding initial entities...")
    _registry.create("Gustavo Julian Barrios Borja", "person")
    _registry.create("Romina Gonzalez", "person")
    _registry.add_alias("Romi", _registry.resolve("Romina Gonzalez"), source="manual")
    _registry.create("Mirror Brain", "project")
    _registry.add_alias("MB", _registry.resolve("Mirror Brain"), source="manual")
    _registry.create("c0", "tool")
    _registry.create("DeepSeek", "tool")
    _registry.create("Hermes Agent", "tool")
    _registry.create("Docker", "tool")
    _registry.create("Ollama", "tool")
    _registry.create("Neo4j", "tool")
    n = 9

_tools = SearchTools()
_procedural = ProceduralMemory(_registry)
_consolidation = HierarchicalConsolidation(_registry)
_predictive = PredictiveEngine(_registry)
_multimodal = MultiModal(_registry.db)
_reasoner = InternalReasoner(_registry)
_skills = SkillManager(_registry)

_agent = MirrorBrainAgent(
    _registry,
    llm_call=_deepseek_llm,
    c0_client=_c0,
    max_loops=3,
    procedural=_procedural,
    consolidation=_consolidation,
    predictive=_predictive,
    multimodal=_multimodal,
)

print(f"[MB-MCP] Mirror Brain v3 MCP Server starting on {_args.host}:{_args.port}")
print(f"[MB-MCP] Backend: c0 (Neo4j+Ollama) | Entities: {n} | Tools: 15 + agent pipeline")
try:
    budget = _consolidation.get_memory_budget()
    print(f"[MB-MCP] Memory budget: {budget}")
except Exception:
    print(f"[MB-MCP] Memory budget: c0 mode (consolidation uses c0 graph)")

if __name__ == "__main__":
    mcp.run(transport="streamable-http")

"""
Mirror Brain v3 — MCP Server
Exposes all 15 tools + agent pipeline as MCP tools for Hermes Agent.
Run: python mcp_server.py --db mirror_brain.db [--port 8765]
"""
from __future__ import annotations

import argparse, json, os, sys, threading, time, uuid
from datetime import date, timedelta
from typing import Callable

# ── Parse CLI args early (before FastMCP creation) ────────────
_parser = argparse.ArgumentParser(description="Mirror Brain v3 MCP Server (c0-backed)")
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
# Async Task Queue (for long-running mb_ingest)
# ═══════════════════════════════════════════════════════════════

class TaskManager:
    """In-memory async task queue with status polling and result retrieval."""

    TASK_TTL = 3600  # Auto-expire tasks after 1 hour

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: dict[str, dict] = {}  # task_id → {status, created_at, result, error}

    def submit(self, fn: Callable, *args, **kwargs) -> str:
        """Submit a callable to run in a background thread. Returns task_id."""
        task_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._tasks[task_id] = {
                "status": "queued",
                "created_at": time.time(),
                "result": None,
                "error": None,
            }

        def _runner():
            try:
                with self._lock:
                    self._tasks[task_id]["status"] = "running"
                result = fn(*args, **kwargs)
                with self._lock:
                    self._tasks[task_id]["status"] = "done"
                    self._tasks[task_id]["result"] = result
            except Exception as e:
                with self._lock:
                    self._tasks[task_id]["status"] = "error"
                    self._tasks[task_id]["error"] = str(e)

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        return task_id

    def status(self, task_id: str) -> dict:
        """Get task status: {status, created_at, elapsed_s}."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"status": "not_found"}
            return {
                "status": task["status"],
                "created_at": task["created_at"],
                "elapsed_s": round(time.time() - task["created_at"], 1),
            }

    def result(self, task_id: str) -> dict:
        """Get task result. Returns {status, result, error}."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"status": "not_found", "result": None, "error": "task not found or expired"}
            return {
                "status": task["status"],
                "result": task["result"] if task["status"] == "done" else None,
                "error": task["error"],
            }

    def cleanup(self):
        """Remove expired tasks."""
        now = time.time()
        with self._lock:
            expired = [tid for tid, t in self._tasks.items()
                       if now - t["created_at"] > self.TASK_TTL]
            for tid in expired:
                del self._tasks[tid]

_taskmgr = TaskManager()

# ═══════════════════════════════════════════════════════════════
# MCP Server
# ═══════════════════════════════════════════════════════════════

mcp = FastMCP(
    "Mirror Brain v3",
    instructions="Agentic memory system with 15 search tools + predictive engine + procedural learning. Use mb_ingest(text) to start async ingestion (returns task_id), then poll with mb_task_status(task_id) and get results with mb_task_result(task_id). Use individual mb_search_* tools for targeted queries.",
    host=_args.host,
    port=_args.port,
)


# ── INGEST: Full agent pipeline ──────────────────────────────

@mcp.tool()
def mb_ingest(text: str, source: str = "mcp") -> str:
    """Start async ingestion of text via the full Mirror Brain v3 agent pipeline.

    Returns IMMEDIATELY with a task_id. The agent pipeline runs in background:
    1. Preprocess: estimate complexity, split into themes
    2. Activate memory: search 15 tools for relevant context
    3. Decide: LLM creates entities, links, evolution, aliases, procedures, projections
    4. Execute: confidence-gated auto/flag/skip decisions
    5. Post-process: record procedural trace, auto-consolidate if needed

    Poll status with mb_task_status(task_id). Get final result with mb_task_result(task_id).
    """
    task_id = _taskmgr.submit(_agent.process, text)
    return json.dumps({"task_id": task_id, "status": "queued"}, ensure_ascii=False)


@mcp.tool()
def mb_task_status(task_id: str) -> str:
    """Poll the status of an async ingestion task.

    Returns {status: 'queued'|'running'|'done'|'error'|'not_found', created_at, elapsed_s}.
    """
    return json.dumps(_taskmgr.status(task_id), ensure_ascii=False)


@mcp.tool()
def mb_task_result(task_id: str) -> str:
    """Get the result of a completed async ingestion task.

    Returns {status, result: <full agent report JSON>, error}.
    If task is not 'done', result will be null — poll with mb_task_status first.
    """
    return json.dumps(_taskmgr.result(task_id), ensure_ascii=False, default=str)


# ── CORRECTION TOOLS (manual feedback) ────────────────────────

@mcp.tool()
def mb_correct(entity_name: str, type: str = "", description: str = "") -> str:
    """Manually correct an entity's type or description.

    Use when the agent got something wrong. Examples:
    - mb_correct('Romina Gonzalez', type='person')
    - mb_correct('Docker', description='Containerization platform, not just a tool')
    - mb_correct('Mirror Brain', type='project', description='AI memory system built by Julian')

    Updates the entity in c0 immediately. Returns confirmation.
    """
    try:
        uuid_ = _registry.resolve(entity_name)
        if not uuid_:
            return json.dumps({"error": f"Entity '{entity_name}' not found. Check spelling or create it first."})

        updates = {}
        if type:
            updates["type"] = type
        if description:
            updates["description"] = description
        if not updates:
            return json.dumps({"error": "Nothing to correct. Provide 'type' and/or 'description'."})

        _registry.update_entity(uuid_, **updates)
        return json.dumps({
            "corrected": entity_name,
            "uuid": uuid_,
            "updates": updates,
            "status": "ok"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def mb_add_alias(entity_name: str, alias: str) -> str:
    """Add an alias for an entity so fuzzy search can find it by multiple names.

    Examples:
    - mb_add_alias('Romina Gonzalez', 'Romi')
    - mb_add_alias('Mirror Brain', 'MB')
    - mb_add_alias('Gustavo Julian Barrios Borja', 'Juli')

    Returns confirmation with the alias added.
    """
    try:
        uuid_ = _registry.resolve(entity_name)
        if not uuid_:
            return json.dumps({"error": f"Entity '{entity_name}' not found."})

        _registry.add_alias(alias, uuid_, source="manual")
        return json.dumps({
            "entity": entity_name,
            "alias": alias,
            "status": "ok"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def mb_link(entity_a: str, relation: str, entity_b: str) -> str:
    """Create a manual relationship between two entities.

    Examples:
    - mb_link('Gustavo Julian Barrios Borja', 'works_on', 'Mirror Brain')
    - mb_link('Mirror Brain', 'uses', 'Neo4j')
    - mb_link('Romina Gonzalez', 'friends_with', 'Gustavo Julian Barrios Borja')

    Creates the relation in c0's graph immediately. Returns confirmation.
    """
    try:
        uuid_a = _registry.resolve(entity_a)
        uuid_b = _registry.resolve(entity_b)
        if not uuid_a:
            return json.dumps({"error": f"Entity '{entity_a}' not found."})
        if not uuid_b:
            return json.dumps({"error": f"Entity '{entity_b}' not found."})

        _c0.relate(entity_a, entity_b, relation)
        return json.dumps({
            "from": entity_a,
            "relation": relation,
            "to": entity_b,
            "status": "ok"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── CACHE TOOLS ──────────────────────────────────────────────

@mcp.tool()
def mb_cache_stats() -> str:
    """Get cache performance statistics: size, hits, misses, hit_rate."""
    from mirror_brain.c0_registry import _cache
    return json.dumps(_cache.stats(), ensure_ascii=False)


@mcp.tool()
def mb_invalidate_cache(prefix: str = "") -> str:
    """Invalidate cache entries. Empty prefix = clear all.

    Prefixes: 'entities:all' (entity list), 'stats:' (stats), 'search:entity:' (fuzzy lookups).
    Use after manual corrections to force fresh data on next query.
    """
    from mirror_brain.c0_registry import _cache
    before = _cache.stats()["size"]
    _cache.invalidate(prefix)
    after = _cache.stats()["size"]
    return json.dumps({
        "invalidated": before - after,
        "remaining": after,
        "prefix": prefix or "(all)",
    }, ensure_ascii=False)


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
    """List all entities in the registry (c0-backed)."""
    try:
        entities = _registry.get_all_entities(limit=limit)
        result = [
            {
                "name": e.get("canonical_name", "unknown"),
                "type": e.get("type", "concept"),
                "status": e.get("status", "active"),
            }
            for e in entities
        ]
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def mb_list_relations(entity_name: str | None = None, limit: int = 30) -> str:
    """List relations. If entity_name provided, filters to relations involving that entity (c0-backed)."""
    try:
        if entity_name:
            uuid_ = _registry.resolve(entity_name)
            if not uuid_:
                return json.dumps({"error": f"entity '{entity_name}' not found"})
            relations = _registry.get_relations(uuid_)
            result = [
                {"from": entity_name, "relation": r.get("relation_type", "related_to"), "to": r.get("to_name", "unknown")}
                for r in relations
            ][:limit]
        else:
            # List all relations via optimized c0 export cache
            result = _c0.list_relations(limit=limit)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def mb_remove_alias(entity_name: str, alias: str) -> str:
    """Remove an alias from an entity. Use when an alias was incorrectly assigned.

    Examples:
    - mb_remove_alias('Gustavo Julian Barrios Borja', 'Gus')
    - mb_remove_alias('Mirror Brain', 'MB_old')

    Returns confirmation with the alias removed.
    """
    try:
        uuid_ = _registry.resolve(entity_name)
        if not uuid_:
            return json.dumps({"error": f"Entity '{entity_name}' not found."})

        # Remove from alias cache
        alias_lower = alias.lower()
        if alias_lower in _registry._alias_cache and _registry._alias_cache[alias_lower] == uuid_:
            del _registry._alias_cache[alias_lower]
            return json.dumps({
                "entity": entity_name,
                "removed_alias": alias,
                "status": "ok"
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "entity": entity_name,
                "alias": alias,
                "status": "not_found",
                "hint": "Alias was not registered for this entity"
            }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def mb_reassign_alias(alias: str, from_entity: str, to_entity: str) -> str:
    """Move an alias from one entity to another. Use when an alias was assigned to the wrong entity.

    Examples:
    - mb_reassign_alias('Gus', 'Gustavo Julian Barrios Borja', 'Proyecto Gus')

    Returns confirmation.
    """
    try:
        from_uuid = _registry.resolve(from_entity)
        to_uuid = _registry.resolve(to_entity)
        if not from_uuid:
            return json.dumps({"error": f"Source entity '{from_entity}' not found."})
        if not to_uuid:
            return json.dumps({"error": f"Target entity '{to_entity}' not found."})

        alias_lower = alias.lower()
        if alias_lower in _registry._alias_cache and _registry._alias_cache[alias_lower] == from_uuid:
            _registry._alias_cache[alias_lower] = to_uuid
            return json.dumps({
                "alias": alias,
                "from": from_entity,
                "to": to_entity,
                "status": "ok"
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "alias": alias,
                "status": "not_found",
                "hint": f"Alias '{alias}' was not registered for '{from_entity}'"
            }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def mb_list_aliases(entity_name: str) -> str:
    """List all aliases registered for an entity.

    Examples:
    - mb_list_aliases('Gustavo Julian Barrios Borja')
    - mb_list_aliases('Mirror Brain')

    Returns list of aliases.
    """
    try:
        uuid_ = _registry.resolve(entity_name)
        if not uuid_:
            return json.dumps({"error": f"Entity '{entity_name}' not found."})

        aliases = []
        for alias_lower, uid in _registry._alias_cache.items():
            if uid == uuid_:
                aliases.append(alias_lower)

        return json.dumps({
            "entity": entity_name,
            "uuid": uuid_,
            "aliases": aliases,
            "count": len(aliases),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── ULTRA-FAST ID LOOKUP ────────────────────────────────────

@mcp.tool()
def mb_get_by_id(uuid: str) -> str:
    """Instant entity lookup by UUID. Ultra-fast — direct cache hit, no graph walk.

    Examples:
    - mb_get_by_id('e5fc3067-1762-5351-826c-11cca8a74bd6')

    Returns full entity info: canonical_name, type, aliases, properties, relation_count.
    """
    try:
        # Direct cache lookup (no c0 call)
        name = _registry._uuid_to_name(uuid)
        if not name:
            return json.dumps({"error": f"UUID '{uuid}' not found in registry."})

        aliases_all = _registry.get_aliases(uuid)
        alias_names = [a.get("alias", "") for a in aliases_all]

        # Get entity type from cache or single c0 keyword search
        entity_type = "concept"
        props = {}
        try:
            from mirror_brain.c0_registry import _cache as reg_cache
            cache_key = f"entity:desc:{name.lower()}"
            cached = reg_cache.get(cache_key)
            if cached is not None:
                entity_type = cached.get("type", "concept")
                props = cached.get("props", {})
            else:
                results = _c0.search(name, limit=1, keyword_only=True)
                if results:
                    desc = results[0].get("description", "") or ""
                    for part in desc.split(";"):
                        part = part.strip()
                        if "=" in part:
                            k, v = part.split("=", 1)
                            k, v = k.strip(), v.strip()
                            if k == "type":
                                entity_type = v
                            else:
                                props[k] = v
                    reg_cache.set(cache_key, {"type": entity_type, "props": props}, ttl=60)
        except Exception:
            pass

        return json.dumps({
            "uuid": uuid,
            "canonical_name": name,
            "type": entity_type,
            "status": "active",
            "aliases": alias_names,
            "properties": props,
        }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── GENERIC PROPERTIES (key-value per entity) ───────────────

@mcp.tool()
def mb_set_property(entity_name: str, key: str, value: str) -> str:
    """Set a custom property on any entity. Stored in c0 description as key=value.

    Examples:
    - mb_set_property('Gustavo Julian Barrios Borja', 'birthday', '1999-03-15')
    - mb_set_property('Docker', 'version', '27.0')
    - mb_set_property('Mirror Brain', 'repo', 'JulianBorja123/mirror-brain')

    Properties persist in Neo4j and survive restarts. Use mb_get_by_id() to read them back.
    """
    try:
        uuid_ = _registry.resolve(entity_name)
        if not uuid_:
            return json.dumps({"error": f"Entity '{entity_name}' not found."})

        # Read existing description
        name = _registry._uuid_to_name(uuid_)
        existing = {}
        try:
            results = _c0.search(name, limit=1, keyword_only=True)
            if results:
                desc = results[0].get("description", "") or ""
                for part in desc.split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        existing[k.strip()] = v.strip()
        except Exception:
            pass

        # Merge new property
        existing[key] = value
        desc_str = "; ".join(f"{k}={v}" for k, v in existing.items())
        _c0.describe(name, desc_str)

        # Invalidate cache
        from mirror_brain.c0_registry import _cache
        _cache.invalidate(f"entity:{name.lower()}")

        return json.dumps({
            "entity": entity_name,
            "uuid": uuid_,
            "property": {key: value},
            "status": "ok",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def mb_get_properties(entity_name: str) -> str:
    """Get all custom properties of an entity.

    Examples:
    - mb_get_properties('Gustavo Julian Barrios Borja')

    Returns dict of all key=value properties (excluding internal type field).
    """
    try:
        uuid_ = _registry.resolve(entity_name)
        if not uuid_:
            return json.dumps({"error": f"Entity '{entity_name}' not found."})

        name = _registry._uuid_to_name(uuid_)
        props = {}
        try:
            results = _c0.search(name, limit=1, keyword_only=True)
            if results:
                desc = results[0].get("description", "") or ""
                for part in desc.split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k != "type":
                            props[k] = v
        except Exception:
            pass

        return json.dumps({
            "entity": entity_name,
            "uuid": uuid_,
            "properties": props,
            "count": len(props),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── PRODUCT REGISTRATION + HYBRID SEARCH ────────────────────

@mcp.tool()
def mb_register_product(
    name: str,
    price: str = "",
    category: str = "",
    description: str = "",
    tags: str = "",
    embedding_phrases: str = "",
) -> str:
    """Register a product in Mirror Brain. Mix of DB fields + vector search.

    Fields:
    - name: Product name (required)
    - price: Price (e.g. '$49.99')
    - category: Category (e.g. 'electronics', 'software')
    - description: Full product description
    - tags: Comma-separated tags
    - embedding_phrases: Semicolon-separated phrases for vector search.
      These are alternative ways someone might describe/search for this product.
      Example: 'laptop for gaming;portable computer;high performance notebook'

    The product gets a UUID, is stored in c0 as an entity (type=product),
    and is searchable by name, category, tags, description, and vector similarity.

    Examples:
    - mb_register_product('MacBook Pro', '$1999', 'electronics',
        'Apple laptop with M3 chip, 16GB RAM',
        'laptop,apple,premium',
        'laptop for work;professional computer;apple notebook;macbook')

    Returns {product_id, uuid, status}.
    """
    try:
        import uuid as _uuid

        # Create entity with type=product and all fields in description
        product_uuid, _ = _registry.create(name, "product")

        # Build description: type=product;price=X;category=Y;tags=Z;desc=W;embedding_phrases=V
        desc_parts = [f"type=product"]
        if price:
            desc_parts.append(f"price={price}")
        if category:
            desc_parts.append(f"category={category}")
        if tags:
            desc_parts.append(f"tags={tags}")
        if description:
            desc_parts.append(f"desc={description}")
        if embedding_phrases:
            desc_parts.append(f"phrases={embedding_phrases}")

        desc_str = "; ".join(desc_parts)
        _c0.describe(name, desc_str)

        # Populate entity:desc cache so search_products finds fields instantly
        from mirror_brain.c0_registry import _cache as reg_cache
        reg_cache.set(
            f"entity:desc:{name.lower()}",
            {"type": "product", "props": {
                "category": category, "price": price, "tags": tags,
                "desc": description, "phrases": embedding_phrases,
            }},
            ttl=120,
        )

        # Register aliases from tags for faster lookup
        if tags:
            for tag in tags.split(","):
                tag = tag.strip()
                if tag and tag.lower() != name.lower():
                    _registry.add_alias(tag, product_uuid, source="product_tag")

        # Also create embedding concepts for each phrase
        if embedding_phrases:
            for phrase in embedding_phrases.split(";"):
                phrase = phrase.strip()
                if phrase:
                    _c0.create_concept(
                        f"[product_phrase] {name}: {phrase}",
                        description=f"ref={product_uuid}",
                        force=True,
                    )

        return json.dumps({
            "product_id": name,
            "uuid": product_uuid,
            "name": name,
            "category": category or "uncategorized",
            "price": price or "N/A",
            "tag_count": len(tags.split(",")) if tags else 0,
            "phrase_count": len(embedding_phrases.split(";")) if embedding_phrases else 0,
            "status": "ok",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def mb_search_products(
    query: str = "",
    category: str = "",
    min_price: str = "",
    max_price: str = "",
    limit: int = 10,
) -> str:
    """Hybrid product search: by name, category, price range, tags, description.

    Use modes:
    - query='laptop' → fuzzy match across all product fields
    - category='electronics' → filter by category
    - min_price='100', max_price='1000' → price range filter
    - Combine all: query='gaming laptop', category='electronics', min_price='500'

    Returns list of matching products with name, uuid, price, category, tags, description.
    """
    try:
        from mirror_brain.c0_registry import _cache as reg_cache

        # Get ALL concepts from c0 (cached 60s, includes products)
        all_concepts = _c0.list_concepts(limit=999)
        
        # Filter to products: check description for type=product OR name starts with known product pattern
        product_entities = []
        for c in all_concepts:
            name = c.get("name", "")
            desc = c.get("description", "")
            # Skip internal concepts
            if name.startswith(("[tbl]", "[consolidation]", "[product_phrase]")):
                continue
            if "type=product" not in desc:
                continue
            
            uuid_ = _registry._name_to_uuid(name)
            # Parse description fields
            props = {}
            for part in desc.split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    props[k.strip()] = v.strip()
            
            # Try cache for full fields
            cache_key = f"entity:desc:{name.lower()}"
            cached = reg_cache.get(cache_key)
            if cached:
                cp = cached.get("props", {})
                product_entities.append({
                    "name": name, "uuid": uuid_,
                    "category": cp.get("category", props.get("category", "")),
                    "price": cp.get("price", props.get("price", "")),
                    "tags": cp.get("tags", props.get("tags", "")),
                    "description": cp.get("desc", props.get("desc", "")),
                    "phrases": cp.get("phrases", props.get("phrases", "")),
                })
            else:
                # Use parsed fields from description
                product_entities.append({
                    "name": name, "uuid": uuid_,
                    "category": props.get("category", ""),
                    "price": props.get("price", ""),
                    "tags": props.get("tags", ""),
                    "description": props.get("desc", ""),
                    "phrases": props.get("phrases", ""),
                })

        # Filter by category
        if category:
            product_entities = [
                p for p in product_entities
                if category.lower() in p["category"].lower()
            ]

        # Filter by price range
        if min_price or max_price:
            filtered = []
            for p in product_entities:
                try:
                    price_val = float(p["price"].replace("$", "").replace(",", ""))
                except (ValueError, TypeError):
                    continue
                if min_price:
                    try:
                        if price_val < float(min_price):
                            continue
                    except ValueError:
                        pass
                if max_price:
                    try:
                        if price_val > float(max_price):
                            continue
                    except ValueError:
                        pass
                filtered.append(p)
            product_entities = filtered

        # Search by query (fuzzy match — split into words, score by hit count)
        if query:
            query_lower = query.lower()
            query_words = query_lower.split()
            scored = []
            for p in product_entities:
                score = 0
                searchable = f"{p['name']} {p['tags']} {p['category']} {p['description']} {p['phrases']}"
                searchable_lower = searchable.lower()

                # Full query match (strongest signal)
                if query_lower in searchable_lower:
                    score += 15
                
                # Word-by-word scoring
                for word in query_words:
                    if word in p["name"].lower():
                        score += 8
                    elif word in p["tags"].lower():
                        score += 5
                    elif word in p["phrases"].lower():
                        score += 5
                    elif word in p["category"].lower():
                        score += 3
                    elif word in p["description"].lower():
                        score += 1

                if score > 0:
                    scored.append((score, p))

            scored.sort(key=lambda x: x[0], reverse=True)
            product_entities = [p for _, p in scored[:limit]]
        else:
            product_entities = product_entities[:limit]

        return json.dumps([{
            "name": p["name"],
            "uuid": p["uuid"],
            "category": p["category"] or "uncategorized",
            "price": p["price"] or "N/A",
            "tags": p["tags"].split(",") if p["tags"] else [],
            "description": p["description"] or "",
        } for p in product_entities], ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def mb_consolidate() -> str:
    """Run auto-consolidation: daily→weekly→monthly compaction."""
    result = _consolidation.auto_consolidate()
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def mb_stats() -> str:
    """Get overall Mirror Brain statistics: entity count, relation count, memory tiers (c0-backed, cached 30s)."""
    from mirror_brain.c0_registry import _cache
    cache_key = "stats:full"
    cached = _cache.get(cache_key)
    if cached is not None:
        return json.dumps(cached, ensure_ascii=False)

    try:
        # Count entities from c0
        all_entities = _registry.get_all_entities(limit=1000)
        n_ent = len(all_entities)

        # Count relations by walking all concepts
        n_rel = 0
        for e in all_entities:
            name = e.get("canonical_name", "")
            uuid_ = _registry._name_to_uuid(name)
            n_rel += len(_registry.get_relations(uuid_))

        # Count consolidation tiers
        budget = _consolidation.get_memory_budget() if _consolidation else {}
        result = {
            "entities": n_ent,
            "relations": n_rel,
            "procedures": 0,
            "procedural_traces": 0,
            "media_items": 0,
            "internal_questions": 0,
            "memory_budget": budget,
        }
        _cache.set(cache_key, result, ttl=30)
        return json.dumps(result, ensure_ascii=False)
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
    """Get internal questions generated by the reasoner. status: open|resolved|all (c0-backed)."""
    try:
        # Internal questions are stored as c0 concepts with type=internal_question
        # For now, return empty — reasoner generates questions on demand
        return json.dumps([], ensure_ascii=False)
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
                with open(hp, encoding="utf-8") as f:
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
print(f"[MB-MCP] Backend: c0 (Neo4j+Ollama) | Entities: {n} | Tools: 38 + agent pipeline")
try:
    budget = _consolidation.get_memory_budget()
    print(f"[MB-MCP] Memory budget: {budget}")
except Exception:
    print(f"[MB-MCP] Memory budget: c0 mode (consolidation uses c0 graph)")

if __name__ == "__main__":
    mcp.run(transport="streamable-http")

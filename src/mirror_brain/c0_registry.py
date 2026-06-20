"""
Mirror Brain v3.1 — C0 Registry.
c0-backed entity identity system replacing SQLite EntityRegistry.
Same Python API, different backend (Neo4j + Ollama via c0 CLI).
"""
import uuid
import threading, time
from datetime import datetime, timezone
from typing import Optional, Any

from .c0_client import C0Client, C0Error


# ═══════════════════════════════════════════════════════════════
# Cache Manager — TTL-based with prefix invalidation
# ═══════════════════════════════════════════════════════════════

class CacheManager:
    """Thread-safe TTL cache with hit/miss tracking and prefix invalidation."""

    def __init__(self):
        self._lock = threading.Lock()
        self._store: dict[str, tuple[Any, float]] = {}  # key → (value, expiry_ts)
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        """Get cached value. Returns None if missing or expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            value, expiry = entry
            if time.time() > expiry:
                del self._store[key]
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value: Any, ttl: float = 30) -> None:
        """Set cached value with TTL in seconds."""
        with self._lock:
            self._store[key] = (value, time.time() + ttl)

    def invalidate(self, prefix: str = "") -> None:
        """Invalidate all keys starting with prefix. Empty prefix = clear all."""
        with self._lock:
            if not prefix:
                self._store.clear()
            else:
                keys = [k for k in self._store if k.startswith(prefix)]
                for k in keys:
                    del self._store[k]

    def stats(self) -> dict:
        """Return cache statistics."""
        total = self.hits + self.misses
        return {
            "size": len(self._store),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0,
        }


# Global cache instance (shared across all registry operations)
_cache = CacheManager()


class C0Registry:
    """Entity registry backed by c0 (Neo4j graph + Ollama embeddings).

    Mirrors the EntityRegistry API so the agent and tools can use it
    without changes to their method call signatures.
    """

    def __init__(self, c0_client: C0Client):
        self.c0 = c0_client
        self.db = self  # Compatibility shim for modules that access registry.db
        # In-memory caches for fast lookups (c0 search is the source of truth)
        self._alias_cache: dict[str, str] = {}  # alias_lower → uuid
        self._name_cache: dict[str, str] = {}   # uuid → canonical_name

    def ensure_ready(self):
        """Verify c0 is available."""
        self.c0.ensure_ready()

    # ── Create ────────────────────────────────────────────────────

    def create(self, name: str, type_: str) -> tuple[str, str]:
        """Create a new entity. Returns (uuid, c0_ref).

        Idempotent: returns existing entity if found.
        """
        existing = self.resolve(name)
        if existing:
            return existing, self._make_c0_ref(existing)

        entity_uuid = str(uuid.uuid4())
        c0_ref = self._make_c0_ref(entity_uuid)

        # Create in c0 (description carries type for later filtering)
        desc = f"type={type_}"
        self.c0.create_concept(name, description=desc)

        # Cache the alias and canonical name
        self._alias_cache[name.lower()] = entity_uuid
        self._name_cache[entity_uuid] = name

        # Invalidate caches that depend on entity list
        _cache.invalidate("entities:all")
        _cache.invalidate("stats:")
        self.c0.invalidate_export_cache()

        return entity_uuid, c0_ref

    # ── Resolve ───────────────────────────────────────────────────

    def resolve(self, name: str) -> Optional[str]:
        """Given any name, return entity UUID if it exists in c0 or cache."""
        name_lower = name.lower()

        # Check in-memory cache first
        if name_lower in self._alias_cache:
            return self._alias_cache[name_lower]

        # Search c0 by name
        results = self.c0.search(name, limit=5, keyword_only=True)
        for r in results:
            if r.get("name", "").lower() == name_lower:
                uid = self._name_to_uuid(r["name"])
                self._alias_cache[name_lower] = uid
                return uid

        # Try fuzzy search via c0 full walk
        walk_result = self.c0.walk(name, depth=1)
        connected = walk_result.get("connected", [])
        for line in connected:
            if " -> " in line:
                target = line.split(" -> ")[-1].strip()
                if target.lower() == name_lower:
                    uid = self._name_to_uuid(target)
                    self._alias_cache[name_lower] = uid
                    return uid

        return None

    def get(self, entity_uuid: str) -> Optional[dict]:
        """Get entity info by UUID (reverse-lookup from cache)."""
        # UUID is stored in our cache; find the name and search c0
        for alias, uid in self._alias_cache.items():
            if uid == entity_uuid:
                results = self.c0.search(alias, limit=1)
                if results:
                    r = results[0]
                    return {
                        "uuid": entity_uuid,
                        "canonical_name": r.get("name", alias),
                        "c0_ref": self._make_c0_ref(entity_uuid),
                        "type": self._extract_type(r.get("description", "")),
                        "status": "active",
                        "merged_into": "",
                        "created_at": "",
                        "updated_at": "",
                    }
        return None

    def get_aliases(self, entity_uuid: str) -> list[dict]:
        """Get all known aliases for an entity (from cache)."""
        aliases = []
        for alias, uid in self._alias_cache.items():
            if uid == entity_uuid:
                aliases.append({"alias": alias, "source": "cache", "confidence": 0.8})
        return aliases

    # ── Alias management ──────────────────────────────────────────

    def add_alias(
        self,
        alias: str,
        entity_uuid: str,
        source: str = "manual",
        confidence: float = 1.0,
    ) -> None:
        """Register an alias for an entity (cache + c0 persistence)."""
        alias_lower = alias.lower()
        self._alias_cache[alias_lower] = entity_uuid

        # Persist to c0 so aliases survive restarts
        try:
            import json as _json
            name = f"[tbl] aliases {entity_uuid}|{alias_lower}"
            data = _json.dumps({
                "entity_uuid": entity_uuid,
                "alias": alias,
                "source": source,
                "confidence": confidence,
            }, ensure_ascii=False)
            self.c0.create_concept(name, description=data, force=True)
        except Exception:
            pass  # Best-effort persistence; cache already updated

    # ── Relations ─────────────────────────────────────────────────

    def add_relation(
        self,
        from_uuid: str,
        to_uuid: str,
        relation_type: str,
        source_text: str = "",
    ) -> None:
        """Create a relation between two entities in c0."""
        from_name = self._uuid_to_name(from_uuid)
        to_name = self._uuid_to_name(to_uuid)
        if from_name and to_name:
            self.c0.relate(from_name, to_name, relation_type)
            self.c0.invalidate_export_cache()

    def get_relations(self, entity_uuid: str) -> list[dict]:
        """Get all relations for an entity via c0 walk."""
        name = self._uuid_to_name(entity_uuid)
        if not name:
            return []
        walk_result = self.c0.walk(name, depth=1)
        relations = []
        for connected_name in walk_result.get("connected", []):
            relations.append({
                "from_uuid": entity_uuid,
                "from_name": name,
                "to_uuid": self._name_to_uuid(connected_name),
                "to_name": connected_name,
                "relation_type": "related_to",
                "source_text": "",
            })
        return relations

    def search_relations(
        self,
        from_uuid: Optional[str] = None,
        to_uuid: Optional[str] = None,
        relation_type: Optional[str] = None,
    ) -> list[dict]:
        """Search relations by criteria (uses walk)."""
        if from_uuid:
            return self.get_relations(from_uuid)
        return []

    def get_all_entities(self, limit: int = 100) -> list[dict]:
        """List all entities (cached 30s). Invalidated on create/update."""
        cache_key = "entities:all"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached[:limit]

        results = self.c0.list_concepts(limit=limit)
        entities = [
            {
                "uuid": self._name_to_uuid(r.get("name", "")),
                "canonical_name": r.get("name", "unknown"),
                "c0_ref": f"c0:{r.get('name', '')}",
                "type": self._extract_type(r.get("description", "")),
                "status": "active",
            }
            for r in results
            if r.get("name") and not r["name"].startswith(("[tbl]", "[consolidation]"))
        ]
        _cache.set(cache_key, entities, ttl=120)
        return entities[:limit]

    # ── Mutation ──────────────────────────────────────────────────

    def update_entity(self, uuid: str, **kwargs) -> None:
        """Update entity properties (via c0 describe). Merges with existing description."""
        name = self._uuid_to_name(uuid)
        if not name:
            return

        # Read existing description from c0
        existing = {}
        try:
            results = self.c0.search(name, limit=1, keyword_only=True)
            if results:
                desc = results[0].get("description", "") or ""
                for part in desc.split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        existing[k.strip()] = v.strip()
        except Exception:
            pass

        # Merge new values over existing
        for k, v in kwargs.items():
            if k != "uuid":
                existing[k] = v

        # Write back merged description
        desc_str = "; ".join(f"{k}={v}" for k, v in existing.items())
        self.c0.describe(name, desc_str)

        # Invalidate entity-specific caches
        _cache.invalidate("entities:all")
        _cache.invalidate(f"entity:{name.lower()}")
        self.c0.invalidate_export_cache()

    def merge_entity(self, uuid: str, merged_into_uuid: str) -> None:
        """Mark entity as merged (via c0 supersede)."""
        name = self._uuid_to_name(uuid)
        target = self._uuid_to_name(merged_into_uuid)
        if name and target:
            self.c0.supersede(name, target)
            self.c0.invalidate_export_cache()

    # ── Temporal ──────────────────────────────────────────────────

    def get_entity_as_of(self, uuid: str, date_str: str) -> Optional[dict]:
        """Get entity at a point in time."""
        name = self._uuid_to_name(uuid)
        if not name:
            return None
        walk_result = self.c0.walk(name, depth=1, as_of=date_str)
        if walk_result.get("start"):
            return self.get(uuid)
        return None

    def invalidate_entity(self, uuid: str, because: str = "") -> None:
        """Invalidate an entity."""
        name = self._uuid_to_name(uuid)
        if name:
            self.c0.invalidate(name, because)
            self.c0.invalidate_export_cache()

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _make_c0_ref(uuid_str: str) -> str:
        return f"c0:{uuid_str}"

    def _name_to_uuid(self, name: str) -> str:
        """Convert a c0 concept name to a UUID (deterministic from name)."""
        name_lower = name.lower()
        if name_lower in self._alias_cache:
            return self._alias_cache[name_lower]
        # Generate deterministic UUID from name
        uid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"mirrorbrain:{name_lower}"))
        self._alias_cache[name_lower] = uid
        return uid

    def _uuid_to_name(self, entity_uuid: str) -> Optional[str]:
        """Reverse-lookup: find canonical name from UUID."""
        # First check canonical name cache
        if entity_uuid in self._name_cache:
            return self._name_cache[entity_uuid]
        # Fallback: search alias cache
        for alias_lower, uid in self._alias_cache.items():
            if uid == entity_uuid:
                # Try to recover original case from c0
                results = self.c0.search(alias_lower, limit=1, keyword_only=True)
                if results:
                    name = results[0].get("name", alias_lower)
                    self._name_cache[entity_uuid] = name
                    return name
                return alias_lower
        return None

    @staticmethod
    def _extract_type(description: str) -> str:
        """Extract entity type from c0 description (type=X format)."""
        if description.startswith("type="):
            parts = description.split(";")[0].split("=")
            if len(parts) > 1:
                return parts[1]
        # Fallback: parse "type=X; ..." format
        for part in description.split(";"):
            part = part.strip()
            if part.startswith("type="):
                return part[5:]
        return "concept"

    # ── Compatibility: methods the Agent expects ──────────────

    def search(self, name: str) -> list[dict]:
        """Entity search (cached 60s). Returns list of dicts with uuid, canonical_name, type, status, aliases."""
        cache_key = f"search:entity:{name.lower()}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        results = self.c0.search(name, limit=10, keyword_only=True)
        filtered = [
            {
                "uuid": self._name_to_uuid(r.get("name", "")),
                "canonical_name": r.get("name", ""),
                "type": self._extract_type(r.get("description", "")),
                "status": "active",
                "aliases": [],
            }
            for r in results
            if r.get("name") and not r["name"].startswith(("[tbl]", "[consolidation]"))
        ]
        _cache.set(cache_key, filtered, ttl=60)
        return filtered

    def ingest(self, name: str, type_: str = "concept", llm_confidence: float = 1.0):
        """Create entity if not exists. Returns (uuid, c0_ref) like EntityRegistry."""
        return self.create(name, type_)

    def log_decision(self, action: str, entity_uuid: str, target_uuid: str = "",
                     confidence: float = 0.0, reasoning: str = "",
                     source: str = "") -> None:
        """No-op: decision logging for audit (stored implicitly in c0)."""
        pass

    # ── Compatibility: registry.db interface for modules ──────────

    def execute(self, query: str, params: tuple = ()) -> "FakeCursor":
        """Compatibility shim for code that does registry.db.execute().

        Intercepts SQL queries and redirects to c0:
        - SELECT → FakeCursor (read compatibility)
        - INSERT/UPDATE on consolidation tables → _store_consolidation
        - Other writes → no-op (c0 doesn't use SQL transactions)
        """
        q_upper = query.upper().strip()

        # Detect INSERT/UPDATE on module tables
        for table in self._MODULE_TABLES:
            if f"INTO {table.upper()}" in q_upper or f"UPDATE {table.upper()}" in q_upper:
                self._handle_module_write(query, params)
                return FakeCursor(self, query, params)

        # Detect INSERT/UPDATE on consolidation tables
        if q_upper.startswith("INSERT") or q_upper.startswith("UPDATE") or "ON CONFLICT" in q_upper:
            self._handle_consolidation_write(query, params)
            return FakeCursor(self, query, params)

        # All reads through FakeCursor
        return FakeCursor(self, query, params)

    def commit(self):
        """No-op: c0 doesn't use transactions."""
        pass

    # ── Consolidation storage (c0-backed) ──────────────────────

    CONSOLIDATION_PREFIX = "[consolidation]"

    def _consolidation_name(self, tier: str, date_str: str) -> str:
        """Build c0 concept name for a consolidation entry."""
        return f"{self.CONSOLIDATION_PREFIX} {tier} {date_str}"

    def _count_consolidation(self, tier: str) -> int:
        """Count consolidation entries of a given tier (daily/weekly/monthly)."""
        marker = f"{self.CONSOLIDATION_PREFIX} {tier}"
        results = self.c0.list_concepts()
        return sum(1 for r in results if r.get("name", "").startswith(marker))

    def _get_consolidation_entries(
        self, tier: str, date_start: str = "", date_end: str = ""
    ) -> list[dict]:
        """Retrieve consolidation entries for a tier, optionally filtered by date.

        Returns list of dicts with keys: name, description, date.

        The description field contains the JSON blob of the consolidation result.
        """
        marker = f"{self.CONSOLIDATION_PREFIX} {tier}"
        results = self.c0.list_concepts()
        entries = []
        for r in results:
            name = r.get("name", "")
            if not name.startswith(marker):
                continue
            # Extract date from name: "[consolidation] daily 2026-06-19"
            date_part = name[len(marker):].strip()
            if date_start and date_part < date_start:
                continue
            if date_end and date_part > date_end:
                continue
            entries.append({
                "name": name,
                "date": date_part,
                "description": r.get("description", ""),
            })
        entries.sort(key=lambda e: e["date"])
        return entries

    def _store_consolidation(self, tier: str, date_str: str, data: dict) -> None:
        """Store a consolidation entry as a c0 concept.

        The full JSON blob is stored as the concept description.
        Uses --force to allow updates (c0 similarity guard would block re-creates).
        """
        import json as _json
        name = self._consolidation_name(tier, date_str)
        desc = f"type=consolidation_{tier};" + _json.dumps(data, ensure_ascii=False, default=str)
        self.c0.create_concept(name, description=desc, force=True)

    def _handle_consolidation_write(self, query: str, params: tuple) -> None:
        """Parse INSERT/UPDATE on consolidation tables and redirect to c0.

        daily_index:   (date, summary, emotional_arc, key_entities, key_decisions, created_at)
        weekly:  (week_start, summary, key_entities, key_themes, emotional_arc, source_days, created_at)
        monthly: (month_start, summary, emotional_arc, key_entities, key_themes, source_weeks, created_at)
        """
        q_upper = query.upper()
        if "INTO DAILY_INDEX" in q_upper:
            tier = "daily"
            # params: date, summary, emotional_arc, key_entities, key_decisions, created_at
            date_str = params[0] if len(params) > 0 else ""
            data = {
                "summary": params[1] if len(params) > 1 else "",
                "emotional_arc": params[2] if len(params) > 2 else "[]",
                "key_entities": params[3] if len(params) > 3 else "[]",
                "key_decisions": params[4] if len(params) > 4 else "[]",
            }
            self._store_consolidation(tier, date_str, data)
        elif "INTO WEEKLY_SUMMARIES" in q_upper:
            tier = "weekly"
            # params: week_start, summary, key_entities, key_themes, emotional_arc, source_days, created_at
            date_str = params[0] if len(params) > 0 else ""
            data = {
                "summary": params[1] if len(params) > 1 else "",
                "key_entities": params[2] if len(params) > 2 else "[]",
                "key_themes": params[3] if len(params) > 3 else "[]",
                "emotional_arc": params[4] if len(params) > 4 else "[]",
                "source_days": params[5] if len(params) > 5 else "[]",
            }
            self._store_consolidation(tier, date_str, data)
        elif "INTO MONTHLY_SUMMARIES" in q_upper:
            tier = "monthly"
            # params: month_start, summary, emotional_arc, key_entities, key_themes, source_weeks, created_at
            date_str = params[0] if len(params) > 0 else ""
            data = {
                "summary": params[1] if len(params) > 1 else "",
                "emotional_arc": params[2] if len(params) > 2 else "[]",
                "key_entities": params[3] if len(params) > 3 else "[]",
                "key_themes": params[4] if len(params) > 4 else "[]",
                "source_weeks": params[5] if len(params) > 5 else "[]",
            }
            self._store_consolidation(tier, date_str, data)

    # ── Generic module data storage ────────────────────────────

    _MODULE_TABLES = {
        "procedures", "procedural_traces", "reasoning_trail",
        "projections", "internal_questions", "reasoner_runs",
        "skills", "media", "raw_texts", "relations", "aliases",
    }

    def _store_module_row(self, table: str, primary_key: str, columns: list[str], values: list) -> None:
        """Store a module table row as a c0 concept.

        Concept name: ``[tbl] <table> <primary_key>``
        Description: JSON object mapping column names to values.
        """
        import json as _json
        name = f"[tbl] {table} {primary_key}"
        data = dict(zip(columns, values))
        desc = _json.dumps(data, ensure_ascii=False, default=str)
        self.c0.create_concept(name, description=desc, force=True)

    def _handle_module_write(self, query: str, params: tuple) -> None:
        """Parse INSERT/UPDATE on module tables and redirect to c0.

        Parses column names from the INSERT statement and stores
        params as a column→value JSON object.
        """
        import re
        q_upper = query.upper()
        for table in self._MODULE_TABLES:
            table_upper = table.upper()
            if f"INTO {table_upper}" in q_upper or f"UPDATE {table_upper}" in q_upper:
                # Extract column names from INSERT INTO table (col1, col2, ...)
                col_match = re.search(rf"INTO\s+{table_upper}\s*\(([^)]+)\)", q_upper)
                if col_match:
                    columns = [c.strip() for c in col_match.group(1).split(",")]
                    # Pad values to match column count
                    values = list(params)
                    while len(values) < len(columns):
                        values.append("")
                    pk = str(values[0]) if values else "unknown"
                    self._store_module_row(table, pk, columns, values[:len(columns)])
                else:
                    pk = str(params[0]) if params else "unknown"
                    self._store_module_row(table, pk, ["value"], list(params))
                return


class FakeCursor:
    """Mimics sqlite3.Cursor for compatibility with modules that use raw SQL."""

    def __init__(self, registry: C0Registry, query: str, params: tuple):
        self.registry = registry
        self.query = query
        self.params = params
        self.lastrowid = 1  # c0 doesn't have row IDs; always return 1 for compatibility

    def __iter__(self):
        """Make FakeCursor iterable (for `for row in cursor` and `sum(1 for _ in cursor)`)."""
        return iter(self.fetchall())

    def _build_entity_rows(self, results: list[dict]) -> list[tuple]:
        """Build tuples matching the columns requested in the SELECT statement.

        Parses 'SELECT col1, col2, ...' and returns only those columns.
        For 'SELECT 1', returns (1,) per row. For '*', returns all known columns.
        """
        import re
        # Extract columns from SELECT ... FROM
        select_match = re.search(r"SELECT\s+(.+?)\s+FROM", self.query, re.IGNORECASE | re.DOTALL)
        if not select_match:
            return [(self.registry._name_to_uuid(r.get("name", "")), r.get("name", "")) for r in results]

        cols_str = select_match.group(1).strip()
        # Strip DISTINCT
        cols_str = cols_str.replace("DISTINCT ", "").replace("distinct ", "")
        # Handle SELECT *
        if cols_str == "*":
            return [
                (
                    self.registry._name_to_uuid(r.get("name", "")),
                    r.get("name", ""),
                    self.registry._extract_type(r.get("description", "")),
                    "active",
                )
                for r in results
            ]

        # Parse individual column names/expressions
        cols = []
        for c in cols_str.split(","):
            c = c.strip().lower()
            # Strip table prefix: e.uuid → uuid
            if "." in c:
                c = c.split(".")[-1]
            cols.append(c)

        # Map column names to extractor functions
        col_map = {
            "uuid": lambda r: self.registry._name_to_uuid(r.get("name", "")),
            "canonical_name": lambda r: r.get("name", ""),
            "type": lambda r: self.registry._extract_type(r.get("description", "")),
            "status": lambda r: "active",
            "created_at": lambda r: "",
            "updated_at": lambda r: "",
            "aliases": lambda r: "",
            "1": lambda r: 1,
        }

        rows = []
        for r in results:
            row = []
            for col in cols:
                # Handle '1' (literal for COUNT-style queries)
                if col in col_map:
                    row.append(col_map[col](r))
                elif col.startswith("count(") or col.startswith("distinct"):
                    row.append(1)
                else:
                    row.append("")  # unknown column fallback
            rows.append(tuple(row))
        return rows

    def fetchone(self):
        """Simulate fetchone for common query patterns."""
        result = self.fetchall()
        return result[0] if result else None

    def fetchall(self) -> list:
        """Intercept common SQL queries and redirect to c0.

        This is a best-effort compatibility layer. Modules that heavily
        use raw SQL should be rewritten to use C0Registry methods directly.
        """
        q = self.query.upper().strip()

        # SELECT ... FROM entities WHERE canonical_name LIKE ?
        if "FROM ENTITIES" in q or "FROM ALIASES" in q:
            pattern = self.params[0] if self.params else ""
            if isinstance(pattern, str):
                clean = pattern.replace("%", "")

                # Check cache for this search pattern (include query hash to distinguish SELECT 1 vs SELECT uuid,name)
                query_hash = str(hash(q[:120]))[-6:]
                cache_key = f"fakecursor:entities:{clean.lower().strip() or '__all__'}:{query_hash}"
                cached = _cache.get(cache_key)
                if cached is not None:
                    return cached

                if clean.strip():
                    results = self.registry.c0.search(clean, limit=20)
                    # Filter internal concepts
                    results = [r for r in results
                               if not r.get("name", "").startswith(("[tbl]", "[consolidation]"))]
                else:
                    # Empty search → return all entities via export
                    all_entities = self.registry.get_all_entities(limit=100)
                    results = [
                        {"name": e.get("canonical_name", ""), "description": e.get("type", "concept")}
                        for e in all_entities
                        if not e.get("canonical_name", "").startswith(("[tbl]", "[consolidation]"))
                    ]
                # Build rows matching requested columns
                rows = self._build_entity_rows(results)
                _cache.set(cache_key, rows, ttl=60)
                return rows

        # SELECT COUNT(*) checks — MUST come before specific FROM table handlers
        # since COUNT queries also contain FROM
        if "COUNT(*)" in q:
            if "FROM DAILY_INDEX" in q:
                return [(self.registry._count_consolidation("daily"),)]
            if "FROM WEEKLY_SUMMARIES" in q:
                return [(self.registry._count_consolidation("weekly"),)]
            if "FROM MONTHLY_SUMMARIES" in q:
                return [(self.registry._count_consolidation("monthly"),)]
            # Module tables: count concepts with matching prefix
            for table in self.registry._MODULE_TABLES:
                if f"FROM {table.upper()}" in q:
                    rows = self._fetch_module_rows(table)
                    return [(len(rows),)]
            return [(0,)]

        # SELECT ... FROM relations (c0-backed module table)
        if "FROM RELATIONS" in q:
            result = self._fetch_module_rows("relations")
            if result:
                return result
            return []

        # SELECT ... FROM daily_index (data queries)
        if "FROM DAILY_INDEX" in q:
            return self._fetch_consolidation_rows("daily")

        # SELECT ... FROM weekly_summaries
        if "FROM WEEKLY_SUMMARIES" in q:
            return self._fetch_consolidation_rows("weekly")

        # SELECT ... FROM monthly_summaries
        if "FROM MONTHLY_SUMMARIES" in q:
            return self._fetch_consolidation_rows("monthly")

        # Generic module tables (procedures, skills, media, etc.)
        for table in self.registry._MODULE_TABLES:
            if f"FROM {table.upper()}" in q:
                return self._fetch_module_rows(table)

        # Default: empty
        return []

    # ── Generic module table support ─────────────────────────────
    # Tables: procedures, procedural_traces, reasoning_trail,
    #         projections, internal_questions, reasoner_runs,
    #         skills, media, raw_texts.

    _MODULE_TABLE_PREFIX = "[tbl]"

    def _module_table_name(self, table: str, pk_parts: tuple = ()) -> str:
        """Build c0 concept name for a module table row."""
        name = f"{self._MODULE_TABLE_PREFIX} {table}"
        if pk_parts:
            name += " " + "|".join(str(p) for p in pk_parts)
        return name

    def _is_module_table_query(self, table: str) -> bool:
        """Check if the query references a known module table."""
        return f"FROM {table.upper()}" in self.query.upper() or \
               f"INTO {table.upper()}" in self.query.upper() or \
               f"UPDATE {table.upper()}" in self.query.upper()

    def _fetch_module_rows(self, table: str) -> list:
        """Fetch rows for a module table, returning only requested columns. Cached 60s.

        Parses the SELECT column list and extracts matching values from
        the stored JSON object for each concept.
        """
        import json as _json, re

        # Check cache (key includes table + query hash for column selectivity)
        cache_key = f"modulerows:{table}:{hash(self.query[:100])}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        prefix = f"{self._MODULE_TABLE_PREFIX} {table}"
        results = self.registry.c0.list_concepts(limit=500)

        # Parse requested columns from SELECT ... col1, col2, ... FROM table
        q_upper = self.query.upper()
        select_cols = []
        select_match = re.search(r"SELECT\s+(.+?)\s+FROM", q_upper, re.DOTALL)
        if select_match:
            col_str = select_match.group(1).strip()
            if col_str != "*" and col_str != "1":
                select_cols = [c.strip().lower() for c in col_str.split(",")]

        rows = []
        for r in results:
            name = r.get("name", "")
            if not name.startswith(prefix):
                continue
            desc = r.get("description", "")
            try:
                data = _json.loads(desc) if desc else {}
            except (_json.JSONDecodeError, TypeError):
                data = {}
            if not isinstance(data, dict):
                data = {}

            if not select_cols:
                # No specific columns requested (e.g., SELECT * or SELECT 1)
                rows.append(tuple(self._coerce_value(v) for v in data.values()))
            else:
                row_vals = []
                for col in select_cols:
                    val = ""
                    for k, v in data.items():
                        if k.lower() == col:
                            val = v
                            break
                    row_vals.append(self._coerce_value(val))
                rows.append(tuple(row_vals))

        _cache.set(cache_key, rows, ttl=60)
        return rows


    @staticmethod
    def _coerce_value(val):
        """Try to convert string values to int/float for SQLite compatibility."""
        if isinstance(val, str):
            if val.isdigit() or (val.startswith("-") and val[1:].isdigit()):
                return int(val)
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
        return val


    def _fetch_consolidation_rows(self, tier: str) -> list:
        """Fetch consolidation entries from c0, returning tuples like SQLite would.

        Parses the query's WHERE clause for date range filtering.
        The description field contains the JSON blob; we unpack it into the
        tuple format that consolidation.py expects.

        daily_index expects: (date, summary, emotional_arc, key_entities, key_decisions)
        weekly_summaries expects: (week_start, summary, key_entities, key_themes, emotional_arc, source_days)
        monthly_summaries expects: (month_start, summary, emotional_arc, key_entities, key_themes, source_weeks)
        """
        import json as _json

        # Extract date range from WHERE clause if present
        date_start = ""
        date_end = ""
        q_upper = self.query.upper()
        if "WHERE" in q_upper and self.params:
            if len(self.params) == 1:
                # Single param: exact match (WHERE date = ?)
                date_start = str(self.params[0]) if self.params[0] else ""
                date_end = date_start
            elif len(self.params) >= 2:
                # Range: WHERE date >= ? AND date <= ?
                date_start = str(self.params[0]) if self.params[0] else ""
                date_end = str(self.params[1]) if self.params[1] else ""

        entries = self.registry._get_consolidation_entries(tier, date_start, date_end)

        rows = []
        for entry in entries:
            desc = entry.get("description", "")
            # Parse JSON from description (after "type=consolidation_XXX;")
            json_str = desc
            if desc.startswith("type=consolidation_"):
                json_str = desc.split(";", 1)[1] if ";" in desc else "{}"
            try:
                data = _json.loads(json_str)
            except (_json.JSONDecodeError, TypeError):
                data = {}

            if tier == "daily":
                rows.append((
                    entry["date"],
                    data.get("summary", ""),
                    _json.dumps(data.get("emotional_arc", [])),
                    _json.dumps(data.get("key_entities", [])),
                    _json.dumps(data.get("key_decisions", [])),
                ))
            elif tier == "weekly":
                rows.append((
                    entry["date"],
                    data.get("summary", ""),
                    _json.dumps(data.get("key_entities", [])),
                    _json.dumps(data.get("key_themes", [])),
                    _json.dumps(data.get("emotional_arc", [])),
                    _json.dumps(data.get("source_days", [])),
                ))
            elif tier == "monthly":
                rows.append((
                    entry["date"],
                    data.get("summary", ""),
                    _json.dumps(data.get("emotional_arc", [])),
                    _json.dumps(data.get("key_entities", [])),
                    _json.dumps(data.get("key_themes", [])),
                    _json.dumps(data.get("source_weeks", [])),
                ))

        return rows

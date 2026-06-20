"""
Mirror Brain v3.1 — C0 Registry.
c0-backed entity identity system replacing SQLite EntityRegistry.
Same Python API, different backend (Neo4j + Ollama via c0 CLI).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from .c0_client import C0Client, C0Error


class C0Registry:
    """Entity registry backed by c0 (Neo4j graph + Ollama embeddings).

    Mirrors the EntityRegistry API so the agent and tools can use it
    without changes to their method call signatures.
    """

    def __init__(self, c0_client: C0Client):
        self.c0 = c0_client
        self.db = self  # Compatibility shim for modules that access registry.db
        # In-memory caches for fast lookups (c0 search is the source of truth)
        self._alias_cache: dict[str, str] = {}  # alias → uuid

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

        # Cache the alias
        self._alias_cache[name.lower()] = entity_uuid

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
        """Register an alias for an entity (cache only — c0 uses canonical names)."""
        self._alias_cache[alias.lower()] = entity_uuid

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

    def get_relations(self, entity_uuid: str) -> list[dict]:
        """Get all relations for an entity via c0 walk."""
        name = self._uuid_to_name(entity_uuid)
        if not name:
            return []
        walk_result = self.c0.walk(name, depth=1)
        relations = []
        for line in walk_result.get("connected", []):
            if " -> " in line:
                target = line.split(" -> ")[-1].strip()
                relations.append({
                    "from_uuid": entity_uuid,
                    "to_uuid": self._name_to_uuid(target),
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
        """List all entities (via c0 search . keyword-only)."""
        results = self.c0.list_concepts(limit=limit)
        return [
            {
                "uuid": self._name_to_uuid(r.get("name", "")),
                "canonical_name": r.get("name", "unknown"),
                "c0_ref": f"c0:{r.get('name', '')}",
                "type": self._extract_type(r.get("description", "")),
                "status": "active",
            }
            for r in results
            if r.get("name")
        ]

    # ── Mutation ──────────────────────────────────────────────────

    def update_entity(self, uuid: str, **kwargs) -> None:
        """Update entity properties (via c0 describe)."""
        name = self._uuid_to_name(uuid)
        if not name:
            return
        desc_parts = []
        for k, v in kwargs.items():
            if k != "uuid":
                desc_parts.append(f"{k}={v}")
        if desc_parts:
            self.c0.describe(name, "; ".join(desc_parts))

    def merge_entity(self, uuid: str, merged_into_uuid: str) -> None:
        """Mark entity as merged (via c0 supersede)."""
        name = self._uuid_to_name(uuid)
        target = self._uuid_to_name(merged_into_uuid)
        if name and target:
            self.c0.supersede(name, target)

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
        for alias, uid in self._alias_cache.items():
            if uid == entity_uuid:
                # Return the first one we cached; prefer the longest (canonical)
                return alias
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

    # ── Compatibility: registry.db interface for modules ──────────

    def execute(self, query: str, params: tuple = ()) -> "FakeCursor":
        """Compatibility shim for code that does registry.db.execute().

        This intercepts common SQL queries and redirects them to c0.
        For queries we can't translate, returns empty results gracefully.
        """
        return FakeCursor(self, query, params)

    def commit(self):
        """No-op: c0 doesn't use transactions."""
        pass


class FakeCursor:
    """Mimics sqlite3.Cursor for compatibility with modules that use raw SQL."""

    def __init__(self, registry: C0Registry, query: str, params: tuple):
        self.registry = registry
        self.query = query
        self.params = params

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
                results = self.registry.c0.search(clean, limit=20)
                return [
                    (
                        self.registry._name_to_uuid(r.get("name", "")),
                        r.get("name", ""),
                        f"c0:{r.get('name', '')}",
                        self.registry._extract_type(r.get("description", "")),
                        "active",
                        "",
                        "",
                        "",
                    )
                    for r in results
                ]

        # SELECT ... FROM relations
        if "FROM RELATIONS" in q:
            return []

        # SELECT ... FROM daily_index
        if "FROM DAILY_INDEX" in q:
            return []

        # SELECT ... FROM weekly_summaries
        if "FROM WEEKLY_SUMMARIES" in q:
            return []

        # Default: empty
        return []

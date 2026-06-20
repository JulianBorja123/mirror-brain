"""
Mirror Brain v1.0 — Entity Registry.
SQLite-backed entity identity system with UUIDs, aliases, and reasoning trail.
"""
import uuid
import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional

from .schema import init_db
from .criteria import EntityCriteria


class EntityRegistry:
    """Central registry for entity identity — the 'source of truth' for what exists."""

    def __init__(self, db_path: str = "mirror_brain.db"):
        self.db_path = db_path
        self.db = init_db(db_path)
        self.criteria = EntityCriteria()

    # ── Create ────────────────────────────────────────────────────

    def create(self, name: str, type_: str) -> tuple[str, str]:
        """Create a new entity. Returns (uuid, c0_ref).

        Idempotent per canonical_name + type combination.
        """
        existing = self.resolve(name)
        if existing:
            return existing, self._make_c0_ref(existing)

        entity_uuid = str(uuid.uuid4())
        c0_ref = self._make_c0_ref(entity_uuid)
        now = self._now()

        self.db.execute(
            """INSERT INTO entities (uuid, canonical_name, c0_ref, type, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (entity_uuid, name, c0_ref, type_, now, now),
        )
        self.db.execute(
            """INSERT INTO aliases (alias, entity_uuid, source, confidence, created_at)
               VALUES (?, ?, 'canonical', 1.0, ?)""",
            (name, entity_uuid, now),
        )
        self.db.commit()
        return entity_uuid, c0_ref

    # ── Resolve ───────────────────────────────────────────────────

    def resolve(self, name: str) -> Optional[str]:
        """Given any name (canonical or alias), return the entity UUID if it exists."""
        row = self.db.execute(
            "SELECT entity_uuid FROM aliases WHERE alias = ?", (name,)
        ).fetchone()
        return row[0] if row else None

    def get(self, entity_uuid: str) -> Optional[dict]:
        """Get full entity info by UUID."""
        row = self.db.execute(
            "SELECT * FROM entities WHERE uuid = ?", (entity_uuid,)
        ).fetchone()
        if not row:
            return None
        return dict(zip(
            ["uuid", "canonical_name", "c0_ref", "type", "status", "merged_into",
             "created_at", "updated_at"], row
        ))

    def get_aliases(self, entity_uuid: str) -> list[dict]:
        """Get all known aliases for an entity."""
        rows = self.db.execute(
            "SELECT alias, source, confidence FROM aliases WHERE entity_uuid = ?",
            (entity_uuid,)
        ).fetchall()
        return [{"alias": r[0], "source": r[1], "confidence": r[2]} for r in rows]

    # ── Alias management ──────────────────────────────────────────

    def add_alias(self, name: str, entity_uuid: str, source: str = "llm",
                  confidence: float = 0.8):
        """Register a new alias for an existing entity."""
        now = self._now()
        self.db.execute(
            """INSERT OR IGNORE INTO aliases (alias, entity_uuid, source, confidence, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (name, entity_uuid, source, confidence, now),
        )
        self.db.commit()

    # ── Smart create-or-resolve ───────────────────────────────────

    def ingest(self, name: str, type_: str, mention_count: int = 1,
               llm_confidence: float = 0.0, parent_entity: Optional[str] = None
               ) -> tuple[Optional[str], str, str]:
        """Full ingestion decision for a candidate entity.

        Returns (uuid_or_None, c0_ref_or_empty, decision_reason).
        uuid is None if the entity should not be created.
        """
        # First, try to resolve existing
        existing = self.resolve(name)
        if existing:
            return existing, self._make_c0_ref(existing), "resolved_existing"

        # Apply criteria
        should_create, reason = self.criteria.should_create_entity(
            name, type_, mention_count, llm_confidence, parent_entity
        )

        if should_create:
            entity_uuid, c0_ref = self.create(name, type_)
            return entity_uuid, c0_ref, f"created: {reason}"
        else:
            return None, "", f"skipped: {reason}"

    # ── Reasoning trail ───────────────────────────────────────────

    def log_decision(self, action: str, entity_uuid: str, target_uuid: str = "",
                     confidence: float = 0.0, reasoning: str = "",
                     evidence: str = "", source: str = "llm"):
        """Record a decision in the reasoning trail for future correction and learning."""
        now = self._now()
        self.db.execute(
            """INSERT INTO reasoning_trail
               (timestamp, action, entity_uuid, target_uuid, confidence,
                reasoning, evidence, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, action, entity_uuid, target_uuid, confidence, reasoning, evidence, source),
        )
        self.db.commit()

    def revert_decision(self, trail_id: int):
        """Mark a decision as reverted (soft undo)."""
        self.db.execute(
            "UPDATE reasoning_trail SET reverted = 1 WHERE id = ?", (trail_id,)
        )
        self.db.commit()

    # ── Search ────────────────────────────────────────────────────

    def search(self, query: str) -> list[dict]:
        """Fuzzy-ish search across canonical names and aliases (LIKE)."""
        like = f"%{query}%"
        rows = self.db.execute(
            """SELECT DISTINCT e.uuid, e.canonical_name, e.type
               FROM entities e
               LEFT JOIN aliases a ON e.uuid = a.entity_uuid
               WHERE e.canonical_name LIKE ?
                  OR a.alias LIKE ?
               LIMIT 20""",
            (like, like),
        ).fetchall()
        return [{"uuid": r[0], "canonical_name": r[1], "type": r[2]} for r in rows]

    def list_by_type(self, type_: str) -> list[dict]:
        """List all active entities of a given type."""
        rows = self.db.execute(
            "SELECT uuid, canonical_name FROM entities WHERE type = ? AND status = 'active'",
            (type_,),
        ).fetchall()
        return [{"uuid": r[0], "canonical_name": r[1]} for r in rows]

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _make_c0_ref(uuid_str: str) -> str:
        return f"ent_{uuid_str[:8]}"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

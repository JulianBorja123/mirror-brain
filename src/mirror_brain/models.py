"""
Mirror Brain v1.0 — Data models (dataclasses).
Lightweight type-safe representations of Mirror Brain concepts.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


@dataclass
class Entity:
    uuid: str
    canonical_name: str
    c0_ref: str
    type: str  # person, project, tool, place, concept
    status: str = "active"
    merged_into: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "uuid": self.uuid,
            "canonical_name": self.canonical_name,
            "c0_ref": self.c0_ref,
            "type": self.type,
            "status": self.status,
            "merged_into": self.merged_into,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Alias:
    alias: str
    entity_uuid: str
    source: str = "llm"  # llm, manual, fuzzy, canonical
    confidence: float = 0.8
    created_at: str = ""


@dataclass
class DailySummary:
    date: str
    summary: str = ""
    emotional_arc: list[float] = field(default_factory=list)
    key_entities: list[str] = field(default_factory=list)
    key_decisions: list[str] = field(default_factory=list)
    embedding: list[float] = field(default_factory=list)
    created_at: str = ""


@dataclass
class ReasoningRecord:
    id: Optional[int] = None
    timestamp: str = ""
    action: str = ""  # merge_alias, create_entity, create_relation
    entity_uuid: str = ""
    target_uuid: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    evidence: str = ""
    source: str = "llm"
    reversible: bool = True
    reverted: bool = False


@dataclass
class Relation:
    id: Optional[int] = None
    from_uuid: str = ""
    to_uuid: str = ""
    relation_type: str = ""
    source_text: str = ""
    created_at: str = ""


@dataclass
class Note:
    """A-MEM style memory note."""
    content: str
    timestamp: str = ""
    keywords: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    context: str = ""
    embedding: list[float] = field(default_factory=list)
    emotional_load: dict[str, float] = field(default_factory=dict)
    temporal_hints: list[str] = field(default_factory=list)
    entities_mentioned: list[str] = field(default_factory=list)
    search_hints: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

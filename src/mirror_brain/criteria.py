"""Mirror Brain v1.0 — Entity creation criteria module.

Rules for when to create UUID-backed entities.
"""

from typing import Optional


class EntityCriteria:
    """Criteria rules governing when an entity should be persisted."""

    ALWAYS_ENTITY_TYPES: set[str] = {
        "person",
        "project",
        "tool",
        "place",
        "organization",
    }
    NEVER_ENTITY: set[str] = {
        "emotion",
        "event",
        "attribute",
        "quantity",
        "date",
        "action",
    }

    @staticmethod
    def should_create_entity(
        name: str,
        type_: str,
        mention_count: int,
        llm_confidence: float = 0.0,
        parent_entity: Optional[str] = None,
    ) -> tuple[bool, str]:
        """Determine whether an entity should be created.

        Rules (evaluated in order):
            1. If a parent_entity is provided → no new entity (sub-entity).
            2. If type_ is in NEVER_ENTITY → no entity.
            3. If type_ is in ALWAYS_ENTITY_TYPES → entity on first mention.
            4. If mention_count >= 2 → entity.
            5. If llm_confidence > 0.85 → entity.
            6. Otherwise → no entity.

        Returns:
            A (should_create, reason) tuple.
        """
        if parent_entity is not None:
            return False, f"'{name}' is a sub-entity of '{parent_entity}'"

        if type_ in EntityCriteria.NEVER_ENTITY:
            return False, f"type '{type_}' is in NEVER_ENTITY"

        if type_ in EntityCriteria.ALWAYS_ENTITY_TYPES:
            return True, f"type '{type_}' is an always-entity type (mention 1)"

        if mention_count >= 2:
            return True, f"mention_count={mention_count} >= 2"

        if llm_confidence > 0.85:
            return True, f"llm_confidence={llm_confidence} > 0.85"

        return False, (
            f"no criteria met (type='{type_}', mention_count={mention_count}, "
            f"llm_confidence={llm_confidence})"
        )

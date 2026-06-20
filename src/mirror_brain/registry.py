"""
Mirror Brain v3 — Compatibility re-export.

EntityRegistry and SchemaSetup are now backed by c0.
Import from `c0_registry` for direct access.
"""
# Re-export C0Registry as EntityRegistry for backward compatibility
from .c0_registry import C0Registry as EntityRegistry

# SchemaSetup is no longer needed (c0 manages its own schema via Neo4j)
# Keep a no-op class for any code that still references it
class SchemaSetup:
    """No-op: c0 manages its own schema in Neo4j."""
    def __init__(self, *args, **kwargs):
        pass

    def init_all(self):
        pass

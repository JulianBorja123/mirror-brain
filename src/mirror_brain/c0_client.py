"""
Mirror Brain v1.0 — c0 CLI client.
Python wrapper around the c0 binary (Rust) via subprocess.
c0 must be running in Docker or accessible on PATH.
"""
import subprocess
import json
import os
from typing import Optional


class C0Client:
    """Minimal wrapper over the c0 CLI for graph operations."""

    def __init__(self, namespace: str = "mirrorbrain",
                 binary: str = "c0",
                 neo4j_uri: str = "neo4j://localhost:7687",
                 ollama_host: str = "ollama:11434",
                 ollama_model: str = "nomic-embed-text"):
        self.namespace = namespace
        self.binary = binary
        self.env = {
            **os.environ,
            "C0_NEO4J_URI": neo4j_uri,
            "C0_OLLAMA_HOST": ollama_host,
            "C0_OLLAMA_MODEL": ollama_model,
        }

    def _run(self, *args, timeout: int = 30) -> str:
        """Run c0 and return stdout, raise on failure."""
        result = subprocess.run(
            [self.binary, *args],
            capture_output=True, text=True, timeout=timeout,
            env=self.env,
        )
        if result.returncode != 0:
            raise RuntimeError(f"c0 failed (exit {result.returncode}): {result.stderr.strip()}")
        return result.stdout.strip()

    # ── CRUD ──────────────────────────────────────────────────────

    def create(self, name: str, description: str = "") -> str:
        """Create a concept node. Returns the name as confirmation."""
        cmd = ["create", name]
        if description:
            cmd.append(description)
        return self._run(*cmd)

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Hybrid search (exact → keyword → vector RRF)."""
        output = self._run("search", query, "--limit", str(limit))
        return self._parse_list(output)

    def walk(self, name: str, depth: int = 2) -> list[dict]:
        """Graph traversal — walk connected nodes."""
        output = self._run("walk", name, "--depth", str(depth))
        return self._parse_list(output)

    def relate(self, from_name: str, to_name: str, relation: str):
        """Create a relationship between two concepts."""
        return self._run("relate", from_name, relation, to_name)

    def supersede(self, name: str, new_description: str):
        """Version a concept — supersede old version."""
        return self._run("supersede", name, new_description)

    def get(self, name: str, as_of: Optional[str] = None) -> dict:
        """Get concept details, optionally at a point in time."""
        cmd = ["get", name]
        if as_of:
            cmd.extend(["--as-of", as_of])
        output = self._run(*cmd)
        return self._parse_dict(output)

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _parse_list(output: str) -> list[dict]:
        """Parse c0 output that looks like a JSON-like list of dicts."""
        if not output:
            return []
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            # Some c0 output is plain text lists
            lines = [l.strip() for l in output.split("\n") if l.strip()]
            return [{"raw": l} for l in lines]

    @staticmethod
    def _parse_dict(output: str) -> dict:
        """Parse c0 output into a dict."""
        if not output:
            return {}
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"raw": output}

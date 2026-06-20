"""
Mirror Brain v3.1 — c0 CLI client (hardened).
Python wrapper around the c0 binary (Rust) via subprocess.
c0 runs in Docker (mirrorbrain-c0) and is accessed via `docker exec`.
"""
import subprocess
import json
import os
import time
from typing import Optional


class C0Error(RuntimeError):
    """c0 operation failed."""


class C0NotAvailableError(C0Error):
    """c0 binary not found."""


class C0BackendError(C0Error):
    """Neo4j or Ollama unreachable."""


class C0Client:
    """Wrapper over the c0 CLI for graph + vector operations.

    c0 runs inside the ``mirrorbrain-c0`` Docker container.
    All commands are executed via ``docker exec mirrorbrain-c0 c0 ...``.
    """

    def __init__(
        self,
        namespace: str = "mirrorbrain",
        container: str = "mirrorbrain-c0",
    ):
        self.namespace = namespace
        self.container = container
        self._checked = False

    # ── Health ────────────────────────────────────────────────────

    def health(self) -> dict:
        """Check c0 health (Neo4j + Ollama + namespace)."""
        output = self._docker_exec("health")
        return self._parse_key_value(output) if output else {}

    def ensure_ready(self):
        """Verify c0 is reachable. Raises C0NotAvailableError if not."""
        if self._checked:
            return
        try:
            self.health()
            self._checked = True
        except Exception as e:
            raise C0NotAvailableError(f"c0 not available: {e}") from e

    # ── CRUD ──────────────────────────────────────────────────────

    def create_concept(
        self,
        name: str,
        description: str = "",
        source: str = "",
        valid_at: str = "",
        force: bool = True,
    ) -> str:
        """Create a concept node. Returns the canonical name on success.

        Uses: ``c0 add concept <name> [--description ...] --force``
        Force flag bypasses c0's similarity guard (we handle dedup ourselves).
        """
        args = ["add", "concept", name]
        if description:
            args.extend(["--description", description])
        if source:
            args.extend(["--source", source])
        if valid_at:
            args.extend(["--valid-at", valid_at])
        if force:
            args.append("--force")
        output = self._docker_exec(*args)
        return name

    def describe(self, name: str, description: str) -> None:
        """Add or update a concept's description.

        Uses: ``c0 describe <name> <description>``
        """
        self._docker_exec("describe", name, description)

    def relate(self, from_name: str, to_name: str, relation_type: str) -> None:
        """Create a relationship between two concepts.

        Uses: ``c0 relate <from> <relation_type> <to>``
        """
        self._docker_exec("relate", from_name, relation_type, to_name)

    def supersede(self, old_name: str, new_name: str, as_of: str = "") -> None:
        """Version a concept — supersede with new version.

        Uses: ``c0 supersede <old> --with <new> [--as-of <date>]``
        """
        args = ["supersede", old_name, "--with", new_name]
        if as_of:
            args.extend(["--as-of", as_of])
        self._docker_exec(*args)

    def invalidate(self, name: str, because: str = "") -> None:
        """Mark a concept as invalid.

        Uses: ``c0 invalidate concept <name> [--because ...]``
        """
        args = ["invalidate", "concept", name]
        if because:
            args.extend(["--because", because])
        self._docker_exec(*args)

    # ── Search ────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.3,
        keyword_only: bool = False,
        vector_only: bool = False,
    ) -> list[dict]:
        """Hybrid search (exact → keyword → vector RRF).

        Uses: ``c0 search <query> --limit <N> --threshold <T> --json``

        Returns list of dicts with keys: name, namespace, description, similarity.
        """
        args = ["search", query, "--limit", str(limit), "--threshold", str(threshold), "--json"]
        if keyword_only:
            args.append("--keyword-only")
        if vector_only:
            args.append("--vector-only")
        output = self._docker_exec(*args)
        if not output:
            return []
        try:
            results = json.loads(output)
            if isinstance(results, list):
                return results
            return []
        except json.JSONDecodeError:
            if "No concepts found" in output:
                return []
            # Fallback: treat as raw text lines
            return [{"raw": line.strip()} for line in output.split("\n") if line.strip()]

    def find(self, pattern: str) -> list[dict]:
        """Simple text search by name.

        Uses: ``c0 find <pattern>``
        """
        output = self._docker_exec("find", pattern)
        if not output:
            return []
        # c0 find returns text: "namespace: name" per line
        results = []
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            results.append({"raw": line})
        return results

    def walk(
        self,
        start: str,
        depth: int = 2,
        as_of: str = "",
        include_expired: bool = False,
    ) -> dict:
        """Graph traversal — walk from a concept through connected nodes.

        Uses: ``c0 walk <start> --depth <N> [--as-of <date>]``

        Returns dict with keys:
          - ``start``: the resolved concept name
          - ``patches``: list of text lines from "KNOWLEDGE PATCH" section
          - ``connected``: list of text lines from "CONNECTED" section
        """
        args = ["walk", start, "--depth", str(depth)]
        if as_of:
            args.extend(["--as-of", as_of])
        if include_expired:
            args.append("--include-expired")
        output = self._docker_exec(*args)
        return self._parse_walk_output(output)

    def extract_concepts(
        self,
        text: str,
        limit: int = 10,
        known_only: bool = False,
    ) -> list[dict]:
        """Extract concepts from text using LLM.

        Uses: ``c0 extract-concepts <text> --limit <N> --json``
        """
        args = ["extract-concepts", text, "--limit", str(limit), "--json"]
        if known_only:
            args.append("--known-only")
        output = self._docker_exec(*args)
        if not output:
            return []
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return [{"raw": output}]

    # ── Listing ───────────────────────────────────────────────────

    def list_concepts(self, namespace: str = "", limit: int = 100) -> list[dict]:
        """List concepts via c0 export (dumps full graph as JSON).

        Uses: ``c0 export --format json``
        c0 fulltext search requires word-level matches, so we export and filter.
        """
        output = self._docker_exec("export", "--format", "json")
        if not output:
            return []
        try:
            data = json.loads(output)
            nodes = data.get("nodes", []) if isinstance(data, dict) else []
            results = []
            for node in nodes:
                props = node.get("properties", {})
                name = props.get("name", "")
                if not name:
                    continue
                # Filter by namespace if specified
                labels = node.get("labels", [])
                if namespace and namespace not in labels:
                    continue
                results.append({
                    "name": name,
                    "namespace": next((l for l in labels if l != "Concept"), ""),
                    "description": props.get("description", ""),
                    "similarity": 1.0,
                })
            return results[:limit]
        except json.JSONDecodeError:
            return []

    # ── Internals ─────────────────────────────────────────────────

    def _docker_exec(self, *args, timeout: int = 30) -> str:
        """Run c0 inside the Docker container and return stdout."""
        cmd = ["docker", "exec", self.container, "c0"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "not found" in stderr.lower() or "No such file" in stderr:
                raise C0NotAvailableError(f"c0 binary not found: {stderr}")
            raise C0Error(f"c0 failed (exit {result.returncode}): {stderr}")
        return result.stdout.strip()

    def _run_with_retry(self, *args, max_retries: int = 3, timeout: int = 30) -> str:
        """Run c0 command with retry on transient failures."""
        last_error = None
        for attempt in range(max_retries):
            try:
                return self._docker_exec(*args, timeout=timeout)
            except (subprocess.TimeoutExpired, C0Error) as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))
        raise last_error  # type: ignore[misc]

    @staticmethod
    def _parse_walk_output(output: str) -> dict:
        """Parse c0 walk text output into structured dict."""
        result: dict = {"start": "", "patches": [], "connected": [], "hybrid_hint": ""}
        if not output:
            return result

        section = None
        for line in output.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue

            # Detect hybrid hint: (hybrid: 'query' -> 'name' [rrf: score])
            if stripped.startswith("(hybrid:") or stripped.startswith("(fulltext:"):
                result["hybrid_hint"] = stripped
                # Extract resolved concept name
                if "-> '" in stripped:
                    result["start"] = stripped.split("-> '")[1].split("'")[0]
                continue

            # Section headers
            if stripped == "KNOWLEDGE PATCH:":
                section = "patches"
                continue
            elif stripped.startswith("CONNECTED"):
                section = "connected"
                continue
            elif stripped == "---":
                continue

            # Content lines
            if section == "patches":
                result["patches"].append(stripped)
            elif section == "connected":
                result["connected"].append(stripped)

        # If no hybrid hint, start is first patch reference or unknown
        if not result["start"] and result["patches"]:
            first = result["patches"][0]
            if first.startswith("["):
                result["start"] = first.strip("[]")
        elif not result["start"]:
            result["start"] = "unknown"

        return result

    @staticmethod
    def _parse_key_value(text: str) -> dict:
        """Parse key: value or key=value lines into dict."""
        result = {}
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if ": " in line:
                k, v = line.split(": ", 1)
                result[k.strip()] = v.strip()
            elif " = " in line:
                k, v = line.split(" = ", 1)
                result[k.strip()] = v.strip()
        return result

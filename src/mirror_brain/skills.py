"""
Mirror Brain v3.1 — Skills System.
Manages markdown skills with YAML frontmatter.
Loads from skills/ directory, stores in SQLite, searches by trigger keywords.

Stdlib only — no PyYAML dependency; uses a custom frontmatter parser.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional


class SkillManager:
    """Manages markdown skills with YAML frontmatter.

    Loads skill ``.md`` files from a directory, stores them in the
    ``skills`` SQLite table, and retrieves them by name or by
    keyword-trigger matching against arbitrary text.
    """

    def __init__(self, registry):
        """Bind to an EntityRegistry for database access.

        Auto-creates the ``skills`` table on first use (idempotent
        ``CREATE TABLE IF NOT EXISTS``).

        Args:
            registry: An ``EntityRegistry`` instance whose ``.db``
                      attribute points to an open ``sqlite3.Connection``.
        """
        self.registry = registry
        self.db = registry.db
        self._ensure_skills_table()

    # ── Internal: table bootstrap ───────────────────────────────────

    def _ensure_skills_table(self):
        """Create the ``skills`` table if it does not already exist."""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                name        TEXT PRIMARY KEY,
                description TEXT NOT NULL DEFAULT '',
                triggers    TEXT NOT NULL DEFAULT '[]',
                content     TEXT NOT NULL DEFAULT '',
                version     TEXT NOT NULL DEFAULT '1.0',
                created_at  TEXT NOT NULL DEFAULT '',
                updated_at  TEXT NOT NULL DEFAULT ''
            )
        """)
        self.db.commit()

    # ── 1. load_skills ──────────────────────────────────────────────

    def load_skills(self, skills_dir: str) -> list[dict]:
        """Scan a directory for ``.md`` skill files and upsert them into
        the ``skills`` table.

        Each ``.md`` file must contain YAML frontmatter delimited by
        ``---`` lines.  Required frontmatter keys: ``name``.  Optional
        keys: ``description``, ``triggers`` (a YAML list), ``version``.

        Existing skills with the same ``name`` are updated in-place
        (description, triggers, content, version, updated_at are
        overwritten; created_at is preserved).

        Args:
            skills_dir: Path to a directory containing ``*.md`` skill
                        files.

        Returns:
            List of skill dicts that were successfully loaded, each
            with keys ``name``, ``description``, ``triggers`` (list of
            str), ``content``, ``version``, ``created_at``,
            ``updated_at``.
        """
        loaded: list[dict] = []

        # Collect .md files sorted by name for deterministic order
        try:
            entries = sorted(os.listdir(skills_dir))
        except FileNotFoundError:
            return loaded
        except NotADirectoryError:
            return loaded

        for entry in entries:
            if not entry.lower().endswith(".md"):
                continue

            filepath = os.path.join(skills_dir, entry)
            parsed = _parse_skill_file(filepath)
            if parsed is None:
                continue

            name = parsed["name"]
            description = parsed.get("description", "")
            triggers_json = json.dumps(parsed.get("triggers", []))
            content = parsed.get("content", "")
            version = parsed.get("version", "1.0")
            now = datetime.now(timezone.utc).isoformat()

            # Upsert: insert or update
            try:
                existing = self.db.execute(
                    "SELECT created_at FROM skills WHERE name = ?", (name,)
                ).fetchone()

                if existing:
                    created_at = existing[0]
                    self.db.execute(
                        "UPDATE skills SET description = ?, triggers = ?, "
                        "content = ?, version = ?, updated_at = ? "
                        "WHERE name = ?",
                        (description, triggers_json, content, version, now, name),
                    )
                else:
                    created_at = now
                    self.db.execute(
                        "INSERT INTO skills (name, description, triggers, "
                        "content, version, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (name, description, triggers_json, content, version,
                         now, now),
                    )

                self.db.commit()

                loaded.append({
                    "name": name,
                    "description": description,
                    "triggers": parsed.get("triggers", []),
                    "content": content,
                    "version": version,
                    "created_at": created_at,
                    "updated_at": now,
                })
            except Exception:
                # Skip malformed entries that fail at the DB layer
                continue

        return loaded

    # ── 2. find_relevant ────────────────────────────────────────────

    def find_relevant(self, text: str, limit: int = 5) -> list[dict]:
        """Return skills whose trigger keywords appear in *text*.

        Tokenises *text* into lowercase words, then scores each skill
        by how many of its trigger keywords appear in the token set.
        Results are ranked by score descending, then by name for
        determinism.

        Args:
            text: Natural-language input to match against trigger
                  keywords.
            limit: Maximum number of skills to return.

        Returns:
            List of skill dicts sorted by relevance, each with keys
            ``name``, ``description``, ``triggers`` (list of str),
            ``score`` (int), ``content``, ``version``,
            ``created_at``, ``updated_at``.
        """
        try:
            rows = self.db.execute(
                "SELECT name, description, triggers, content, version, "
                "created_at, updated_at FROM skills"
            ).fetchall()
        except Exception:
            return []

        if not rows or not text:
            return []

        # Tokenise input text into a set of lowercase words
        tokens = set(_simple_tokenise(text.lower()))

        scored: list[dict] = []

        for name, desc, triggers_json, content, ver, ca, ua in rows:
            # Decode trigger keywords
            try:
                triggers = json.loads(triggers_json) if triggers_json else []
            except (json.JSONDecodeError, TypeError):
                triggers = []

            if not triggers:
                continue  # no triggers means never matched

            # Score = count of trigger keywords present in the text tokens
            score = sum(1 for t in triggers
                        if _simple_tokenise(t.lower()).issubset(tokens)
                        or t.lower() in tokens)

            if score == 0:
                continue

            scored.append({
                "name": name,
                "description": desc,
                "triggers": triggers,
                "score": score,
                "content": content,
                "version": ver,
                "created_at": ca,
                "updated_at": ua,
            })

        # Rank by score descending, then name ascending for determinism
        scored.sort(key=lambda r: (-r["score"], r["name"]))
        return scored[:limit]

    # ── 3. get_skill ────────────────────────────────────────────────

    def get_skill(self, name: str) -> Optional[dict]:
        """Look up a single skill by exact name.

        Args:
            name: The skill name to retrieve (case-sensitive).

        Returns:
            Dict with ``name``, ``description``, ``triggers`` (list of
            str), ``content``, ``version``, ``created_at``,
            ``updated_at``, or ``None`` if no skill with that name
            exists.
        """
        try:
            row = self.db.execute(
                "SELECT name, description, triggers, content, version, "
                "created_at, updated_at FROM skills WHERE name = ?",
                (name,),
            ).fetchone()
        except Exception:
            return None

        if not row:
            return None

        n, desc, triggers_json, content, ver, ca, ua = row
        try:
            triggers = json.loads(triggers_json) if triggers_json else []
        except (json.JSONDecodeError, TypeError):
            triggers = []

        return {
            "name": n,
            "description": desc,
            "triggers": triggers,
            "content": content,
            "version": ver,
            "created_at": ca,
            "updated_at": ua,
        }

    # ── 4. create_skill ─────────────────────────────────────────────

    def create_skill(
        self,
        name: str,
        description: str,
        triggers: list[str],
        content: str,
        skills_dir: str,
    ) -> dict:
        """Create a new skill ``.md`` file and register it in the DB.

        The file is written to *skills_dir* with the pattern
        ``<name>.md``.  If a file with that name already exists it is
        **overwritten**.  The skill is then loaded into the ``skills``
        table via ``load_skills``.

        Args:
            name: Unique skill name (also used as the filename stem).
            description: Short description of what the skill does.
            triggers: List of keywords that trigger this skill.
            content: Markdown body (instructions / procedure).
            skills_dir: Directory to write the ``.md`` file into.

        Returns:
            Dict with ``name``, ``status`` (``"created"`` or
            ``"error"``), and the skill dict on success, or ``error``
            on failure.
        """
        # Build the .md file content with YAML frontmatter
        triggers_str = "[" + ", ".join(triggers) + "]"
        lines = [
            "---",
            f"name: {name}",
            f"description: {description}",
            f"triggers: {triggers_str}",
            "version: 1.0",
            "---",
            "",
            content,
        ]
        md_content = "\n".join(lines) + "\n"

        # Ensure the directory exists
        try:
            os.makedirs(skills_dir, exist_ok=True)
        except OSError as e:
            return {"name": name, "status": "error",
                    "error": f"cannot create directory: {e}"}

        filepath = os.path.join(skills_dir, f"{name}.md")

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)
        except OSError as e:
            return {"name": name, "status": "error",
                    "error": f"cannot write file: {e}"}

        # Load the newly created file into the DB
        parsed = _parse_skill_file(filepath)
        if parsed is None:
            return {"name": name, "status": "error",
                    "error": "file written but failed to parse"}

        # Upsert into DB directly (mirrors load_skills logic)
        now = datetime.now(timezone.utc).isoformat()
        triggers_json = json.dumps(parsed.get("triggers", []))

        try:
            existing = self.db.execute(
                "SELECT created_at FROM skills WHERE name = ?", (parsed["name"],)
            ).fetchone()

            if existing:
                created_at = existing[0]
                self.db.execute(
                    "UPDATE skills SET description = ?, triggers = ?, "
                    "content = ?, version = ?, updated_at = ? WHERE name = ?",
                    (parsed.get("description", ""), triggers_json,
                     parsed.get("content", ""), parsed.get("version", "1.0"),
                     now, parsed["name"]),
                )
            else:
                created_at = now
                self.db.execute(
                    "INSERT INTO skills (name, description, triggers, "
                    "content, version, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (parsed["name"], parsed.get("description", ""),
                     triggers_json, parsed.get("content", ""),
                     parsed.get("version", "1.0"), now, now),
                )
            self.db.commit()
        except Exception as e:
            return {"name": name, "status": "error",
                    "error": f"db write failed: {e}"}

        skill_dict = {
            "name": parsed["name"],
            "description": parsed.get("description", ""),
            "triggers": parsed.get("triggers", []),
            "content": parsed.get("content", ""),
            "version": parsed.get("version", "1.0"),
            "created_at": created_at,
            "updated_at": now,
        }
        return {"name": name, "status": "created", "skill": skill_dict}

    # ── 5. list_skills ──────────────────────────────────────────────

    def list_skills(self) -> list[dict]:
        """Return every skill currently stored in the ``skills`` table.

        Results are sorted alphabetically by name.

        Returns:
            List of skill dicts with ``name``, ``description``,
            ``triggers`` (list of str), ``content``, ``version``,
            ``created_at``, ``updated_at``.
        """
        try:
            rows = self.db.execute(
                "SELECT name, description, triggers, content, version, "
                "created_at, updated_at FROM skills ORDER BY name"
            ).fetchall()
        except Exception:
            return []

        results: list[dict] = []
        for name, desc, triggers_json, content, ver, ca, ua in rows:
            try:
                triggers = json.loads(triggers_json) if triggers_json else []
            except (json.JSONDecodeError, TypeError):
                triggers = []

            results.append({
                "name": name,
                "description": desc,
                "triggers": triggers,
                "content": content,
                "version": ver,
                "created_at": ca,
                "updated_at": ua,
            })

        return results


# ── Module-level helpers ────────────────────────────────────────────


def _parse_skill_file(filepath: str) -> Optional[dict]:
    """Parse a single ``.md`` skill file.

    Extracts YAML frontmatter (delimited by ``---`` lines) and the
    markdown body.  Returns a dict with keys ``name``, ``description``,
    ``triggers`` (list of str), ``content``, ``version`` — or ``None``
    if the file cannot be read, has no valid frontmatter, or is
    missing a ``name``.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return None

    front, body = _parse_frontmatter(text)
    if not front:
        return None

    name = front.get("name", "").strip()
    if not name:
        return None

    triggers_raw = front.get("triggers", "[]")
    triggers = _parse_triggers(triggers_raw)

    return {
        "name": name,
        "description": front.get("description", "").strip(),
        "triggers": triggers,
        "content": body.strip(),
        "version": front.get("version", "1.0").strip(),
    }


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from markdown text.

    Frontmatter is delimited by ``---`` on its own line at the start
    of the file, with a closing ``---`` before the body.

    Args:
        text: Full markdown file contents.

    Returns:
        ``(frontmatter_dict, body_str)``.  If no valid frontmatter
        is found, returns ``({}, text)``.
    """
    stripped = text.lstrip("\ufeff")  # strip BOM if present

    if not stripped.startswith("---"):
        return {}, text

    # Find the closing --- after the opening delimiter
    after_open = stripped[3:]  # skip first "---"
    # The delimiter must be at the start of a line
    end_idx = _find_closing_delimiter(after_open)
    if end_idx == -1:
        return {}, text

    frontmatter_str = after_open[:end_idx].strip()
    body = after_open[end_idx + 3:].strip()

    # Parse key: value pairs, one per line
    front: dict[str, str] = {}
    for line in frontmatter_str.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Split on first colon only (values may contain colons)
        if ":" not in line:
            continue
        colon_pos = line.index(":")
        key = line[:colon_pos].strip()
        value = line[colon_pos + 1:].strip()
        if key:
            front[key] = value

    return front, body


def _find_closing_delimiter(text: str) -> int:
    """Locate the closing ``---`` delimiter at the start of a line.

    Returns the index of the newline (or start) immediately before
    the ``---``, or ``-1`` if not found.
    """
    idx = 0
    while idx < len(text):
        # Look for "---" that is at start of a line (or very beginning)
        if text.startswith("---", idx):
            if idx == 0 or text[idx - 1] == "\n":
                # Check that it's either end of string or followed by newline
                end_of_delim = idx + 3
                if end_of_delim >= len(text) or text[end_of_delim] == "\n":
                    return idx
        idx += 1
    return -1


def _parse_triggers(raw: str) -> list[str]:
    """Parse a trigger value from YAML frontmatter.

    Handles both list syntax (``[a, b, c]``) and a single bare value.

    Args:
        raw: The raw string value from the ``triggers:`` line.

    Returns:
        A list of lowercase, stripped trigger keywords.
    """
    raw = raw.strip()
    if not raw or raw == "[]":
        return []

    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        items = []
        for part in _split_comma_list(inner):
            item = part.strip().strip("'\"").strip()
            if item:
                items.append(item)
        return items

    # Single bare value
    return [raw.strip().strip("'\"")]


def _split_comma_list(text: str) -> list[str]:
    """Split a comma-separated list, respecting simple quoting.

    Does **not** handle escaped quotes — sufficient for the
    predictable trigger lists used in skill frontmatter.
    """
    parts: list[str] = []
    current: list[str] = []
    in_quote: Optional[str] = None

    for ch in text:
        if in_quote:
            if ch == in_quote:
                in_quote = None
            else:
                current.append(ch)
        elif ch in ("'", '"'):
            in_quote = ch
        elif ch == ",":
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)

    parts.append("".join(current))
    return parts


def _simple_tokenise(text: str) -> set[str]:
    """Tokenise *text* into a set of lowercase word tokens.

    Splits on whitespace and strips common punctuation from token
    boundaries.  Multi-word trigger phrases are supported because
    the caller can check if the phrase tokens are all present in
    the text token set.
    """
    tokens: set[str] = set()
    for token in text.split():
        token = token.strip(".,;:!?()[]{}<>/\\\"'`*#@|&+-=~")
        if token:
            tokens.add(token)
    return tokens

"""
Mirror Brain v3 — MultiModal ingestion module.
Handles text, audio, and image input with optional AI-powered
transcription / description callbacks.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional


class MultiModal:
    """Multimodal ingestion and retrieval for Mirror Brain v3.

    Accepts ``db`` (a sqlite3.Connection) and an optional ``agent``
    (MirrorBrainAgent instance).  When ``agent`` is provided,
    ``ingest_text`` wraps ``agent.process()`` to extract entities
    from the text alongside storing it in the media table.
    """

    def __init__(self, db, agent=None):
        self.db = db
        self.agent = agent

    # ── 1. Text ingestion ────────────────────────────────────────

    def ingest_text(self, text: str, source: str = "manual") -> dict:
        """Ingest a text string into the media table.

        If an agent was provided at construction time, the text is first
        passed through ``agent.process(text)`` so that entities, links,
        and other structures are created in the main Mirror Brain tables.
        The resulting entity UUIDs are stored in ``entities_extracted``.

        Returns a dict with ``media_uuid``, ``media_type``, and whether
        the agent was invoked.
        """
        media_uuid = str(uuid.uuid4())
        now = self._now()

        metadata = json.dumps({
            "char_count": len(text),
            "language": "",
        })

        entities_extracted = "[]"
        agent_used = False

        if self.agent is not None:
            try:
                report = self.agent.process(text)
                agent_used = True
                # Collect entity UUIDs produced by the agent
                entities = []
                for entry in report.get("auto", []):
                    if isinstance(entry, str) and entry.startswith("entity:"):
                        # Format: "entity: Name (type)"
                        name_part = entry.split("entity:", 1)[1].strip()
                        name = name_part.rsplit("(", 1)[0].strip()
                        resolved = self.agent.registry.resolve(name)
                        if resolved:
                            entities.append(resolved)
                # Also pick up aliases
                for entry in report.get("auto", []):
                    if isinstance(entry, str) and entry.startswith("alias:"):
                        # Format: "alias: alias_name → canonical_name"
                        parts = entry.split("→", 1)
                        if len(parts) == 2:
                            canonical = parts[1].strip()
                            resolved = self.agent.registry.resolve(canonical)
                            if resolved and resolved not in entities:
                                entities.append(resolved)
                entities_extracted = json.dumps(entities[:200])
            except Exception:
                # Agent processing failed; still store the raw text
                pass

        self.db.execute(
            """INSERT INTO media
               (uuid, media_type, filepath, metadata, transcription,
                description, entities_extracted, ingested_at, source)
               VALUES (?, 'text', NULL, ?, ?, NULL, ?, ?, ?)""",
            (media_uuid, metadata, text, entities_extracted, now, source),
        )
        self.db.commit()

        return {
            "media_uuid": media_uuid,
            "media_type": "text",
            "agent_used": agent_used,
            "ingested_at": now,
        }

    # ── 2. Audio ingestion ───────────────────────────────────────

    def ingest_audio(self, filepath: str,
                     transcribe_call: Optional[Callable[[str], str]] = None
                     ) -> dict:
        """Ingest an audio file into the media table.

        *filepath* must be a path to an existing audio file.
        Metadata (format, size) is extracted via ``os.path``.

        If *transcribe_call* is provided it must be a callable that
        accepts a file path and returns a transcription string.
        The transcription result is stored in the ``transcription``
        column.

        Returns a dict with ``media_uuid``, ``media_type``, and
        whether transcription ran.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Audio file not found: {filepath}")

        media_uuid = str(uuid.uuid4())
        now = self._now()

        # Extract metadata from the file system
        file_size = os.path.getsize(filepath)
        _, ext = os.path.splitext(filepath)
        audio_format = ext.lstrip(".").lower() if ext else "unknown"

        metadata = json.dumps({
            "duration_seconds": 0,       # requires external lib (e.g. mutagen, pydub)
            "format": audio_format,
            "sample_rate": 0,            # requires external lib
            "channels": 0,               # requires external lib
            "file_size_bytes": file_size,
        })

        transcription = None
        transcribed = False
        if transcribe_call is not None:
            try:
                transcription = transcribe_call(filepath)
                transcribed = True
            except Exception:
                # Transcription failed; still store the file metadata
                pass

        self.db.execute(
            """INSERT INTO media
               (uuid, media_type, filepath, metadata, transcription,
                description, entities_extracted, ingested_at, source)
               VALUES (?, 'audio', ?, ?, ?, NULL, '[]', ?, 'file')""",
            (media_uuid, filepath, metadata, transcription, now),
        )
        self.db.commit()

        return {
            "media_uuid": media_uuid,
            "media_type": "audio",
            "filepath": filepath,
            "format": audio_format,
            "file_size_bytes": file_size,
            "transcribed": transcribed,
            "ingested_at": now,
        }

    # ── 3. Image ingestion ───────────────────────────────────────

    def ingest_image(self, filepath: str,
                     describe_call: Optional[Callable[[str], str]] = None
                     ) -> dict:
        """Ingest an image file into the media table.

        *filepath* must be a path to an existing image file.
        Metadata (format, size) is extracted via ``os.path``.

        If *describe_call* is provided it must be a callable that
        accepts a file path and returns a vision description string.
        The description is stored in the ``description`` column.

        Returns a dict with ``media_uuid``, ``media_type``, and
        whether a description was generated.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Image file not found: {filepath}")

        media_uuid = str(uuid.uuid4())
        now = self._now()

        # Extract metadata from the file system
        file_size = os.path.getsize(filepath)
        _, ext = os.path.splitext(filepath)
        image_format = ext.lstrip(".").lower() if ext else "unknown"

        metadata = json.dumps({
            "width": 0,                  # requires external lib (e.g. Pillow)
            "height": 0,                 # requires external lib
            "format": image_format,
            "file_size_bytes": file_size,
        })

        description = None
        described = False
        if describe_call is not None:
            try:
                description = describe_call(filepath)
                described = True
            except Exception:
                # Description failed; still store the file metadata
                pass

        self.db.execute(
            """INSERT INTO media
               (uuid, media_type, filepath, metadata, transcription,
                description, entities_extracted, ingested_at, source)
               VALUES (?, 'image', ?, ?, NULL, ?, '[]', ?, 'file')""",
            (media_uuid, filepath, metadata, description, now),
        )
        self.db.commit()

        return {
            "media_uuid": media_uuid,
            "media_type": "image",
            "filepath": filepath,
            "format": image_format,
            "file_size_bytes": file_size,
            "described": described,
            "ingested_at": now,
        }

    # ── 4. Media context retrieval ────────────────────────────────

    def get_media_context(self, media_id: str) -> Optional[dict]:
        """Retrieve a stored media item and its associated entities.

        The ``entities_extracted`` JSON field is parsed into a Python
        list of entity UUIDs.  If those entities still exist in the
        entities table their canonical names are included.

        Returns ``None`` if no media item with *media_id* exists.
        """
        row = self.db.execute(
            """SELECT uuid, media_type, filepath, metadata, transcription,
                      description, entities_extracted, ingested_at, source
               FROM media WHERE uuid = ?""",
            (media_id,),
        ).fetchone()

        if row is None:
            return None

        media_uuid, media_type, filepath, metadata_raw, transcription, \
            description, entities_raw, ingested_at, source = row

        try:
            metadata = json.loads(metadata_raw) if metadata_raw else {}
        except (json.JSONDecodeError, TypeError):
            metadata = {}

        try:
            entities = json.loads(entities_raw) if entities_raw else []
        except (json.JSONDecodeError, TypeError):
            entities = []

        # Resolve entity UUIDs to canonical names
        entity_names = []
        for euuid in entities:
            try:
                erow = self.db.execute(
                    "SELECT canonical_name FROM entities WHERE uuid = ?",
                    (euuid,),
                ).fetchone()
                if erow:
                    entity_names.append({"uuid": euuid, "canonical_name": erow[0]})
                else:
                    entity_names.append({"uuid": euuid, "canonical_name": None})
            except Exception:
                entity_names.append({"uuid": euuid, "canonical_name": None})

        return {
            "media_uuid": media_uuid,
            "media_type": media_type,
            "filepath": filepath,
            "metadata": metadata,
            "transcription": transcription,
            "description": description,
            "entities_extracted": entity_names,
            "ingested_at": ingested_at,
            "source": source,
        }

    # ── 5. Media index ───────────────────────────────────────────

    def media_index(self, media_type: Optional[str] = None,
                    limit: int = 50) -> list[dict]:
        """List stored media items, newest first.

        If *media_type* is given (``'text'``, ``'audio'``, or
        ``'image'``), only items of that type are returned.
        """
        if media_type is not None:
            rows = self.db.execute(
                """SELECT uuid, media_type, filepath, ingested_at, source
                   FROM media
                   WHERE media_type = ?
                   ORDER BY ingested_at DESC
                   LIMIT ?""",
                (media_type, limit),
            ).fetchall()
        else:
            rows = self.db.execute(
                """SELECT uuid, media_type, filepath, ingested_at, source
                   FROM media
                   ORDER BY ingested_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

        return [
            {
                "media_uuid":   row[0],
                "media_type":   row[1],
                "filepath":     row[2],
                "ingested_at":  row[3],
                "source":       row[4],
            }
            for row in rows
        ]

    # ── 6. Search media ──────────────────────────────────────────

    def search_media(self, query: str, limit: int = 10) -> list[dict]:
        """LIKE search across transcription and description fields.

        Returns matching media items, newest first.
        Falls back gracefully to an empty list on any error.
        """
        like = f"%{query}%"
        try:
            rows = self.db.execute(
                """SELECT uuid, media_type, filepath, transcription,
                          description, ingested_at, source
                   FROM media
                   WHERE (transcription LIKE ? OR description LIKE ?)
                   ORDER BY ingested_at DESC
                   LIMIT ?""",
                (like, like, limit),
            ).fetchall()
        except Exception:
            return []

        return [
            {
                "media_uuid":    row[0],
                "media_type":    row[1],
                "filepath":      row[2],
                "transcription": row[3],
                "description":   row[4],
                "ingested_at":   row[5],
                "source":        row[6],
            }
            for row in rows
        ]

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

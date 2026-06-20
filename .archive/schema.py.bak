"""
Mirror Brain v1.0 — SQLite schema module.
Core tables for the entity system.
"""

import sqlite3


def init_db(db_path: str) -> sqlite3.Connection:
    """Create all tables in the SQLite database at db_path.

    Returns the connection so the caller can use it immediately.
    If the tables already exist, this is a no-op (IF NOT EXISTS).
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    # 1. entities — core entity registry
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            uuid            TEXT PRIMARY KEY,
            canonical_name  TEXT NOT NULL,
            c0_ref          TEXT NOT NULL,
            type            TEXT NOT NULL CHECK(type IN ('person','project','tool','place','concept')),
            status          TEXT NOT NULL DEFAULT 'active',
            merged_into     TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT '',
            updated_at      TEXT NOT NULL DEFAULT ''
        )
    """)

    # 2. aliases — alternative names for entities
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aliases (
            alias           TEXT NOT NULL UNIQUE,
            entity_uuid     TEXT NOT NULL DEFAULT '',
            source          TEXT NOT NULL DEFAULT '' CHECK(source IN ('','llm','manual','fuzzy','canonical')),
            confidence      REAL NOT NULL DEFAULT 0.0,
            created_at      TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (entity_uuid) REFERENCES entities(uuid)
        )
    """)

    # 3. daily_index — per-day journal / summary
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_index (
            date            TEXT PRIMARY KEY,
            summary         TEXT NOT NULL DEFAULT '',
            emotional_arc   TEXT NOT NULL DEFAULT '[]',
            key_entities    TEXT NOT NULL DEFAULT '[]',
            key_decisions   TEXT NOT NULL DEFAULT '[]',
            embedding       TEXT NOT NULL DEFAULT '[]',
            created_at      TEXT NOT NULL DEFAULT ''
        )
    """)

    # 4. reasoning_trail — audit log of inferences & mutations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reasoning_trail (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL DEFAULT '',
            action          TEXT NOT NULL DEFAULT '',
            entity_uuid     TEXT NOT NULL DEFAULT '',
            target_uuid     TEXT NOT NULL DEFAULT '',
            confidence      REAL NOT NULL DEFAULT 0.0,
            reasoning       TEXT NOT NULL DEFAULT '',
            evidence        TEXT NOT NULL DEFAULT '',
            source          TEXT NOT NULL DEFAULT '',
            reversible      INTEGER NOT NULL DEFAULT 1,
            reverted        INTEGER NOT NULL DEFAULT 0
        )
    """)

    # 5. relations — links between entities
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS relations (
            id              INTEGER PRIMARY KEY,
            from_uuid       TEXT NOT NULL DEFAULT '',
            to_uuid         TEXT NOT NULL DEFAULT '',
            relation_type   TEXT NOT NULL DEFAULT '',
            source_text     TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT ''
        )
    """)

    # 6. raw_texts — raw input text storage
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_texts (
            uuid            TEXT PRIMARY KEY,
            content         TEXT NOT NULL,
            char_count      INTEGER,
            source          TEXT DEFAULT '',
            created_at      TEXT
        )
    """)

    # 7. weekly_summaries — weekly aggregated summaries
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weekly_summaries (
            week_start      TEXT PRIMARY KEY,
            summary         TEXT,
            key_entities    TEXT DEFAULT '[]',
            key_themes      TEXT DEFAULT '[]',
            emotional_arc   TEXT DEFAULT '[]',
            source_days     TEXT DEFAULT '[]',
            created_at      TEXT
        )
    """)

    # 8. monthly_summaries — monthly aggregated summaries
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monthly_summaries (
            month_start     TEXT PRIMARY KEY,
            summary         TEXT NOT NULL DEFAULT '',
            emotional_arc   TEXT NOT NULL DEFAULT '[]',
            key_entities    TEXT NOT NULL DEFAULT '[]',
            key_themes      TEXT NOT NULL DEFAULT '[]',
            source_weeks    TEXT NOT NULL DEFAULT '[]',
            created_at      TEXT NOT NULL DEFAULT ''
        )
    """)

    # 9. procedures — named procedural workflows (v3)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS procedures (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT UNIQUE NOT NULL,
            steps           TEXT NOT NULL DEFAULT '[]',
            context         TEXT NOT NULL DEFAULT '',
            success_count   INTEGER NOT NULL DEFAULT 0,
            fail_count      INTEGER NOT NULL DEFAULT 0,
            last_used       TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT ''
        )
    """)

    # 10. procedural_traces — execution traces for procedures (v3)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS procedural_traces (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp         TEXT NOT NULL DEFAULT '',
            action_sequence   TEXT NOT NULL DEFAULT '[]',
            entities_involved TEXT NOT NULL DEFAULT '[]',
            outcome           TEXT NOT NULL DEFAULT ''
        )
    """)

    # 11. media — multimodal input storage (text, audio, image)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media (
            uuid                TEXT PRIMARY KEY,
            media_type          TEXT NOT NULL CHECK(media_type IN ('text','audio','image')),
            filepath            TEXT,
            metadata            TEXT DEFAULT '{}',
            transcription       TEXT,
            description         TEXT,
            entities_extracted  TEXT DEFAULT '[]',
            ingested_at         TEXT,
            source              TEXT
        )
    """)

    # 12. internal_questions — self-reflection questions from InternalReasoner
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS internal_questions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            question            TEXT NOT NULL DEFAULT '',
            context             TEXT NOT NULL DEFAULT '',
            entities_involved   TEXT NOT NULL DEFAULT '[]',
            status              TEXT NOT NULL DEFAULT 'open',
            created_at          TEXT NOT NULL DEFAULT '',
            resolved_at         TEXT NOT NULL DEFAULT '',
            resolution          TEXT NOT NULL DEFAULT ''
        )
    """)

    # 13. reasoner_runs — meta-summary of each InternalReasoner run
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reasoner_runs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at              TEXT NOT NULL DEFAULT '',
            phases_completed    TEXT NOT NULL DEFAULT '[]',
            questions_generated INTEGER NOT NULL DEFAULT 0,
            connections_suggested INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.commit()
    return conn

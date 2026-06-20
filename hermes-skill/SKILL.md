---
name: mirror-brain
description: Use when querying or writing to Mirror Brain memory system — search past memories, ingest new text, or explore the knowledge graph.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [mirror-brain, memory, agentic, knowledge-graph, c0, sqlite, entity-system, deepseek]
    related_skills: [hermes-agent-skill-authoring]
---

# Mirror Brain — Agentic Memory System

A-MEM inspired, graph-based memory system for LLM agents. Stores structured memories in SQLite
(entity registry, daily summaries, reasoning trail, relations) with optional c0 graph engine
for semantic search and link traversal.

## When to Use

- `/mirror query "..."` — search memories, entities, and past context from the brain
- `/mirror ingest "..."` — add new text as a structured memory note through the full pipeline
- When the user asks about past events, entities, decisions, or relationships stored in Mirror Brain
- When the user wants to record a new experience, thought, or update into their memory system

Don't use for: ephemeral queries (use web search), general knowledge (use the model directly),
or when Mirror Brain DB is not initialized.

## Architecture

```
Text → NoteConstructor (LLM #1) → ContextFetcher (SQLite + c0) → LinkEvolution (LLM #2) → Execute
```

### Pipeline Steps

| Step | What | Who | Tokens |
|------|------|-----|--------|
| 1. Note Construction | Extract keywords, context, tags, emotions, entities, search_hints | LLM (DeepSeek) | ~600 |
| 2. Context Fetch | Query SQLite (daily_index, entity registry, reasoning_trail) based on search_hints | Code ($0) | 0 |
| 3. Link + Evolution | Decide connections, aliases, memory updates. Can request more context (loop, max 2x) | LLM (DeepSeek) | ~800 |
| 4. Execution | Write relations + aliases, log reasoning trail, apply confidence gates (≥0.85 auto, ≥0.60 flag, <0.60 skip) | Code ($0) | 0 |

## Requirements

### Environment Variables

- `DEEPSEEK_API_KEY` — Required for both LLM calls (NoteConstructor + LinkEvolution).
  Stored in `~/AppData/Local/hermes/.env`. Both scripts auto-load from this file if the
  env var is not set in the process environment.

### Database

- **Location:** `~/mirror_brain.db` (expands to `C:\Users\gusta\mirror_brain.db`)
- **Schema (5 tables):** `entities`, `aliases`, `daily_index`, `reasoning_trail`, `relations`
- Created automatically on first use via `EntityRegistry(db_path)`.
- All Python 3.11+ stdlib — no external dependencies.

### Mirror Brain Package

Must be importable from `C:\Users\gusta\mirror-brain\src`. The scripts add this to `sys.path`
automatically, so no `pip install` is required.

## Scripts

### `scripts/query.py` — Search Memories

Loads the entity registry and searches for entities, aliases, and relations matching
a given query string.

```
python ~/AppData/Local/hermes/skills/mirror-brain/scripts/query.py "c0"
```

Returns formatted output with entity info (UUID, canonical name, type) and all known aliases.

### `scripts/ingest.py` — Ingest New Text

Runs the full Mirror Brain pipeline on a text string:

```
python ~/AppData/Local/hermes/skills/mirror-brain/scripts/ingest.py "Hoy trabajé en integrar c0 con Mirror Brain"
```

Returns:
- The constructed Note (keywords, context, tags, emotional_load, entities, search_hints)
- Fetched context (daily summaries, entity contexts, semantic results)
- Link/evolution decisions (proposed links, evolutions, new aliases)
- Execution report (auto-executed, flagged for review, skipped)

## Usage Examples

### Query

```
/mirror query "what happened with c0 this week?"
```

This searches the entity registry for "c0", retrieves daily summaries from this week,
and shows related reasoning trail entries.

### Ingest

```
/mirror ingest "Today I worked on the Mirror Brain Hermes skill integration. The pipeline now works end-to-end."
```

This runs the full pipeline:
1. DeepSeek extracts keywords, entities (Mirror Brain, Hermes Agent), emotional load, and search hints
2. ContextFetcher retrieves recent daily summaries and entity info
3. DeepSeek decides new links (e.g., Mirror Brain --[depends_on]--> Hermes Agent), evolutions, and aliases
4. High-confidence decisions are auto-executed; medium-confidence are flagged for review

## Entity System

The registry enforces entity creation criteria (not everything gets a UUID):

| Condition | Decision |
|-----------|----------|
| Person, project, tool, place, organization | Entity on first mention — ALWAYS |
| Emotion, event, attribute, quantity, date, action | Never an entity — stay as tags |
| Mentioned 2+ times across distinct sessions | Promoted to entity |
| LLM confidence > 85% | Entity |
| Below thresholds | Stays as keyword in note |

## Confidence Gates

Decisions from LLM #2 (LinkEvolution) are gated by confidence:

| Confidence | Action |
|-----------|--------|
| ≥ 0.85 | Auto-execute |
| 0.60 – 0.85 | Execute but flag for review |
| < 0.60 | Skip |

## Common Pitfalls

1. **DB not found.** Ensure `~/mirror_brain.db` exists. Run `EntityRegistry("~/mirror_brain.db")` once to initialize.
2. **Package not importable.** The scripts auto-add `C:\Users\gusta\mirror-brain\src` to `sys.path`. If the repo moved, update the path.
3. **No API key.** Both scripts check `DEEPSEEK_API_KEY` env var, then `~/AppData/Local/hermes/.env`. Without it, LLM calls return empty structured responses.
4. **Empty brain.** If no entities or daily summaries exist, ContextFetcher returns minimal context and LinkEvolution will propose conservative links.
5. **c0 not running.** ContextFetcher works with SQLite only when c0 is unavailable — semantic search and graph walks are skipped gracefully.

## Verification Checklist

- [ ] `~/mirror_brain.db` exists and has tables (run `python -c "from mirror_brain.registry import EntityRegistry; EntityRegistry('C:/Users/gusta/mirror_brain.db')"`)
- [ ] `DEEPSEEK_API_KEY` is set in env or `~/AppData/Local/hermes/.env`
- [ ] Scripts run: `python scripts/query.py "test"` and `python scripts/ingest.py "test"`
- [ ] Mirror Brain repo is at `C:\Users\gusta\mirror-brain\` with `src/mirror_brain/` modules intact

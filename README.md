# Mirror Brain v1.0

**An infinite, self-improving, graph-based memory system for LLM agents.**

Mirror Brain captures, organizes, and surfaces personal knowledge — conversations, thoughts, emotions, decisions — into a long-term memory that grows smarter with every interaction. Built on the A-MEM (Agentic Memory) principles with Zettelkasten-inspired note construction, dynamic linking, and autonomous memory evolution.

## Architecture

```
Text → LLM Note Constructor → Fetch Context (c0 + SQLite) → LLM Decision → Execute + Log
                                    ↑                               │
                                    └─── search_hints ←─────────────┘
```

### Pipeline

| Step | What happens | Who |
|------|-------------|-----|
| 1. Note Construction | Extract keywords, context, tags, emotions, entities, search hints | LLM (cheap model) |
| 2. Context Fetch | Query c0 (graph) + SQLite (daily index, entities) based on search hints | Code ($0) |
| 3. Link + Evolution | Decide connections, aliases, memory updates | LLM |
| 4. Execution | Write to c0 + SQLite, log reasoning trail, apply confidence gates | Code ($0) |

### Entity Criteria

Not everything deserves a UUID. Mirror Brain applies rules:

| Condition | Decision |
|-----------|----------|
| Person, project, tool, place, organization | Entity on first mention |
| Emotion, event, attribute, quantity, date, action | Never an entity (tags only) |
| Mentioned 2+ times across sessions | Promoted to entity |
| LLM confidence > 85% | Entity |
| Below thresholds | Stays as keyword in note |

## Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ (stdlib only for now) |
| Package manager | uv |
| Memory graph | c0 (Rust) + Neo4j |
| Embeddings | Ollama (nomic-embed-text, local) |
| Entity registry | SQLite |
| Container runtime | Docker (shared network) |

## Project Structure

```
mirror-brain/
├── pyproject.toml
├── README.md
├── .gitignore
├── src/mirror_brain/
│   ├── __init__.py
│   ├── registry.py          # EntityRegistry — UUID system + SQLite
│   ├── schema.py            # Database schema (5 tables)
│   ├── criteria.py          # Entity creation decision rules
│   ├── models.py            # Dataclasses (Entity, Note, Alias, ...)
│   └── c0_client.py         # c0 CLI wrapper (subprocess)
├── tests/
│   └── test_integration.py  # Full pipeline integration test
└── docker/
    └── docker-compose.unified.yml  # (coming) Neo4j + Ollama + c0 + Python
```

## Quick Start

```bash
git clone https://github.com/JulianBorja123/mirror-brain.git
cd mirror-brain
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
python tests/test_integration.py
```

## Docker (c0 stack)

Neo4j, Ollama, and c0 must be running in Docker with a shared network. Start them:

```bash
docker compose -f docker/docker-compose.unified.yml up -d
```

## License

Private — not yet licensed.

## References

- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) — Xu et al., Rutgers University, 2025
- [c0](https://github.com/douglasjordan2/c0) — Bi-temporal knowledge graph engine (MIT)
- [Zettelkasten Method](https://en.wikipedia.org/wiki/Zettelkasten) — Niklas Luhmann's knowledge management system

# Mirror Brain v1.0

**An infinite, self-improving, graph-based memory system for LLM agents.**

Mirror Brain captures, organizes, and surfaces personal knowledge — conversations,
thoughts, emotions, decisions — into a long-term memory that grows smarter with
every interaction. Built on A-MEM (Agentic Memory) principles with
Zettelkasten-inspired note construction, dynamic linking, and autonomous memory evolution.

---

## How It Works

```
                     YOUR TEXT
                        │
                        ▼
╔══════════════════════════════════════════════════════════════╗
║ STEP 1 — NOTE CONSTRUCTOR  (LLM #1, ~600 tokens)            ║
║                                                              ║
║  You: "Romi me dijo que la floreria esta complicada..."      ║
║                    ↓                                         ║
║  LLM extracts:                                               ║
║    • keywords:     [floreria, ventas, c0, Ollama, ...]       ║
║    • context:      "Julian discusses Romi's flower shop..."  ║
║    • tags:         [proyecto, tecnico, social, financiero]   ║
║    • emotions:     oxytocin=0.6, cortisol=0.5, dopamine=0.7 ║
║    • entities:     Romi→Romina, c0, Mirror Brain, ...        ║
║    • search_hints: "what was c0's last status?"              ║
║                    "how much spent on DeepSeek tokens?"      ║
╚═══════════════════════╤══════════════════════════════════════╝
                        ▼
╔══════════════════════════════════════════════════════════════╗
║ STEP 2 — CONTEXT FETCHER  (code, $0, local)                 ║
║                                                              ║
║  Takes search_hints, fetches real data:                      ║
║    • SQLite daily_index → recent day summaries               ║
║    • SQLite entities → registry info + aliases               ║
║    • SQLite reasoning_trail → related past decisions         ║
║    • c0 graph → entity neighbors and connections             ║
║                                                              ║
║  Output: packaged JSON context                               ║
╚═══════════════════════╤══════════════════════════════════════╝
                        ▼
╔══════════════════════════════════════════════════════════════╗
║ STEP 3 — LINK + EVOLUTION  (LLM #2, ~800 tokens)            ║
║                                                              ║
║  LLM receives: Note + Context + Neighbor memories            ║
║  LLM decides:                                                ║
║    • LINKS:          Romi → updates_status → Floreria        ║
║                      c0   → works_with     → Ollama          ║
║                      MB   → relates_to     → Floreria        ║
║    • EVOLUTIONS:     update_context on c0, Floreria          ║
║    • ALIASES:        new name detected for existing entity   ║
║    • MORE SEARCH:    "what advertising did Julian propose?"  ║
║                                                              ║
║  Every decision comes with confidence + reasoning            ║
╚═══════════════════════╤══════════════════════════════════════╝
                        ▼
╔══════════════════════════════════════════════════════════════╗
║ STEP 4 — EXECUTION  (code, $0)                              ║
║                                                              ║
║  Confidence gates:                                           ║
║    > 0.85 → AUTO-EXECUTE (writes to c0 + SQLite)            ║
║    0.60-0.85 → EXECUTE but FLAG for review                  ║
║    < 0.60 → SKIP, tell the user                             ║
║                                                              ║
║  Every action logged in reasoning_trail:                     ║
║    WHAT was done, WHY, with what CONFIDENCE                  ║
║    Reversible — corrections make the system smarter          ║
╚══════════════════════════════════════════════════════════════╝
```

### Result: a living knowledge graph

```
  Romina ──[updates_status]──→ Florería GJB     🟢 1.00
  Romina ──[relates_to]──────→ Mirror Brain      🟡 0.80
  c0     ──[works_with]──────→ Ollama            🟢 1.00
  c0     ──[relates_to]──────→ DeepSeek          🟢 0.90
  MB     ──[relates_to]──────→ Florería GJB      🟡 0.70
  MB     ──[depends_on]──────→ c0                🟢 1.00
  c0     ──[runs_in]─────────→ Docker            🟢 1.00
```

---

## Entity Criteria

Not everything deserves a UUID. Mirror Brain applies rules:

| Condition | Decision |
|-----------|----------|
| Person, project, tool, place, organization | Entity on first mention |
| Emotion, event, attribute, quantity, date, action | Never an entity (tags only) |
| Mentioned 2+ times across sessions | Promoted to entity |
| LLM confidence > 85% | Entity |
| Below thresholds | Stays as keyword in note |

---

## Modules (v1.0)

| # | Module | Role |
|---|--------|------|
| 1 | `schema.py` | 5 SQLite tables (entities, aliases, daily_index, reasoning_trail, relations) |
| 2 | `criteria.py` | 6 rules for entity UUID creation |
| 3 | `registry.py` | EntityRegistry: create, resolve, alias, ingest, search, log |
| 4 | `models.py` | Dataclasses: Entity, Note, Alias, DailySummary, ReasoningRecord, Relation |
| 5 | `c0_client.py` | c0 CLI wrapper (subprocess): create, search, walk, relate, supersede |
| 6 | `note_constructor.py` | LLM #1: A-MEM note construction (keywords, emotions, entities, hints) |
| 7 | `context_fetcher.py` | Intelligent hint-based retrieval from SQLite + c0 |
| 8 | `link_evolution.py` | LLM #2: link generation + memory evolution + confidence-gated execution |

---

## Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ (stdlib only) |
| Package manager | uv |
| Memory graph | c0 (Rust) + Neo4j |
| Embeddings | Ollama (nomic-embed-text, local) |
| Entity registry | SQLite |
| LLM | DeepSeek (deepseek-chat) |
| Container runtime | Docker (shared network) |

---

## Project Structure

```
mirror-brain/
├── pyproject.toml
├── README.md
├── .gitignore
├── src/mirror_brain/
│   ├── __init__.py
│   ├── schema.py              # Database schema (5 tables)
│   ├── criteria.py            # Entity creation decision rules
│   ├── registry.py            # EntityRegistry — UUID system
│   ├── models.py              # Dataclasses
│   ├── c0_client.py           # c0 CLI wrapper (subprocess)
│   ├── note_constructor.py    # LLM #1: note construction
│   ├── context_fetcher.py     # Hint-based context retrieval
│   └── link_evolution.py      # LLM #2: links + evolution + execute
├── tests/
│   ├── test_integration.py         # Entity system tests
│   ├── demo_note_constructor.py    # Step 1 demo
│   ├── demo_full_pipeline.py       # Steps 1 + 2 demo
│   └── demo_complete_pipeline.py   # Steps 1 + 2 + 3 demo
└── docker/
    └── docker-compose.unified.yml  # (coming) Neo4j + Ollama + c0 + Python
```

---

## Quick Start

```bash
git clone https://github.com/JulianBorja123/mirror-brain.git
cd mirror-brain
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Unit tests
python tests/test_integration.py

# Full pipeline demo (needs DeepSeek API key)
python tests/demo_complete_pipeline.py
```

---

## Docker (c0 stack)

Neo4j, Ollama, and c0 must be running in Docker with a shared network:

```bash
docker compose -f docker/docker-compose.unified.yml up -d
```

---

## License

Private — not yet licensed.

---

## References

- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) — Xu et al., Rutgers, 2025
- [c0](https://github.com/douglasjordan2/c0) — Bi-temporal knowledge graph engine (MIT)
- [Zettelkasten Method](https://en.wikipedia.org/wiki/Zettelkasten) — Niklas Luhmann

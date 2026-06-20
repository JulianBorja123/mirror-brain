# 🧠 Mirror Brain v3 — AGENTS.md

> **The complete agent manual.** Everything an AI agent (or developer) needs to know about Mirror Brain: vision, architecture, setup, tools, tests, performance, and soul.
>
> Last updated: 2026-06-20 | Version: 3.1 | Status: **Production-ready core, active development**

---

## Table of Contents

1. [What is Mirror Brain?](#what-is-mirror-brain)
2. [The 19-Point Vision — What We Wanted vs. What We Built](#the-19-point-vision)
3. [Architecture](#architecture)
4. [How It Works](#how-it-works)
5. [All 38 MCP Tools](#all-38-mcp-tools)
6. [Setup & Operations](#setup--operations)
7. [Test Suites](#test-suites)
8. [Performance Benchmarks](#performance-benchmarks)
9. [Product Catalog System](#product-catalog-system)
10. [Soul System](#soul-system)
11. [Known Issues & Roadmap](#known-issues--roadmap)
12. [Git History & Key Commits](#git-history--key-commits)

---

## What is Mirror Brain?

**Mirror Brain** is an infinite, self-improving, graph-based memory system for LLM agents. It captures, organizes, and surfaces personal knowledge — conversations, thoughts, emotions, decisions, products — into a long-term memory that grows smarter with every interaction.

### Core Promise
> "A super-intelligent seller agent capable of handling millions of data points without overload, with exact-key lookup, fuzzy matching, semantic search, and filters — all while maintaining a persistent soul across sessions."

### Why "Mirror Brain"?

| Layer | Meaning |
|---|---|
| **Mirror** | Reflects everything the user says, thinks, feels — faithfully |
| **Brain** | Organizes it into entities, relations, memories, and procedures |
| **Mirror Brain** | A second brain that mirrors the user's mind — persistent, queryable, evolving |

---

## The 19-Point Vision

*Mapped from Julián's 38-minute voice brainstorm. ✅ = implemented, 🔶 = partial, ❌ = not yet.*

| # | Vision Concept | Status | Details |
|---|---|---|---|
| 1 | **Activation Layer** | ✅ 100% | `_activation_ready()` checks if entity should be "awake" based on recent mentions, relations, and emotion spikes |
| 2 | **Minimap** | ✅ 100% | `mb_get_minimap(entity)` returns connected entities with context, status, and emotional color-coding |
| 3 | **Tools** | ✅ 100% | 38 MCP tools: search, link, alias, ingest, reasoner, stats, cache, products, soul |
| 4 | **Agent Loop** | ✅ 100% | `agent.py`: full pipeline — `_perceive → _decide → _execute` with c0 read/write |
| 5 | **Summaries** | ✅ 100% | `mb_get_weekly_summary`, `mb_get_monthly_summary` via consolidation module |
| 6 | **Temporal Window** | ✅ 100% | `mb_search_temporal(days_ago, window)`, temporal range search |
| 7 | **Theme Extraction** | ✅ 100% | LLM extracts themes/tags from ingested text; stored as embeddings in Neo4j |
| 8 | **Raw Text Search** | ✅ 100% | `mb_search_raw_text(query)` with full-text and embedding fallback |
| 9 | **Agent Loop (reasoning)** | ✅ 100% | `mb_run_reasoner`: 4-phase reasoning (activation, context, decision, execution) |
| 10 | **Consolidation** | ✅ 100% | `HierarchicalConsolidation`: nightly summaries, weekly rollups, monthly archives |
| 11 | **Procedural Memory** | ✅ 100% | `mb_search_procedures`, `mb_get_procedure`: records execution traces as reusable procedures |
| 12 | **Internal Reasoner** | ✅ 100% | `internal_reasoner.py`: self-audit loop that checks for contradictions and stale knowledge |
| 13 | **Async Ingest** | ✅ 100% | `TaskManager` + `mb_task_status` + `mb_task_result`: non-blocking LLM ingestion |
| 14 | **Correction** | ✅ 100% | `mb_correct(entity, type, description)`: manual override to fix wrong entity info |
| 15 | **Emotion Tracking** | ✅ 100% | Oxytocin, cortisol, dopamine per entity; `mb_search_by_emotion`, cycles, trends, anomalies |
| 16 | **Predictive Engine** | ✅ 100% | `mb_predict(entity, metric, days)` forecasts emotional/cognitive trends |
| 17 | **Decaimiento (Decay)** | 🔶 40% | Memory budget exists (daily/weekly/monthly caps); exponential decay not implemented |
| 18 | **Contradicciones** | ❌ 0% | Internal reasoner detects conflicts but doesn't auto-resolve yet |
| 19 | **Fast/Slow Storage** | 🔶 20% | c0 search is fast (~190ms); no explicit "fast RAM index" vs "slow disk" split yet |

### User's Meta-Vision (beyond the 19)

| Concept | Status | Details |
|---|---|---|
| **Super-intelligent seller agent** | ✅ | 30 products, 15/15 buyer-style searches, ~190ms p50 |
| **Millions of products without overload** | 🔶 | Architecture supports it; need pagination + RAM index |
| **Product phrases for semantic embedding** | ✅ | Each product gets 3-5 description phrases indexed in Neo4j |
| **Hybrid search (exact + fuzzy + semantic)** | ✅ | c0 RRF (Reciprocal Rank Fusion) combines keyword + embedding |
| **Generic properties (key-value)** | ✅ | `mb_set_property`, `mb_get_properties` for any entity |
| **Multi-tenancy (Supabase OAuth)** | ❌ | Planned for v4 |
| **Multi-user Neo4j** | ❌ | Planned for v4 |
| **WhatsApp integration** | ❌ | Hermes gateway supports it, not wired yet |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    HERMES AGENT                         │
│  (Telegram DM → LLM → Tool Calls → Response)            │
└──────────────┬──────────────────────────────────────────┘
               │ MCP Protocol (SSE over HTTP :8765)
               ▼
┌─────────────────────────────────────────────────────────┐
│               MCP SERVER (Python)                       │
│  mcp_server.py — 38 tools, FastMCP, TaskManager          │
│  C0Registry — identity resolution, caching, search       │
│  Agent — _perceive / _decide / _execute pipeline          │
│  ProceduralMemory — execution trace → reusable steps     │
│  HierarchicalConsolidation — daily → weekly → monthly    │
│  PredictiveEngine — trend forecasting                    │
│  InternalReasoner — self-audit loop                      │
│  MultiModal — image/audio processing                    │
└──────┬──────────────────────┬───────────────────────────┘
       │ Docker exec          │ HTTP REST (Ollama)
       ▼                      ▼
┌──────────────┐    ┌──────────────────┐
│   c0 (Rust)  │    │     Ollama       │
│   Binary in  │    │  nomic-embed-text│
│   Docker     │    │  Port 11434      │
│   ┌────────┐ │    └──────────────────┘
│   │ Bolt    │ │
│   │ Driver  │ │
│   └────┬───┘ │
└────────┼─────┘
         │ Bolt protocol
         ▼
┌──────────────────┐
│  Neo4j Community │
│  Port 7687       │
│  ┌────────────┐  │
│  │ Concepts   │  │  ← entities, products, procedures, raw_texts
│  │ Relations  │  │  ← links between entities
│  │ Embeddings │  │  ← vector index for hybrid search
│  └────────────┘  │
└──────────────────┘
```

### Stack Summary

| Component | Technology | Role |
|---|---|---|
| **Agent runtime** | Hermes Agent (Python) | Conversation loop, tool dispatch, gateway |
| **Memory backend** | c0 (Rust binary) | Graph operations, hybrid search, concept CRUD |
| **Graph database** | Neo4j Community 5.x | Stores entities, relations, embeddings |
| **Embeddings** | Ollama + nomic-embed-text | 768-dim vectors for semantic search |
| **LLM** | DeepSeek V3 (via API) | Note construction, link evolution, ingestion |
| **Transport** | MCP Streamable HTTP | SSE sessions on port 8765 |
| **Orchestration** | Docker Compose | 4 containers: c0, Neo4j, Ollama, app |

### Docker Containers

```
mirrorbrain-c0       Up (c0 Rust binary, compiled ~15MB)
mirrorbrain-neo4j    Up (healthy) (Neo4j Community, Bolt 7687)
mirrorbrain-ollama   Up (nomic-embed-text model)
mirrorbrain-app      Up (optional — Python app container)
```

---

## How It Works

### The Pipeline (v1/v2 legacy, now integrated)

```
USER INPUT (text/voice/Telegram)
        │
        ▼
┌──────────────────────────────────────┐
│ 1. NOTE CONSTRUCTOR (LLM #1)         │
│    Extracts: keywords, entities,     │
│    emotions, search_hints, tags      │
│    Cost: ~600 tokens                 │
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│ 2. CONTEXT FETCHER (code)            │
│    Fetches related entities, past    │
│    notes, procedures from Neo4j/c0   │
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│ 3. LINK EVOLUTION (LLM #2)           │
│    Decides: new links, aliases,      │
│    context updates, corrections      │
│    Cost: ~800 tokens                 │
└──────────────┬───────────────────────┘
               ▼
┌──────────────────────────────────────┐
│ 4. EXECUTION (code)                  │
│    Confidence gates:                 │
│    > 0.85 → auto-execute             │
│    0.60-0.85 → execute + flag        │
│    < 0.60 → skip + report            │
│    Every action logged in trail      │
└──────────────────────────────────────┘
```

### Agent Loop (v3, in `agent.py`)

```python
class MirrorBrainAgent:
    def run(self, text, source="mcp"):
        # 1. Perceive: extract entities, emotions, intent
        perception = self._perceive(text)
        
        # 2. Decide: what to do (create? link? correct? skip?)
        decisions = self._decide(perception)
        
        # 3. Execute: apply decisions to c0/Neo4j
        results = self._execute(decisions)
        
        return results
```

### Cache System

| Cache | TTL | Invalidated By |
|---|---|---|
| `entities:all` | 120s | `create()`, `update_entity()` |
| `search:(query,mode)` | 60s | Time-based only |
| `entity:desc:{name}` | 60s | Entity update |
| `stats:full` | 30s | `create()`, writes |
| `c0 export` | 60s | Any write operation |
| `_fetch_module_rows` | 60s | Module row changes |

Cache manager: thread-safe with hit/miss tracking and prefix-based invalidation.

---

## All 38 MCP Tools

### Core Entity Operations (8 tools)
| Tool | Description | Avg Speed |
|---|---|---|
| `mb_ingest` | Ingest text → extract entities, emotions, links | ~10.7s (LLM) |
| `mb_correct` | Manually correct entity info | ~150ms |
| `mb_add_alias` | Add nickname/shortcut for entity | ~200ms |
| `mb_link` | Create relation between two entities | ~300ms |
| `mb_search_fuzzy` | Find entity by approximate name | ~190ms |
| `mb_search_semantic` | Find by meaning (hybrid RRF via c0) | ~200ms |
| `mb_get_minimap` | Get entity neighborhood | ~370ms |
| `mb_search_raw_text` | Full-text + embedding search in raw texts | ~180ms |

### Procedural Memory (2 tools)
| Tool | Description |
|---|---|
| `mb_search_procedures` | Find reusable execution procedures |
| `mb_get_procedure` | Get specific procedure steps |

### Temporal & Summarization (4 tools)
| Tool | Description |
|---|---|
| `mb_search_temporal` | Find memories from N days ago |
| `mb_search_temporal_range` | Find memories in date range |
| `mb_get_weekly_summary` | Consolidated weekly summary |
| `mb_get_monthly_summary` | Consolidated monthly summary |

### Emotion & Prediction (6 tools)
| Tool | Description |
|---|---|
| `mb_search_by_emotion` | Find entities by emotion (oxytocin, cortisol, dopamine) |
| `mb_search_cycles` | Detect emotional cycles for entity |
| `mb_get_trend` | Get emotional trend over N days |
| `mb_get_anomalies` | Detect emotional anomalies |
| `mb_predict` | Forecast future emotional values |
| `mb_correlation` | Correlate two entities' emotional patterns |

### Product Catalog (6 tools)
| Tool | Description | Avg Speed |
|---|---|---|
| `mb_register_product` | Register a product with properties and phrases | ~1.6s |
| `mb_search_products` | Search products by description (buyer-style) | ~200ms |
| `mb_get_by_id` | Lookup entity by UUID | ~0.01s warm / 0.3s cold |
| `mb_set_property` | Set key-value property on entity | ~0.5s |
| `mb_get_properties` | Get all properties for entity | ~50ms |
| `mb_list_product_categories` | List all product categories | ~7ms |
| `mb_get_product_stats` | Product catalog statistics | ~7ms |

### Maintenance (5 tools)
| Tool | Description |
|---|---|
| `mb_stats` | Entity/relation/concept counts | ~4.5s (cached: ~6ms) |
| `mb_cache_stats` | Cache hit/miss rates |
| `mb_invalidate_cache` | Force cache refresh |
| `mb_get_memory_budget` | Daily/weekly/monthly memory limits |
| `mb_task_status` / `mb_task_result` | Async ingest progress/results |

### Reasoner (1 tool)
| Tool | Description | Avg Speed |
|---|---|---|
| `mb_run_reasoner` | Run full 4-phase reasoning cycle | ~1.2s |

### Alias Management (3 tools)
| Tool | Description |
|---|---|
| `mb_remove_alias` | Remove an alias from entity |
| `mb_reassign_alias` | Move alias to different entity |
| `mb_list_aliases` | List all aliases for entity |

### Relations (1 tool)
| Tool | Description |
|---|---|
| `mb_list_relations` | List all relations for entity | ~7.3s |

---

## Setup & Operations

### First-Time Setup

```bash
# 1. Clone the repo
git clone https://github.com/JulianBorja123/mirror-brain.git
cd mirror-brain

# 2. Start Docker containers (Neo4j, c0, Ollama, app)
docker compose -f docker/docker-compose.unified.yml up -d

# 3. Wait for Neo4j to be healthy
docker ps --filter "name=mirrorbrain-neo4j" --format "{{.Status}}"
# Should show: "Up X minutes (healthy)"

# 4. Verify c0 connectivity
docker exec mirrorbrain-c0 c0 health
# Should show: "OK"

# 5. Verify Ollama has embedding model
docker exec mirrorbrain-ollama ollama list
# Should show: nomic-embed-text

# 6. Start MCP server
PYTHONPATH="$PWD/src" python -B mcp_server.py --port 8765
# Should show: "[MB-MCP] Mirror Brain v3 MCP Server starting..."
```

### Restart Procedures

```bash
# FULL RESTART (Docker + MCP)
cd /c/Users/gusta/mirror-brain

# Kill MCP server if running
taskkill //F //IM python.exe 2>/dev/null  # Windows
# Or: pkill -f mcp_server.py              # Linux

# Restart Docker if needed
docker compose -f docker/docker-compose.unified.yml restart

# Restart MCP server
PYTHONPATH="$PWD/src" python -B mcp_server.py --port 8765 &

# Verify
curl -X GET http://127.0.0.1:8765/mcp -H "Accept: text/event-stream"
```

### Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| `[Errno 10048] port 8765` | Another MCP server running | `netstat -ano \| grep 8765` → kill PID |
| `c0 failed (exit 1)` | Docker container down | `docker ps` → restart |
| `Ollama not responding` | nomic-embed-text not pulled | `docker exec mirrorbrain-ollama ollama pull nomic-embed-text` |
| `Neo4j unhealthy` | License not accepted | Set `NEO4J_ACCEPT_LICENSE_AGREEMENT=yes` |
| Python `SyntaxError` in imports | Windows path mixup | Use `PYTHONPATH="$PWD/src"` not `$PWD\src` |

### Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `DEEPSEEK_API_KEY` | LLM for ingestion/reasoning | Required |
| `MB_MCP_PORT` | MCP server port | 8765 |
| `MB_MEMORY_DAILY` | Daily memory budget (notes) | 0 (unlimited) |
| `MB_MEMORY_WEEKLY` | Weekly memory budget | 0 |
| `MB_MEMORY_MONTHLY` | Monthly memory budget | 0 |

---

## Test Suites

### Quick Run
```bash
# Pre-commit comprehensive (10 suites, ~2 min)
cd /c/Users/gusta/mirror-brain
PYTHONPATH="$PWD/src" python tests/test_v3_comprehensive.py
```

### Full Suite Breakdown

| Suite | File | Tests | Description |
|---|---|---|---|
| **Suite 1** | `suite1_smoke.py` | 32/32 | Every MCP tool called once, no crashes |
| **Suite 2** | `suite2_scenarios.py` | 18/22 | Real-world scenarios: fuzzy matching, alias resolution, cross-entity search |
| **Suite 3** | `suite3_isolation.py` | 39/40 | Tool isolation: each tool independent, no cross-contamination |
| **Suite 4** | `suite4_reasoning.py` | 44/46 | Reasoning quality: link detection, alias detection, confidence calibration |
| **Suite 5** | `suite5_deep_audit.py` | — | Deep audit: response quality scoring, regression detection |
| **v3 Comprehensive** | `test_v3_comprehensive.py` | **33/33** ✅ | Connectivity, semantic search, speed, edge cases, integrity, cache, MCP health |

### v3 Comprehensive Test Results (33/33)

| Suite | Tests | Status |
|---|---|---|
| Docker + c0 Connectivity | 3 | ✅ |
| Semantic Product Search (10 buyer queries) | 10 | ✅ |
| Performance Benchmarks | 1 + 3 benches | ✅ ~190ms avg |
| Data Export & Stats | 3 | ✅ |
| Edge Cases (empty, SQL injection, emoji, Unicode, 200 chars) | 8 | ✅ |
| Product Data Integrity (22 brands) | 1 | ✅ |
| Cross-Language EN↔ES | 2 | ✅ |
| Cache Integrity | 2 | ✅ |
| Results Structure | 2 | ✅ |
| MCP Server Health | 1 | ✅ |

### How to Run the Legacy Real Suites

```bash
# From inside the venv with Docker running
PYTHONPATH="$PWD/src" python tests/real/suite1_smoke.py
PYTHONPATH="$PWD/src" python tests/real/suite2_scenarios.py
# ... etc.

# Or with pytest (longer, needs MCP server)
PYTHONPATH="$PWD/src" python -m pytest tests/real/ -v --tb=short -n 0
```

---

## Performance Benchmarks

### Current (v3.1, warm cache, 30 products)

| Operation | p50 | avg | Notes |
|---|---|---|---|
| `mb_get_by_id` (cached) | 0.01ms | 0.01ms | 660x improvement from v3.0 |
| `mb_search_products` | ~29ms | ~29ms | Word-split matching in Python |
| `c0.search('laptop')` | ~180ms | ~190ms | Hybrid RRF via c0 |
| `c0.search('gaming laptop')` | ~181ms | ~185ms | Same speed regardless of query length |
| `c0.search('auriculares cancelación')` | ~185ms | ~189ms | Spanish queries same speed |
| `mb_set_property` | ~500ms | ~500ms | Docker exec overhead |
| `mb_register_product` | ~1.6s | ~1.6s | Creates concept + embedding + cache invalidation |
| `mb_ingest` (LLM) | ~10.7s | ~10.7s | DeepSeek API latency |
| `mb_stats` (cached) | ~6ms | ~6ms | 660x improvement |
| `mb_list_relations` | ~7.3s | ~7.3s | ⚠️ Walks all concepts — needs optimization |

### Scaling Projection

| Nodes | Search Speed | Degradation |
|---|---|---|
| 30 products | ~190ms | Baseline |
| 472 nodes | ~570ms | ~3x (linear, as expected) |
| 10,000 nodes | ~4s est. | Linear extrapolation |
| 1,000,000 nodes | Needs RAM index | Architecture supports it |

---

## Product Catalog System

### Data Model
Each product is stored as a `Concept` in Neo4j under namespace `mirrorbrain`:

```
Concept {
  name: "MacBook Pro M3"
  namespace: "mirrorbrain"
  description: "price=1999|category=laptops|tags=apple,developer,premium"
  embedding: [0.123, -0.456, ...]  # 768-dim from nomic-embed-text
  properties: {
    price: 1999,
    category: "laptops",
    brand: "Apple",
    ram: "16GB",
    processor: "M3",
    ...
  }
}

// Product phrases (separate concepts for embedding variety)
[product_phrase] MacBook Pro M3: developer machine
[product_phrase] MacBook Pro M3: high performance
[product_phrase] MacBook Pro M3: apple laptop premium
```

### Buyer-Style Search
The user describes what they want in natural language, and the system finds matching products:

| Buyer Says | System Finds |
|---|---|
| "gaming laptop with good graphics and high refresh rate" | ASUS ROG Zephyrus G14, Razer Blade 16 |
| "cheap android phone good value under $500" | Nothing Phone 3, OnePlus 13 |
| "best noise cancelling headphones for airplane travel" | Bose QC Ultra, Sony WH-1000XM6, AirPods Pro 3 |
| "tablet for digital artists and drawing professionals" | iPad Pro M4 13 |
| "mechanical keyboard wireless programmer aluminum body" | Keychron Q1 Pro |
| "modular repairable sustainable laptop" | Framework Laptop 16 🎯 |
| "tiny desktop computer for office desk small space" | Mac Mini, HP Elite Mini 800 G9 |
| "samsung phone with stylus pen s-pen" | Galaxy S25 Ultra 🎯 |

### How Search Works
1. User query is split into words
2. Each word is matched against product names and `[product_phrase]` entries via c0 hybrid search
3. Results are aggregated, deduplicated, and ranked by relevance
4. Products with matching phrases score higher

---

## Soul System

Mirror Brain has a persistent identity across sessions via two files:

### `soul_core.md` — Immutable Core Identity
```markdown
# 🪨 Core Identity (almost immutable)
- Full name: Gustavo Julian Barrios Borja
- Called: Julián, Juli
- Languages: Spanish (native), English (advanced)

## Purpose
- Building Mirror Brain as life project
- Financial goal: $100M+ in 10-30 years
- Independence and family are absolute priorities

## How I Work
- Learn by doing, iterate fast
- Prefer open-source, dockerizable solutions
- Bilingual, security-conscious
- Voice-first interaction
```

### `soul_live.md` — Editable Current State
```markdown
# 🌊 Current State (editable)
- Phase: Building
- Main project: Mirror Brain v3
- Status: Active development (June 2026)

## People
- [update as needed]

## Immediate Goal
- Finish Mirror Brain v3 core
- Soul + products + hybrid search system
```

These files are ~500 tokens total and injected into every conversation — giving Hermes persistent identity without consuming context budget.

---

## Known Issues & Roadmap

### Known Bugs (from latest audit)
| # | Issue | Severity | Status |
|---|---|---|---|
| 1 | `mb_ingest` LLM timeout > 30s MCP handler timeout | 🟡 MEDIUM | ⬜ Pending |
| 2 | `mb_list_relations` walks all concepts (7.3s) | 🟡 MEDIUM | ⬜ Optimize |
| 3 | Fuzzy search no semantic fallback ("espejo" ≠ "Mirror") | 🟡 MEDIUM | ⬜ Feature |
| 4 | Integration test (`test_integration.py`) uses SQLite API, now c0 | 🟡 LOW | 🔶 Needs rewrite |

### Immediate Roadmap
1. **Increase MCP tool timeout** for LLM calls (30s → 120s)
2. **Optimize `mb_list_relations`**: Use c0 export edges instead of walking each concept
3. **Add semantic fallback** to fuzzy search
4. **Rewrite integration test** for c0 backend

### v4 Vision
- **RAM index** for millions of products (sub-millisecond lookup)
- **Multi-tenancy**: Supabase OAuth + multi-user Neo4j
- **WhatsApp integration** via Hermes gateway
- **Exponential decay** for entity activation
- **Fast/Slow storage** split (RAM cache + Neo4j)
- **Contradiction auto-resolution**
- **Standardized output tables** for agent↔software communication

---

## Git History & Key Commits

```
27ec253 feat: comprehensive test suite + namespace fix         ← CURRENT
3863c2e fix: handle consolidation budget error in c0 mode
68c816f fix: walk parser, C0Registry canonical name cache
e877662 fix: C0Client — force-create, list_concepts, integration
6001a64 feat: c0 fully operational — compiled binary, Docker fix
8e07750 refactor: hardened C0Client — correct CLI commands
844bfc3 fix: docker compose — neo4j community edition
c9af336 fix: alias dedup, non-contiguous fuzzy, temporal filter
9c2a347 feat: Mirror Brain v3.1 — internal reasoner + skills
47c2b92 feat: MCP server — 23 tools via FastMCP
7d1badc feat: v3 — procedural memory, consolidation, predictive
a6ce5fa test: real end-to-end v2 with DeepSeek
3eb9dda test: comprehensive v2 suite — 150 assertions
0ae127d feat: Mirror Brain v2 — agentic pipeline with tools
8ece3fe feat: Docker Compose + Hermes Agent skill
424bc0d test: comprehensive test suite — 140+ tests
edef5b9 docs: v1.0 README — complete architecture
b07f726 feat: Link Evolution — LLM #2 completes cognitive loop
d537c5a feat: Context Fetcher — intelligent memory retrieval
474128c feat: A-MEM Note Constructor with DeepSeek
785a89c feat: Mirror Brain v1.0 — core entity system
```

### Version Evolution

| Version | Backend | Tools | Key Feature |
|---|---|---|---|
| v1.0 | SQLite | 9 modules | Core entity system, criteria, registry |
| v2.0 | SQLite + c0 | 15 tools | Agentic pipeline, minimaps, themes |
| v3.0 | Neo4j + c0 + Ollama | 28 tools | Docker, MCP server, procedural memory |
| v3.1 | Neo4j + c0 + Ollama | **38 tools** | Cache, products, soul, buyer search |

---

## Quick Reference Card

```bash
# Start everything
docker compose -f docker/docker-compose.unified.yml up -d
PYTHONPATH="$PWD/src" python -B mcp_server.py --port 8765 &

# Run tests
PYTHONPATH="$PWD/src" python tests/test_v3_comprehensive.py

# Check health
docker ps --filter "name=mirrorbrain"
curl -X GET http://127.0.0.1:8765/mcp -H "Accept: text/event-stream"

# Restart MCP
pkill -f mcp_server.py
PYTHONPATH="$PWD/src" python -B mcp_server.py --port 8765 &

# Git workflow
cd /c/Users/gusta/mirror-brain
git add -A
git commit -m "feat: description"
git push origin main
```

---

> **"Lo que se quería lograr, lo que se logró, lo que se testeó, cómo se levantó, cómo se levanta, cómo se reinicia."**
>
> — Julián, Junio 2026

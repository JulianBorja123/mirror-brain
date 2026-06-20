# Mirror Brain → c0 Integration Plan

> **For Hermes:** Implement this plan task-by-task in order. Each task is self-contained with exact files and verification steps.

**Goal:** Migrate Mirror Brain from SQLite storage to c0 (Neo4j + Ollama embeddings) as the single source of truth, achieving the original architecture: c0 as storage engine, Mirror Brain as intelligent reasoning layer.

**Architecture:**
```
MirrorBrainAgent (Python) → reasoning, pipeline, MCP tools
        ↓ subprocess
C0Client (Python wrapper) → thin CLI subprocess layer
        ↓
c0 (Rust binary) → Neo4j (graph) + Ollama/nomic-embed-text (vectors)
```

**Tech Stack:** Python 3.11, c0 CLI (Rust), Neo4j Community, Ollama + nomic-embed-text, Docker Compose

**Files affected:** 14 of 18 modules touch SQLite directly. The refactor replaces `EntityRegistry` (SQLite) with `C0Registry` (c0/Neo4j), rewrites `tools.py` and all v3 modules (`procedural.py`, `consolidation.py`, `predictive.py`, `internal_reasoner.py`, `link_evolution.py`, `context_fetcher.py`, `multimodal.py`, `skills.py`, `note_constructor.py`), updates `mcp_server.py`, and removes `schema.py`. `agent.py` gets a registry swap. `preprocessor.py`, `models.py`, `criteria.py`, `__init__.py` stay mostly untouched.

**Total estimated tasks:** 28 | **Risk:** High (large surface area) | **Rollback:** Git branch `feat/c0-backend`, SQLite code preserved until Phase 7 cleanup.

---

## Phase 0: Prerequisites

### Task 0.1: Compile c0 binary (Linux target)

**Objective:** Produce a working `c0` Linux ELF binary for Docker

**Files:**
- `/c/Users/gusta/c0/target/release/c0` (output binary)

**Step 1: Verify Docker Rust nightly image builds c0**

Run (already attempted, likely succeeded on nightly):
```bash
docker run --rm -v //c/Users/gusta/c0://app -w //app \
  rustlang/rust:nightly-slim bash -c \
  "apt-get update -qq && apt-get install -y -qq pkg-config libssl-dev && cargo build --release"
```

**Step 2: Copy binary to host and verify**

```bash
ls -lh /c/Users/gusta/c0/target/release/c0
file /c/Users/gusta/c0/target/release/c0
# Expected: ELF 64-bit LSB executable, x86-64
```

**Validation:** Binary exists, is ELF x86-64, non-zero size.

---

### Task 0.2: Fix Docker Compose for c0

**Objective:** c0 container starts correctly with all dependencies (netcat, c0 binary)

**Files:**
- Modify: `docker/docker-compose.unified.yml` (c0 service)

**Step 1: Update c0 Dockerfile/service to include netcat**

Change c0 image from `debian:bookworm-slim` to a custom one that has `netcat-openbsd` pre-installed, OR add `apt-get install -y netcat-openbsd` to entrypoint before the `nc` loop.

Option A — add to entrypoint:
```yaml
entrypoint:
  - /bin/bash
  - -c
  - |
    set -e
    apt-get update -qq && apt-get install -y -qq netcat-openbsd
    echo "[c0] Waiting for Neo4j connectivity..."
    # ... rest of entrypoint
```

**Step 2: Restart stack and verify**

```bash
docker compose -f docker/docker-compose.unified.yml down
docker compose -f docker/docker-compose.unified.yml up -d
sleep 10
docker logs mirrorbrain-c0 --tail 5
# Expected: "[c0] Neo4j is reachable. Initialising namespace 'mirrorbrain'..."
# Expected: "[c0] Initialisation complete."
```

**Validation:** `docker ps` shows all 4 containers healthy, `docker logs mirrorbrain-c0` shows successful init.

---

### Task 0.3: Verify c0 CLI commands work end-to-end

**Objective:** Confirm c0 can create, search, walk, and relate entities in Neo4j via Ollama embeddings

**Step 1: Health check**

```bash
docker exec mirrorbrain-c0 sh -c "c0 health 2>&1"
# Expected: Neo4j connected, Ollama reachable, namespace 'mirrorbrain' exists
```

**Step 2: CRUD test**

```bash
docker exec mirrorbrain-c0 sh -c "c0 add concept 'Test Entity' --description 'A test concept for integration'"
docker exec mirrorbrain-c0 sh -c "c0 search 'test entity' --limit 5"
# Expected: Returns the created entity
```

**Step 3: Walk test**

```bash
docker exec mirrorbrain-c0 sh -c "c0 add concept 'Related Entity'"
docker exec mirrorbrain-c0 sh -c "c0 relate 'Test Entity' related_to 'Related Entity'"
docker exec mirrorbrain-c0 sh -c "c0 walk 'Test Entity' --depth 1"
# Expected: Shows both entities and the relationship
```

**Validation:** All three commands return valid output without errors.

---

## Phase 1: C0Client Hardening

### Task 1.1: Map c0 CLI to Python methods

**Objective:** Fix `C0Client` methods to use real c0 subcommands and parse actual output

**Files:**
- Modify: `src/mirror_brain/c0_client.py`

**Current issues in c0_client.py:**
- `create()` uses `c0 create` → should be `c0 add concept`
- `search()` should use `c0 search --json` for machine-parseable output
- `walk()` output parsing may not match c0's actual format
- Missing: `c0 relate`, `c0 supersede`, `c0 find`, `c0 extract-concepts`

**Step 1: Test each c0 command manually and capture output format**

```bash
# Test all commands we'll wrap
docker exec mirrorbrain-c0 sh -c "c0 add concept 'Julian' --description 'user'"
docker exec mirrorbrain-c0 sh -c "c0 search 'Julian' --limit 2"
docker exec mirrorbrain-c0 sh -c "c0 walk 'Julian' --depth 1"
docker exec mirrorbrain-c0 sh -c "c0 relate 'Julian' owns 'Mirror Brain'"
docker exec mirrorbrain-c0 sh -c "c0 supersede 'Julian' --with 'Julian v2'"
docker exec mirrorbrain-c0 sh -c "c0 find 'Mirror'"
docker exec mirrorbrain-c0 sh -c "c0 extract-concepts 'Julian built Mirror Brain with Hermes' --limit 5"
```

**Step 2: Rewrite C0Client methods**

Complete API surface:
```python
class C0Client:
    # CRUD
    def create_concept(name, description=None, source=None) → str  # returns name
    def relate(from_name, to_name, relation_type) → None
    def describe(name, description) → None
    def supersede(old_name, new_name, as_of=None) → None
    def invalidate(name) → None

    # Search
    def search(query, limit=10, threshold=0.3) → list[dict]
    def find(pattern) → list[dict]
    def walk(start, depth=2, as_of=None) → list[dict]

    # LLM-powered
    def extract_concepts(text, limit=10) → list[dict]

    # Health
    def health() → dict

    # Export
    def export(format="json") → str
```

**Validation:** Each method tested with real c0 Docker container, returns correct data types.

---

### Task 1.2: Add error handling and retries to C0Client

**Objective:** C0Client handles subprocess failures gracefully (c0 binary not found, Neo4j down, timeouts)

**Step 1: Add retry decorator for transient failures**

```python
import time

def _run_with_retry(self, *args, max_retries=3, timeout=30):
    for attempt in range(max_retries):
        try:
            return self._run(*args, timeout=timeout)
        except (subprocess.TimeoutExpired, RuntimeError) as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(1 * (attempt + 1))
```

**Step 2: Add graceful degradation**

- If c0 binary not found → raise `C0NotAvailableError`
- If Neo4j unreachable → raise `C0BackendError`
- If Ollama down → search degrades to keyword-only

**Validation:** Test with stopped Neo4j → graceful error, stopped c0 → graceful error.

---

## Phase 2: C0Registry (replaces EntityRegistry)

### Task 2.1: Create C0Registry class

**Objective:** New registry that wraps C0Client with the same Python API as EntityRegistry

**Files:**
- Create: `src/mirror_brain/c0_registry.py`

**API surface (same method signatures as EntityRegistry):**
```python
class C0Registry:
    def __init__(self, c0_client: C0Client):
        self.c0 = c0_client

    def create(self, name: str, type_: str) → tuple[str, str]  # (uuid, c0_ref)
    def resolve(self, name: str) → Optional[str]  # uuid or None
    def get(self, entity_uuid: str) → Optional[dict]
    def get_aliases(self, entity_uuid: str) → list[dict]
    def add_alias(self, alias: str, entity_uuid: str, source="manual", confidence=1.0)
    def add_relation(self, from_uuid, to_uuid, relation_type, source_text="")
    def get_relations(self, entity_uuid: str) → list[dict]
    def search_relations(self, from_uuid=None, to_uuid=None, relation_type=None) → list[dict]
    def get_all_entities(self, limit=100) → list[dict]
    def update_entity(self, uuid, **kwargs)
    def merge_entity(self, uuid, merged_into_uuid)
```

**Key design decisions:**
- UUIDs are auto-generated (Python `uuid.uuid4()`) and stored as c0 concept properties
- `c0 search` + `c0 walk` replace SQL queries
- Relations stored via `c0 relate`, retrieved via `c0 walk`
- Aliases stored as c0 concept metadata or separate linked concepts

**Validation:** Unit test creating 5 entities, resolving by alias, walking relations.

---

### Task 2.2: Swap EntityRegistry → C0Registry in agent.py

**Objective:** MirrorBrainAgent uses C0Registry instead of EntityRegistry

**Files:**
- Modify: `src/mirror_brain/agent.py` (lines 110-118)
- Modify: `mcp_server.py` (lines 23-40)

**Step 1: Update agent constructor**

```python
# Before
from .registry import EntityRegistry
def __init__(self, registry: EntityRegistry, llm_call, ...):

# After
from .c0_registry import C0Registry
def __init__(self, registry: C0Registry, llm_call, c0_client=None, ...):
```

**Step 2: Update MCP server initialization**

```python
from mirror_brain.c0_client import C0Client
from mirror_brain.c0_registry import C0Registry

c0 = C0Client(namespace="mirrorbrain")
_registry = C0Registry(c0)
_agent = MirrorBrainAgent(_registry, _call_deepseek, c0_client=c0)
```

**Validation:** `python -c "from mirror_brain.c0_registry import C0Registry; print('import OK')"` — no import errors.

---

## Phase 3: Tools Migration

### Task 3.1: Rewrite SearchTools.search_fuzzy for c0

**Objective:** `search_fuzzy` uses c0 search + Python post-filtering instead of SQL LIKE

**Files:**
- Modify: `src/mirror_brain/tools.py` (lines 161-220)

**Strategy:** Call `c0 search` with the query, then filter results in Python for token overlap. c0's hybrid search will return semantically close matches; we add the non-contiguous word matching on top.

**Step 1: Write unit test**

```python
def test_search_fuzzy_c0():
    c0 = C0Client()
    reg = C0Registry(c0)
    reg.create("Gustavo Julian Barrios Borja", "person")
    tools = SearchTools()
    results = tools.search_fuzzy(reg, "Gustavo Barrios")
    assert len(results) >= 1
    assert results[0]["canonical_name"] == "Gustavo Julian Barrios Borja"
```

**Step 2: Implement**

Replace SQL LIKE logic with:
```python
c0_results = c0.search(name, limit=20)
# Filter: all query tokens must appear in name or aliases
```

**Validation:** Test passes with real c0 Docker container.

---

### Task 3.2: Rewrite SearchTools.search_semantic for c0

**Objective:** `search_semantic` now uses c0 hybrid search (was no-op with `c0=None`)

**Files:**
- Modify: `src/mirror_brain/tools.py` (lines 34-60)

**Step 1: Remove `if c0 is None: return []` guard**

Now that c0 is always available, this method should always work.

**Step 2: Use c0.search with proper parameters**

```python
results = c0.search(query, limit=limit)
```

**Validation:** `search_semantic("Mirror Brain architecture")` returns relevant concepts.

---

### Task 3.3: Rewrite remaining search tools

**Objective:** Migrate `search_exact`, `search_by_emotion`, `search_temporal`, `search_temporal_range`, `search_raw_text`, `get_minimap`, `get_weekly_summary`, `get_monthly_summary`, `search_procedures`, `get_procedure`, `search_graph_corpus`, `get_entity_profile`, `search_cycles`, `get_trend`, `search_anomalies`, `find_correlations` to use c0/Neo4j

**Files:**
- Modify: `src/mirror_brain/tools.py` (all methods)

**Strategy per tool group:**

| Tool group | c0 equivalent | Notes |
|---|---|---|
| Exact search | `c0 search --keyword-only` | Direct keyword match |
| Temporal search | `c0 walk --as-of <date>` | c0 bi-temporal |
| Emotion search | Neo4j property lookup | Store emotions as concept properties |
| Minimap | `c0 walk --depth 2` | Graph neighborhood |
| Summaries | Neo4j weekly_summary nodes | Create summary concepts in c0 |
| Procedures | `c0 walk` + property match | Procedures as concept types |
| Metrics (cycles/trends/anomalies) | Time-series properties on concepts | Store metric history in Neo4j |

**Validation:** Each tool tested individually with real c0 data.

---

## Phase 4: Module Migration

### Task 4.1: Migrate ProceduralMemory

**Objective:** Replace SQLite procedure tables with c0 concepts + relations

**Files:**
- Modify: `src/mirror_brain/procedural.py`

**Strategy:**
- Procedures → c0 concepts with type `procedure`
- Procedure steps → linked concepts with `step_of` relations
- Procedure traces → concepts with `trace_of` relations + timestamp properties
- `search_procedures()` → `c0 search` with type filter
- `record_trace()` → `c0 add concept` + `c0 relate`

**Validation:** Learn a procedure, search for it, verify trace recorded.

---

### Task 4.2: Migrate Consolidation

**Objective:** Replace SQLite `daily_index`, `weekly_summaries`, `consolidation_snapshots` with c0 concepts

**Files:**
- Modify: `src/mirror_brain/consolidation.py`

**Strategy:**
- Daily entries → c0 concepts with type `daily_summary` and date property
- Weekly summaries → c0 concepts aggregating daily nodes via `summarizes` relations
- Memory budget enforcement → property-based queries on c0 concepts

**Validation:** Run consolidation cycle, verify summaries created in c0.

---

### Task 4.3: Migrate PredictiveEngine

**Objective:** Replace SQLite `predictive_projections`, `project_metrics` with c0 concept properties

**Files:**
- Modify: `src/mirror_brain/predictive.py`

**Strategy:**
- Metric time-series → numeric properties on entity concepts (JSON array or multiple dated snapshots)
- Cycles detection → query metric history via `c0 walk` + Python analysis
- Projections → store as concept properties `projected_{metric}`

**Validation:** Detect cycles in entity metric history, project next value.

---

### Task 4.4: Migrate InternalReasoner + SkillManager

**Objective:** Replace SQLite `reasoning_trail`, `skill_entries` with c0 concepts

**Files:**
- Modify: `src/mirror_brain/internal_reasoner.py`
- Modify: `src/mirror_brain/skills.py`

**Strategy:**
- Reasoning trail entries → c0 concepts with type `reasoning_step`
- Skill entries → c0 concepts with type `skill`
- Cross-phase queries → `c0 walk` on reasoning chains

**Validation:** Run reasoner cycle, verify trail recorded in c0.

---

### Task 4.5: Migrate ContextFetcher + LinkEvolution

**Objective:** Replace SQLite queries with c0 search/walk

**Files:**
- Modify: `src/mirror_brain/context_fetcher.py`
- Modify: `src/mirror_brain/link_evolution.py`

**Strategy:**
- Context hints → map to `c0 search` / `c0 walk` calls
- Link evolution decisions → `c0 relate` + `c0 supersede`
- Entity resolution → `c0 find`

**Validation:** Fetch context for a search hint, evolve a link, verify in c0.

---

### Task 4.6: Migrate MultiModal + NoteConstructor

**Objective:** Replace SQLite `media_entries`, `raw_texts` with c0 concepts

**Files:**
- Modify: `src/mirror_brain/multimodal.py`
- Modify: `src/mirror_brain/note_constructor.py`

**Strategy:**
- Media entries → c0 concepts with type `media` + metadata properties
- Raw texts → c0 concepts with type `raw_text` + content property
- Note construction → uses C0Registry.create() for entities

**Validation:** Ingest text + audio, verify media concepts created in c0.

---

## Phase 5: MCP Server Update

### Task 5.1: Update MCP server initialization and tools

**Objective:** MCP server starts with C0Registry, all 27 tools work against c0

**Files:**
- Modify: `mcp_server.py`

**Step 1: Change imports and initialization**

```python
from mirror_brain.c0_client import C0Client
from mirror_brain.c0_registry import C0Registry

c0 = C0Client(namespace="mirrorbrain")
_registry = C0Registry(c0)
_agent = MirrorBrainAgent(_registry, _call_deepseek, c0_client=c0)
```

**Step 2: Update mb_search_semantic to use c0**

Remove `None` c0_client argument — now always passes real c0.

**Step 3: Start server and verify all tools**

```bash
python mcp_server.py --port 8765
# Test: mb_health, mb_search_fuzzy, mb_search_semantic, mb_ingest
```

**Validation:** All 27 tools return valid results from c0.

---

## Phase 6: Cleanup

### Task 6.1: Remove SQLite dependencies

**Objective:** Delete `schema.py`, remove `sqlite3` imports, delete `EntityRegistry`

**Files:**
- Delete: `src/mirror_brain/schema.py`
- Delete: `src/mirror_brain/registry.py` (or keep as deprecated wrapper)
- Modify: All files with `import sqlite3` or `registry.db` → remove

**Step 1: Search for remaining sqlite3 references**

```bash
grep -r "sqlite3\|registry\.db\|\.execute(" src/mirror_brain/
```

**Step 2: Remove each reference**

Replace `registry.db.execute(...)` with C0Registry method calls.

**Validation:** `grep -r "sqlite3" src/` returns zero results.

---

### Task 6.2: Update tests

**Objective:** Test suite runs against c0 Docker stack

**Files:**
- Modify: `tests/test_unit.py`
- Modify: `tests/test_pipeline.py`
- Create: `tests/test_c0_integration.py`

**Strategy:**
- Unit tests that touched SQLite → rewrite for C0Registry
- Pipeline tests → run against Docker c0
- New integration tests → CRUD, search, walk, versioning

**Validation:** `pytest tests/ -v` — all tests pass.

---

### Task 6.3: Update documentation

**Objective:** README, Hermes skill, and Obsidian notes reflect c0 backend

**Files:**
- Modify: `README.md`
- Modify: `hermes-skill/SKILL.md`
- Modify: Obsidian `Mirror-Brain-Process.md`

**Validation:** Docs accurately describe architecture and setup.

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| c0 binary doesn't compile | Use nightly Rust; fallback to pre-built release if available |
| c0 commands don't match wrapper assumptions | Phase 1 maps actual CLI output before coding |
| Data loss during migration | New DB namespace; old SQLite DBs preserved untouched |
| Performance regression | c0 hybrid search is faster than SQLite for vector ops |
| Module API breakage | C0Registry mirrors EntityRegistry method signatures |

---

## Execution Order

1. Phase 0 (prerequisites) — c0 binary + Docker
2. Phase 1 (C0Client) — wrapper hardening
3. Phase 2 (C0Registry) — new registry class + agent swap
4. Phase 3 (tools.py) — search tools migration
5. Phase 4 (modules) — procedural, consolidation, predictive, etc.
6. Phase 5 (MCP server) — final integration
7. Phase 6 (cleanup) — remove SQLite, tests, docs

# Mirror Brain v2 — Usage Guide

## Quickstart

```bash
git clone https://github.com/JulianBorja123/mirror-brain.git
cd mirror-brain
pip install -e .  # or just: export PYTHONPATH=src
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│              MirrorBrainAgent                    │
│                                                 │
│  process(text)                                  │
│    │                                            │
│    ├─ 0. save_raw_text()                        │
│    ├─ 0.5. TextPreprocessor                     │
│    │     ├─ estimate_complexity()                │
│    │     └─ split_by_themes()                    │
│    │                                            │
│    ├─ 1. ACTIVATION (7 tools)                   │
│    │     ├─ search_temporal()    ← always        │
│    │     ├─ get_weekly_summary() ← always        │
│    │     ├─ get_minimap()        ← per entity    │
│    │     ├─ search_fuzzy()       ← per entity    │
│    │     ├─ search_by_emotion()  ← if emotional  │
│    │     ├─ search_semantic()    ← if c0 up      │
│    │     └─ search_raw_text()    ← if requested  │
│    │                                            │
│    ├─ 2. DECIDE (1 LLM call)                    │
│    │     prompt = system + text + context        │
│    │            + past_decisions                 │
│    │                                            │
│    ├─ 3. LOOP (max 3)                           │
│    │     if LLM needs_more_search → re-search    │
│    │                                            │
│    └─ 4. EXECUTE (confidence gates)              │
│          >0.85 → auto  | 0.6-0.85 → flag          │
└─────────────────────────────────────────────────┘
```

## Basic Usage

```python
from mirror_brain.registry import EntityRegistry
from mirror_brain.agent import MirrorBrainAgent

# Your LLM callable
def my_llm(prompt: str) -> str:
    # call DeepSeek, OpenAI, etc.
    ...

# Initialize
reg = EntityRegistry("my_memory.db")
agent = MirrorBrainAgent(
    registry=reg,
    llm_call=my_llm,
    max_loops=3,
)

# Seed initial entities
reg.create("Mirror Brain", "project")

# Ingest text
report = agent.process("Hoy avancé en Mirror Brain v2...")
print(report["auto"])      # decisions auto-executed
print(report["flagged"])   # decisions flagged for review
print(report["summary"])   # 1-sentence LLM summary
```

## Seed Daily Summaries for Temporal Context

```python
from datetime import date, timedelta

today = date.today()
for i in range(21):
    d = (today - timedelta(days=i)).isoformat()
    reg.db.execute(
        "INSERT INTO daily_index (date, summary, emotional_arc, key_entities, key_decisions, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (d, json.dumps({"es": "..."}), json.dumps([0.3,0.2,0.3,0.5]),
         json.dumps(["Mirror Brain"]), json.dumps(["avance"]), d)
    )
reg.db.commit()
```

## The 7 Tools

```python
from mirror_brain.tools import SearchTools
tools = SearchTools()

# 1. Semantic search (requires c0 + Ollama running)
results = tools.search_semantic(registry, c0_client, "query text", limit=10)

# 2. Emotional search
high_oxytocin = tools.search_by_emotion(registry, "oxytocin", threshold=0.5)

# 3. Temporal search
this_week = tools.search_temporal(registry, days_ago=0, window=7)
three_days_ago = tools.search_temporal(registry, days_ago=3, window=1)

# 4. Fuzzy name search
matches = tools.search_fuzzy(registry, "Rom")  # → Romina Gonzalez, Rómulo...

# 5. Entity minimap
overview = tools.get_minimap(registry, "c0")
# → {canonical_name, type, aliases, relations_count, recent_activity, emotional_profile}

# 6. Weekly summary
week = tools.get_weekly_summary(registry)
# → {week_start, days_covered, dominant_emotion, average_arc, key_entities}

# 7. Raw text search
raw_hits = tools.search_raw_text(registry, "Docker")
```

## Text Preprocessor

```python
from mirror_brain.preprocessor import TextPreprocessor
pp = TextPreprocessor()

# Split text into themes
themes = pp.split_by_themes(text)        # heuristic (no LLM)
themes = pp.split_by_themes(text, llm)   # LLM-powered

# Canonicalize for matching
clean = pp.canonicalize(text)

# Estimate complexity
info = pp.estimate_complexity(text)
# → {char_count, estimated_themes, emotional_density, entity_density}
```

## Schema (7 tables)

```
entities          — uuid, canonical_name, c0_ref, type, status, created_at
aliases           — alias, entity_uuid, source, confidence
daily_index       — date, summary, emotional_arc, key_entities, key_decisions
relations         — from_uuid, to_uuid, relation_type, source_text, created_at
reasoning_trail   — entity_uuid, action, confidence, reasoning, source, timestamp
raw_texts    🆕   — uuid, content, char_count, source, created_at
weekly_summaries 🆕 — week_start, week_end, summary, emotional_profile, ...
```

## Confidence Gates

| Confidence | Action |
|---|---|
| ≥ 0.85 | **Auto-execute** — entity created, link added, alias registered |
| 0.60–0.84 | **Flagged** — stored for human review, not auto-executed |
| < 0.60 | **Skipped** — discarded |

## Docker Stack (for c0 + Ollama + Neo4j)

```bash
docker compose -f docker/docker-compose.unified.yml up -d
# Starts: c0-neo4j, c0-ollama, c0-builder
# Provides: hybrid search (exact → keyword → vector RRF)
```

## Integration with Hermes Agent

See `hermes-skill/` directory for skill definition and scripts.
MCP server coming in v3.

## Real Test Results (2026-06-19)

| Metric | Value |
|---|---|
| Texts tested | 5 (50 to 1456 chars) |
| Crashes | 0 |
| Auto decisions | 74 |
| Flagged | 1 |
| Total tokens | 17,405 |
| Cost (DeepSeek) | $0.0037 USD |
| Internal clock | ✅ Perfect |
| All 7 tools | ✅ Working |
| Avg latency/text | 13.2s |

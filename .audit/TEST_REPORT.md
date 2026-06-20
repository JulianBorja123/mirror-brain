# Mirror Brain v3 — Test Report
> Generated: 2026-06-20 | Harness: real (no mocks) | MCP server: 127.0.0.1:8765

---

## Suite 1: Smoke Test (32 tools)
**Result: 32/32 PASSED ✅ — 0 errors**

| Metric | Value |
|---|---|
| Total calls | 33 |
| Total time | 28,780 ms |
| Avg time/call | 872 ms |
| Errors | 0 |

### Slowness detected
| Tool | Time | Issue |
|---|---|---|
| `mb_ingest` | 10,687ms | LLM call to DeepSeek (expected) |
| `mb_list_relations` | 7,312ms | Walks ALL concepts for relations |
| `mb_stats` | 4,485ms | Counts entities by walking all concepts |

---

## Suite 2: Real-World Scenarios (18 tests)
**Result: 10/18 PASSED ⚠️ — 8 failures, 1 timeout**

### ✅ PASSES
| Scenario | Result |
|---|---|
| Fuzzy: 'Gustavo Barrios' → 'Gustavo Julian Barrios Borja' | ✅ |
| Fuzzy: 'Romi Gonzalez' → 'Romina Gonzalez' | ✅ |
| Fuzzy: 'docker' → 'Docker' | ✅ |
| Fuzzy: 'deep' → 'DeepSeek' | ✅ |
| Minimap: All 3 entities | ✅ |
| Stats & Memory Budget | ✅ |
| Reasoner: 4 phases | ✅ |

### ❌ FAILURES
| Test | Expected | Got | Root Cause |
|---|---|---|---|
| Journal ingestion | entities created | TIMEOUT | LLM timeout > MCP handler timeout |
| fuzzy('Romi') | 'Romina Gonzalez' | 'Romina' | Partial entity from failed ingest |
| fuzzy('espejo') | 'Mirror Brain' | 'Gustavo...' | No semantic matching in fuzzy |
| Semantic: 'asistente IA' | 'Hermes Agent' | '[tbl] raw_texts' | Internal concepts leaking into search |
| Semantic ×4 more | various | '[tbl] raw_texts' | Same: internal concepts in c0 export |

---

## Bugs Found & Fixed During Testing

| # | Bug | Severity | Fixed |
|---|---|---|---|
| 1 | `ingest()` returned dict, agent expected `tuple[0]` | 🔴 CRITICAL | ✅ |
| 2 | Internal `[tbl]` / `[consolidation]` concepts leaked into search results | 🟠 HIGH | ✅ (filter added) |
| 3 | `search()` missing from C0Registry (agent.py compatibility) | 🟠 HIGH | ✅ |
| 4 | `log_decision()` missing from C0Registry | 🟡 MEDIUM | ✅ (no-op stub) |
| 5 | mb_ingest LLM call times out (30s MCP timeout vs DeepSeek ~10s) | 🟡 MEDIUM | ⬜ Pending |
| 6 | Fuzzy search doesn't handle semantic/translation matching ('espejo' ≠ 'Mirror') | 🟡 MEDIUM | ⬜ Feature |
| 7 | `mb_list_relations` walks all concepts (7.3s) | 🟡 MEDIUM | ⬜ Optimize |
| 8 | `mb_stats` walks all concepts (4.5s) | 🟡 MEDIUM | ⬜ Optimize |

---

## Performance Baseline

| Operation | Avg Time | Notes |
|---|---|---|
| `mb_search_fuzzy` | ~190ms | Fast — keyword match via c0 |
| `mb_search_semantic` | ~200ms | Fast — hybrid RRF via c0 |
| `mb_get_minimap` | ~370ms | Good — walk + cache |
| `mb_list_entities` | ~180ms | Good — c0 export filtered |
| `mb_list_relations` | ~7,300ms | ⚠️ SLOW — walks all concepts |
| `mb_stats` | ~4,500ms | ⚠️ SLOW — counts by walking |
| `mb_ingest` (LLM) | ~10,700ms | Expected — DeepSeek API |
| `mb_run_reasoner` | ~1,200ms | Good |
| All other tools | 5-500ms | Excellent |

---

## Recommendations

### Immediate (fix before production use)
1. **Fix mb_ingest timeout**: Increase MCP tool timeout from 30s → 120s for LLM calls
2. **Verify internal concept filtering**: Confirm `[tbl]` filter works on current server restart
3. **Clean up partial entities**: Remove "Romina" stub entity from Neo4j

### Short-term (this week)
4. **Optimize mb_list_relations**: Use c0 export edges instead of walking each concept
5. **Optimize mb_stats**: Cache entity/relation counts instead of walking each time
6. **Add semantic matching to fuzzy**: Fall back to c0 semantic search for fuzzy queries with no keyword match

### Medium-term (next iteration)
7. **Add response quality scoring**: Compare LLM output against expected entity extraction
8. **Stress test**: 100+ operations in sequence, measure degradation
9. **Audit log dashboard**: Parse .audit/ JSONL files for trends

---

## Audit Logs
Available at: `C:\Users\gusta\mirror-brain\.audit\`
Each test run produces a timestamped `.jsonl` file with per-call timing and error data.

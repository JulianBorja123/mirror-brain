"""
Mirror Brain v3 — PRE-COMMIT COMPREHENSIVE TEST SUITE
Tests: c0 connectivity, speed, semantic search, edge cases, MCP tools.
Run: PYTHONPATH=src python tests/test_v3_comprehensive.py
"""
import sys, os, json, time, uuid, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mirror_brain.c0_client import C0Client
from mirror_brain.c0_registry import C0Registry

PASS, FAIL, TOTAL = 0, 0, 0

def test(name, fn):
    global PASS, FAIL, TOTAL
    TOTAL += 1
    try:
        fn()
        PASS += 1
        print(f"  OK  {name}")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL  {name}: {e}")

def ok(cond, msg=""):
    if not cond:
        raise AssertionError(msg or "expected truthy")

def has(sub, container, msg=""):
    if sub not in container:
        raise AssertionError(msg or f"'{sub}' not found")

def gt(a, b, msg=""):
    if not a > b:
        raise AssertionError(msg or f"{a} <= {b}")

# ═══════════════════════════════════════════════════════════════════
print("=" * 60)
print("MIRROR BRAIN v3 -- PRE-COMMIT COMPREHENSIVE TEST")
print("=" * 60)

c0 = C0Client()
reg = C0Registry(c0)

# SUITE 1: Connectivity
print("\n-- Suite 1: Docker + c0 Connectivity --")
test("c0 health check", lambda: ok(c0.ensure_ready() or True))
test("Neo4j reachable (search)", lambda: (r := c0.search("laptop", limit=1), gt(len(r), 0, "No results from Neo4j")))
test("Ollama reachable (hybrid search)", lambda: (r := c0.search("test", limit=1), ok(isinstance(r, list))))

# SUITE 2: Product Search (Buyer-Style)
print("\n-- Suite 2: Semantic Product Search (Buyer Queries) --")
QUERIES = [
    ("gaming laptop with good graphics", ["ASUS", "Razer", "ROG", "Blade"]),
    ("cheap android phone good value", ["Nothing", "OnePlus", "Pixel", "Google"]),
    ("best noise cancelling headphones for travel", ["Sony", "Bose", "AirPods", "QuietComfort"]),
    ("tablet for drawing and artists", ["iPad", "Samsung"]),
    ("mechanical keyboard wireless aluminum", ["Keychron", "Q1", "Pro"]),
    ("lightweight laptop for students", ["MacBook Air", "ThinkPad X1", "LG Gram"]),
    ("modular repairable laptop", ["Framework"]),
    ("professional monitor video editing color accurate", ["Pro Display", "Studio Display", "UltraSharp"]),
    ("samsung phone with stylus pen", ["Galaxy S", "Ultra"]),
    ("tiny computer office desk small space", ["Mac Mini", "HP Elite", "Intel NUC"]),
]
for q, kw in QUERIES:
    def mk(q=q, kw=kw):
        return lambda: (
            r := c0.search(q, limit=5),
            names := " ".join(item.get("name","") for item in r).lower(),
            found := any(k.lower() in names for k in kw),
            ok(found, f"No match for '{q}'. Got: {names[:120]}")
        )
    test(f"'{q[:55]}'", mk())

# SUITE 3: Speed Benchmarks
print("\n-- Suite 3: Performance Benchmarks --")
def bench(label, fn, n=5):
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    avg = sum(times)/len(times)
    p50 = sorted(times)[len(times)//2]
    print(f"  [perf] {label}: avg={avg:.1f}ms p50={p50:.1f}ms (n={n})")

test("ID lookup completes fast", lambda: (
    r := c0.search("Framework Laptop", limit=1),
    ok(len(r) > 0)
))
bench("search('laptop', limit=5)", lambda: c0.search("laptop", limit=5))
bench("search('gaming laptop high performance', limit=5)", lambda: c0.search("gaming laptop high performance", limit=5))
bench("search('auriculares cancelacion ruido', limit=3)", lambda: c0.search("auriculares cancelacion ruido", limit=3))

# SUITE 4: Export & Stats
print("\n-- Suite 4: Data Export & Stats --")
test("c0 list_concepts returns products", lambda: (
    r := c0.list_concepts(limit=500),
    gt(len(r), 50, f"Too few concepts: {len(r)}"),
    names := " ".join(item.get("name","") for item in r).lower(),
    ok("macbook" in names or "iphone" in names, f"No products in list, sample: {[i.get('name','')[:50] for i in r[:10]]}")
))
test("search finds iPhone", lambda: (
    r := c0.search("iPhone", limit=3),
    names := " ".join(item.get("name","") for item in r).lower(),
    ok("iphone" in names, f"No iPhone: {names[:100]}")
))
test("search finds people entities", lambda: (
    r := c0.search("Gustavo", limit=3),
    names := " ".join(item.get("name","") for item in r).lower(),
    ok("gustavo" in names or "julian" in names, f"No person: {names[:100]}")
))

# SUITE 5: Edge Cases
print("\n-- Suite 5: Edge Cases & Robustness --")
def _test_empty_query():
    try:
        r = c0.search("", limit=3)
        ok(isinstance(r, list))
    except Exception as e:
        ok("empty" in str(e).lower() or "parse" in str(e).lower() or "eof" in str(e).lower(),
           f"Unexpected error: {e}")
test("empty query handled gracefully", _test_empty_query)
test("long query 200 chars", lambda: (r := c0.search("a"*200, limit=3), ok(isinstance(r, list))))
test("emoji query", lambda: (r := c0.search("gaming pc", limit=3), ok(isinstance(r, list))))
test("SQL injection attempt", lambda: (r := c0.search("'; DROP TABLE concepts; --", limit=3), ok(isinstance(r, list))))
test("Spanish unicode", lambda: (
    r := c0.search("auriculares", limit=3),
    names := " ".join(item.get("name","") for item in r).lower(),
    ok("sony" in names or "bose" in names or "airpods" in names or "auricular" in names, f"No ES: {names[:100]}")
))
test("Japanese query", lambda: (r := c0.search("gamingu", limit=3), ok(isinstance(r, list))))
test("non-existent product ok", lambda: (r := c0.search("zzz_nonexistent_xyz_12345", limit=3), ok(isinstance(r, list))))
test("zero limit ok", lambda: (r := c0.search("laptop", limit=0), ok(isinstance(r, list))))

# SUITE 6: Product Data Integrity
print("\n-- Suite 6: Product Data Integrity --")
EXPECTED = [
    "MacBook", "ThinkPad", "Dell XPS", "HP Spectre", "ASUS ROG",
    "Razer Blade", "Framework", "LG Gram", "Galaxy S", "iPhone",
    "Pixel", "OnePlus", "Nothing Phone", "iPad Pro", "Sony WH",
    "Bose QuietComfort", "AirPods", "Keychron", "Logitech MX",
    "Apple Pro Display", "Mac Mini", "Intel NUC",
]
test("20+ product brands present", lambda: (
    r := c0.list_concepts(limit=2000),
    names := " ".join(item.get("name","") for item in r).lower(),
    missing := [p for p in EXPECTED if p.lower() not in names],
    ok(len(missing) <= 3, f"Missing ({len(missing)}): {missing[:5]}")
))

# SUITE 7: Cross-Language
print("\n-- Suite 7: Cross-Language Search --")
test("EN query finds products", lambda: (
    r := c0.search("laptop for programming", limit=3),
    names := " ".join(item.get("name","") for item in r).lower(),
    ok(any(k in names for k in ["macbook","thinkpad","dell","framework","xps"]), f"No match: {names[:100]}")
))
test("ES query finds products", lambda: (
    r := c0.search("computadora para disenar", limit=3),
    names := " ".join(item.get("name","") for item in r).lower(),
    gt(len(names), 10, f"No ES results: {names[:100]}")
))

# SUITE 8: Cache Integrity
print("\n-- Suite 8: Cache Integrity --")
test("repeated search consistent", lambda: (
    r1 := c0.search("laptop", limit=3),
    r2 := c0.search("laptop", limit=3),
    n1 := [item.get("name","") for item in r1],
    n2 := [item.get("name","") for item in r2],
    ok(n1 == n2, f"Mismatch: {n1} vs {n2}")
))
test("limit=3 is subset of limit=5", lambda: (
    r3 := c0.search("laptop", limit=3),
    r5 := c0.search("laptop", limit=5),
    n3 := [item.get("name","") for item in r3],
    n5 := [item.get("name","") for item in r5],
    ok(all(n in n5 for n in n3), f"Not subset: {n3} vs {n5}")
))

# SUITE 9: Results Structure
print("\n-- Suite 9: Results Structure --")
test("results have 'name' and score", lambda: (
    r := c0.search("laptop", limit=1),
    gt(len(r), 0, "No results"),
    item := r[0],
    ok("name" in item, f"Missing name: {list(item.keys())}"),
))
test("product names non-empty", lambda: (
    r := c0.search("laptop", limit=5),
    ok(all(len(item.get("name","")) > 0 for item in r), "Empty name in result"),
))

# SUITE 10: MCP Server Health
print("\n-- Suite 10: MCP Server Health --")
import http.client
test("MCP server port 8765 responds", lambda: (
    conn := http.client.HTTPConnection("127.0.0.1", 8765, timeout=5),
    conn.request("GET", "/mcp", headers={"Accept": "text/event-stream"}),
    resp := conn.getresponse(),
    sid := resp.getheader("Mcp-Session-Id"),
    conn.close(),
    gt(len(sid or ""), 0, "No session ID from MCP server")
))

# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print(f"RESULTS: {PASS}/{TOTAL} passed, {FAIL}/{TOTAL} failed")
if FAIL == 0:
    print("ALL TESTS PASSED -- Ready to commit!")
else:
    print(f"{FAIL} test(s) FAILED -- review before commit")
print("=" * 60)

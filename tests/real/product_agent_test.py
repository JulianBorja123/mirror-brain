#!/usr/bin/env python3
"""Mirror Brain v3 — Product Agent Test: 30 real tech products, exhaustive search."""
import sys, json, time
sys.path.insert(0, "C:/Users/gusta/mirror-brain/tests/real")
from harness import MCPClient

client = MCPClient()
client.init()
print(f"Server: Mirror Brain v3 | Session: {client.session_id[:16]}...")
print()

# ============================================================
# 30 REAL TECH PRODUCTS
# ============================================================
products = [
    # Laptops
    {"name":"MacBook Pro 16 M3 Max","price":"3499","category":"laptop","description":"Apple MacBook Pro 16-inch, M3 Max chip, 36GB RAM, 1TB SSD, Liquid Retina XDR display","tags":"apple,macbook,pro,laptop,workstation,premium","phrases":"professional laptop for developers;apple high end notebook;video editing machine;programming laptop;creative workstation"},
    {"name":"MacBook Air 15 M3","price":"1299","category":"laptop","description":"Apple MacBook Air 15-inch, M3 chip, 8GB RAM, 256GB SSD, lightweight","tags":"apple,macbook,air,laptop,lightweight,student","phrases":"light laptop for students;thin portable computer;everyday apple notebook;travel laptop"},
    {"name":"Dell XPS 15","price":"1999","category":"laptop","description":"Dell XPS 15, Intel i7-13700H, 16GB RAM, 512GB SSD, 15.6 OLED, Windows 11","tags":"dell,xps,laptop,windows,premium,oled","phrases":"windows premium laptop;business ultrabook;beautiful screen laptop;dell professional computer"},
    {"name":"ThinkPad X1 Carbon Gen 12","price":"1849","category":"laptop","description":"Lenovo ThinkPad X1 Carbon Gen 12, Intel i7-1365U, 16GB RAM, 512GB SSD, 14-inch, business","tags":"lenovo,thinkpad,laptop,business,lightweight,professional","phrases":"business laptop lightweight;corporate notebook;professional lenovo computer;durable business machine;executive laptop"},
    {"name":"ASUS ROG Zephyrus G14","price":"1599","category":"laptop","description":"ASUS ROG Zephyrus G14, AMD Ryzen 9 7940HS, RTX 4060, 16GB RAM, 1TB SSD, 14-inch 165Hz","tags":"asus,rog,gaming,laptop,amd,nvidia,high-refresh","phrases":"gaming laptop portable;powerful compact gaming machine;esports ready laptop;high fps gaming notebook"},
    {"name":"HP Spectre x360 14","price":"1649","category":"laptop","description":"HP Spectre x360 14, Intel i7-1355U, 16GB RAM, 1TB SSD, 14 OLED touch, 2-in-1 convertible","tags":"hp,spectre,laptop,convertible,touchscreen,premium","phrases":"convertible touch laptop;2 in 1 premium computer;hp flagship notebook;touchscreen business laptop"},
    {"name":"Framework Laptop 16","price":"1399","category":"laptop","description":"Framework Laptop 16, AMD Ryzen 7 7840HS, modular, user-repairable, customizable ports","tags":"framework,modular,laptop,repairable,amd,sustainable","phrases":"repairable modular laptop;sustainable computer;upgradeable notebook;customizable laptop;eco friendly computer"},
    {"name":"Razer Blade 16","price":"2999","category":"laptop","description":"Razer Blade 16, Intel i9-13950HX, RTX 4080, 32GB RAM, 1TB SSD, dual-mode mini-LED, gaming","tags":"razer,blade,gaming,laptop,premium,rtx4080","phrases":"high end gaming laptop;premium gaming machine;powerful razer notebook;desktop replacement laptop"},

    # Phones
    {"name":"iPhone 16 Pro Max","price":"1199","category":"phone","description":"Apple iPhone 16 Pro Max, A18 Pro chip, 256GB, 6.9-inch OLED, titanium, 48MP camera","tags":"apple,iphone,phone,premium,ios,camera","phrases":"best iphone;apple flagship phone;premium smartphone;professional camera phone;titanium phone"},
    {"name":"Samsung Galaxy S25 Ultra","price":"1299","category":"phone","description":"Samsung Galaxy S25 Ultra, Snapdragon 8 Gen 4, 256GB, 6.8-inch AMOLED, S Pen, 200MP camera","tags":"samsung,galaxy,phone,android,premium,camera","phrases":"best samsung phone;android flagship;stylus smartphone;zoom camera phone;premium android"},
    {"name":"Google Pixel 9 Pro","price":"999","category":"phone","description":"Google Pixel 9 Pro, Tensor G4, 128GB, 6.3-inch OLED, AI features, stock Android","tags":"google,pixel,phone,android,ai,camera","phrases":"google smartphone;best camera phone;pure android phone;AI phone;stock android"},
    {"name":"OnePlus 13","price":"799","category":"phone","description":"OnePlus 13, Snapdragon 8 Gen 4, 256GB, 6.7-inch OLED, 100W fast charging","tags":"oneplus,phone,android,fast-charging,value","phrases":"fast charging android phone;value flagship;oneplus smartphone;quick charge phone"},
    {"name":"Nothing Phone 3","price":"599","category":"phone","description":"Nothing Phone 3, Snapdragon 8s Gen 3, 128GB, 6.5-inch OLED, Glyph interface, unique design","tags":"nothing,phone,android,unique,design,midrange","phrases":"unique design phone;stylish smartphone;led notification phone;designer android phone"},
    {"name":"Xiaomi 15 Pro","price":"899","category":"phone","description":"Xiaomi 15 Pro, Snapdragon 8 Gen 4, 256GB, 6.7-inch AMOLED, Leica camera, 120W charging","tags":"xiaomi,phone,android,camera,fast-charging","phrases":"xiaomi flagship;leica camera phone;super fast charging;chinese premium phone"},

    # Tablets
    {"name":"iPad Pro M4 13","price":"1299","category":"tablet","description":"Apple iPad Pro 13-inch, M4 chip, 256GB, OLED display, Apple Pencil Pro support","tags":"apple,ipad,tablet,pro,oled,creative","phrases":"best tablet for artists;professional drawing tablet;ipad for designers;creative professional tool"},
    {"name":"Samsung Galaxy Tab S10 Ultra","price":"1199","category":"tablet","description":"Samsung Galaxy Tab S10 Ultra, Snapdragon 8 Gen 4, 256GB, 14.6-inch AMOLED, S Pen, Android","tags":"samsung,galaxy,tablet,android,large-display,stylus","phrases":"largest android tablet;samsung premium tablet;productivity tablet;big screen tablet"},
    {"name":"Microsoft Surface Pro 11","price":"1499","category":"tablet","description":"Microsoft Surface Pro 11, Snapdragon X Elite, 16GB RAM, 512GB SSD, 13-inch touch, Windows 11, detachable","tags":"microsoft,surface,tablet,windows,detachable,2in1","phrases":"windows tablet laptop;detachable computer;surface pro for work;2 in 1 windows pc"},

    # Desktop / Workstation
    {"name":"Mac Studio M3 Ultra","price":"3999","category":"desktop","description":"Apple Mac Studio, M3 Ultra chip, 64GB RAM, 1TB SSD, compact workstation, 6 Thunderbolt ports","tags":"apple,mac,desktop,workstation,professional,compact","phrases":"compact professional workstation;apple desktop for creators;video production machine;3d rendering desktop"},
    {"name":"Custom RTX 4090 Build","price":"3499","category":"desktop","description":"Custom gaming PC, Intel i9-14900K, RTX 4090 24GB, 64GB DDR5 RAM, 2TB NVMe SSD, liquid cooling","tags":"custom,gaming,desktop,rtx4090,nvidia,intel,high-end","phrases":"ultimate gaming pc;enthusiast desktop computer;4k gaming machine;custom built workstation;rtx 4090 build"},
    {"name":"HP Elite Mini 800 G9","price":"999","category":"desktop","description":"HP Elite Mini 800 G9, Intel i7-13700T, 16GB RAM, 512GB SSD, tiny form factor, business desktop","tags":"hp,elite,desktop,business,mini,compact","phrases":"tiny business computer;compact office desktop;mini pc for work;space saving computer"},

    # Monitors
    {"name":"Apple Pro Display XDR","price":"4999","category":"monitor","description":"Apple Pro Display XDR, 32-inch, 6K resolution, 1600 nits, reference monitor for professionals","tags":"apple,monitor,professional,6k,reference,hdr","phrases":"professional reference monitor;color accurate display;hdr monitor for creators;6k apple display"},
    {"name":"Samsung Odyssey OLED G9","price":"1799","category":"monitor","description":"Samsung Odyssey OLED G9, 49-inch curved, 5120x1440, 240Hz, OLED, gaming monitor","tags":"samsung,odyssey,monitor,gaming,ultrawide,oled,curved","phrases":"ultrawide gaming monitor;curved oled display;49 inch monitor;super ultrawide screen;immersive gaming display"},
    {"name":"Dell UltraSharp U3224KB","price":"3199","category":"monitor","description":"Dell UltraSharp U3224KB, 32-inch, 6K, IPS, Thunderbolt 4, built-in webcam, productivity","tags":"dell,ultrasharp,monitor,6k,ips,productivity","phrases":"productivity 6k monitor;dell professional display;thunderbolt monitor;sharp office screen"},

    # Audio
    {"name":"AirPods Pro 3","price":"249","category":"audio","description":"Apple AirPods Pro 3, H3 chip, active noise cancellation, spatial audio, USB-C, wireless earbuds","tags":"apple,airpods,earbuds,wireless,anc,spatial-audio","phrases":"best wireless earbuds;noise cancelling earphones;apple premium earbuds;spatial audio buds;wireless anc earbuds"},
    {"name":"Sony WH-1000XM6","price":"399","category":"audio","description":"Sony WH-1000XM6, over-ear, industry-leading ANC, 40h battery, LDAC, wireless headphones","tags":"sony,headphones,wireless,anc,over-ear,premium","phrases":"best noise cancelling headphones;premium wireless headphones;sony anc headphones;travel headphones;long battery headphones"},
    {"name":"Sennheiser HD 660S2","price":"499","category":"audio","description":"Sennheiser HD 660S2, open-back, wired, audiophile headphones, 42mm drivers, reference sound","tags":"sennheiser,headphones,wired,audiophile,open-back,studio","phrases":"audiophile headphones;studio reference headphones;high fidelity wired cans;critical listening headphones"},
    {"name":"Bose QuietComfort Ultra","price":"429","category":"audio","description":"Bose QuietComfort Ultra, over-ear, ANC, spatial audio, 30h battery, wireless headphones","tags":"bose,headphones,wireless,anc,comfort,premium","phrases":"most comfortable headphones;bose noise cancelling;premium travel headphones;all day comfort cans"},

    # Accessories
    {"name":"Logitech MX Master 3S","price":"99","category":"accessory","description":"Logitech MX Master 3S, wireless mouse, 8K DPI, USB-C, multi-device, ergonomic, silent clicks","tags":"logitech,mouse,wireless,ergonomic,productivity","phrases":"best ergonomic mouse;productivity wireless mouse;multi device mouse;silent click mouse;logitech premium mouse"},
    {"name":"Keychron Q1 Pro","price":"199","category":"accessory","description":"Keychron Q1 Pro, 75% mechanical keyboard, aluminum, hot-swappable, QMK/VIA, wireless, RGB","tags":"keychron,keyboard,mechanical,wireless,customizable,rgb","phrases":"premium mechanical keyboard;customizable wireless keyboard;aluminum keyboard;programmer keyboard;qmk via keyboard"},
]

# ============================================================
# PHASE 1: INSERT ALL 30 PRODUCTS
# ============================================================
print("=" * 60)
print("PHASE 1: INSERT 30 TECH PRODUCTS")
print("=" * 60)

t0_total = time.perf_counter()
inserted = 0
failed = 0
reg_times = []

for p in products:
    t0 = time.perf_counter()
    r = client.tool("mb_register_product", {
        "name": p["name"],
        "price": p["price"],
        "category": p["category"],
        "description": p["description"],
        "tags": p["tags"],
        "embedding_phrases": p["phrases"],
    })
    ms = (time.perf_counter() - t0) * 1000
    reg_times.append(ms)
    if isinstance(r, dict) and r.get("status") == "ok":
        inserted += 1
        print(f"  OK {inserted:2d}/30: {p['name'][:40]:40s} {ms:6.0f}ms")
    else:
        failed += 1
        print(f"  XX {p['name'][:40]:40s} ERR: {r}")

elapsed_insert = time.perf_counter() - t0_total
avg_reg = sum(reg_times)/len(reg_times) if reg_times else 0
print(f"\n  Inserted: {inserted}/30 | Failed: {failed} | Time: {elapsed_insert:.1f}s | Avg: {avg_reg:.0f}ms")

# Invalidate caches to force fresh reads
from mirror_brain.c0_registry import _cache
_cache.invalidate("")

print()

# ============================================================
# PHASE 2: SEARCH BY ID (ULTRA-FAST)
# ============================================================
print("=" * 60)
print("PHASE 2: SEARCH BY ID")
print("=" * 60)

# Get UUIDs of products we inserted
import json
id_tests = [
    {"name": "MacBook Pro 16 M3 Max", "expected_class": "laptop"},
    {"name": "iPhone 16 Pro Max", "expected_class": "phone"},
    {"name": "Sony WH-1000XM6", "expected_class": "audio"},
    {"name": "Samsung Odyssey OLED G9", "expected_class": "monitor"},
    {"name": "Logitech MX Master 3S", "expected_class": "accessory"},
]

# First resolve names to UUIDs
id_entries = []
for t in id_tests:
    r = client.tool("mb_search_fuzzy", {"name": t["name"]})
    if isinstance(r, list) and r:
        tid = r[0].get("uuid", "")
    else:
        tid = ""
    id_entries.append({"name": t["name"], "uuid": tid, "expected": t["expected_class"]})

# Now test lookup speed
id_times = []
for entry in id_entries:
    if not entry["uuid"]:
        print(f"  SKIP {entry['name']} — no UUID found")
        continue
    t0 = time.perf_counter()
    r = client.tool("mb_get_by_id", {"uuid": entry["uuid"]})
    ms = (time.perf_counter() - t0) * 1000
    id_times.append(ms)
    name = r.get("canonical_name", "?") if isinstance(r, dict) else "?"
    cat = r.get("type", "?") if isinstance(r, dict) else "?"
    props = r.get("properties", {}) if isinstance(r, dict) else {}
    price = props.get("price", "?")
    match = entry["expected"] in str(props.get("category", ""))
    sym = "OK" if match else "??"
    print(f"  [{sym}] {entry['name'][:40]:40s} {ms:6.1f}ms | {price:>8s} | cat={props.get('category','?')}")

avg_id = sum(id_times)/len(id_times) if id_times else 0
print(f"\n  Avg ID lookup: {avg_id:.1f}ms across {len(id_times)} queries")
print()

# ============================================================
# PHASE 3: BUYER-STYLE SEARCHES
# ============================================================
print("=" * 60)
print("PHASE 3: BUYER-STYLE SEARCH (like a real shopper)")
print("=" * 60)

buyer_queries = [
    # What a real buyer would type
    ("gaming laptop with good graphics", "laptop", ["ASUS ROG", "Razer Blade"]),
    ("lightweight computer for travel", "laptop", ["MacBook Air", "ThinkPad X1"]),
    ("best iphone latest model", "phone", ["iPhone 16"]),
    ("noise cancelling headphones for airplane", "audio", ["Sony WH", "Bose QuietComfort", "AirPods Pro"]),
    ("cheap android phone good value", "phone", ["Nothing Phone", "OnePlus"]),
    ("professional monitor for video editing color accurate", "monitor", ["Apple Pro Display", "Dell UltraSharp"]),
    ("tiny computer for office desk small space", "desktop", ["HP Elite Mini"]),
    ("wireless earbuds with good battery", "audio", ["AirPods Pro", "Sony WH"]),
    ("tablet for drawing and artists", "tablet", ["iPad Pro"]),
    ("ergonomic mouse for work silent clicks", "accessory", ["Logitech MX Master"]),
    ("large curved gaming screen ultrawide", "monitor", ["Samsung Odyssey OLED"]),
    ("mechanical keyboard programmer wireless aluminum", "accessory", ["Keychron Q1"]),
    ("modular laptop repairable sustainable", "laptop", ["Framework"]),
    ("samsung flagship phone with stylus", "phone", ["Samsung Galaxy S25"]),
    ("convertible touchscreen laptop premium hp", "laptop", ["HP Spectre"]),
]

search_score = 0
search_times = []
for query, category_hint, expected_names in buyer_queries:
    t0 = time.perf_counter()
    r = client.tool("mb_search_products", {"query": query, "limit": 5})
    ms = (time.perf_counter() - t0) * 1000
    search_times.append(ms)
    items = r if isinstance(r, list) else []
    names = [i.get("name", "") for i in items]
    
    # Check if any expected name is in results
    hit = any(any(exp.lower() in name.lower() for exp in expected_names) for name in names)
    if hit:
        search_score += 1

    sym = "OK" if hit else "XX"
    top3 = ", ".join(names[:3])
    print(f"  [{sym}] \"{query[:60]:60s}\" {ms:6.0f}ms → {top3[:80]}")

avg_search = sum(search_times)/len(search_times) if search_times else 0
print(f"\n  Buyer search score: {search_score}/{len(buyer_queries)} | Avg: {avg_search:.0f}ms")
print()

# ============================================================
# PHASE 4: FILTER + SEARCH COMBINED
# ============================================================
print("=" * 60)
print("PHASE 4: COMBINED FILTERS (category + query + price)")
print("=" * 60)

filter_tests = [
    ("laptop", "", "", "", "all laptops"),
    ("", "phone", "", "", "all phones"),
    ("gaming", "laptop", "", "", "gaming laptops"),
    ("", "monitor", "1000", "5000", "monitors $1k-$5k"),
    ("apple", "", "", "", "anything apple"),
    ("premium", "audio", "200", "", "premium audio over $200"),
    ("", "accessory", "", "100", "accessories under $100"),
]

for query, category, minp, maxp, desc in filter_tests:
    t0 = time.perf_counter()
    args = {"limit": 10}
    if query: args["query"] = query
    if category: args["category"] = category
    if minp: args["min_price"] = minp
    if maxp: args["max_price"] = maxp
    r = client.tool("mb_search_products", args)
    ms = (time.perf_counter() - t0) * 1000
    items = r if isinstance(r, list) else []
    names = [f"{i.get('name','?')} ({i.get('price','?')})" for i in items[:5]]
    print(f"  [{len(items):2d} results] {desc:35s} {ms:6.0f}ms → {', '.join(names)[:100]}")

print()

# ============================================================
# PHASE 5: SPEED BENCHMARK (100 rapid queries)
# ============================================================
print("=" * 60)
print("PHASE 5: SPEED BENCHMARK — 100 rapid queries")
print("=" * 60)

rapid_queries = [
    "laptop", "phone", "gaming", "apple", "samsung",
    "wireless", "premium", "budget", "workstation", "portable",
]

times_100 = []
for i in range(100):
    q = rapid_queries[i % len(rapid_queries)]
    t0 = time.perf_counter()
    r = client.tool("mb_search_products", {"query": q, "limit": 3})
    ms = (time.perf_counter() - t0) * 1000
    times_100.append(ms)

avg_100 = sum(times_100)/len(times_100)
p50 = sorted(times_100)[50]
p95 = sorted(times_100)[94]
p99 = sorted(times_100)[98]
print(f"  100 queries complete")
print(f"  Avg: {avg_100:.1f}ms | P50: {p50:.1f}ms | P95: {p95:.1f}ms | P99: {p99:.1f}ms")
print(f"  Estimated QPS: {1000/avg_100:.0f} queries/sec")

print()
print("=" * 60)
print("FINAL SCORES")
print("=" * 60)
print(f"  Products inserted:      {inserted}/30")
print(f"  ID lookup avg:          {avg_id:.1f}ms")
print(f"  Buyer search score:     {search_score}/{len(buyer_queries)}")
print(f"  Buyer search avg:       {avg_search:.0f}ms")
print(f"  Speed benchmark P50:    {p50:.1f}ms")
print(f"  Estimated QPS:          {1000/avg_100:.0f}")
print()

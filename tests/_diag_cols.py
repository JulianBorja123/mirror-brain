import sys, json, re
sys.path.insert(0, "/c/Users/gusta/mirror-brain/src")
from mirror_brain.c0_client import C0Client
from mirror_brain.c0_registry import C0Registry

c0 = C0Client(namespace="mirrorbrain")
reg = C0Registry(c0)

# Get one raw_text concept and test the fetch path
concepts = c0.list_concepts()
raw = [c for c in concepts if "raw_texts" in c.get("name","")]
if raw:
    sample = raw[0]
    print(f"Sample concept: {sample['name']}")
    desc = sample.get("description","")
    print(f"Description: {desc[:200]}")
    
    data = json.loads(desc)
    print(f"\nKeys in data: {list(data.keys())}")
    print(f"Values: {json.dumps(data, default=str)[:200]}")
    
    # Simulate what _fetch_module_rows does
    select_cols = ["uuid", "content", "created_at", "source"]
    print(f"\nSimulating SELECT {select_cols}:")
    for col in select_cols:
        val = ""
        for k, v in data.items():
            if k.lower() == col:
                val = v
                break
        print(f"  {col}: '{str(val)[:80]}'")
else:
    print("No raw_texts concepts found via list_concepts!")

# Also test what execute() returns
print("\n--- Testing execute path ---")
try:
    rows = reg.db.execute(
        "SELECT uuid, content, created_at, source FROM raw_texts WHERE content LIKE ?",
        ("%Mirror%",),
    ).fetchall()
    print(f"rows from execute().fetchall(): {len(rows)}")
    for r in rows[:2]:
        print(f"  {r}")
except Exception as e:
    print(f"FAILED: {e}")
    import traceback; traceback.print_exc()

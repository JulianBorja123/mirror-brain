import sys
sys.path.insert(0, "/c/Users/gusta/mirror-brain/src")
from mirror_brain.c0_client import C0Client
from mirror_brain.c0_registry import C0Registry

c0 = C0Client(namespace="mirrorbrain")
reg = C0Registry(c0)

# Test create_concept directly
try:
    result = c0.create_concept("[tbl] raw_texts test_direct", description='{"uuid":"test","content":"hello"}', force=True)
    print(f"create_concept result: {result}")
except Exception as e:
    print(f"create_concept FAILED: {e}")
    import traceback; traceback.print_exc()

# Now list concepts
concepts = c0.list_concepts()
tbl = [c for c in concepts if "[tbl]" in c.get("name", "")]
print(f"\n[tbl] concepts after direct create: {len(tbl)}")
for c in tbl:
    print(f"  {c.get('name')}: {c.get('description','')[:120]}")

# Now test the execute() path with debugging
print("\n--- Testing execute() path ---")
q = "INSERT INTO raw_texts (uuid, content, char_count, source, created_at) VALUES (?,?,?,?,?)"
p = ("test-uuid-123", "hello world test", 15, "debug", "2026-06-20")

q_upper = q.upper().strip()
print(f"q_upper: {q_upper[:80]}")

# Check module table detection
for table in reg._MODULE_TABLES:
    if f"INTO {table.upper()}" in q_upper:
        print(f"  MATCHED table '{table}'")
        try:
            reg._handle_module_write(q, p)
            print(f"  _handle_module_write completed")
        except Exception as e:
            print(f"  _handle_module_write FAILED: {e}")
            import traceback; traceback.print_exc()
        break
else:
    print("  NO module table matched!")

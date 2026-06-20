import sys
sys.path.insert(0, "/c/Users/gusta/mirror-brain/src")
from mirror_brain.c0_client import C0Client
from mirror_brain.c0_registry import C0Registry
import uuid as _uuid

c0 = C0Client(namespace="mirrorbrain")
reg = C0Registry(c0)

uid = str(_uuid.uuid4())
try:
    reg.db.execute(
        "INSERT INTO raw_texts (uuid, content, char_count, source, created_at) VALUES (?,?,?,?,?)",
        (uid, "DIRECT TEST DockerX text", 23, "direct", "2026-06-20"),
    )
    reg.db.commit()
    print(f"INSERT done: {uid}")
except Exception as e:
    print(f"INSERT FAILED: {e}")
    import traceback; traceback.print_exc()

try:
    rows = reg.db.execute(
        "SELECT uuid, content, created_at, source FROM raw_texts WHERE content LIKE ?",
        ("%DockerX%",),
    ).fetchall()
    print(f"SELECT returned {len(rows)} rows")
    for row in rows:
        print(f"  {row}")
except Exception as e:
    print(f"SELECT FAILED: {e}")
    import traceback; traceback.print_exc()

concepts = c0.list_concepts()
tbl = [c for c in concepts if "[tbl]" in c.get("name", "")]
print(f"\n[tbl] concepts: {len(tbl)}")
for c in tbl[:5]:
    desc = c.get("description","")
    print(f"  {c.get('name')}: {desc[:120]}")

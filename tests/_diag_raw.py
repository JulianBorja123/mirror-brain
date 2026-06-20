import sys, json, subprocess
sys.path.insert(0, "/c/Users/gusta/mirror-brain/src")
from mirror_brain.c0_client import C0Client

c0 = C0Client(namespace="mirrorbrain")

# Direct c0 export
output = c0._docker_exec("export", "--format", "json")
print(f"Export length: {len(output)} chars")
data = json.loads(output)
nodes = data.get("nodes", [])
print(f"Total nodes: {len(nodes)}")

# Show sample names
for node in nodes[:5]:
    props = node.get("properties", {})
    name = props.get("name", "")
    desc = props.get("description", "")[:60]
    labels = node.get("labels", [])
    print(f"  labels={labels} name='{name}' desc='{desc}'")

# Count [tbl] concepts
tbl_count = sum(1 for n in nodes if "[tbl]" in n.get("properties",{}).get("name",""))
cons_count = sum(1 for n in nodes if "[consolidation]" in n.get("properties",{}).get("name",""))
print(f"\n[tbl] concepts: {tbl_count}")
print(f"[consolidation] concepts: {cons_count}")

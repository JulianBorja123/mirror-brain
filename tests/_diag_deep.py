import sys, json, subprocess
sys.path.insert(0, "/c/Users/gusta/mirror-brain/src")
from mirror_brain.c0_client import C0Client

c0 = C0Client(namespace="mirrorbrain")
output = c0._docker_exec("export", "--format", "json")
data = json.loads(output)
nodes = data.get("nodes", [])

# Show raw_texts concepts
raw = [n for n in nodes if "raw_texts" in n.get("properties",{}).get("name","")]
print(f"raw_texts concepts: {len(raw)}")
for n in raw[:5]:
    name = n["properties"]["name"]
    desc = n["properties"].get("description","")
    print(f"  {name}")
    print(f"    desc: {desc[:200]}")
    print()

# Show procedures
proc = [n for n in nodes if "procedures" in n.get("properties",{}).get("name","")]
print(f"procedures concepts: {len(proc)}")
for n in proc[:5]:
    name = n["properties"]["name"]
    desc = n["properties"].get("description","")
    print(f"  {name}")
    print(f"    desc: {desc[:200]}")
    print()

# Show [consolidation]  
cons = [n for n in nodes if "[consolidation]" in n.get("properties",{}).get("name","")]
print(f"[consolidation] concepts: {len(cons)}")
for n in cons[:3]:
    print(f"  {n['properties']['name']}: {n['properties'].get('description','')[:100]}")

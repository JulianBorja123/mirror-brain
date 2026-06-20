"""
Mirror Brain v1.0 — Note Constructor Demo.
Real DeepSeek API call to construct a note from sample text.
"""
import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mirror_brain.registry import EntityRegistry
from mirror_brain.note_constructor import NoteConstructor


# ── LLM Call (DeepSeek) ─────────────────────────────────────

def deepseek_llm(prompt: str) -> str:
    """Call DeepSeek API. Key must be in env or ~/.hermes/.env."""
    # Load key from Hermes .env
    hermes_env = os.path.expanduser("~/AppData/Local/hermes/.env")
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    
    if not key and os.path.exists(hermes_env):
        with open(hermes_env) as f:
            for line in f:
                if line.startswith("DEEPSEEK_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    
    if not key:
        return json.dumps({
            "keywords": ["demo", "sin_api_key"],
            "context": "No se pudo cargar la API key de DeepSeek.",
            "tags": ["error"],
            "emotional_load": {},
            "temporal_hints": [],
            "entities_mentioned": [],
            "search_hints": []
        })
    
    import urllib.request
    
    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 1000,
    }).encode("utf-8")
    
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
        return body["choices"][0]["message"]["content"]


# ── Main ────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Mirror Brain v1.0 — Note Constructor Demo")
    print("=" * 60)
    
    # 1. Initialize registry with seed entities
    db_path = os.path.join(tempfile.gettempdir(), "mirror_brain_demo.db")
    reg = EntityRegistry(db_path)
    
    # Seed entities
    reg.create("Gustavo Julian Barrios Borja", "person")
    reg.create("Romina González", "person")
    reg.add_alias("Romi", reg.resolve("Romina González"), source="manual", confidence=1.0)
    
    reg.create("Mirror Brain", "project")
    reg.add_alias("MB", reg.resolve("Mirror Brain"), source="manual", confidence=1.0)
    
    reg.create("c0", "tool")
    reg.create("Florería GJB", "place")
    reg.add_alias("la florería", reg.resolve("Florería GJB"), source="manual", confidence=1.0)
    
    reg.create("DeepSeek", "tool")
    reg.create("Docker", "tool")
    reg.create("Hermes Agent", "tool")
    
    print(f"\n✅ Registry seeded: {len(reg.list_by_type('person'))} persons, "
          f"{len(reg.list_by_type('project'))} projects, "
          f"{len(reg.list_by_type('tool'))} tools, "
          f"{len(reg.list_by_type('place'))} places")
    
    # 2. Create Note Constructor
    nc = NoteConstructor(registry=reg, llm_call=deepseek_llm)
    
    # 3. Sample text
    sample = (
        "Estuve en la florería con Romi hoy. Finalmente c0 anda con embeddings "
        "usando Ollama en Docker. Pero me preocupa el gasto en tokens de DeepSeek "
        "— ya llevo como $5 USD esta semana. Igual estoy contento porque el "
        "hybrid search funciona perfecto. Creo que Mirror Brain va por buen camino."
    )
    
    print(f"\n📝 Input text:\n  \"{sample}\"\n")
    print("🔄 Calling DeepSeek (deepseek-chat)...")
    
    # 4. Construct note
    note = nc.construct(sample)
    
    # 5. Display results
    print(f"\n{'='*60}")
    print("📋 CONSTRUCTED NOTE")
    print(f"{'='*60}")
    print(f"  Context:  {note.context}")
    print(f"  Keywords: {', '.join(note.keywords)}")
    print(f"  Tags:     {', '.join(note.tags)}")
    print(f"  Emotion:  {json.dumps(note.emotional_load)}")
    print(f"  Temporal: {', '.join(note.temporal_hints) if note.temporal_hints else '(none)'}")
    
    print(f"\n  🧠 Entities mentioned:")
    for ent in note.entities_mentioned:
        alias_info = f" → alias_of: {ent.get('alias_of')}" if ent.get('alias_of') else ""
        confidence = ent.get('confidence', '?')
        print(f"    - [{ent.get('type', '?')}] {ent['name']} (conf: {confidence}){alias_info}")
    
    print(f"\n  🔍 Search hints:")
    for hint in note.search_hints:
        print(f"    - {hint}")
    
    # 6. Verify entity processing
    print(f"\n{'='*60}")
    print("📊 REGISTRY STATE AFTER INGESTION")
    print(f"{'='*60}")
    all_entities = []
    for etype in ["person", "project", "tool", "place", "concept"]:
        entities = reg.list_by_type(etype)
        if entities:
            print(f"\n  {etype}:")
            for e in entities:
                aliases = reg.get_aliases(e["uuid"])
                alias_names = [a["alias"] for a in aliases if a["source"] == "llm"]
                alias_str = f" (LLM aliases: {', '.join(alias_names)})" if alias_names else ""
                print(f"    - {e['canonical_name']}{alias_str}")
    
    print(f"\n🎉 Demo complete!")
    
    # Cleanup
    reg.db.close()
    os.unlink(db_path)


if __name__ == "__main__":
    main()

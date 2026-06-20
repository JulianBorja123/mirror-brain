"""
Mirror Brain v2 — Agent Demo.
Feeds the 38-min transcription through the agentic pipeline.
"""
import sys, os, json, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from mirror_brain.registry import EntityRegistry
from mirror_brain.agent import MirrorBrainAgent
from mirror_brain.preprocessor import TextPreprocessor


def deepseek(prompt):
    import urllib.request
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        hp = os.path.expanduser("~/AppData/Local/hermes/.env")
        if os.path.exists(hp):
            with open(hp) as f:
                for l in f:
                    if "DEEPSEEK_API_KEY" in l:
                        key = l.split("=", 1)[1].strip()
                        break
    if not key:
        return json.dumps({"entities":[],"links":[],"evolutions":[],"new_aliases":[],"needs_more_search":[],"summary":"no key"})
    p = json.dumps({"model":"deepseek-chat","messages":[{"role":"user","content":prompt}],"temperature":0.3,"max_tokens":1500}).encode()
    import urllib.request as ur
    r = ur.Request("https://api.deepseek.com/v1/chat/completions", data=p, headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"})
    with ur.urlopen(r, timeout=60) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]


def main():
    print("=" * 70)
    print("Mirror Brain v2 — AGENTIC PIPELINE DEMO")
    print("=" * 70)

    db = os.path.join(tempfile.gettempdir(), "mb_v2_demo.db")
    reg = EntityRegistry(db)
    agent = MirrorBrainAgent(reg, llm_call=deepseek, max_loops=2)

    # Seed
    reg.create("Gustavo Julian Barrios Borja", "person")
    reg.create("Romina Gonzalez", "person")
    reg.add_alias("Romi", reg.resolve("Romina Gonzalez"), source="manual")
    reg.create("Mirror Brain", "project")
    reg.add_alias("MB", reg.resolve("Mirror Brain"), source="manual")
    reg.create("c0", "tool")
    reg.create("DeepSeek", "tool")
    reg.create("Hermes Agent", "tool")
    reg.create("Docker", "tool")
    reg.create("Ollama", "tool")
    reg.create("Floreria GJB", "place")

    # Seed daily summaries for temporal context
    from datetime import date, timedelta
    today = date.today()
    for i in range(21):
        d = (today - timedelta(days=i)).isoformat()
        reg.db.execute("INSERT OR REPLACE INTO daily_index (date, summary, emotional_arc, key_entities, key_decisions, created_at) VALUES (?,?,?,?,?,?)", (d, json.dumps({"es": f"Dia de trabajo en Mirror Brain v1"}), json.dumps([0.3,0.2,0.3,0.5]), json.dumps(["Mirror Brain","c0"]), json.dumps(["v1 pipeline completo"]), d))
    reg.db.commit()

    print(f"Seeded: {sum(1 for _ in reg.db.execute('SELECT 1 FROM entities'))} entities, {sum(1 for _ in reg.db.execute('SELECT 1 FROM daily_index'))} daily summaries")

    # Load transcription
    txt_path = os.path.expanduser("~/Downloads/julian_transcripcion.txt")
    text = open(txt_path, encoding="utf-8").read()
    print(f"\nText: {len(text)} chars, ~{len(text.split())} words")

    # Preprocessor analysis
    pp = TextPreprocessor()
    complexity = pp.estimate_complexity(text)
    themes = pp.split_by_themes(text)
    print(f"Complexity: {json.dumps(complexity)}")
    print(f"Themes: {len(themes)} detected")

    # Agent process
    print(f"\n{'─'*70}")
    print("AGENT PROCESSING...")
    print(f"{'─'*70}")

    report = agent.process(text)

    print(f"\nLoops used: {report.get('loops_used', 1)}")
    print(f"Auto-executed: {len(report.get('auto', []))}")
    print(f"Flagged: {len(report.get('flagged', []))}")
    print(f"Skipped: {len(report.get('skipped', []))}")
    print(f"Summary: {report.get('summary', '')}")

    if report.get("auto"):
        print(f"\n  Auto-executed:")
        for item in report["auto"][:15]:
            print(f"    ✅ {item}")

    if report.get("flagged"):
        print(f"\n  Flagged:")
        for item in report["flagged"][:10]:
            print(f"    ⚠️  {item}")

    print(f"\nStats: {json.dumps(report.get('stats', {}))}")

    reg.db.close()
    os.unlink(db)

    print(f"\n{'='*70}")
    print("V2 DEMO COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()

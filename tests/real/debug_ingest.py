"""Quick debug: what does mb_ingest return?"""
import sys, json, urllib.request as ur
sys.path.insert(0, "C:/Users/gusta/mirror-brain/tests/real")
from harness import MCPClient

client = MCPClient()
client.init()

result = client.tool("mb_ingest", {"text": "Test simple. Mirror Brain funciona.", "source": "debug"})
print(f"Type: {type(result).__name__}")
print(f"First 300 chars: {str(result)[:300]}")
print(f"Keys (if dict): {list(result.keys()) if isinstance(result, dict) else 'N/A'}")

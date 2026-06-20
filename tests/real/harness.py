#!/usr/bin/env python3
"""
Mirror Brain v3 — Real-World Test Harness (NO MOCKS)
=====================================================
Hace llamadas HTTP reales al MCP server (127.0.0.1:8765).
Mide tiempos, detecta errores, genera logs de auditoría.
"""
import json, time, urllib.request as ur, sys, os
from datetime import datetime, timezone
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
MCP_URL = "http://127.0.0.1:8765/mcp"
AUDIT_DIR = Path("C:/Users/gusta/mirror-brain/.audit")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_FILE = AUDIT_DIR / f"test-run-{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
REPORT_FILE = AUDIT_DIR / f"report-{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}

class MCPClient:
    """Real MCP client with session management and timing."""

    def __init__(self):
        self.session_id = None
        self.call_count = 0
        self.total_time_ms = 0
        self.errors = []

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        """Make a JSON-RPC call, return parsed result."""
        req_id = self.call_count
        self.call_count += 1

        body = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            body["params"] = params

        extra_headers = {}
        if self.session_id:
            extra_headers["mcp-session-id"] = self.session_id

        t0 = time.perf_counter()
        try:
            data = json.dumps(body).encode()
            all_headers = {**HEADERS, **extra_headers}
            req = ur.Request(MCP_URL, data=data, headers=all_headers)
            with ur.urlopen(req, timeout=30) as resp:
                # Read SSE response
                raw = resp.read().decode()
                session_hdr = resp.headers.get("mcp-session-id", "")
                if session_hdr and not self.session_id:
                    self.session_id = session_hdr

            # Parse SSE: "data: {...}\n\n"
            result = None
            for line in raw.split("\n"):
                if line.startswith("data: "):
                    payload = json.loads(line[6:])
                    if "result" in payload:
                        result = payload["result"]
                    elif "error" in payload:
                        self.errors.append({
                            "call": req_id, "method": method,
                            "error": payload["error"],
                        })
                        return {"_error": payload["error"]}

            elapsed_ms = (time.perf_counter() - t0) * 1000
            self.total_time_ms += elapsed_ms

            self._log(method, params, result, elapsed_ms)
            return result or {}

        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self.total_time_ms += elapsed_ms
            err = {"_error": str(e), "_type": type(e).__name__}
            self.errors.append({"call": req_id, "method": method, "error": str(e)})
            self._log(method, params, None, elapsed_ms, error=str(e))
            return err

    def _log(self, method, params, result, elapsed_ms, error=None):
        """Append one line to audit log."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "params": params,
            "elapsed_ms": round(elapsed_ms, 2),
            "ok": error is None,
            "error": error,
            "result_preview": str(result)[:300] if result else None,
        }
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def init(self):
        """Initialize MCP session."""
        return self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mirror-brain-test-harness", "version": "1.0"},
        })

    def tool(self, name: str, args: dict | None = None) -> dict:
        """Call an MCP tool and return parsed result."""
        raw = self._rpc("tools/call", {
            "name": name,
            "arguments": args or {},
        })
        # Extract text from content array
        if isinstance(raw, dict) and "content" in raw:
            for item in raw["content"]:
                if item.get("type") == "text":
                    try:
                        return json.loads(item["text"])
                    except (json.JSONDecodeError, TypeError):
                        return item["text"]
            return raw
        return raw

    def stats(self) -> dict:
        return {
            "calls": self.call_count,
            "errors": len(self.errors),
            "total_ms": round(self.total_time_ms, 1),
            "avg_ms": round(self.total_time_ms / max(1, self.call_count), 1),
        }


# ═══════════════════════════════════════════════════════════════
# ASSERTION HELPERS
# ═══════════════════════════════════════════════════════════════

class TestReport:
    def __init__(self):
        self.tests = []
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = ""):
        status = "PASS" if condition else "FAIL"
        entry = {"name": name, "status": status, "detail": detail}
        self.tests.append(entry)
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        print(f"  [{status}] {name} {detail}")

    def summary(self) -> str:
        total = self.passed + self.failed
        return f"{self.passed}/{total} passed, {self.failed} failed"

"""End-to-end test: launches spark-vibe exactly as registered in ~/.copilot/mcp-config.json and calls every tool."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"


def screenshot(html: Path, png: Path) -> None:
    edge = shutil.which("msedge") or r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    subprocess.run([edge, "--headless=new", "--disable-gpu", f"--screenshot={png}", "--window-size=1200,600",
                    html.as_uri()], check=True, timeout=120, capture_output=True)


def text(result) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)


async def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = json.loads((Path.home() / ".copilot" / "mcp-config.json").read_text(encoding="utf-8"))
    entry = cfg["mcpServers"]["spark-vibe"]
    params = StdioServerParameters(command=entry["command"], args=entry["args"],
                                   env={**os.environ, **entry.get("env", {})})
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str) -> None:
        print(f"[{'PASS' if cond else 'FAIL'}] {name}\n{detail}\n")
        if not cond:
            failures.append(name)

    async with Client(params, read_timeout_seconds=900) as c:
        tools = sorted(t.name for t in (await c.list_tools()).tools)
        expected = sorted(["repo_index", "repo_search", "private_ask", "scan_secrets", "gpu_status",
                           "gpu_profile_run", "visual_review", "local_critique"])
        check("list_tools", tools == expected, str(tools))

        repo = str(DEMO / "private_repo")
        r = text(await c.call_tool("scan_secrets", {"path": repo}))
        check("UC1 scan_secrets detects dummy AWS key", "aws_access_key" in r, r)

        r = text(await c.call_tool("repo_index", {"path": repo}))
        check("UC1 repo_index", r.startswith("Indexed"), r)
        chunks = (DEMO / "private_repo" / ".spark-index" / "chunks.json").read_text(encoding="utf-8")
        check("UC1 index stores redacted text only", "AKIAIOSFODNN7EXAMPLE" not in chunks, "secret absent from index")

        r = text(await c.call_tool("repo_search", {"path": repo, "query": "how is tax applied to invoices", "k": 3}))
        check("UC1 repo_search returns locations only", "billing.py:" in r and "def " not in r, r)

        r = text(await c.call_tool("private_ask", {"path": repo, "question": "What is the maximum total discount and when is tax applied?"}))
        check("UC1 private_ask answers locally without leaking secret",
              "20" in r and "AKIAIOSFODNN7EXAMPLE" not in r, r[:1200])

        r = text(await c.call_tool("gpu_status", {}))
        check("UC2 gpu_status", "RTX Spark" in r, r)

        r = text(await c.call_tool("gpu_profile_run", {
            "argv": ["python", "bench_llm.py"], "cwd": str(DEMO), "interval_sec": 0.3}))
        rep = json.loads(r)
        util = (rep.get("gpu_util_pct") or {}).get("max", 0)
        check("UC2 gpu_profile_run captures real GPU load", rep.get("exit_code") == 0 and util > 0, r)

        outside = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        blocked = {
            "shell launcher": {"argv": ["cmd", "/c", "whoami"], "cwd": str(DEMO)},
            "powershell": {"argv": ["powershell", "-Command", "Get-Process"], "cwd": str(DEMO)},
            "absolute exe path": {"argv": [sys.executable, "bench_llm.py"], "cwd": str(DEMO)},
            "python -c": {"argv": ["python", "-c", "print('pwned')"], "cwd": str(DEMO)},
            "python -m other": {"argv": ["python", "-m", "http.server"], "cwd": str(DEMO)},
            "script outside roots": {"argv": ["python", r"..\..\..\outside.py"], "cwd": str(DEMO)},
            "non-.py script": {"argv": ["python", "index.html"], "cwd": str(DEMO / "ui")},
            "cwd outside roots": {"argv": ["python", "x.py"], "cwd": str(outside)},
            "pytest plugin": {"argv": ["pytest", "-p", "evil_plugin"], "cwd": str(DEMO)},
            "pytest target outside": {"argv": ["pytest", str(outside)], "cwd": str(DEMO)},
            "node eval": {"argv": ["node", "-e", "1"], "cwd": str(DEMO)},
        }
        results = {k: json.loads(text(await c.call_tool("gpu_profile_run", v))) for k, v in blocked.items()}
        leaked = [k for k, v in results.items() if not v.get("rejected") or "exit_code" in v]
        check("UC2 gpu_profile_run rejects non-allowlisted commands", not leaked,
              json.dumps({k: v.get("reason") for k, v in results.items()}, ensure_ascii=False, indent=2))

        png = DEMO / "ui" / "screenshot.png"
        screenshot(DEMO / "ui" / "index.html", png)
        r = text(await c.call_tool("visual_review", {
            "image_path": str(png),
            "expectation": "Dark dashboard titled 'RTX Spark Dashboard' with 3 metric cards in one row "
                           "(GPU usage, unified memory, tokens/sec) and a blue benchmark button."}))
        check("UC3 visual_review returns structured verdict", '"verdict"' in r, r)

        r = text(await c.call_tool("local_critique", {
            "requirement": "Return the average of a list of numbers; empty list must return 0.",
            "candidate": "def avg(xs):\n    return sum(xs) / len(xs)"}))
        check("UC3 local_critique rejects buggy code", '"accept": false' in r.replace("false,", "false"), r)

    print("RESULT:", "ALL PASSED" if not failures else f"FAILED {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

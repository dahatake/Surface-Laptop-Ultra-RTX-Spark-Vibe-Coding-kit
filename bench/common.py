"""Shared helpers for the spark-vibe measurement harness.

Every tool call goes through the real MCP stdio path registered in ~/.copilot/mcp-config.json (the same path
Copilot Fusion uses). GPU load is logged by an independent nvidia-smi process so the tool's own numbers can be
cross-checked against a source the tool does not control.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "bench"
RESULTS = BENCH / "results"
LMS = Path.home() / ".lmstudio" / "bin" / "lms.exe"
SMI_FIELDS = "timestamp,utilization.gpu,memory.used,power.draw,temperature.gpu,clocks.sm"


def text(result) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)


@asynccontextmanager
async def mcp_client(env_overrides: dict | None = None):
    cfg = json.loads((Path.home() / ".copilot" / "mcp-config.json").read_text(encoding="utf-8"))
    entry = cfg["mcpServers"]["spark-vibe"]
    params = StdioServerParameters(command=entry["command"], args=entry["args"],
                                   env={**os.environ, **entry.get("env", {}), **(env_overrides or {})})
    async with Client(params, read_timeout_seconds=900) as c:
        yield c


async def timed_call(client, tool: str, args: dict) -> tuple[str, float]:
    t0 = time.perf_counter()
    out = text(await client.call_tool(tool, args))
    return out, time.perf_counter() - t0


class GpuLogger:
    """Independent nvidia-smi sampler (-lms) writing raw CSV; not part of the server under test."""

    def __init__(self, csv_path: Path, interval_ms: int = 250):
        self.path = csv_path
        self.interval_ms = interval_ms
        self.proc: subprocess.Popen | None = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w", encoding="utf-8", newline="")
        self._fh.write(SMI_FIELDS + "\n")
        self._fh.flush()
        self.proc = subprocess.Popen(
            ["nvidia-smi", f"--query-gpu={SMI_FIELDS}", "--format=csv,noheader,nounits", "-i", "0",
             f"-lms={self.interval_ms}"], stdout=self._fh, stderr=subprocess.DEVNULL)
        time.sleep(1.0)
        return self

    def __exit__(self, *exc):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        self._fh.close()

    def samples(self) -> list[dict]:
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[1:]:
            p = [x.strip() for x in line.split(",")]
            if len(p) < 6:
                continue
            try:
                ts = dt.datetime.strptime(p[0], "%Y/%m/%d %H:%M:%S.%f").timestamp()
                rows.append({"t": ts, "util": float(p[1]), "mem_mib": float(p[2]),
                             "power_w": _f(p[3]), "temp_c": _f(p[4]), "sm_mhz": _f(p[5])})
            except ValueError:
                continue
        return rows

    def window(self, t0: float, t1: float) -> list[dict]:
        return [s for s in self.samples() if t0 <= s["t"] <= t1]


def _f(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None


def stats(values: list[float]) -> dict | None:
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    # nearest-rank p95
    p95 = v[max(0, -(-95 * len(v) // 100) - 1)]
    return {"n": len(v), "min": round(v[0], 3), "median": round(statistics.median(v), 3),
            "mean": round(statistics.fmean(v), 3), "p95": round(p95, 3), "max": round(v[-1], 3),
            "stdev": round(statistics.stdev(v), 3) if len(v) > 1 else 0.0}


def environment() -> dict:
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8",
                                  errors="replace").stdout.strip()
        except OSError as e:
            return f"unavailable: {e}"

    server = ROOT / "server.py"
    return {
        "captured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "os": platform.platform(), "machine": platform.machine(), "python": sys.version.split()[0],
        "gpu": run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader", "-i", "0"]),
        "lms_ps": run([str(LMS), "ps"]),
        "server_py_sha256": hashlib.sha256(server.read_bytes()).hexdigest(),
    }


class Recorder:
    """Appends one JSON object per measurement to raw.jsonl."""

    def __init__(self, uc: str):
        self.dir = RESULTS / uc
        self.dir.mkdir(parents=True, exist_ok=True)
        self.raw = self.dir / "raw.jsonl"
        self.raw.write_text("", encoding="utf-8")
        (self.dir / "environment.json").write_text(json.dumps(environment(), ensure_ascii=False, indent=2),
                                                   encoding="utf-8")

    def add(self, **row):
        row.setdefault("ts", time.time())
        with open(self.raw, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def summary(self, data: dict):
        (self.dir / "summary.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def svg_timeseries(samples: list[dict], spans: list[tuple[float, float, str]], path: Path, title: str) -> None:
    """Dependency-free SVG chart of GPU util (%) and memory (GiB) with shaded measurement spans."""
    if not samples:
        return
    W, H, L, R, T, B = 960, 320, 56, 64, 36, 40
    t0, t1 = samples[0]["t"], samples[-1]["t"]
    span = max(t1 - t0, 1e-6)
    mem_max = max(s["mem_mib"] for s in samples) / 1024 * 1.1
    x = lambda t: L + (t - t0) / span * (W - L - R)
    yu = lambda u: T + (1 - u / 100) * (H - T - B)
    ym = lambda m: T + (1 - (m / 1024) / mem_max) * (H - T - B)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="Segoe UI,sans-serif" font-size="12">',
             f'<rect width="{W}" height="{H}" fill="#0f172a"/>',
             f'<text x="{L}" y="22" fill="#e2e8f0" font-size="14">{title}</text>']
    for a, b, label in spans:
        parts.append(f'<rect x="{x(a):.1f}" y="{T}" width="{max(x(b) - x(a), 1):.1f}" height="{H - T - B}" fill="#334155" opacity="0.6"/>')
        parts.append(f'<text x="{x(a) + 2:.1f}" y="{T + 12}" fill="#94a3b8" font-size="10">{label}</text>')
    for u in (0, 25, 50, 75, 100):
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{yu(u):.1f}" y2="{yu(u):.1f}" stroke="#1e293b"/>')
        parts.append(f'<text x="{L - 6}" y="{yu(u) + 4:.1f}" fill="#22c55e" text-anchor="end">{u}%</text>')
    step = max(1, int(mem_max // 4))
    for g in range(0, int(mem_max) + 1, step):
        parts.append(f'<text x="{W - R + 6}" y="{ym(g * 1024) + 4:.1f}" fill="#60a5fa">{g} GiB</text>')
    for sec in range(0, int(span) + 1, max(1, int(span // 8))):
        parts.append(f'<text x="{x(t0 + sec):.1f}" y="{H - B + 16}" fill="#94a3b8" text-anchor="middle">{sec}s</text>')
    util = " ".join(f"{x(s['t']):.1f},{yu(s['util']):.1f}" for s in samples)
    mem = " ".join(f"{x(s['t']):.1f},{ym(s['mem_mib']):.1f}" for s in samples)
    parts += [f'<polyline points="{util}" fill="none" stroke="#22c55e" stroke-width="1.5"/>',
              f'<polyline points="{mem}" fill="none" stroke="#60a5fa" stroke-width="1.5"/>',
              f'<text x="{W - R - 250}" y="22" fill="#22c55e">— GPU util (%)</text>',
              f'<text x="{W - R - 130}" y="22" fill="#60a5fa">— GPU memory (GiB)</text>',
              "</svg>"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts), encoding="utf-8")

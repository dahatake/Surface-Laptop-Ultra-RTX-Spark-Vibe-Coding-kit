"""UC2 GPU-grounded critique: throughput scaling, tool-vs-independent GPU telemetry, and allowlist rejections."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from common import BENCH, ROOT, GpuLogger, Recorder, mcp_client, stats, svg_timeseries, timed_call

ATTACKS = {
    "shell launcher": ["cmd", "/c", "whoami"],
    "powershell": ["powershell", "-Command", "Get-Process"],
    "absolute exe path": [sys.executable, "llm_workload.py"],
    "python -c": ["python", "-c", "print('pwned')"],
    "python -m other": ["python", "-m", "http.server"],
    "script outside roots": ["python", r"..\..\..\outside.py"],
    "non-.py script": ["python", "README.md"],
    "pytest plugin": ["pytest", "-p", "evil_plugin"],
    "pytest target outside": ["pytest", os.environ.get("SystemRoot", r"C:\Windows")],
    "node eval": ["node", "-e", "1"],
}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


async def main(n: int, levels: list[int]) -> None:
    rec = Recorder("uc2")
    spans = []
    summary: dict = {"n_per_level": n, "levels": {}}
    with GpuLogger(rec.dir / "gpu_log.csv") as gpu:
        t_idle = time.time()
        time.sleep(5)
        idle = gpu.window(t_idle, time.time())
        summary["idle"] = {"util": stats([s["util"] for s in idle]), "mem_mib": stats([s["mem_mib"] for s in idle]),
                           "power_w": stats([s["power_w"] for s in idle])}
        idle_mem = summary["idle"]["mem_mib"]["median"]
        async with mcp_client() as c:
            for p in levels:
                runs = []
                for i in range(n + 1):
                    t0 = time.time()
                    out, sec = await timed_call(c, "gpu_profile_run", {
                        "argv": ["python", "llm_workload.py", str(p)], "cwd": str(BENCH), "interval_sec": 0.25})
                    t1 = time.time()
                    rep = json.loads(out)
                    wl = json.loads(rep["output_tail"].strip().splitlines()[-1])
                    ind = gpu.window(t0, t1)
                    row = {
                        "parallel": p, "run": i, "warmup": i == 0, "exit_code": rep["exit_code"],
                        "wall_time_sec": rep["wall_time_sec"], "tool_samples": rep["samples"],
                        "tool_util_avg": rep["gpu_util_pct"]["avg"], "tool_util_max": rep["gpu_util_pct"]["max"],
                        "tool_mem_max_mib": rep["gpu_mem_used_mib"]["max"],
                        "ind_samples": len(ind), "ind_util_avg": round(mean([s["util"] for s in ind]), 1),
                        "ind_util_max": max(s["util"] for s in ind), "ind_mem_max_mib": max(s["mem_mib"] for s in ind),
                        "ind_power_avg_w": round(mean([s["power_w"] for s in ind]) or 0, 1),
                        "workload": wl,
                    }
                    rec.add(kind="profile_run", **row, tool_report=rep)
                    if i:
                        runs.append(row)
                        spans.append((t0, t1, f"p{p}"))
                summary["levels"][str(p)] = {
                    "aggregate_tokens_per_sec": stats([r["workload"]["aggregate_tokens_per_sec"] for r in runs]),
                    "client_tokens_per_sec_per_request": stats([x for r in runs for x in r["workload"]["client_tokens_per_sec_per_request"]]),
                    "server_tokens_per_sec_per_request": stats([x for r in runs for x in r["workload"]["server_tokens_per_sec_per_request"]]),
                    "server_ttft_sec": stats([x for r in runs for x in r["workload"]["server_ttft_sec"]]),
                    "tool_util_avg": stats([r["tool_util_avg"] for r in runs]),
                    "independent_util_avg": stats([r["ind_util_avg"] for r in runs]),
                    "util_avg_abs_diff_tool_vs_independent": stats([abs(r["tool_util_avg"] - r["ind_util_avg"]) for r in runs]),
                    "mem_peak_mib_tool": stats([r["tool_mem_max_mib"] for r in runs]),
                    "mem_peak_mib_independent": stats([r["ind_mem_max_mib"] for r in runs]),
                    "mem_delta_over_idle_mib": stats([r["ind_mem_max_mib"] - idle_mem for r in runs]),
                    "power_avg_w": stats([r["ind_power_avg_w"] for r in runs]),
                    "wall_time_sec": stats([r["wall_time_sec"] for r in runs]),
                    "model": runs[0]["workload"]["model"], "quant": runs[0]["workload"]["quant"],
                    "runtime": runs[0]["workload"]["runtime"],
                }

            rejections = {}
            for name, argv in ATTACKS.items():
                out, sec = await timed_call(c, "gpu_profile_run", {"argv": argv, "cwd": str(BENCH)})
                rep = json.loads(out)
                ok = bool(rep.get("rejected")) and "exit_code" not in rep
                rejections[name] = {"rejected": ok, "reason": rep.get("reason"), "latency_ms": round(sec * 1000, 1)}
                rec.add(kind="attack", name=name, argv=argv, rejected=ok, latency_sec=sec, output=rep)
            out, sec = await timed_call(c, "gpu_profile_run", {"argv": ["python", "x.py"],
                                                              "cwd": os.environ.get("SystemRoot", r"C:\Windows")})
            rep = json.loads(out)
            rejections["cwd outside roots"] = {"rejected": bool(rep.get("rejected")), "reason": rep.get("reason"),
                                               "latency_ms": round(sec * 1000, 1)}
            summary["rejections"] = {"total": len(rejections), "rejected": sum(v["rejected"] for v in rejections.values()),
                                     "cases": rejections}
    rec.summary(summary)
    svg_timeseries(gpu.samples(), spans, ROOT / "docs" / "media" / "uc2-gpu-timeline.svg",
                   f"UC2 — independent nvidia-smi log, parallel={levels} x N={n} (shaded = measured runs)")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--levels", default="1,2,4")
    a = ap.parse_args()
    asyncio.run(main(a.n, [int(x) for x in a.levels.split(",")]))

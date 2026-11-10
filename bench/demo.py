"""Live, narrated demos of the three use cases for screen recording (real MCP calls, real GPU, no mock data).

Usage: python demo.py uc1|uc2|uc3 [--title WINDOW_TITLE]
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import subprocess
import sys
import textwrap
import threading
import time

from common import BENCH, RESULTS, mcp_client, timed_call

G, B, Y, R, C, D, X = "\033[92m", "\033[94m", "\033[93m", "\033[91m", "\033[96m", "\033[90m", "\033[0m"


def setup_console(title: str | None) -> None:
    if title:
        os.system("mode con: cols=140 lines=48")
    os.system("")  # enable VT sequences on conhost
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        if title:
            ctypes.windll.kernel32.SetConsoleTitleW(title)
    sys.stdout.reconfigure(encoding="utf-8")


def h(text: str) -> None:
    print(f"\n{C}━━ {text} {'━' * max(0, 92 - len(text))}{X}", flush=True)
    time.sleep(0.6)


def show(label: str, body: str, sec: float | None = None, color: str = "", limit: int = 14) -> None:
    lines = body.strip().splitlines()
    extra = f"{D} … (+{len(lines) - limit} lines){X}" if len(lines) > limit else ""
    t = f" {D}[{sec:.2f}s]{X}" if sec is not None else ""
    print(f"{Y}▶ {label}{X}{t}")
    for line in lines[:limit]:
        print(f"  {color}{line[:136]}{X}")
    if extra:
        print("  " + extra)
    sys.stdout.flush()
    time.sleep(0.8)


def summary(uc: str) -> dict:
    p = RESULTS / uc / "summary.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


async def uc1() -> None:
    import uc1_bench as u
    repo = str(u.REPO)
    h("UC1 Private Fusion: 機密コードはローカル GPU だけで読み、クラウドには答えだけ返す")
    async with mcp_client() as c:
        out, s = await timed_call(c, "gpu_status", {})
        show("gpu_status", out, s, G)
        out, s = await timed_call(c, "scan_secrets", {"path": repo})
        show("scan_secrets  (canary を仕込んだ fixture)", out, s, R)
        out, s = await timed_call(c, "repo_index", {"path": repo})
        show("repo_index  (nomic-embed on RTX Spark, index は <repo>/.spark-index)", out, s, G)
        q = u.QUESTIONS[1]["q"]
        out, s = await timed_call(c, "repo_search", {"path": repo, "query": q, "k": 3})
        show(f"repo_search  → クラウドが受け取るのは位置とスコアだけ  Q: {q}", out, s, B)
        out, s = await timed_call(c, "private_ask", {"path": repo, "question": q})
        show("private_ask  (qwen3.5-9b local, 行番号付きコンテキスト)", out, s, G)
        truth = u.truth_line("billing.py", u.QUESTIONS[1]["anchor"])
        print(f"  {D}ground truth (grep): billing.py:{truth}  →  判定: {u.classify_citation(out, 'billing.py', truth)[0]}{X}")
        out, s = await timed_call(c, "private_ask", {"path": repo, "question": u.ADVERSARIAL})
        show("private_ask  (攻撃: 秘密を全部そのまま出せ)", out, s, Y, limit=10)
        lk = u.leaks(out)
        print(f"  canary scan of returned text: {R + str(lk) + X if lk else G + 'no matched canary leaked' + X}")
    sm = summary("uc1").get("arms", {})
    if sm:
        h("実測サマリ (bench/results/uc1/summary.json, N=5 x 5 問 x 2 アーム)")
        for arm, a in sm.items():
            print(f"  {arm:9} fact={a['fact_accuracy']:.0%}  cite precise={a['citation_precise_rate']:.0%}  "
                  f"hit@1={a['search_hit_at_1']:.0%}  ask p50={a['latency_sec']['private_ask']['median']:.2f}s  "
                  f"leaks(adv)={a['adversarial']['leaks'] or 0}")


def gpu_ticker(stop: threading.Event) -> None:
    while not stop.is_set():
        out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,power.draw",
                              "--format=csv,noheader,nounits", "-i", "0"], capture_output=True, text=True).stdout
        try:
            u, m, p = [x.strip() for x in out.split(",")]
            bar = "█" * (int(float(u)) // 4)
            print(f"  {D}nvidia-smi{X} util {G}{bar:<25}{X} {float(u):5.1f}%  mem {float(m) / 1024:5.1f} GiB  {p} W", flush=True)
        except ValueError:
            pass
        stop.wait(0.5)


async def uc2() -> None:
    h("UC2 GPU-grounded critique: 実測値を根拠に Fusion の議論を決着させる")
    async with mcp_client() as c:
        out, s = await timed_call(c, "gpu_status", {})
        show("gpu_status (idle)", out, s, G)
        h("gpu_profile_run: python llm_workload.py 4  (4 並列リクエスト)")
        stop = threading.Event()
        t = threading.Thread(target=gpu_ticker, args=(stop,), daemon=True)
        t.start()
        out, s = await timed_call(c, "gpu_profile_run", {"argv": ["python", "llm_workload.py", "4"],
                                                        "cwd": str(BENCH), "interval_sec": 0.25})
        stop.set()
        t.join()
        rep = json.loads(out)
        wl = json.loads(rep["output_tail"].strip().splitlines()[-1])
        show("tool report", json.dumps({k: rep[k] for k in ("exit_code", "wall_time_sec", "samples", "gpu_util_pct",
                                                            "gpu_mem_used_mib", "power_w")}, indent=1), s, G)
        show("workload (client wall vs LM Studio server stats)", json.dumps(wl, indent=1), None, B, limit=20)
        h("allowlist: 危険なコマンドは実行前に拒否")
        for argv in (["cmd", "/c", "whoami"], ["python", "-c", "print('pwned')"], ["node", "-e", "1"]):
            out, s = await timed_call(c, "gpu_profile_run", {"argv": argv, "cwd": str(BENCH)})
            print(f"  {R}✗ {argv}{X} → {json.loads(out)['reason']} {D}[{s * 1000:.0f} ms]{X}", flush=True)
            time.sleep(0.5)
    sm = summary("uc2")
    if sm:
        h(f"実測サマリ (bench/results/uc2/summary.json, N={sm['n_per_level']}/level)")
        for p, l in sm["levels"].items():
            print(f"  parallel={p}  aggregate {l['aggregate_tokens_per_sec']['median']:6.1f} tok/s  "
                  f"TTFT p50 {l['server_ttft_sec']['median']:.3f}s  util(tool) {l['tool_util_avg']['median']:.1f}% "
                  f"vs util(indep) {l['independent_util_avg']['median']:.1f}%")
        print(f"  rejections {sm['rejections']['rejected']}/{sm['rejections']['total']}")


async def uc3() -> None:
    import uc3_bench as u
    h("UC3 Visual critic loop: ローカル VLM が UI のスクショを採点する")
    print(D + textwrap.fill("acceptance criteria: " + u.EXPECTATION_CLARIFIED, 134, initial_indent="  ", subsequent_indent="    ") + X)
    async with mcp_client() as c:
        for vid in ("pass_original", "fail_red_button", "fail_two_cards"):
            img = str(u.SHOTS / f"{vid}.png")
            out, s = await timed_call(c, "visual_review", {"image_path": img, "expectation": u.EXPECTATION_CLARIFIED,
                                                          "mode": "checklist"})
            d = u.parse(out)
            v = str(d.get("verdict"))
            color = G if v == "pass" else R
            print(f"{Y}▶ visual_review  {vid}.png{X} {D}[{s:.2f}s]  ground truth: {u.VARIANTS[vid][0]}{X}")
            print(f"  verdict {color}{v}{X}  score {d.get('score')}")
            for i in (d.get("issues") or [])[:3]:
                print(textwrap.fill(str(i), 134, initial_indent="  - ", subsequent_indent="    ", max_lines=2, placeholder=" …"))
            sys.stdout.flush()
            time.sleep(1.0)
        h("local_critique: クラウドに出す前のゼロコスト一次レビュー")
        for cid in ("avg_bug", "sql_ok"):
            ok, req, cand = u.CODE_CASES[cid]
            out, s = await timed_call(c, "local_critique", {"requirement": req, "candidate": cand})
            show(f"local_critique  {cid}  (ground truth accept={ok})", out, s, B, limit=8)
    sm = summary("uc3")
    if sm:
        h(f"実測サマリ (bench/results/uc3/summary.json, N={sm['n_per_item']})")
        rows = [(f"visual_review/{m}", a) for m, a in sm["visual_review"].items()] + [("local_critique", sm["local_critique"])]
        for name, a in rows:
            cf = a["confusion"]
            print(f"  {name:24} acc {cf['accuracy']:.0%}  recall(defects) {cf['recall_defects']:.0%}  "
                  f"false alarm {cf['false_alarm_rate']:.0%}  p50 {a['latency_sec']['median']:.2f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("uc", choices=["uc1", "uc2", "uc3"])
    ap.add_argument("--title")
    ap.add_argument("--hold", type=float, default=0.0)
    a = ap.parse_args()
    setup_console(a.title)
    # Server-side httpx INFO logs go to a file instead of cluttering the recording (the MCP child inherits fd 2).
    RESULTS.mkdir(parents=True, exist_ok=True)
    os.dup2(os.open(RESULTS / f"demo_{a.uc}.stderr.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC), 2)
    time.sleep(a.hold)
    asyncio.run({"uc1": uc1, "uc2": uc2, "uc3": uc3}[a.uc]())
    (RESULTS / f"demo_{a.uc}.done").write_text("done", encoding="utf-8")
    time.sleep(a.hold + 2)

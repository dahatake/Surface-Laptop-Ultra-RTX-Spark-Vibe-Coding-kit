"""UC3 Visual critic loop: confusion matrix for visual_review on labelled UI variants and for local_critique.

Ground truth = labels assigned when the variants are generated (each fail variant breaks exactly one criterion).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

from common import BENCH, RESULTS, ROOT, GpuLogger, Recorder, mcp_client, stats, svg_timeseries, timed_call

BASE = (ROOT / "demo" / "ui" / "index.html").read_text(encoding="utf-8")
UI_DIR = BENCH / "fixtures" / "ui"
SHOTS = ROOT / "docs" / "media" / "uc3-variants"
EXPECTATION = ("Dark dashboard titled 'RTX Spark Dashboard' with 3 metric cards in one row "
               "(GPU usage, unified memory, tokens/sec) and a blue benchmark button.")
# Same spec, but states that labels may be localized (the UI under test is Japanese).
EXPECTATION_CLARIFIED = EXPECTATION + " Card labels may be localized (e.g. Japanese); judge meaning, not language."
ARMS = {"holistic": ("holistic", EXPECTATION), "checklist": ("checklist", EXPECTATION),
        "checklist_clarified": ("checklist", EXPECTATION_CLARIFIED)}

# id -> (label, html transform, regex that the model's *issues* must match to count as naming the real defect)
VARIANTS = {
    "pass_original": ("pass", lambda h: h, None),
    "pass_other_values": ("pass", lambda h: h.replace("72%", "91%").replace("38 GB", "44 GB").replace(">85<", ">112<"), None),
    "fail_stacked": ("fail", lambda h: h.replace("repeat(3, 1fr)", "1fr"), r"stack|vertical"),
    "fail_two_cards": ("fail", lambda h: re.sub(r'\s*<div class="card"><div>トークン/秒</div>.*?</div></div>', "", h),
                       r"\b(two|2)\b(\s+\w+){0,2}\s+cards|third[^.]*(missing|not)|(no|missing)[^.]*tokens"),
    "fail_red_button": ("fail", lambda h: h.replace("background: #2563eb", "background: #dc2626"), r"\bred\b|not blue"),
    "fail_wrong_title": ("fail", lambda h: h.replace("<h1>RTX Spark Dashboard</h1>", "<h1>GPU Monitor</h1>"),
                         r"GPU Monitor|title[^.]*(missing|incorrect|wrong|differ|not)"),
    "fail_light_theme": ("fail", lambda h: h.replace("background: #0f172a; color: #e2e8f0", "background: #f8fafc; color: #0f172a")
                         .replace("background: #1e293b", "background: #e2e8f0"), r"light (mode|theme|background|colou?r)|not dark|white"),
}

CODE_CASES = {
    "avg_bug": (False, "Return the average of a list of numbers; empty list must return 0.",
                "def avg(xs):\n    return sum(xs) / len(xs)"),
    "avg_ok": (True, "Return the average of a list of numbers; empty list must return 0.",
               "def avg(xs):\n    return sum(xs) / len(xs) if xs else 0"),
    "leap_bug": (False, "Return True if year is a Gregorian leap year.",
                 "def is_leap(y):\n    return y % 4 == 0"),
    "leap_ok": (True, "Return True if year is a Gregorian leap year.",
                "def is_leap(y):\n    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)"),
    "sql_bug": (False, "Look up a user by name using a DB-API cursor; must be safe against SQL injection.",
                "def find(cur, name):\n    cur.execute(f\"SELECT * FROM users WHERE name = '{name}'\")\n    return cur.fetchone()"),
    "sql_ok": (True, "Look up a user by name using a DB-API cursor; must be safe against SQL injection.",
               "def find(cur, name):\n    cur.execute(\"SELECT * FROM users WHERE name = ?\", (name,))\n    return cur.fetchone()"),
}


def render_variants() -> dict[str, str]:
    UI_DIR.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    paths = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1200, "height": 600})
        for vid, (_, tf, _) in VARIANTS.items():
            html = UI_DIR / f"{vid}.html"
            html.write_text(tf(BASE), encoding="utf-8")
            png = SHOTS / f"{vid}.png"
            page.goto(html.as_uri())
            page.screenshot(path=str(png), full_page=True)
            paths[vid] = str(png)
        b.close()
    return paths


def matrix(rows: list[tuple[str, str]]) -> dict:
    """rows of (truth, predicted) where positive class = 'fail' (defect detected)."""
    tp = sum(t == "fail" and p == "fail" for t, p in rows)
    tn = sum(t == "pass" and p == "pass" for t, p in rows)
    fp = sum(t == "pass" and p == "fail" for t, p in rows)
    fn = sum(t == "fail" and p == "pass" for t, p in rows)
    other = len(rows) - tp - tn - fp - fn
    return {"tp": tp, "tn": tn, "fp_false_alarm": fp, "fn_missed_defect": fn, "unparseable": other,
            "accuracy": round((tp + tn) / len(rows), 3) if rows else None,
            "recall_defects": round(tp / (tp + fn), 3) if tp + fn else None,
            "false_alarm_rate": round(fp / (fp + tn), 3) if fp + tn else None}


def parse(out: str) -> dict:
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}


async def main(n: int, shots: dict[str, str]) -> None:
    rec = Recorder("uc3")
    spans, code_rows, code_lat = [], [], []
    arms = {}
    with GpuLogger(rec.dir / "gpu_log.csv") as gpu:
        async with mcp_client() as c:
            await timed_call(c, "visual_review", {"image_path": shots["pass_original"], "expectation": EXPECTATION})
            for arm, (mode, expectation) in ARMS.items():
                rows, lat, per_variant = [], [], {}
                reason_hits = reason_total = 0
                for vid, (label, _, reason_re) in VARIANTS.items():
                    pv = {"label": label, "verdicts": [], "scores": [], "reason_ok": 0}
                    for i in range(n):
                        t0 = time.time()
                        out, sec = await timed_call(c, "visual_review", {"image_path": shots[vid],
                                                                        "expectation": expectation, "mode": mode})
                        spans.append((t0, time.time(), ""))
                        d = parse(out)
                        verdict = str(d.get("verdict", "unparseable")).lower()
                        rok = None
                        if label == "fail" and verdict == "fail":
                            rok = bool(re.search(reason_re, " ".join(map(str, d.get("issues", []))), re.I))
                            reason_total += 1
                            reason_hits += rok
                            pv["reason_ok"] += rok
                        pv["verdicts"].append(verdict)
                        pv["scores"].append(d.get("score"))
                        rows.append((label, verdict))
                        lat.append(sec)
                        rec.add(kind="visual_review", arm=arm, mode=mode, variant=vid, label=label, run=i, verdict=verdict,
                                score=d.get("score"), reason_ok=rok, latency_sec=sec, output=out)
                    per_variant[vid] = pv
                arms[arm] = {"confusion": matrix(rows), "latency_sec": stats(lat),
                              "correct_reason_rate_on_detected_defects":
                                  round(reason_hits / reason_total, 3) if reason_total else None,
                              "per_variant": per_variant}
            per_case = {}
            for cid, (ok, req, cand) in CODE_CASES.items():
                truth = "pass" if ok else "fail"
                pc = []
                for i in range(n):
                    out, sec = await timed_call(c, "local_critique", {"requirement": req, "candidate": cand})
                    d = parse(out)
                    pred = {True: "pass", False: "fail"}.get(d.get("accept"), "unparseable")
                    pc.append(pred)
                    code_rows.append((truth, pred))
                    code_lat.append(sec)
                    rec.add(kind="local_critique", case=cid, truth=truth, run=i, predicted=pred, latency_sec=sec, output=out)
                per_case[cid] = {"truth": truth, "predicted": pc}

    summary = {
        "n_per_item": n, "expectation": EXPECTATION,
        "visual_review": arms,
        "local_critique": {"confusion": matrix(code_rows), "latency_sec": stats(code_lat), "per_case": per_case},
        "screenshots": {k: str(v) for k, v in shots.items()},
    }
    rec.summary(summary)
    svg_timeseries(gpu.samples(), spans, ROOT / "docs" / "media" / "uc3-gpu-timeline.svg",
                   f"UC3 — independent nvidia-smi log ({len(VARIANTS)} UI variants + {len(CODE_CASES)} code cases, N={n})")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def rescore() -> None:
    """Re-grade reason_ok from raw.jsonl with the current regexes (no model calls); verdicts are untouched."""
    rec_dir = RESULTS / "uc3"
    rows = [json.loads(l) for l in (rec_dir / "raw.jsonl").read_text(encoding="utf-8").splitlines() if l]
    summary = json.loads((rec_dir / "summary.json").read_text(encoding="utf-8"))
    changed = 0
    for arm, a in summary["visual_review"].items():
        hits = total = 0
        for vid, pv in a["per_variant"].items():
            ok = 0
            for r in rows:
                if r["kind"] == "visual_review" and r["arm"] == arm and r["variant"] == vid and r["reason_ok"] is not None:
                    new = bool(re.search(VARIANTS[vid][2], " ".join(map(str, parse(r["output"]).get("issues", []))), re.I))
                    changed += new != r["reason_ok"]
                    r["reason_ok"] = new
                    ok += new
                    total += 1
            pv["reason_ok"] = ok
            hits += ok
        a["correct_reason_rate_on_detected_defects"] = round(hits / total, 3) if total else None
    summary["reason_regexes"] = {k: v[2] for k, v in VARIANTS.items() if v[2]}
    (rec_dir / "raw.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (rec_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rescored: {changed} reason_ok labels changed")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--rescore", action="store_true", help="re-grade reasons from raw.jsonl without calling models")
    args = ap.parse_args()
    if args.rescore:
        rescore()
    else:
        asyncio.run(main(args.n, render_variants()))

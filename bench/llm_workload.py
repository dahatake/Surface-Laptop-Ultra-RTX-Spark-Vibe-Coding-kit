"""UC2 workload: local LLM decode throughput with 1..P concurrent requests (run under gpu_profile_run).

Prints one JSON line with client-side wall-clock throughput AND LM Studio's server-side stats
(tokens_per_second, time_to_first_token), so the two measurements can be cross-checked.
"""

import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = os.environ.get("SPARK_LMSTUDIO_URL", "http://localhost:1234/v1").rsplit("/v1", 1)[0] + "/api/v0/chat/completions"
MODEL = os.environ.get("SPARK_CHAT_MODEL", "qwen/qwen3.5-9b")
PARALLEL = int(sys.argv[1]) if len(sys.argv) > 1 else 1
MAX_TOKENS = int(sys.argv[2]) if len(sys.argv) > 2 else 400


def one(i: int) -> dict:
    body = json.dumps({
        "model": MODEL, "max_tokens": MAX_TOKENS, "temperature": 0.7, "reasoning_effort": "none",
        "messages": [{"role": "user", "content": f"[{i}] Write a long, detailed explanation of CUDA warp scheduling."}],
    }).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)
    return {"wall": time.perf_counter() - t0, "tokens": d["usage"]["completion_tokens"], "stats": d.get("stats", {}),
            "quant": d.get("model_info", {}).get("quant"), "runtime": d.get("runtime", {}).get("name")}


t0 = time.perf_counter()
with ThreadPoolExecutor(PARALLEL) as ex:
    res = list(ex.map(one, range(PARALLEL)))
wall = time.perf_counter() - t0
tokens = sum(r["tokens"] for r in res)
print(json.dumps({
    "model": MODEL, "quant": res[0]["quant"], "runtime": res[0]["runtime"], "parallel": PARALLEL,
    "completion_tokens": tokens, "wall_sec": round(wall, 3),
    "aggregate_tokens_per_sec": round(tokens / wall, 2),
    "client_tokens_per_sec_per_request": [round(r["tokens"] / r["wall"], 2) for r in res],
    "server_tokens_per_sec_per_request": [round(r["stats"].get("tokens_per_second", 0), 2) for r in res],
    "server_ttft_sec": [round(r["stats"].get("time_to_first_token", 0), 3) for r in res],
}))

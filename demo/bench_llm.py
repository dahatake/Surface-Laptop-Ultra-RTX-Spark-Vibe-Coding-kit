"""Measures local LLM decode throughput on the RTX Spark GPU (demo workload for Use Case 2)."""

import json
import os
import sys
import time
import urllib.request

URL = os.environ.get("SPARK_LMSTUDIO_URL", "http://localhost:1234/v1") + "/chat/completions"
MODEL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SPARK_CHAT_MODEL", "qwen/qwen3.5-9b")

body = json.dumps({
    "model": MODEL, "max_tokens": 400, "temperature": 0.7,
    "messages": [{"role": "user", "content": "Write a detailed explanation of CUDA warp scheduling."}],
    "reasoning_effort": "none",
}).encode()
req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
t0 = time.time()
with urllib.request.urlopen(req, timeout=600) as r:
    data = json.load(r)
dt = time.time() - t0
tokens = data["usage"]["completion_tokens"]
print(json.dumps({"model": MODEL, "completion_tokens": tokens, "seconds": round(dt, 2),
                  "tokens_per_sec": round(tokens / dt, 1)}))

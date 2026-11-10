"""spark-vibe MCP server.

Exposes the Surface Laptop Ultra's NVIDIA RTX Spark (local GPU + unified memory,
served through LM Studio's OpenAI-compatible API) as tools that GitHub Copilot
Fusion can orchestrate from VS Code or Copilot CLI.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import numpy as np
from mcp.server.mcpserver import MCPServer

LMSTUDIO_URL = os.environ.get("SPARK_LMSTUDIO_URL", "http://localhost:1234/v1")
CHAT_MODEL = os.environ.get("SPARK_CHAT_MODEL", "qwen/qwen3.5-9b")
VISION_MODEL = os.environ.get("SPARK_VISION_MODEL", "google/gemma-4-e4b")
EMBED_MODEL = os.environ.get("SPARK_EMBED_MODEL", "text-embedding-nomic-embed-text-v1.5")
# Hybrid reasoning models (e.g. qwen3.5) otherwise spend the whole token budget thinking and return empty content.
REASONING_EFFORT = os.environ.get("SPARK_REASONING_EFFORT", "none")
# Prefix each context line with its real line number so the local model can cite file:line exactly.
NUMBERED_CONTEXT = os.environ.get("SPARK_NUMBERED_CONTEXT", "1") != "0"
INDEX_DIR_NAME = ".spark-index"

CODE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".cs", ".java", ".go", ".rs", ".c", ".h",
    ".cpp", ".hpp", ".cu", ".cuh", ".kt", ".swift", ".rb", ".php", ".sql", ".ps1",
    ".sh", ".md", ".yaml", ".yml", ".json", ".toml", ".bicep", ".tf", ".html", ".css",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
             "bin", "obj", ".next", INDEX_DIR_NAME, "target"}
MAX_FILE_BYTES = 400_000
CHUNK_LINES = 60
CHUNK_MAX_CHARS = 1500

SECRET_PATTERNS = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("azure_storage_key", re.compile(r"AccountKey=[A-Za-z0-9+/=]{40,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("connection_string_password", re.compile(r"(?i)password\s*=\s*[^;\s'\"]{6,}")),
    ("generic_secret", re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-+/=]{16,}['\"]")),
]

# gpu_profile_run never uses a shell: only these launchers, only scripts/targets under the allowed roots.
PROFILE_ROOTS = [Path(p).expanduser().resolve() for p in
                 os.environ.get("SPARK_PROFILE_ROOTS", str(Path(__file__).resolve().parent)).split(os.pathsep)
                 if p.strip()]
PROFILE_LAUNCHERS = {"python", "pytest", "node"}
# Interpreter for profiled Python projects; set by the user via server env, never by the tool caller.
PROFILE_PYTHON = os.environ.get("SPARK_PROFILE_PYTHON") or sys.executable
PYTHON_SCRIPT_EXTS = {".py"}
NODE_SCRIPT_EXTS = {".js", ".mjs", ".cjs"}
# pytest options that load code or config from outside the allowed roots.
PYTEST_BLOCKED_OPTS = ("-p", "--pyargs", "-c", "--config-file", "--rootdir", "--confcutdir", "--import-mode")
PROFILE_MAX_TIMEOUT_SEC = 3600

mcp = MCPServer("spark-vibe")


def _client() -> httpx.Client:
    return httpx.Client(base_url=LMSTUDIO_URL, timeout=httpx.Timeout(600.0, connect=5.0))


def _chat(messages: list[dict], model: str, max_tokens: int = 1500, temperature: float = 0.2) -> str:
    with _client() as c:
        r = c.post("/chat/completions", json={
            "model": model, "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature, "reasoning_effort": REASONING_EFFORT,
        })
        r.raise_for_status()
        content = r.json()["choices"][0]["message"].get("content") or ""
    return re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()


def _embed(texts: list[str]) -> np.ndarray:
    vectors: list[list[float]] = []
    with _client() as c:
        for i in range(0, len(texts), 32):
            r = c.post("/embeddings", json={"model": EMBED_MODEL, "input": texts[i:i + 32]})
            r.raise_for_status()
            vectors.extend(d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"]))
    arr = np.asarray(vectors, dtype=np.float32)
    return arr / np.maximum(np.linalg.norm(arr, axis=1, keepdims=True), 1e-9)


def _redact(text: str) -> tuple[str, list[str]]:
    found: list[str] = []
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            found.append(name)
            text = pattern.sub(f"[REDACTED:{name}]", text)
    return text, found


def _iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            p = Path(dirpath) / f
            if p.suffix.lower() in CODE_EXTS and p.stat().st_size <= MAX_FILE_BYTES:
                yield p


def _chunks(path: Path, root: Path):
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return
    rel = path.relative_to(root).as_posix()
    for start in range(0, max(len(lines), 1), CHUNK_LINES):
        body = "\n".join(lines[start:start + CHUNK_LINES])[:CHUNK_MAX_CHARS]
        if body.strip():
            yield {"file": rel, "start": start + 1, "end": min(start + CHUNK_LINES, len(lines)), "text": body}


def _extract_json(raw: str) -> str:
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if m:
        try:
            return json.dumps(json.loads(m.group(0)), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
    return raw


# ---------------------------------------------------------------------------
# Use case 1: Private-by-default Fusion (local RAG + local reasoning on secrets)
# ---------------------------------------------------------------------------

@mcp.tool()
def repo_index(path: str) -> str:
    """Build a local semantic index of a repository on the RTX Spark GPU (nomic embeddings via LM Studio).
    The index is stored in <path>/.spark-index and never leaves the device."""
    root = Path(path).resolve()
    if not root.is_dir():
        return f"Not a directory: {root}"
    started = time.time()
    chunks = [c for f in _iter_files(root) for c in _chunks(f, root)]
    if not chunks:
        return "No indexable files found."
    for c in chunks:
        c["text"] = _redact(c["text"])[0]
    vecs = _embed([f"search_document: {c['file']}\n{c['text']}" for c in chunks])
    out = root / INDEX_DIR_NAME
    out.mkdir(exist_ok=True)
    np.save(out / "vectors.npy", vecs)
    (out / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    (out / ".gitignore").write_text("*\n", encoding="utf-8")
    files = len({c["file"] for c in chunks})
    return f"Indexed {len(chunks)} chunks from {files} files in {time.time() - started:.1f}s -> {out}"


def _search(root: Path, query: str, k: int) -> list[dict]:
    idx = root / INDEX_DIR_NAME
    if not (idx / "vectors.npy").exists():
        raise FileNotFoundError(f"No index at {idx}. Call repo_index first.")
    vecs = np.load(idx / "vectors.npy")
    chunks = json.loads((idx / "chunks.json").read_text(encoding="utf-8"))
    q = _embed([f"search_query: {query}"])[0]
    scores = vecs @ q
    top = np.argsort(-scores)[:k]
    return [{**chunks[i], "score": round(float(scores[i]), 4)} for i in top]


@mcp.tool()
def repo_search(path: str, query: str, k: int = 8) -> str:
    """Semantic search over the local index. Returns file:line locations and scores only (no code bodies),
    so the cloud model learns WHERE to look without receiving proprietary code."""
    try:
        hits = _search(Path(path).resolve(), query, k)
    except FileNotFoundError as e:
        return str(e)
    return "\n".join(f"{h['score']:.3f}  {h['file']}:{h['start']}-{h['end']}" for h in hits)


def _numbered(hit: dict) -> str:
    return "\n".join(f"{hit['start'] + i:>4}| {line}" for i, line in enumerate(hit["text"].splitlines()))


@mcp.tool()
def private_ask(path: str, question: str, k: int = 6) -> str:
    """Answer a question about proprietary code using ONLY the local LLM on the RTX Spark GPU.
    Relevant code is retrieved locally, secrets are redacted, and only the local model's natural-language
    answer is returned to Copilot Fusion."""
    try:
        hits = _search(Path(path).resolve(), question, k)
    except FileNotFoundError as e:
        return str(e)
    context = "\n\n".join(f"### {h['file']}:{h['start']}-{h['end']}\n{_numbered(h) if NUMBERED_CONTEXT else h['text']}"
                          for h in hits)
    answer = _chat([
        {"role": "system", "content": "You are a senior engineer reviewing a private codebase. Answer precisely, "
         "cite file:line, and never reproduce secrets or long verbatim code. Summarize behavior instead."},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ], CHAT_MODEL)
    return _redact(answer)[0]


@mcp.tool()
def scan_secrets(path: str) -> str:
    """Scan a file or directory for credentials before any content is shared with cloud models."""
    target = Path(path).resolve()
    files = [target] if target.is_file() else list(_iter_files(target))
    findings = []
    for f in files:
        try:
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                findings.extend(f"{f}:{n}  {k}" for k in _redact(line)[1])
        except OSError:
            continue
    return "\n".join(findings) if findings else f"No secrets detected in {len(files)} file(s)."


# ---------------------------------------------------------------------------
# Use case 2: GPU-grounded critique (real measurements as evidence)
# ---------------------------------------------------------------------------

_SMI_FIELDS = "name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,clocks.sm"


def _num(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None


def _smi_sample() -> dict | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={_SMI_FIELDS}", "--format=csv,noheader,nounits", "-i", "0"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    parts = [p.strip() for p in out.split(",")]
    if len(parts) < 7:
        return None
    return {"name": parts[0], "util": _num(parts[1]), "mem_used_mib": _num(parts[2]),
            "mem_total_mib": _num(parts[3]), "temp_c": _num(parts[4]), "power_w": _num(parts[5]),
            "sm_clock_mhz": _num(parts[6])}


@mcp.tool()
def gpu_status() -> str:
    """Current NVIDIA RTX Spark GPU status (utilization, unified memory, temperature, power, clocks)."""
    s = _smi_sample()
    return json.dumps(s, ensure_ascii=False) if s else "nvidia-smi not available."


def _in_roots(p: Path) -> bool:
    return any(p == r or p.is_relative_to(r) for r in PROFILE_ROOTS)


def _rooted_file(arg: str, cwd: Path, exts: set[str]) -> str:
    p = (cwd / arg).resolve()
    if p.suffix.lower() not in exts:
        raise ValueError(f"'{arg}' must be a {'/'.join(sorted(exts))} file.")
    if not _in_roots(p) or not p.is_file():
        raise ValueError(f"'{arg}' is not an existing file under the allowed roots.")
    return str(p)


def _pytest_args(args: list[str], cwd: Path) -> list[str]:
    for a in args:
        if a.startswith("-"):
            if any(a == o or a.startswith(o + "=") or (len(o) == 2 and a.startswith(o)) for o in PYTEST_BLOCKED_OPTS):
                raise ValueError(f"pytest option '{a}' is not allowed.")
        elif not _in_roots((cwd / a.split("::", 1)[0]).resolve()):
            raise ValueError(f"pytest target '{a}' is outside the allowed roots.")
    return [PROFILE_PYTHON, "-m", "pytest", *args]


def _profile_argv(argv: list[str], cwd: Path) -> list[str]:
    """Map an allowlisted launcher + args to a concrete argv; raise ValueError for anything else."""
    if not argv or argv[0].lower() not in PROFILE_LAUNCHERS:
        raise ValueError(f"argv[0] must be one of {sorted(PROFILE_LAUNCHERS)} (no paths, no shell).")
    launcher, rest = argv[0].lower(), list(argv[1:])
    if launcher == "pytest":
        return _pytest_args(rest, cwd)
    if launcher == "python":
        if rest[:2] == ["-m", "pytest"]:
            return _pytest_args(rest[2:], cwd)
        if not rest or rest[0].startswith("-"):
            raise ValueError("python accepts only '<script>.py [args]' or '-m pytest [args]'.")
        return [PROFILE_PYTHON, _rooted_file(rest[0], cwd, PYTHON_SCRIPT_EXTS), *rest[1:]]
    node = shutil.which("node")
    if not node:
        raise ValueError("node is not installed.")
    if not rest or rest[0].startswith("-"):
        raise ValueError("node accepts only '<script>.js|.mjs|.cjs [args]'.")
    return [node, _rooted_file(rest[0], cwd, NODE_SCRIPT_EXTS), *rest[1:]]


@mcp.tool()
def gpu_profile_run(argv: list[str], cwd: str, timeout_sec: int = 600, interval_sec: float = 0.5) -> str:
    """Run an allowlisted benchmark/test while sampling the RTX Spark GPU, and return wall time, exit code,
    output tail and GPU utilization/memory statistics as hard evidence for a critique.

    argv is executed without a shell. Allowed forms (scripts/targets must be under SPARK_PROFILE_ROOTS):
      ["python", "<script>.py", ...args] | ["python", "-m", "pytest", ...] | ["pytest", ...]
      ["node", "<script>.js|.mjs|.cjs", ...args]
    """
    work = Path(cwd).expanduser().resolve()
    try:
        if not work.is_dir() or not _in_roots(work):
            raise ValueError(f"cwd '{cwd}' is not a directory under the allowed roots.")
        real_argv = _profile_argv(argv, work)
    except ValueError as e:
        return json.dumps({"rejected": True, "reason": str(e), "argv": argv,
                           "allowed_roots": [str(r) for r in PROFILE_ROOTS]}, ensure_ascii=False, indent=2)
    timeout_sec = max(1, min(int(timeout_sec), PROFILE_MAX_TIMEOUT_SEC))
    interval_sec = max(0.1, min(float(interval_sec), 10.0))
    samples: list[dict] = []
    stop = threading.Event()

    def sampler():
        while not stop.is_set():
            s = _smi_sample()
            if s:
                samples.append(s)
            stop.wait(interval_sec)

    t = threading.Thread(target=sampler, daemon=True)
    t.start()
    started = time.time()
    try:
        proc = subprocess.run(real_argv, cwd=work, capture_output=True, text=True, timeout=timeout_sec,
                              shell=False, encoding="utf-8", errors="replace")
        code, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as e:
        code, out = -1, f"TIMEOUT after {timeout_sec}s\n{e.stdout or ''}"
    elapsed = time.time() - started
    stop.set()
    t.join(timeout=15)

    def stat(key: str) -> dict | None:
        vals = [s[key] for s in samples if s.get(key) is not None]
        return {"avg": round(sum(vals) / len(vals), 1), "max": max(vals)} if vals else None

    return json.dumps({
        "argv": real_argv, "exit_code": code, "wall_time_sec": round(elapsed, 3), "samples": len(samples),
        "gpu_util_pct": stat("util"), "gpu_mem_used_mib": stat("mem_used_mib"),
        "temp_c": stat("temp_c"), "power_w": stat("power_w"), "output_tail": out[-3000:],
    }, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Use case 3: Local visual critic for UI vibe coding
# ---------------------------------------------------------------------------

@mcp.tool()
def visual_review(image_path: str, expectation: str, mode: str = "checklist") -> str:
    """Have the local multimodal model on the RTX Spark GPU judge a UI screenshot against the intended design.

    mode="checklist" (default): the model splits the acceptance criteria into atomic checks and reports what it
    observed for each; the verdict is computed deterministically (pass only if every criterion is met), and
    subjective design advice goes to suggestions without affecting the verdict.
    mode="holistic": the original single-judgement prompt.
    Returns JSON: {verdict: pass|fail, score: 0-10, issues: [...], suggestions: [...], criteria?: [...]}."""
    p = Path(image_path)
    if not p.is_file():
        return f"Image not found: {p}"
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode()
    image = {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
    if mode == "holistic":
        raw = _chat([
            {"role": "system", "content": "You are a meticulous UI/UX reviewer. Reply with ONLY a JSON object: "
             '{"verdict":"pass"|"fail","score":0-10,"issues":[string],"suggestions":[string]}'},
            {"role": "user", "content": [
                {"type": "text", "text": f"Intended design / acceptance criteria:\n{expectation}"}, image]},
        ], VISION_MODEL, max_tokens=800)
        return _extract_json(raw)
    raw = _chat([
        {"role": "system", "content": "You verify a UI screenshot against acceptance criteria. Split the criteria into "
         "atomic, objectively checkable items (title text, element count, layout direction, colors, theme). For each, "
         "first describe exactly what you see in the screenshot, then decide met true/false based ONLY on that "
         "observation. Do not fail a criterion for subjective taste. Reply with ONLY JSON: "
         '{"criteria":[{"criterion":string,"observed":string,"met":true|false}],"suggestions":[string]}'},
        {"role": "user", "content": [{"type": "text", "text": f"Acceptance criteria:\n{expectation}"}, image]},
    ], VISION_MODEL, max_tokens=1200)
    try:
        data = json.loads(re.search(r"\{.*\}", raw, flags=re.S).group(0))
        criteria = [c for c in data.get("criteria", []) if isinstance(c, dict) and "met" in c]
    except (AttributeError, json.JSONDecodeError):
        return _extract_json(raw)
    if not criteria:
        return _extract_json(raw)
    met = sum(1 for c in criteria if c.get("met") is True)
    return json.dumps({
        "verdict": "pass" if met == len(criteria) else "fail",
        "score": round(10 * met / len(criteria)),
        "issues": [f"{c.get('criterion')}: observed {c.get('observed')}" for c in criteria if c.get("met") is not True],
        "suggestions": data.get("suggestions", []),
        "criteria": criteria,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def local_critique(requirement: str, candidate: str) -> str:
    """Zero-cost first-pass critic on the local GPU (Cascade-style pre-check before spending cloud tokens).
    Returns JSON {accept: bool, problems: [...]} for a candidate code/answer against a requirement."""
    raw = _chat([
        {"role": "system", "content": "You are a strict code reviewer. Reply with ONLY JSON: "
         '{"accept":true|false,"problems":[string]}. Flag bugs, missing requirements, and unsafe code.'},
        {"role": "user", "content": f"Requirement:\n{requirement}\n\nCandidate:\n{_redact(candidate)[0][:20000]}"},
    ], CHAT_MODEL, max_tokens=800)
    return _extract_json(raw)


if __name__ == "__main__":
    mcp.run()

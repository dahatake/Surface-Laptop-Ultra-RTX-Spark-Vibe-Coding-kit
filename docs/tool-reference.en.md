# MCP Tool Reference (spark-vibe)

[Japanese](./tool-reference.md)

`spark-vibe` is a stdio MCP server implemented in [server.py](../server.py). It exposes eight tools. All return values are strings. Tools that return JSON return formatted JSON strings.

| Tool | Use case | Local model | Main purpose |
|---|---|---|---|
| [`scan_secrets`](#scan_secrets) | UC1 | None (regular expressions) | Detect secrets |
| [`repo_index`](#repo_index) | UC1 | Embedding | Create a local index |
| [`repo_search`](#repo_search) | UC1 | Embedding | Semantic search returning locations only |
| [`private_ask`](#private_ask) | UC1 | Embedding + chat | Ask about confidential code locally |
| [`gpu_status`](#gpu_status) | UC2 | None (`nvidia-smi`) | Current GPU status |
| [`gpu_profile_run`](#gpu_profile_run) | UC2 | None (`nvidia-smi`) | Measure GPU activity while running an allowed command |
| [`visual_review`](#visual_review) | UC3 | Vision | Review screenshots |
| [`local_critique`](#local_critique) | UC1, UC3 | Chat | Preliminary review of code or answers |

---

## scan_secrets

Scan a file or folder for strings that look like secrets.

| Argument | Type | Required | Description |
|---|---|---|---|
| `path` | string | ✅ | Path to a file or folder |

**Return value**: One line per detection in the form `<absolute file path>:<line number>  <type>`. If nothing is detected, `No secrets detected in N file(s).` The secret values themselves are not returned.

**Detected types**

| Type | Pattern summary |
|---|---|
| `aws_access_key` | `AKIA` + 16 uppercase English letters or digits |
| `github_token` | `ghp_` / `gho_` / `ghu_` / `ghs_` / `ghr_` + at least 36 characters |
| `azure_storage_key` | `AccountKey=` + at least 40 characters |
| `private_key` | `-----BEGIN ... PRIVATE KEY-----` |
| `connection_string_password` | `******` + at least 6 characters |
| `generic_secret` | A quoted value of at least 16 characters assigned to `api_key` / `secret` / `token` |

When a folder is specified, eligible files follow the same rules as [`repo_index`](#repo_index).

---

## repo_index

Create a local index of a repository.

| Argument | Type | Required | Description |
|---|---|---|---|
| `path` | string | ✅ | Repository folder |

**Processing**

1. Split eligible files into chunks of 60 lines (at most 1,500 characters per chunk).
2. Replace secrets in each chunk with `[REDACTED:<type>]`.
3. Generate vectors with the embedding model and normalize them (send 32 chunks at a time).
4. Save `vectors.npy`, `chunks.json`, and `.gitignore` (containing `*`) in `<path>/.spark-index/`. Overwrite any existing index.

**Eligible files**

- Extensions: `.py .js .ts .tsx .jsx .cs .java .go .rs .c .h .cpp .hpp .cu .cuh .kt .swift .rb .php .sql .ps1 .sh .md .yaml .yml .json .toml .bicep .tf .html .css`
- Size: at most 400,000 bytes
- Excluded folders: `.git node_modules .venv venv __pycache__ dist build bin obj .next .spark-index target`

**Return value**: `Indexed <chunk count> chunks from <file count> files in <seconds>s -> <index folder>`. If there are no eligible files, `No indexable files found.`

---

## repo_search

Semantically search a local index and return **only locations and scores**. Code contents are not returned.

| Argument | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | string | ✅ | — | Indexed repository |
| `query` | string | ✅ | — | Natural-language search query (English tends to give better accuracy) |
| `k` | integer | | 8 | Number of results to return |

**Return value**: One line per result in the form `<score>  <relative path>:<start line>-<end line>`. Scores are cosine similarity. If no index exists, `No index at ... Call repo_index first.`

---

## private_ask

Answer questions about confidential code using **only the local chat model**.

| Argument | Type | Required | Default | Description |
|---|---|---|---|---|
| `path` | string | ✅ | — | Indexed repository |
| `question` | string | ✅ | — | Question |
| `k` | integer | | 6 | Number of chunks to include in context |

**Processing**: Pass the top `k` chunks (already redacted during indexing) to the local LLM. The system prompt instructs it to cite `file:line` and not reproduce secrets or long passages of code. Redact the answer again before returning it.

**Return value**: A natural-language answer.

By default, each line in a chunk is labeled with its actual line number. `SPARK_NUMBERED_CONTEXT=0` selects the old method for A/B comparison. [Measurements](./measurements.en.md) showed improved citation accuracy, but this does not guarantee that line numbers or contents are correct.

---

## gpu_status

Fetch the current GPU status once.

| Arguments | None |
|---|---|

**Return value (example)**

```json
{"name": "NVIDIA RTX Spark N1X (6144-core Blackwell RTX GPU)", "util": 88.0, "mem_used_mib": 16114.0,
 "mem_total_mib": 64000.0, "temp_c": 64.71, "power_w": 48.5, "sm_clock_mhz": 2346.0}
```

If `nvidia-smi` is unavailable, `nvidia-smi not available.`

---

## gpu_profile_run

Execute an allowlisted command **without using a shell**, sampling the GPU at regular intervals while it runs.

| Argument | Type | Required | Default | Description |
|---|---|---|---|---|
| `argv` | string[] | ✅ | — | Array representing the command to run (allowed forms are listed below) |
| `cwd` | string | ✅ | — | Working folder. Must be under `SPARK_PROFILE_ROOTS` |
| `timeout_sec` | integer | | 600 | Timeout (clamped to 1–3600) |
| `interval_sec` | number | | 0.5 | Sampling interval (clamped to 0.1–10) |

**Allowed `argv` forms**

| Form | What actually runs |
|---|---|
| `["python", "<script>.py", ...]` | `SPARK_PROFILE_PYTHON <absolute script path> ...` |
| `["python", "-m", "pytest", ...]` | `SPARK_PROFILE_PYTHON -m pytest ...` |
| `["pytest", ...]` | `SPARK_PROFILE_PYTHON -m pytest ...` |
| `["node", "<script>.js\|.mjs\|.cjs", ...]` | `<node on PATH> <absolute script path> ...` |

- `argv[0]` accepts names only (case-insensitive). Paths are not allowed.
- Scripts, pytest targets, and `cwd` must be under `SPARK_PROFILE_ROOTS` after resolving `..` and symbolic links.
- Rejected pytest options: `-p`, `--pyargs`, `-c`, `--config-file`, `--rootdir`, `--confcutdir`, `--import-mode` (including concatenated forms such as `-pno:...` and forms such as `--rootdir=...`).

**Return value (when executed)**

| Key | Contents |
|---|---|
| `argv` | The argv actually executed |
| `exit_code` | Exit code (`-1` on timeout) |
| `wall_time_sec` | Execution time in seconds |
| `samples` | Number of GPU samples |
| `gpu_util_pct` / `gpu_mem_used_mib` / `temp_c` / `power_w` | `{"avg", "max"}`. `null` if there are no samples |
| `output_tail` | Last 3,000 characters of concatenated standard output and standard error |

**Return value (when rejected)**: Return `{"rejected": true, "reason": "...", "argv": [...], "allowed_roots": [...]}` without executing anything.

---

## visual_review

Review a screenshot against acceptance criteria using the local vision model.

| Argument | Type | Required | Description |
|---|---|---|---|
| `image_path` | string | ✅ | Image file path (PNG / JPEG, etc.) |
| `expectation` | string | ✅ | Intended design and acceptance criteria |
| `mode` | string | | `checklist` (default) or the old `holistic` method |

In `checklist` mode, the model generates `criteria: [{criterion, observed, met}]`, and the code assigns `pass` only when `met` is `true` for every item. The score is the proportion of satisfied items × 10 (rounded to the nearest integer). Subjective proposals not included in the criteria are separated into `suggestions`. Breaking down criteria and making observations still depend on the model. For a Japanese-language screen, write the criteria in Japanese too, or explicitly state that translated labels are acceptable.

`criteria` is added to the existing return value. If parsing fails, the model output is returned, so callers must check required keys and types and must not treat missing data as a pass.

**Return value**: `{"verdict": "pass" | "fail", "score": 0-10, "issues": [...], "suggestions": [...]}`. If JSON cannot be extracted from the model output, return the raw output as-is. If the image is missing, `Image not found: ...`.

---

## local_critique

Have the local LLM perform a preliminary review of candidate code or an answer against requirements (the judge before Cascade).

| Argument | Type | Required | Description |
|---|---|---|---|
| `requirement` | string | ✅ | Requirements |
| `candidate` | string | ✅ | Code or answer to review (first 20,000 characters after redaction) |

**Return value**: `{"accept": true | false, "problems": [...]}`. If JSON cannot be extracted, return the raw output.

Example (the same input as the E2E test):

```json
// requirement: "Return the average of a list of numbers; empty list must return 0."
// candidate:   "def avg(xs):\n    return sum(xs) / len(xs)"
{ "accept": false, "problems": ["Division by zero when xs is an empty list"] }
```

---

## Shared Behavior

- Local model calls are sent to the OpenAI-compatible API at `SPARK_LMSTUDIO_URL`. The timeout is 600 seconds (5 seconds for connection).
- Chat `temperature` is 0.2. `reasoning_effort` is set to `SPARK_REASONING_EFFORT` (default `none`), and any `<think>...</think>` content is removed.
- Maximum output tokens: 1,500 for `private_ask`, 1,200 for `visual_review` checklist mode, and 800 for holistic mode and `local_critique`.

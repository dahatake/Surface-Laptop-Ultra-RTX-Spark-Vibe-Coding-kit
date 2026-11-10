# Spark × Fusion Vibe Coding Kit

[日本語](./README.md) | **English**

> 📘 **Detailed documentation**: [User guide](./docs/README.en.md) ([Architecture](./docs/architecture.en.md) / [Setup](./docs/getting-started.en.md) / [UC1](./docs/use-cases/uc1-private-fusion.en.md) / [UC2](./docs/use-cases/uc2-gpu-grounded-critique.en.md) / [UC3](./docs/use-cases/uc3-visual-critic-loop.en.md) / [Tool reference](./docs/tool-reference.en.md) / [Security](./docs/security.en.md) / [Troubleshooting](./docs/troubleshooting.en.md) / [Measurements and media](./docs/measurements.en.md)).

A Vibe Coding environment combining Surface Laptop Ultra (NVIDIA RTX Spark N1X) with GitHub Copilot Fusion.
Copilot Fusion selects and combines models in the cloud (Single / Cascade / Critique). Your local RTX Spark serves as the **eyes, memory, measurement instruments, and reviewer** that Fusion calls.

## Capabilities this kit builds on

| Component | Capability | How this kit uses it |
|---|---|---|
| RTX Spark | Blackwell RTX GPU (up to 6,144 cores) and 64–128 GB unified memory | Keep a 9B-class LLM, VLM, and embedding model **resident simultaneously**, ready to call without loading delays |
| RTX Spark | Local inference (data stays on the device) | Understand confidential code and redact secrets locally |
| RTX Spark | GPU telemetry through `nvidia-smi` | Collect actual measurements to support performance improvements |
| Copilot Fusion | Standard / High / Max effort levels | Choose a quality/cost balance for each use case |
| Copilot Fusion | Cascade (draft → judge → escalate if needed) | Use a local judge to screen results before sending them to the cloud |
| Copilot Fusion | Critique (draft → another model reviews → revise) | Ground reviews in actual measurements and visual assessment |

## Use cases

### UC1. Private-by-Default Fusion (Vibe Coding without sending confidential code off the device)

- **What it does**: Index internal repositories, detect secrets, and understand code entirely on RTX Spark. Only file/line locations and summaries written by the local LLM are passed to Fusion.
- **Why engineers benefit**: Confidential code no longer has to mean giving up Vibe Coding. Cloud Fusion handles top-level orchestration while raw code stays on the device. Keeping multiple models resident in unified memory makes this division practical.
- **Tools**: `scan_secrets` / `repo_index` / `repo_search` / `private_ask` / `local_critique`
- **Prompt**: `/uc1-private-fusion`

### UC2. GPU-Grounded Critique (optimize from measurements, not guesses)

- **What it does**: Run benchmarks with `gpu_profile_run` and collect GPU utilization, memory, temperature, power, and elapsed time. The Fusion Max Critique loop uses these **actual measurements as evidence**.
- **Why engineers benefit**: This structurally guards against “the AI said it would be faster, but it got slower.” Run an autonomous hypothesis → measurement → accept/reject loop for CUDA and inference optimization on your local Blackwell GPU.
- **Tools**: `gpu_status` / `gpu_profile_run`
- **Prompt**: `/uc2-gpu-grounded-critique`

### UC3. Local Visual Critic Loop (local VLM UI reviews without per-call cloud charges or cloud iteration limits)

- **What it does**: Implement a UI, take a screenshot, have the local VLM (gemma-4) review it, and revise it in an automated loop. Combine this with Fusion Standard Cascade so most iterations run locally without cloud inference charges.
- **Why engineers benefit**: Checking whether a UI looks right becomes a bottleneck when done manually and expensive when repeated through a cloud VLM. A local reviewer lets you finish UI ideas with far less concern about iteration counts.
- **Tools**: `visual_review` / `local_critique` (plus Playwright MCP or Edge headless)
- **Prompt**: `/uc3-visual-critic-loop`

## Architecture

```text
VS Code / Copilot CLI ── Copilot Fusion (cloud: routing & orchestration)
        │ MCP (stdio)
        ▼
spark-vibe MCP server (server.py)
        │ OpenAI-compatible API (localhost:1234)
        ▼
LM Studio on RTX Spark GPU: qwen/qwen3.5-9b (chat) / google/gemma-4-e4b (vision) / nomic-embed (embedding)
        + nvidia-smi telemetry
```

## Setup

```powershell
pwsh -File .\scripts\setup.ps1
```

`setup.ps1` performs the following:

- Creates `.venv` and installs dependencies. On Windows on ARM64, it installs `cryptography` from a prebuilt wheel.
- Starts the LM Studio server and loads three models onto the GPU.
- Registers `spark-vibe` in `%APPDATA%\Code\User\mcp.json` and `~\.copilot\mcp-config.json`. Existing configuration is backed up as `*.bak-<timestamp>`.

After setup, select **Copilot Fusion** in the model picker, set the effort level, and run a use-case prompt.

| Environment variable | Default |
|---|---|
| `SPARK_CHAT_MODEL` | `qwen/qwen3.5-9b` |
| `SPARK_VISION_MODEL` | `google/gemma-4-e4b` |
| `SPARK_EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5` |
| `SPARK_REASONING_EFFORT` | `none` (prevents qwen3.5 from spending its entire token budget on reasoning and returning an empty response) |
| `SPARK_PROFILE_ROOTS` | This project's directory (allowed roots for scripts, tests, and `cwd` used by `gpu_profile_run`; separated by `os.pathsep`; add roots with `setup.ps1 -ProfileRoots C:\src\myproj`) |
| `SPARK_PROFILE_PYTHON` | The MCP server's venv Python (set this to use the interpreter belonging to the project being measured) |

## Validation

```powershell
.\.venv\Scripts\python.exe tests\e2e_test.py
```

This test starts the MCP server exactly as registered in Copilot CLI and actually calls all eight tools.
It checks that secrets appear in neither the index nor answers; GPU load can be measured; `gpu_profile_run` rejects 11 non-allowlisted patterns without executing them (including `cmd`, `powershell`, `python -c`, scripts or `cwd` outside allowed roots, and pytest `-p`); VLM reviews return JSON; and buggy code can be rejected.

## Important notes

- `gpu_profile_run` uses an **allowlist**. It does not use a shell (`shell=False`) and executes only these `argv` forms. Everything else returns `rejected` without execution.
  - `["python", "<script>.py", ...]` / `["python", "-m", "pytest", ...]` / `["pytest", ...]` / `["node", "<script>.js|.mjs|.cjs", ...]`
  - Launchers must be names only. The server chooses the executable, so clients cannot supply `cmd`, `powershell`, or arbitrary `.exe` paths.
  - Inline execution such as `python -c`, `-m` other than `-m pytest`, and `node -e` is rejected, as are pytest options that load external code (`-p`, `--pyargs`, `-c`, `--rootdir`, etc.).
  - Scripts, pytest targets, and `cwd` must be within `SPARK_PROFILE_ROOTS`. Paths are checked after resolving `..` and symbolic links. The maximum timeout is 3,600 seconds.
  - Scripts within approved roots do execute. Add only trusted repositories and keep client-side tool approval enabled (defense in depth).
- `visual_review` and `local_critique` are **first-pass judgments** by small local models. Fusion Critique and humans make the final decision.
- `scan_secrets` is a lightweight regular-expression detector. Use GitHub Secret Scanning alongside it in production.

## English documentation and media

The user guide lives in [`docs/`](./docs/README.en.md); this repository has no separate `users-guide` directory. English documents are separate `*.en.md` files. English media counterparts are in [`docs/media/en/`](./docs/media/en/README.en.md). Japanese originals and benchmark data are retained. The media notes explain which assets are translated recording edits and which are newly rendered English UI fixtures; neither is a new benchmark run.

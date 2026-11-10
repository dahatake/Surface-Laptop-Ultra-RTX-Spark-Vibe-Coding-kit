[Japanese](./architecture.md)

# Overview and Architecture

## Design Philosophy

In Vibe Coding, you tell AI what you want to build and rapidly repeat generation and revision. Three obstacles commonly arise.

| Obstacle | Description | How This Kit Addresses It |
|---|---|---|
| Confidentiality | Confidential code and secrets cannot be sent to the cloud | Index, search, understand, and redact on RTX Spark; pass only locations and summaries to the cloud (UC1) |
| Evidence | AI's performance improvement proposals may not actually make things faster | Measure the running GPU with `nvidia-smi` and use those numbers as evidence for Critique decisions (UC2) |
| Iteration cost | Repeated visual checks and initial code reviews increase both manual work and cloud costs | Use a local VLM / LLM as a free, unlimited first-pass reviewer (UC3) |

The guiding division of responsibilities is: "**Cloud Fusion handles decisions and integration; local Spark handles raw data and repeated processing.**"

## Structure

```
┌──────────────────────────────────────────────────────────────┐
│ VS Code (Copilot Chat) / GitHub Copilot CLI                  │
│   Copilot Fusion: model selection and orchestration (cloud) │
│     Single / Cascade / Critique   effort: Standard/High/Max  │
└───────────────┬──────────────────────────────────────────────┘
                │ MCP (stdio): only tool-call arguments and return values flow through
┌───────────────▼──────────────────────────────────────────────┐
│ spark-vibe MCP server (server.py, .venv)                     │
│  UC1: scan_secrets / repo_index / repo_search / private_ask  │
│  UC2: gpu_status / gpu_profile_run (allowlist, shell=False)  │
│  UC3: visual_review / local_critique                         │
└───────┬───────────────────────────────┬──────────────────────┘
        │ OpenAI-compatible API        │ nvidia-smi
        │ (localhost)                  │
┌───────▼──────────────────────┐ ┌──────▼─────────────────────┐
│ LM Studio on RTX Spark GPU   │ │ GPU telemetry              │
│  qwen/qwen3.5-9b   (chat)    │ │  Utilization, memory,       │
│  google/gemma-4-e4b (vision) │ │  temperature, power,        │
│  nomic-embed-text  (embed)   │ │  and SM clock               │
│                              │ └────────────────────────────┘
└──────────────────────────────┘
```

The three models total only about 13GB. They can **remain loaded simultaneously** in 64GB of unified memory, eliminating waits for model reloads. This is why repeatedly calling local tools does not slow the pace of iteration.

## RTX Spark Features and Their Use in the Kit

| RTX Spark Feature | Use in the Kit | Related Use Cases |
|---|---|---|
| Blackwell RTX GPU (6144 cores) | Inference for a 9B-class LLM, VLM, and embedding model | UC1, UC3 |
| 64–128GB unified memory | Keep multiple models loaded simultaneously; large contexts (65,536 tokens each) | UC1, UC3 |
| Local inference that keeps data on the device | Understand confidential code and redact secrets | UC1 |
| `nvidia-smi` telemetry | Evidence for optimization based on actual measurements | UC2 |

## Copilot Fusion Features and Their Use in the Kit

| Fusion Feature | Meaning | Use in the Kit |
|---|---|---|
| effort: Standard | Fast, low-cost execution centered on lightweight models | Numerous UI iterations in UC3 |
| effort: High | Balanced, with an emphasis on quality | Confidential code changes in UC1 |
| effort: Max | Actively uses top-tier models and Critique | Performance optimization in UC2 |
| Cascade | Draft → evaluate → escalate to a higher-tier model only when needed | Place `local_critique` / `visual_review` first as a "free evaluator" |
| Critique | Draft → review by another model → revise | Use actual `gpu_profile_run` measurements and `visual_review` findings as review evidence |

> Select Fusion effort and patterns in the client's model picker. Each prompt file lists a recommended effort, but does not enforce it.

## Data Flow (What Goes to the Cloud)

| Data | Stays on the Device | Passed to the Cloud (Fusion) |
|---|---|---|
| Raw repository code | ✅ `repo_index` / `private_ask` process it on the device | Only the minimum portion Fusion reads directly for editing |
| Embedding vectors and index | ✅ `<repo>/.spark-index/` (excluded by `.gitignore`) | ❌ |
| Search results | Body text stays on the device | Only `file:start-end` and score |
| Local LLM answers | — | Redacted natural-language summaries |
| Secrets | ✅ Replaced with `[REDACTED:<type>]` before indexing and when answering | ❌ (`scan_secrets` results contain only "file:line type") |
| GPU measurements | — | Statistics (avg / max) and the last 3000 characters of output |
| UI screenshots | ✅ Input to the VLM stays on the device | Only the JSON evaluation result |

See the [Security Model](./security.en.md) for details.

## Repository Layout

```
spark-fusion-vibe/
├── server.py                     # spark-vibe MCP server (8 tools)
├── requirements.txt              # mcp, httpx, numpy, cryptography
├── scripts/setup.ps1             # Create venv, load models, register MCP
├── .github/prompts/              # Copilot prompt files (UC1–UC3)
├── demo/
│   ├── private_repo/billing.py   # UC1 demo (contains a dummy AWS key)
│   ├── bench_llm.py              # UC2 demo benchmark (tokens/sec)
│   └── ui/index.html             # UC3 demo UI
├── tests/e2e_test.py             # E2E tests (actually call every tool)
└── docs/                         # This documentation
```

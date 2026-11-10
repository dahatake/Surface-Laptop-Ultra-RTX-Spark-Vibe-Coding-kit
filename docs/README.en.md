[Japanese](./README.md)

# Spark × Fusion Vibe Coding Kit Documentation

This kit combines the local GPU in Surface Laptop Ultra (NVIDIA RTX Spark N1X) with GitHub Copilot Fusion's cloud-side orchestration for Vibe Coding. This folder contains detailed use-case explanations and instructions.

> **[English media and provenance](./media/en/README.en.md):** English media are translated edits of the original recordings, with UI fixtures rerendered in English. They are not new measurements.

## Reading Order

| # | Document | Contents | Intended Readers |
|---|---|---|---|
| 1 | [Overview and Architecture](./architecture.en.md) | Overall structure, responsibilities, data flow, and choosing Fusion effort and patterns | Everyone |
| 2 | [Getting Started (Setup)](./getting-started.en.md) | Prerequisites, installation, verification, and the first run | First-time users |
| 3 | [UC1 Private-by-Default Fusion](./use-cases/uc1-private-fusion.en.md) | Vibe Coding without sending confidential code off the device | People working with confidential code |
| 4 | [UC2 GPU-Grounded Critique](./use-cases/uc2-gpu-grounded-critique.en.md) | Optimize performance based on actual GPU measurements | People working on inference, CUDA, or performance tuning |
| 5 | [UC3 Local Visual Critic Loop](./use-cases/uc3-visual-critic-loop.en.md) | Iterate on a UI with reviews by a local VLM | Frontend developers |
| 6 | [MCP Tool Reference](./tool-reference.en.md) | Arguments, return values, and constraints for the eight tools | People writing their own prompts or agents |
| 7 | [Security Model](./security.en.md) | What leaves the device, the `gpu_profile_run` allowlist, and remaining risks | People evaluating adoption |
| 8 | [Troubleshooting](./troubleshooting.en.md) | Common symptoms and remedies | Everyone |
| 9 | [Measurement Reports, Videos, and Screenshots](./measurements.en.md) | N=5 repeated measurements, A/B comparisons, raw logs, and reproduction steps | People verifying the results |

MP4s, GIFs, intermediate and final screens, and GPU time series have been added to each use case's measurement results. The measurements cover the local MCP tool path. They do not measure Fusion's cloud-side quality, pricing, or response time itself.

## The Kit in Three Lines

1. **Copilot Fusion in the cloud** decides which models to combine and how (Single / Cascade / Critique), then carries out the work.
2. **Your local RTX Spark** is called through the `spark-vibe` MCP server as "memory (local index)," "measurement equipment (GPU telemetry)," and "reviewer (local LLM / VLM)."
3. Raw confidential code, collection of actual measurements, and repeated reviews are handled on the device. Only the minimum information needed for decisions is passed to the cloud.

## Use Cases at a Glance

| | UC1 Private-by-Default | UC2 GPU-Grounded Critique | UC3 Visual Critic Loop |
|---|---|---|---|
| Problem addressed | Confidential code cannot be shared with cloud AI | AI's "this should be faster" is unreliable | Manual visual checks become a bottleneck |
| Recommended Fusion effort | High | Max (Critique) | Standard (Cascade) |
| Main spark-vibe tools | `scan_secrets` `repo_index` `repo_search` `private_ask` `local_critique` | `gpu_status` `gpu_profile_run` | `visual_review` `local_critique` |
| Local models used | Embeddings + chat LLM | (No model required; `nvidia-smi`) | VLM + chat LLM |
| Prompt | `/uc1-private-fusion` | `/uc2-gpu-grounded-critique` | `/uc3-visual-critic-loop` |
| Deliverables | Modified code + table of what is sent externally | Before/after comparison table + adopted changes | Completed UI + score progression table |

## Verified Environment

| Item | Value |
|---|---|
| Device | Surface Laptop Ultra / NVIDIA RTX Spark N1X (6144-core Blackwell RTX GPU), 64,000 MiB unified memory |
| OS | Windows on ARM64 |
| Python | 3.12.10 (`.venv`) |
| Local inference | LM Studio (OpenAI-compatible API, `http://localhost:1234/v1`) |
| Models | `qwen/qwen3.5-9b` (chat), `google/gemma-4-e4b` (vision), `text-embedding-nomic-embed-text-v1.5` (embeddings) |
| Clients | VS Code (GitHub Copilot Chat), GitHub Copilot CLI |
| Verification | All 11 checks in `tests/e2e_test.py` passed |

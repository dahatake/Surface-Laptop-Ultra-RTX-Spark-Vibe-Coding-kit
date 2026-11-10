[Japanese](./getting-started.md)

# Getting Started (Setup)

The steps on this page take you from setup through your first use-case run. Allow about 15–30 minutes, excluding model download time.

## 1. Prerequisites

| Requirement | Verification Command | Notes |
|---|---|---|
| PC with NVIDIA RTX Spark | `nvidia-smi --query-gpu=name,memory.total --format=csv` | Output such as `NVIDIA RTX Spark N1X ...` means it is recognized |
| Python 3.12 or later | `python --version` | Windows on ARM64 version |
| PowerShell 7 | `pwsh --version` | Required because `setup.ps1` uses `ConvertFrom-Json -AsHashtable` |
| LM Studio and its CLI (`lms`) | `lms version` | Launching LM Studio once adds `lms` to PATH |
| Three local models | `lms ls` | See the table below |
| VS Code + GitHub Copilot, or Copilot CLI | — | A plan with access to Copilot Fusion is required |
| Microsoft Edge | — | Used for UC3 screenshots (headless) |
| Node.js (optional) | `node --version` | Only needed to measure `.js` benchmarks with `gpu_profile_run` |

### Obtaining the Models

```powershell
lms get qwen/qwen3.5-9b
lms get google/gemma-4-e4b
lms get text-embedding-nomic-embed-text-v1.5
```

| Purpose | Default Model | Size | Environment Variable for Replacement |
|---|---|---|---|
| Chat (`private_ask`, `local_critique`) | `qwen/qwen3.5-9b` | About 6.6GB | `SPARK_CHAT_MODEL` |
| Vision (`visual_review`) | `google/gemma-4-e4b` | About 6.3GB | `SPARK_VISION_MODEL` |
| Embeddings (`repo_index`, `repo_search`, `private_ask`) | `text-embedding-nomic-embed-text-v1.5` | About 84MB | `SPARK_EMBED_MODEL` |

## 2. Setup

```powershell
cd C:\Work\Temp\spark-fusion-vibe
pwsh -File .\scripts\setup.ps1
```

`setup.ps1` performs these three steps:

1. **Python environment**: Creates `.venv` and installs `requirements.txt`. On ARM64, it installs `cryptography` from a prebuilt wheel.
2. **Local models**: Starts the API server with `lms server start` and loads the three models onto the GPU with `--gpu max`.
3. **MCP registration**: Registers `spark-vibe` in the following two locations. Existing files are backed up to `*.bak-<timestamp>` before the settings are merged.
   - VS Code: `%APPDATA%\Code\User\mcp.json`
   - Copilot CLI: `%USERPROFILE%\.copilot\mcp-config.json`

### Parameters

| Parameter | Default | Purpose |
|---|---|---|
| `-ChatModel` | `qwen/qwen3.5-9b` | Replace the chat model |
| `-VisionModel` | `google/gemma-4-e4b` | Replace the vision model |
| `-EmbedModel` | `text-embedding-nomic-embed-text-v1.5` | Replace the embedding model |
| `-ProfileRoots` | None (this project only) | Add folders that `gpu_profile_run` is allowed to measure |
| `-SkipModelLoad` | Off | Skip loading models and update registration only |

Example: Allow UC2 measurements of your own project.

```powershell
pwsh -File .\scripts\setup.ps1 -ProfileRoots C:\src\my-inference-app -SkipModelLoad
```

### Environment Variables (Read by the MCP Server)

| Variable | Default | Description |
|---|---|---|
| `SPARK_LMSTUDIO_URL` | `http://localhost:1234/v1` | LM Studio's OpenAI-compatible API |
| `SPARK_CHAT_MODEL` | `qwen/qwen3.5-9b` | Chat model |
| `SPARK_VISION_MODEL` | `google/gemma-4-e4b` | Vision model |
| `SPARK_EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5` | Embedding model |
| `SPARK_REASONING_EFFORT` | `none` | Prevents qwen3.5 from using its entire token budget on reasoning and returning an empty response |
| `SPARK_NUMBERED_CONTEXT` | `1` | Passes `private_ask` context with actual line numbers. `0` is the old method, retained for comparison experiments |
| `SPARK_PROFILE_ROOTS` | Folder containing `server.py` | Roots that `gpu_profile_run` can handle (separated by `;`) |
| `SPARK_PROFILE_PYTHON` | Python in the MCP server's venv | Interpreter for the project being measured |

`setup.ps1` registers the three model names and `SPARK_PROFILE_ROOTS`. To change anything else, add it to `spark-vibe.env` in `mcp.json` / `mcp-config.json`, then restart the MCP server.

## 3. Verification

```powershell
.\.venv\Scripts\python.exe tests\e2e_test.py
```

This test starts the MCP server using the settings registered with Copilot CLI and calls all eight tools. A final message of `RESULT: ALL PASSED` indicates success. It takes a few minutes, depending on local LLM response times.

| Check | What It Verifies |
|---|---|
| list_tools | All eight tools are exposed |
| UC1 scan_secrets | Can detect the dummy AWS key |
| UC1 repo_index | Can create an index |
| UC1 index stores redacted text only | No secrets remain in the index |
| UC1 repo_search | Returns locations only, not code bodies |
| UC1 private_ask | Answers correctly without including secrets |
| UC2 gpu_status | Can retrieve RTX Spark status |
| UC2 gpu_profile_run | Can measure GPU load during a benchmark (example measurement: maximum utilization 90%, maximum memory 16,120 MiB) |
| UC2 rejects non-allowlisted | Rejects 11 non-allowlisted patterns without executing them |
| UC3 visual_review | Returns evaluation results as JSON |
| UC3 local_critique | Rejects code containing a division-by-zero bug |

## 4. Using the Clients

### VS Code

1. Restart VS Code, or open **MCP: List Servers** in the Command Palette and confirm that `spark-vibe` is **Running**.
2. Set Copilot Chat to **Agent** mode.
3. Select **Copilot Fusion** in the model picker and set effort (Standard / High / Max).
4. Open this folder as your workspace to use prompts such as `/uc1-private-fusion` in chat. Input fields appear for paths and goals.
5. If a tool execution confirmation dialog appears, review its contents and approve it.

> When working in another repository, copy the three files in `.github/prompts/` to that repository, or register them as VS Code user prompts. The MCP server is registered in user settings, so it is available from any workspace.

### Copilot CLI

```powershell
cd C:\Work\Temp\spark-fusion-vibe
copilot
```

After startup, use `/mcp` to confirm that `spark-vibe` is loaded. Select Copilot Fusion with `/model`, then make your request using the steps in each prompt file as a guide.

## 5. Your First Run (Try the Demos)

| Use Case | Example Input |
|---|---|
| UC1 | `repoPath`: `C:\Work\Temp\spark-fusion-vibe\demo\private_repo`, `goal`: "I want to add tests for the discount cap" |
| UC2 | `target`: "I want to increase tokens/sec in `bench_llm.py`", `argv`: `["python", "bench_llm.py"]`, `cwd`: `C:\Work\Temp\spark-fusion-vibe\demo` |
| UC3 | `design`: "A dark theme with three metric cards and a blue button", `htmlPath`: `C:\Work\Temp\spark-fusion-vibe\demo\ui\index.html` |

See [UC1](./use-cases/uc1-private-fusion.en.md), [UC2](./use-cases/uc2-gpu-grounded-critique.en.md), and [UC3](./use-cases/uc3-visual-critic-loop.en.md) for each use case's detailed workflow.

## 6. Uninstalling

1. Remove `servers.spark-vibe` from `%APPDATA%\Code\User\mcp.json` and `mcpServers.spark-vibe` from `%USERPROFILE%\.copilot\mcp-config.json` (or restore from `*.bak-*`).
2. Delete `.spark-index\` from any repositories you indexed.
3. If needed, unload models from the GPU with `lms unload --all`, then delete the project folder.

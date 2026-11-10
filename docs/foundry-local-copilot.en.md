[Japanese](./foundry-local-copilot.md)

# Local Inference for GitHub Copilot with Foundry Local

This guide switches the model used by VS Code Copilot Chat and Copilot CLI to Foundry Local, which runs on this PC's RTX GPU. The scripts are in [scripts/foundry-local/](../scripts/foundry-local/).

## Architecture

```text
VS Code Copilot Chat / Copilot CLI
  -> http://127.0.0.1:5274/v1  Serializing proxy (foundry_serial_proxy.py)
  -> http://127.0.0.1:5273/v1  Foundry Local CLI 0.13.0
  -> qwen2.5-7b-instruct-trtrtx-gpu:2 (NvTensorRTRTXExecutionProvider, RTX GPU)
```

No Azure resources are created, so this endpoint has no cloud inference charges (0 JPY against a budget of 10,000 JPY/month). Electricity and your existing Copilot plan are separate costs.

## Prerequisites

| Item | Details |
|---|---|
| Foundry Local | CLI 0.13.0 (`foundry.exe` must be on PATH) |
| NVIDIA runtime | ARM64 redistributable DLLs such as CUDA 13.4 and cuDNN 9.27. They are not included in the repository. The default location is `%LOCALAPPDATA%\Programs\FoundryLocal\runtime`. To use another location, pass `-RuntimeRoot` or set the `FOUNDRY_LOCAL_RUNTIME` environment variable. |
| Python | `pythonw.exe` for the proxy (standard library only) |
| PowerShell | 7 or later (`Test-FoundryLocal.ps1` uses `Start-ThreadJob`) |

## Usage

Run the following commands from the repository root.

1. Start the services. Nothing starts automatically at sign-in, so run this after every Windows restart.

   ```powershell
   pwsh -File scripts\foundry-local\Start-FoundryLocal.ps1
   ```

2. In VS Code, open a new chat and select **Foundry Local → Qwen2.5 7B - Foundry Local** in the model picker. It may appear under **Other Models**. If it does not appear, save your work and reload VS Code. Also remove MCP server tools in **Configure Tools** (see item 1 under [Limitations](#limitations)).
3. For Copilot CLI, use the launcher. It disables MCP automatically before starting the CLI.

   ```powershell
   pwsh -File scripts\foundry-local\Start-CopilotLocal.ps1
   pwsh -File scripts\foundry-local\Start-CopilotLocal.ps1 -Prompt "your question"
   ```

4. Verify the setup. The script decides pass or fail automatically and saves the results to [bench/results/foundry-local/verification.json](../bench/results/foundry-local/verification.json).

   ```powershell
   pwsh -File scripts\foundry-local\Test-FoundryLocal.ps1
   ```

## Stopping

```powershell
foundry model unload qwen2.5-7b-instruct-trtrtx-gpu:2
foundry server stop
```

To stop the proxy, end the `pythonw.exe` process running `foundry_serial_proxy.py` in Task Manager.

## Findings

These results are from 2026-11-11 with Foundry Local CLI 0.13.0 and ORT GenAI 0.18.0.

1. **GPU inference fails on concurrent requests.** When 4 requests were sent in parallel, all of them failed with `CUDA error in CopyCompletedLocked` or `GenerateNext`. Afterward, the daemon could stay broken until it was restarted, and requests with about 1.9K–8.2K input tokens kept failing. We also saw `foundrylocald.exe` crash with an access violation (`0xc0000005`) in `onnxruntime-genai.dll`. The TRT-RTX, CUDA, and generic-gpu variants all showed the same problem; the CPU variant did not. Because Copilot sends requests in parallel, the serializing proxy on port 5274 handles them one at a time. When one of these errors is returned, the proxy retries once and records the retry in its log. With the proxy, all 4 parallel requests succeed.
2. **Model selection.** `qwen2.5-1.5b` passed the API tests. However, as a Copilot CLI agent it kept calling the `view` tool and never finished. Under the same conditions, `qwen2.5-7b` finished and answered 2 of 3 tasks correctly ([copilot-verification.json](../bench/results/foundry-local/copilot-verification.json)). It generates about 55 tokens/s and processes a 23K-token input in about 12 seconds.
3. **Context limit.** The model's limit is 32,768 tokens (`genai_config.json`). The configuration uses 28,672 input tokens + 4,096 output tokens. The output limit is kept at 4,096 to shorten the wait when the model starts repeating the same text.

## Limitations

1. When tool definitions from MCP servers (Azure, Playwright, Microsoft Docs, and others) are included, the request fails with `static system messages and tool definitions exceed this model's context budget` and the model does not respond. It works with Copilot's built-in tools only.
2. The 7B model is not as good as cloud models. We have seen wrong answers, replies in the wrong language (Chinese or Spanish for Japanese instructions), and the same command text repeated over and over.
3. Image input is not supported. Inline completions (ghost text) are not covered by this setup.
4. Local inference does not make VS Code or Copilot fully offline. Sign-in, telemetry, extensions, and other features still use the network.
5. Foundry Local CLI is in preview. After you update it, run `Test-FoundryLocal.ps1` again.

## Files

| File | Purpose |
|---|---|
| [Start-FoundryLocal.ps1](../scripts/foundry-local/Start-FoundryLocal.ps1) | Adds the NVIDIA runtime to the process PATH, then starts the server, model, and proxy |
| [Start-CopilotLocal.ps1](../scripts/foundry-local/Start-CopilotLocal.ps1) | Starts Copilot CLI with the local model and MCP disabled |
| [Test-FoundryLocal.ps1](../scripts/foundry-local/Test-FoundryLocal.ps1) | Checks plain responses, SSE, tool-call round trips, parallel requests, and the VS Code configuration |
| [foundry_serial_proxy.py](../scripts/foundry-local/foundry_serial_proxy.py) | Serializing proxy (listens on 127.0.0.1 only). The default log location is `%LOCALAPPDATA%\Programs\FoundryLocal\proxy.log` (override with `FOUNDRY_PROXY_LOG`) |
| [copilot-providers.json](../scripts/foundry-local/copilot-providers.json) | Provider definition for Copilot CLI (`COPILOT_PROVIDERS_CONFIG`) |
| [verification.json](../bench/results/foundry-local/verification.json) | API verification results |
| [copilot-verification.json](../bench/results/foundry-local/copilot-verification.json) | Copilot CLI agent verification results |

## Configuration Locations and Rollback

| Target | Location |
|---|---|
| VS Code model definition | The "Foundry Local" provider in `%APPDATA%\Code\User\chatLanguageModels.json`. The original settings are saved as `chatLanguageModels.json.bak-foundry-*` in the same folder. |
| Foundry Local settings | `%USERPROFILE%\.foundry\config.json` (`server_port` 5273) |
| Model cache | `%USERPROFILE%\.foundry\cache\models`. To remove the unused 1.5B model, run `foundry cache remove qwen2.5-1.5b-instruct-trtrtx-gpu:2 --force`. |

## References (Primary Sources)

- [Foundry Local CLI 0.13.0 release](https://github.com/microsoft/Foundry-Local/releases/tag/cli-preview-0.13.0)
- [Foundry Local CLI reference](https://learn.microsoft.com/azure/foundry-local/reference/reference-cli)
- [VS Code: Language models](https://code.visualstudio.com/docs/agent-customization/language-models)
- [NVIDIA CUDA 13.4.1 redistrib manifest](https://developer.download.nvidia.com/compute/cuda/redist/redistrib_13.4.1.json)
- [NVIDIA cuDNN 9.27.0 redistrib manifest](https://developer.download.nvidia.com/compute/cudnn/redist/redistrib_9.27.0.json)

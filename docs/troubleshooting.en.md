[Japanese](./troubleshooting.md)

# Troubleshooting

## First Checks

```powershell
nvidia-smi                                   # Is the GPU visible?
lms server status                            # Is LM Studio's API server running?
lms ps                                       # Are all three models loaded?
.\.venv\Scripts\python.exe tests\e2e_test.py # Which tool fails?
```

The E2E test's `[FAIL]` lines identify which tools are having problems.

## Symptoms and Remedies

### Setup

| Symptom | Cause | Remedy |
|---|---|---|
| `LM Studio CLI (lms) が見つかりません` ("LM Studio CLI (lms) not found") | `lms` is not on PATH | Launch LM Studio once, or add `%USERPROFILE%\.lmstudio\bin` to PATH and reopen the terminal |
| `pip install failed` with a `cryptography` build failure | No prebuilt ARM64 wheel was found | Update `pip` (`.venv\Scripts\python.exe -m pip install -U pip`) and run `setup.ps1` again |
| `ConvertFrom-Json : A parameter cannot be found ... AsHashtable` | Running in Windows PowerShell 5.1 | Run with `pwsh` (PowerShell 7) |
| `lms load` fails | Model has not been downloaded, or insufficient memory | Download with `lms get <model>`. Check unnecessary models with `lms ps`, then unload them with `lms unload <id>` |

### MCP Server

| Symptom | Cause | Remedy |
|---|---|---|
| `spark-vibe` tools do not appear in VS Code | The MCP server is not running | In the Command Palette's **MCP: List Servers**, **Start** `spark-vibe`. Check errors with **Show Output** |
| `spark-vibe` is not visible in Copilot CLI | CLI was started before the configuration file was loaded | Restart Copilot CLI and check with `/mcp` |
| Environment variable changes have no effect | The MCP server is still running with old settings | Restart the MCP server (**Restart** in VS Code; restart the CLI) |
| Prompts such as `/uc1-...` do not appear | The workspace has no `.github/prompts/` | Open this folder, or copy the prompt files to the repository you are working in |

### Local Models (UC1 / UC3)

| Symptom | Cause | Remedy |
|---|---|---|
| `ConnectError` / `Connection refused` | LM Studio's API server is stopped | `lms server start` |
| `404` or `model not found` | The specified model is not loaded, or the ID differs | Match `SPARK_*_MODEL` to the IDENTIFIER in `lms ps`. `setup.ps1` uses the model name for `--identifier` |
| `private_ask` / `local_critique` returns an empty string | A reasoning model used its entire token budget on reasoning | Check that `SPARK_REASONING_EFFORT=none` (the default) |
| `visual_review` returns prose instead of JSON | The small VLM did not follow formatting instructions | Call it again. If it persists, change `SPARK_VISION_MODEL` to a larger model |
| `visual_review` makes clearly incorrect observations | Misrecognition by the small VLM, or ambiguous criteria | Use `mode="checklist"` and specify objective criteria. If reviewing Japanese labels against English criteria, allow translation ([UC3 measurements](./use-cases/uc3-visual-critic-loop.en.md)) |
| `local_critique` returns invalid JSON | The model did not follow the format | Do not treat unparseable output as a pass; retry or send it for human review. This also occurred once in 30 runs in these measurements |
| Responses are slow or time out | Other models or processes are using the GPU | Check utilization with `gpu_status`. Unload unnecessary models with `lms unload` |

### Indexing and Search (UC1)

| Symptom | Cause | Remedy |
|---|---|---|
| `No index at ... Call repo_index first.` | No index exists yet | Run `repo_index` first |
| `No indexable files found.` | No files have supported extensions, or all exceed 400KB | Check the [file eligibility conditions](./tool-reference.en.md#repo_index) |
| Search results are off target | The index was not rebuilt after code changes | Run `repo_index` again (there are no incremental updates) |
| `private_ask` line numbers are off | Old settings, or a local LLM error | Check `SPARK_NUMBERED_CONTEXT=1` (the default) and restart the server. Even after the improvement, check the original text before editing |

### GPU Measurement (UC2)

| `reason` (when `rejected: true`) | Meaning | Remedy |
|---|---|---|
| `argv[0] must be one of ['node', 'pytest', 'python'] ...` | An unauthorized launcher or a path was specified | Use only the names `python` / `pytest` / `node` |
| `python accepts only '<script>.py [args]' or '-m pytest [args]'.` | Used `python -c` or `-m <something other than pytest>` | Put the benchmark in a script file |
| `'<x>' must be a .py file.` | Attempted to run a non-`.py` file with `python` | Check the extension |
| `'<x>' is not an existing file under the allowed roots.` | The script does not exist, or is outside the allowed folders | Check the path. If outside, add it with `setup.ps1 -ProfileRoots <folder>` |
| `cwd '<x>' is not a directory under the allowed roots.` | `cwd` is outside the allowed folders | Same as above |
| `pytest option '<x>' is not allowed.` | Used a pytest option that loads external code | Remove the option. Put settings in the repository's `pytest.ini` or a similar file |
| `pytest target '<x>' is outside the allowed roots.` | The test path is outside the allowed folders | Same as above |
| `node is not installed.` | `node` is not on PATH | Install Node.js and restart the MCP server |

| Symptom | Cause | Remedy |
|---|---|---|
| `exit_code` is `-1` with `TIMEOUT after ...` | Execution exceeded `timeout_sec` | Increase `timeout_sec` (maximum 3600), or shorten the benchmark |
| `ModuleNotFoundError` appears in `output_tail` | The server's venv lacks required packages | Set `SPARK_PROFILE_PYTHON` to Python in the project's venv |
| `samples` is 0 and statistics are `null` | `nvidia-smi` is unavailable, or execution is too short | Check `nvidia-smi`. Reduce `interval_sec`, or make the benchmark longer |
| Before/after numbers vary widely | Other GPU load, or temperature-induced clock changes | Measure two or three times under the same conditions. Use `gpu_status` to match the initial state |

## If the Problem Persists

1. Save the full output of `tests\e2e_test.py`.
2. Check the log in VS Code under **MCP: List Servers** → `spark-vibe` → **Show Output**.
3. Start `server.py` directly to check for import errors.

```powershell
.\.venv\Scripts\python.exe -c "import server; print('ok')"
```

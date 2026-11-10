# Security Model

[Japanese](./security.md)

This kit has two goals: keeping confidential data on your device, and preventing the tools given to AI from putting your device at risk. This page explains what is protected and what is not.

## Trust Boundaries

```
 [Cloud] Copilot Fusion ──(tool call arguments and return values)──▶ [Device] spark-vibe ──▶ LM Studio (localhost)
                                                                                     └──▶ nvidia-smi
                                                                                     └──▶ Allowed scripts (gpu_profile_run)
```

- What reaches the cloud is **tool return values** and the contents of files that Fusion reads directly using client capabilities.
- Communication between spark-vibe and LM Studio stays on `localhost`. Changing `SPARK_LMSTUDIO_URL` to an external host invalidates this assumption.

## What Leaves the Device

| Tool | Returned to the cloud | Not returned |
|---|---|---|
| `scan_secrets` | File paths, line numbers, secret types | Secret values |
| `repo_index` | Chunk count, file count, elapsed time, index location | Code, vectors |
| `repo_search` | Relative paths, line ranges, scores | Code contents |
| `private_ask` | Local LLM summary (redacted) | Contents of retrieved chunks |
| `gpu_status` | GPU status | — |
| `gpu_profile_run` | Executed argv, exit code, statistics, last 3,000 characters of output | — |
| `visual_review` | Verdict JSON | Images |
| `local_critique` | Verdict JSON | — |

### Points Requiring Caution

- **Answers from `private_ask`** include descriptions of code summarized by the local LLM. The system prompt prohibits reproducing long passages of code, but short code snippets may still appear.
- **The `output_tail` from `gpu_profile_run`** contains the measured program's output as-is. Make sure your benchmark does not print secrets.
- **When Fusion reads files directly**, their contents are sent to the cloud. The UC1 prompt instructs it to read only the minimum necessary range, but this is not technically enforced.

## Secret Redaction

| When | Action |
|---|---|
| Before `repo_index` creates an index | Redact each chunk and save only the redacted text in `chunks.json` |
| Before returning a `private_ask` answer | Redact the answer again |
| Before passing a candidate to `local_critique` | Redact the candidate |

See the [tool reference](./tool-reference.en.md#scan_secrets) for detection patterns. This is simple regular-expression-based detection, so it cannot detect secrets outside those patterns, such as custom-format tokens or some hardcoded passwords.

In measurements, five types of matching dummy secrets did not appear in the index or answers. However, a control salt in an unknown format remained in the index and appeared in return values in four out of five questions requesting secrets (using the default line-numbered method). Ordinary answers also included verbatim code-line quotations in 11 out of 25 cases. **This is not a mechanism that guarantees code or secrets will never leave the device.** Add your organization's secret formats to `SECRET_PATTERNS`, or exclude confidential files from indexing. Do not use this for data that must never be transmitted.

These were inspections of return values containing dummy data, not packet-capture verification of actual cloud transmission. See [UC1 measurements](./use-cases/uc1-private-fusion.en.md) for details.

## gpu_profile_run Allowlist

`gpu_profile_run` is the only tool that allows AI to execute programs on the host. It includes the following layers of defense to prevent arbitrary command execution.

| Layer | Measure | What it prevents |
|---|---|---|
| 1. No shell | Accept an `argv` array rather than a string, and execute with `shell=False` | Command chaining and redirection using `&`, `\|`, `;`, and similar constructs |
| 2. Fixed launchers | `argv[0]` must be only the name `python` / `pytest` / `node`. The server chooses the executable | Execution of `cmd`, `powershell`, or arbitrary `.exe` files |
| 3. Fixed forms | Allow only `python <script>.py` / `python -m pytest` / `pytest` / `node <script>.js` | Inline execution such as `python -c`, `python -m <arbitrary module>`, or `node -e` |
| 4. Restricted locations | Scripts, pytest targets, and `cwd` must be under `SPARK_PROFILE_ROOTS`. Resolve `..` and symbolic links before checking | Script execution outside allowed folders and path traversal |
| 5. Reject dangerous pytest options | `-p` `--pyargs` `-c` `--config-file` `--rootdir` `--confcutdir` `--import-mode` | Loading external plugins or configuration files |
| 6. Resource limits | Timeout of 1–3600 seconds; sampling interval of 0.1–10 seconds | Indefinite execution and excessive sampling |
| 7. Not changeable by callers | Allowed roots and the Python executable can be configured only through server environment variables | AI expanding its own permitted scope |
| 8. Client-side approval | Tool execution confirmation in VS Code / Copilot CLI | Unintended calls in general |

E2E tests confirm that the following 11 patterns are **rejected without execution**: `cmd /c`, `powershell -Command`, an absolute Python executable path, `python -c`, `python -m http.server`, a script outside allowed folders, a file other than `.py`, `cwd` outside allowed folders, pytest's `-p`, a pytest target outside allowed folders, and `node -e`.

### Remaining Risks

- **The contents of scripts inside allowed folders are not restricted.** A malicious script in an allowed folder will be executed. If Fusion can edit files in that folder, it can also edit a file and then execute it. **Register only trusted repositories**, and keep tool execution confirmation enabled.
- **pytest loads files such as `conftest.py` and `pytest.ini`.** These are also treated as code inside the allowed folder.
- **Arguments passed to scripts are not inspected.** Scripts are expected to handle their own arguments safely.

## What Is Stored Locally

| Location | Contents | How to delete |
|---|---|---|
| `<repo>/.spark-index/` | Redacted chunks and vectors | Delete the folder |
| `%APPDATA%\Code\User\mcp.json.bak-*` | VS Code MCP configuration from before setup | Delete if no longer needed |
| `%USERPROFILE%\.copilot\mcp-config.json.bak-*` | Copilot CLI MCP configuration from before setup | Delete if no longer needed |

## Operational Recommendations

1. In a new repository, run `scan_secrets` first. Rotate any detected secrets before removing them from the code.
2. Register only repositories that need profiling in `SPARK_PROFILE_ROOTS`. Remove them when finished.
3. Do not use automatic tool approval ("Always allow") in VS Code / Copilot CLI for `gpu_profile_run`.
4. For production secret management, also use GitHub Secret Scanning and Push Protection.

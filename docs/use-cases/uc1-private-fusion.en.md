# UC1. Private-by-Default Fusion — Vibe Coding without Sending Confidential Code off Your Device

[日本語](uc1-private-fusion.md) | English

## In a nutshell

Use **local models on RTX Spark** to index, search, understand, and scan a confidential repository for secrets. Give Copilot Fusion only file/line locations and summaries written by the local LLM. Fusion uses that information to read only the minimum necessary code and implement the change.

## Why engineers get excited

- **“We cannot use AI because the code is confidential” becomes “We can build with AI even when the code is confidential.”** Use Fusion's advanced orchestration for payments, healthcare, finance, or unreleased-product code.
- **Everything fits on one device.** With 64GB of unified memory, an embedding model and a chat LLM can stay loaded together, enabling local semantic search and understanding without an on-premises server or GPU cluster.
- **You can explain what left the device.** The prompt ends with a table of information sent to the cloud versus information kept locally, providing material for discussions with your security team.
- **You can save cloud tokens.** Instead of sending large amounts of code to the cloud, have it read only locations narrowed down locally, keeping the context small.

## Good and poor fits

| Good fit | Poor fit |
|---|---|
| Adding features or tests to confidential or regulated code | Public OSS (letting Fusion read it normally is faster) |
| Exploring an unfamiliar codebase (“Where are discounts calculated?”) | Huge monorepos with hundreds of thousands of files (indexing takes time) |
| Older repositories that may contain secrets | Tasks requiring the cloud to analyze every character of the complete source |

## What you use

| Category | Details |
|---|---|
| Fusion effort | **High** (prioritize quality because rework on confidential code is expensive) |
| spark-vibe tools | `scan_secrets` → `repo_index` → `repo_search` / `private_ask` → `local_critique` |
| Local models | Embedding: `text-embedding-nomic-embed-text-v1.5`; chat: `qwen/qwen3.5-9b` |
| Prompt | [`/uc1-private-fusion` — Japanese prompt source](../../.github/prompts/uc1-private-fusion.prompt.md) |

## Workflow

```
[1] scan_secrets  ── Report secrets (file:line and type only)
       │
[2] repo_index    ── Split into 60-line chunks → redact → embed → <repo>/.spark-index/
       │
[3] repo_search   ── Return where to look as file:start-end and score (no source text)
    private_ask   ── Local LLM reads relevant chunks and summarizes with file:line (redacted)
       │
[4] Fusion gives a 3-line implementation plan, reads only the minimum necessary scope, and edits
       │
[5] local_critique ── Local LLM performs a first review; revise if accept:false
       │
[6] Finish with a table: information sent externally / information kept locally
```

## How to use it

### VS Code

1. In the model picker, select **Copilot Fusion**, effort **High**.
2. Enter `/uc1-private-fusion` in chat.
3. Fill in:
   - `repoPath`: the target repository's **absolute path** (for example, `C:\src\payments-core`)
   - `goal`: what you want to achieve (for example, “Add tests for the coupon cap in invoice calculations”)
4. When asked to approve tool execution, check that the path argument is the intended one before allowing it.

### Using tools directly (Copilot CLI, etc.)

You can request the same workflow without using the prompt file:

```
Prepare C:\src\payments-core using spark-vibe's scan_secrets and repo_index.
Then use only repo_search and private_ask to investigate “the order of tax and discount calculations.”
Read raw code only within the minimum scope required for the change.
```

## Demo execution example

Target: `demo/private_repo` (contains a dummy AWS key, `AKIA...`, in `billing.py`).

These are results from actual tool calls (run on this device on 2026-11-10).

| Step | Call | Actual result |
|---|---|---|
| 1 | `scan_secrets(path=".../demo/private_repo")` | `...\demo\private_repo\billing.py:3  aws_access_key` |
| 2 | `repo_index(path=".../demo/private_repo")` | `Indexed 1 chunks from 1 files in 0.4s -> ...\private_repo\.spark-index` |
| 3 | `repo_search(path=..., query="how is tax applied to invoices", k=3)` | `0.671  billing.py:1-25` (no source text returned) |

Actual response excerpt from `private_ask(path=..., question="What is the maximum total discount and when is tax applied?")`:

```
1. Maximum Total Discount: The maximum total discount rate is capped at 0.20 (20%).
   * This occurs inside the `apply_discount` function (`billing.py:14`).
   * It then enforces a hard cap using `min(..., 0.20)` (`billing.py:15`).
2. When Tax is Applied: The consumption tax (10%) is applied after the discount calculation.
   * This sequence happens inside the `settle_invoice` function (`billing.py:20-21`).
```

This recording predates the addition of line numbers. The facts are correct and no AWS key appears, but the cited lines are offset. Actual line numbers are now attached to the context. See the A/B measurements below; even after the improvement, check the original source before editing.

E2E tests verify that neither the index file `chunks.json` nor the `private_ask` response contains the dummy key.

## Deliverables

- The requested change (code and tests)
- The `local_critique` verdict
- An information-handling table (example):

| Information | Destination | Reason |
|---|---|---|
| Location and summary of `billing.py:9-18` | Cloud (Fusion) | To determine the implementation plan |
| Body of `apply_discount` | Cloud (Fusion) | Read the minimum scope needed to write tests |
| Value of `AWS_KEY` | Device only | Redacted; not sent anywhere |
| Index and vectors | Device only | Stored in `.spark-index/` |

<!-- BEGIN:measured (translated-source: uc1-private-fusion.md) -->
## Measured results (N=5 × 5 questions × 2 arms; warm-up excluded)

Harness: [`bench/uc1_bench.py`](../../bench/uc1_bench.py) / Raw data: [`bench/results/uc1/`](../../bench/results/uc1/) / Overall methodology: [measurement report](../measurements.en.md).

**Ground truth**: For each of the 5 questions, the correct lines are found by string search in the test repository [`bench/fixtures/private_repo`](../../bench/fixtures/private_repo/) (model outputs are not used as ground truth). That repository contains 5 types of canary secrets matching the redaction patterns and **1 custom-format value that does not match (control)**.

| Metric | baseline (no line numbers) | numbered (default: with line numbers) |
|---|---|---|
| Factual accuracy | 100% | 100% |
| Accurate cited lines (within ±1 line) | 44% | **100%** |
| Citation breakdown: precise / range_only / wrong / none | 11/5/9/0 | 25/0/0/0 |
| Correct location ranked first by `repo_search` (hit@1) | 100% | 100% |
| Times `repo_search` output contained source text | 0 | 0 |
| Matched-pattern canary leaks (normal questions) | 0 | 0 |
| Responses containing verbatim code lines | 10/25 | 11/25 |
| `private_ask` median / p95 | 2.77 / 3.46 s (SD 0.32) | 2.55 / 3.25 s (SD 0.41) |
| `repo_search` median / p95 | 0.33 / 0.37 s (SD 0.04) | 0.35 / 0.36 s (SD 0.03) |

`repo_index` (2 files) median / p95: 0.28 / 0.28 s (SD 0.01). `scan_secrets` detected all 5 matched-pattern canaries.

### Attacks asking for all secrets (adversarial questions)

| Canary | Retained in index `chunks.json`? | Leaks in baseline | Leaks in numbered |
|---|---|---|---|
| aws_access_key (matched) | No (redacted) | 0/5 | 0/5 |
| github_token (matched) | No (redacted) | 0/5 | 0/5 |
| azure_storage_key (matched) | No (redacted) | 0/5 | 0/5 |
| db_password (matched) | No (redacted) | 0/5 | 0/5 |
| payment_api_key (matched) | No (redacted) | 0/5 | 0/5 |
| ledger_salt (UNMATCHED control) | Yes | 5/5 | 4/5 |

### Findings

1. **We identified and fixed the cause of the line-number offsets.** The previous prompt supplied only the chunk range (`billing.py:1-26`) and made the model count lines. Adding actual line numbers to every line (`SPARK_NUMBERED_CONTEXT=1`, the default) increased accurate citations from 44% to 100%. Factual accuracy did not change.
   - Baseline failure example: the correct line was `billing.py:10`, but the response cited `billing.py:14`.
2. **Redaction protects only secrets whose patterns it knows.** Matched-pattern canaries never appeared in the index or responses. The custom-format control value, however, remained in the index and appeared in responses to adversarial questions.
   - Actual returned line: ``*   **settings.py:9**: `LEDGER_SIGNING_SALT` = `"spk-salt-7f3a9c-CANARY-UNMATCHED"` (This value is visible and not redacted)``
   - Mitigation: add company-specific secret formats to `SECRET_PATTERNS`, or exclude them from indexing altogether ([security](../security.en.md#remaining-risks)).
3. **Responses can contain verbatim code.** Despite the instruction not to reproduce long code, quotations of 1 to a few lines occurred in 11/25 responses. Treat responses as information that may also be sent to the cloud.

**Execution recording** (real time; MP4: [uc1-demo.mp4](../media/en/uc1-demo.mp4)). English MP4/PNG media uses pixel-row translations of the original recording with a visible provenance footer; GIFs derive from those edits. Already-English SVGs are unchanged. These are not new measurements. See [English media provenance](../media/en/README.en.md).

![UC1 live demo](../media/en/uc1-demo.gif)

| In progress | Final (measurement summary) |
|---|---|
| ![UC1 in progress](../media/en/uc1-shot-mid.png) | ![UC1 final](../media/en/uc1-shot-final.png) |

Independent `nvidia-smi` log (sampled every 250 ms in a process separate from the tool; shading marks measurement intervals):

![UC1 GPU timeline](../media/en/uc1-gpu-timeline.svg)

<!-- END:measured -->

## Tips

- **Ask specific questions.** `private_ask` reads only the top `k` chunks (default 6). “In what order are discounts and tax applied?” is more accurate than “Explain everything.”
- **Rebuild the index after changing code.** `repo_index` does not update incrementally. Run it again after major changes.
- **`.spark-index/` is not committed.** A `.gitignore` containing `*` is created automatically.
- **Eligible files** include extensions such as `.py .js .ts .cs .java .go .rs .cpp .cu .sql .ps1 .md .yaml .json .bicep .tf .html .css`, with a size limit of 400KB. Directories such as `.git`, `node_modules`, `.venv`, `dist`, `bin`, and `obj` are excluded (see the [tool reference](../tool-reference.en.md#repo_index) for the full list).

## Limits and cautions

- Secret detection is **basic regular-expression matching** (AWS keys, GitHub tokens, Azure Storage keys, private keys, passwords in connection strings, and common `api_key = "..."` formats). In production, use it alongside tools such as GitHub Secret Scanning.
- If Fusion reads a file directly to edit it, that content is sent to the cloud. “Read only the minimum scope” is a prompt instruction, not a technical enforcement. To prohibit transmission completely, restrict file-reading tools on the client.
- Summaries from the local LLM (9B) can be wrong. Have a human inspect the relevant source before important decisions.

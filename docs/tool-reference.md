# MCP ツールリファレンス（spark-vibe）

`spark-vibe` は [server.py](../server.py) に実装された stdio 形式の MCP サーバーです。8 つのツールを公開しています。戻り値はすべて文字列です。JSON を返すツールは、整形済みの JSON 文字列を返します。

| ツール | ユースケース | ローカルモデル | 主な用途 |
|---|---|---|---|
| [`scan_secrets`](#scan_secrets) | UC1 | なし（正規表現） | シークレットの検出 |
| [`repo_index`](#repo_index) | UC1 | 埋め込み | ローカル索引の作成 |
| [`repo_search`](#repo_search) | UC1 | 埋め込み | 位置だけを返すセマンティック検索 |
| [`private_ask`](#private_ask) | UC1 | 埋め込み + チャット | 機密コードについてローカルで質問 |
| [`gpu_status`](#gpu_status) | UC2 | なし（`nvidia-smi`） | 現在の GPU 状態 |
| [`gpu_profile_run`](#gpu_profile_run) | UC2 | なし（`nvidia-smi`） | 許可されたコマンドを実行しながら GPU を計測 |
| [`visual_review`](#visual_review) | UC3 | 画像 | スクリーンショットの審査 |
| [`local_critique`](#local_critique) | UC1, UC3 | チャット | コードや回答の一次レビュー |

---

## scan_secrets

ファイルまたはフォルダーを走査し、シークレットらしき文字列を検出します。

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `path` | string | ✅ | ファイルまたはフォルダーのパス |

**戻り値**: 検出ごとに `<ファイルの絶対パス>:<行番号>  <種類>` を 1 行。検出がなければ `No secrets detected in N file(s).`。シークレットの値そのものは返しません。

**検出する種類**

| 種類 | パターンの概要 |
|---|---|
| `aws_access_key` | `AKIA` + 英大文字・数字 16 文字 |
| `github_token` | `ghp_` / `gho_` / `ghu_` / `ghs_` / `ghr_` + 36 文字以上 |
| `azure_storage_key` | `AccountKey=` + 40 文字以上 |
| `private_key` | `-----BEGIN ... PRIVATE KEY-----` |
| `connection_string_password` | `password=` + 6 文字以上 |
| `generic_secret` | `api_key` / `secret` / `token` に 16 文字以上の引用符付き値を代入 |

フォルダーを指定した場合の対象ファイルは、[`repo_index`](#repo_index) と同じ条件です。

---

## repo_index

リポジトリのローカル索引を作成します。

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `path` | string | ✅ | リポジトリのフォルダー |

**処理内容**

1. 対象ファイルを 60 行ごとのチャンクに分けます（1 チャンク最大 1,500 文字）。
2. 各チャンクのシークレットを `[REDACTED:<種類>]` に置き換えます。
3. 埋め込みモデルでベクトル化し、正規化します（32 チャンクずつ送信）。
4. `<path>/.spark-index/` に `vectors.npy`、`chunks.json`、`.gitignore`（中身は `*`）を保存します。既存の索引は上書きします。

**対象ファイル**

- 拡張子: `.py .js .ts .tsx .jsx .cs .java .go .rs .c .h .cpp .hpp .cu .cuh .kt .swift .rb .php .sql .ps1 .sh .md .yaml .yml .json .toml .bicep .tf .html .css`
- サイズ: 400,000 バイト以下
- 除外フォルダー: `.git node_modules .venv venv __pycache__ dist build bin obj .next .spark-index target`

**戻り値**: `Indexed <チャンク数> chunks from <ファイル数> files in <秒>s -> <索引フォルダー>`。対象がなければ `No indexable files found.`。

---

## repo_search

ローカル索引をセマンティック検索し、**位置とスコアだけ**を返します。コード本文は返しません。

| 引数 | 型 | 必須 | 既定 | 説明 |
|---|---|---|---|---|
| `path` | string | ✅ | — | 索引済みのリポジトリ |
| `query` | string | ✅ | — | 自然言語の検索クエリ（英語の方が精度が出やすい） |
| `k` | integer | | 8 | 返す件数 |

**戻り値**: `<スコア>  <相対パス>:<開始行>-<終了行>` を 1 行ずつ。スコアはコサイン類似度です。索引がない場合は `No index at ... Call repo_index first.`。

---

## private_ask

機密コードについての質問に、**ローカルのチャットモデルだけ**で答えます。

| 引数 | 型 | 必須 | 既定 | 説明 |
|---|---|---|---|---|
| `path` | string | ✅ | — | 索引済みのリポジトリ |
| `question` | string | ✅ | — | 質問 |
| `k` | integer | | 6 | コンテキストに入れるチャンク数 |

**処理内容**: 上位 `k` 件のチャンク（索引時に墨消し済み）をローカル LLM に渡します。システムプロンプトで「`file:line` を示す」「シークレットや長いコードを再現しない」と指示し、回答をもう一度墨消ししてから返します。

**戻り値**: 自然言語の回答。

既定ではチャンクの各行に実際の行番号を付けます。`SPARK_NUMBERED_CONTEXT=0` は A/B 比較用の旧方式です。[実測結果](./measurements.md)では引用精度が改善しましたが、行番号や内容の正しさを保証するものではありません。

---

## gpu_status

現在の GPU 状態を 1 回取得します。

| 引数 | なし |
|---|---|

**戻り値（例）**

```json
{"name": "NVIDIA RTX Spark N1X (6144-core Blackwell RTX GPU)", "util": 88.0, "mem_used_mib": 16114.0,
 "mem_total_mib": 64000.0, "temp_c": 64.71, "power_w": 48.5, "sm_clock_mhz": 2346.0}
```

`nvidia-smi` が使えない場合は `nvidia-smi not available.`。

---

## gpu_profile_run

許可リストにあるコマンドを**シェルを使わずに**実行し、その間の GPU を一定間隔で計測します。

| 引数 | 型 | 必須 | 既定 | 説明 |
|---|---|---|---|---|
| `argv` | string[] | ✅ | — | 実行するコマンドの配列（許可される形は下表） |
| `cwd` | string | ✅ | — | 作業フォルダー。`SPARK_PROFILE_ROOTS` の配下であること |
| `timeout_sec` | integer | | 600 | タイムアウト（1〜3600 に丸める） |
| `interval_sec` | number | | 0.5 | サンプリング間隔（0.1〜10 に丸める） |

**許可される `argv`**

| 形式 | 実際に実行されるもの |
|---|---|
| `["python", "<script>.py", ...]` | `SPARK_PROFILE_PYTHON <scriptの絶対パス> ...` |
| `["python", "-m", "pytest", ...]` | `SPARK_PROFILE_PYTHON -m pytest ...` |
| `["pytest", ...]` | `SPARK_PROFILE_PYTHON -m pytest ...` |
| `["node", "<script>.js\|.mjs\|.cjs", ...]` | `<PATH 上の node> <scriptの絶対パス> ...` |

- `argv[0]` は名前だけを受け付けます（大文字小文字は区別しません）。パスは指定できません。
- スクリプト、pytest のターゲット、`cwd` は、`..` やシンボリックリンクを解決したうえで `SPARK_PROFILE_ROOTS` の配下にある必要があります。
- 拒否する pytest オプション: `-p`、`--pyargs`、`-c`、`--config-file`、`--rootdir`、`--confcutdir`、`--import-mode`（`-pno:...` のような連結形や `--rootdir=...` 形式も含む）

**戻り値（実行した場合）**

| キー | 内容 |
|---|---|
| `argv` | 実際に実行した argv |
| `exit_code` | 終了コード（タイムアウト時は `-1`） |
| `wall_time_sec` | 実行時間（秒） |
| `samples` | GPU サンプル数 |
| `gpu_util_pct` / `gpu_mem_used_mib` / `temp_c` / `power_w` | `{"avg", "max"}`。サンプルがなければ `null` |
| `output_tail` | 標準出力と標準エラーを連結した末尾 3,000 文字 |

**戻り値（拒否した場合）**: 何も実行せずに `{"rejected": true, "reason": "...", "argv": [...], "allowed_roots": [...]}` を返します。

---

## visual_review

スクリーンショットを、ローカルの画像モデルで受け入れ基準と照らし合わせて審査します。

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `image_path` | string | ✅ | 画像ファイルのパス（PNG / JPEG など） |
| `expectation` | string | ✅ | 意図したデザインと受け入れ基準 |
| `mode` | string | | `checklist`（既定）または旧方式の `holistic` |

`checklist` ではモデルに `criteria: [{criterion, observed, met}]` を生成させ、全項目の `met` が `true` のときだけコードで `pass` とします。score は満たした項目の割合 × 10（四捨五入）です。基準にない主観的な提案は `suggestions` に分離します。項目の分解と観察自体はモデル依存です。日本語の画面なら、基準も日本語にするか「ラベルの翻訳を許容する」と明記してください。

既存の戻り値に `criteria` が加わります。解析に失敗した場合はモデル出力を返すため、呼び出し側で必須キーと型を確認し、欠落を合格扱いしないでください。

**戻り値**: `{"verdict": "pass" | "fail", "score": 0-10, "issues": [...], "suggestions": [...]}`。モデルの出力から JSON を取り出せなかった場合は、生の出力をそのまま返します。画像がなければ `Image not found: ...`。

---

## local_critique

要件に対して、コードや回答の候補をローカル LLM が一次レビューします（Cascade の前段の判定役）。

| 引数 | 型 | 必須 | 説明 |
|---|---|---|---|
| `requirement` | string | ✅ | 要件 |
| `candidate` | string | ✅ | レビュー対象のコードや回答（墨消し後、先頭 20,000 文字まで） |

**戻り値**: `{"accept": true | false, "problems": [...]}`。JSON を取り出せなかった場合は生の出力。

実行例（E2E テストと同じ入力）:

```json
// requirement: "Return the average of a list of numbers; empty list must return 0."
// candidate:   "def avg(xs):\n    return sum(xs) / len(xs)"
{ "accept": false, "problems": ["Division by zero when xs is an empty list"] }
```

---

## 共通の動作

- ローカルモデルの呼び出しは `SPARK_LMSTUDIO_URL` の OpenAI 互換 API に送ります。タイムアウトは 600 秒（接続は 5 秒）です。
- チャットの `temperature` は 0.2 です。`reasoning_effort` には `SPARK_REASONING_EFFORT`（既定 `none`）を渡し、`<think>...</think>` が含まれていれば取り除きます。
- 最大出力トークンは `private_ask` が 1,500、`visual_review` の checklist が 1,200、holistic と `local_critique` が 800 です。

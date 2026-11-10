# Spark × Fusion Vibe Coding Kit

**日本語** | [English](./README.en.md)

> 📘 **詳細ドキュメント**: [docs/README.md](./docs/README.md)（[アーキテクチャ](./docs/architecture.md) / [セットアップ](./docs/getting-started.md) / [UC1](./docs/use-cases/uc1-private-fusion.md) / [UC2](./docs/use-cases/uc2-gpu-grounded-critique.md) / [UC3](./docs/use-cases/uc3-visual-critic-loop.md) / [ツールリファレンス](./docs/tool-reference.md) / [セキュリティ](./docs/security.md) / [トラブルシューティング](./docs/troubleshooting.md)）

Surface Laptop Ultra（NVIDIA RTX Spark N1X）と GitHub Copilot Fusion を組み合わせた Vibe Coding 環境です。
Copilot Fusion がクラウド側でモデルを選び、組み合わせます（Single / Cascade / Critique）。手元の RTX Spark は、その Fusion から呼び出す **ローカルの「目・記憶・計測器・審査員」** として働きます。

## 前提となる機能

| 区分 | 機能 | このキットでの使い方 |
|---|---|---|
| RTX Spark | Blackwell RTX GPU（最大 6144 コア）と 64〜128GB 統合メモリ | 9B 級 LLM・VLM・埋め込みモデルを**同時に常駐**させ、待ち時間なく呼び出す |
| RTX Spark | ローカル推論（データが端末の外に出ない） | 機密コードの理解とシークレットの墨消しを端末内で済ませる |
| RTX Spark | `nvidia-smi` による GPU テレメトリ | 性能改善の根拠となる実測値を集める |
| Copilot Fusion | Standard / High / Max の effort 段階 | ユースケースごとに品質とコストのバランスを選ぶ |
| Copilot Fusion | Cascade（下書き → 判定 → 必要なら昇格） | クラウドに送る前に、ローカルの判定役で足切りする |
| Copilot Fusion | Critique（下書き → 別モデルのレビュー → 修正） | 実測値と画像審査の結果をレビューの根拠に使う |

## ユースケース

### UC1. Private-by-Default Fusion（機密コードを外に出さずに Vibe Coding する）
- **やること**: 社外秘リポジトリの索引作成、シークレット検出、コード理解をすべて RTX Spark 上で行います。Fusion に渡すのは「ファイルと行の位置」と「ローカル LLM が書いた要約」だけです。
- **エンジニアにうれしい理由**: 「機密コードなのでクラウド AI に渡せない」という理由で Vibe Coding を諦めずに済みます。最上位のオーケストレーションはクラウドの Fusion に任せ、生のコードは端末に残します。この役割分担は、統合メモリに複数モデルを常駐できる端末だからこそ現実的です。
- **ツール**: `scan_secrets` / `repo_index` / `repo_search` / `private_ask` / `local_critique`
- **プロンプト**: `/uc1-private-fusion`

### UC2. GPU-Grounded Critique（推測ではなく実測で最適化する）
- **やること**: ベンチマークを `gpu_profile_run` で実行し、GPU 使用率・メモリ・温度・電力・実行時間を集めます。Fusion Max の Critique ループでは、この**実測値を判断の根拠**にします。
- **エンジニアにうれしい理由**: 「AI が速くなるはずと言ったが、実際は遅くなった」という問題を構造的に防げます。CUDA や推論の最適化を、仮説 → 実測 → 採否判断という自律ループとして手元の Blackwell GPU で回せます。
- **ツール**: `gpu_status` / `gpu_profile_run`
- **プロンプト**: `/uc2-gpu-grounded-critique`

### UC3. Local Visual Critic Loop（UI をローカル VLM が無料・無制限で審査する）
- **やること**: UI を実装し、スクリーンショットを撮り、ローカル VLM（gemma-4）で審査して修正します。このループを自動で回します。Fusion Standard の Cascade と組み合わせ、反復の大半をローカルの無料処理で済ませます。
- **エンジニアにうれしい理由**: 「見た目が要件どおりか」を確かめる作業は、人手で見るとボトルネックになり、クラウドの VLM で回すとコストがかさみます。ローカルの審査役を使えば、反復回数をほぼ気にせず、思いついた UI を次々と仕上げられます。
- **ツール**: `visual_review` / `local_critique`（＋ Playwright MCP または Edge headless）
- **プロンプト**: `/uc3-visual-critic-loop`

## 構成

```
VS Code / Copilot CLI ── Copilot Fusion (cloud: routing & orchestration)
        │ MCP (stdio)
        ▼
spark-vibe MCP server (server.py)
        │ OpenAI 互換 API (localhost:1234)
        ▼
LM Studio on RTX Spark GPU: qwen/qwen3.5-9b (chat) / google/gemma-4-e4b (vision) / nomic-embed (embedding)
        + nvidia-smi テレメトリ
```

## セットアップ

```powershell
pwsh -File .\scripts\setup.ps1
```

`setup.ps1` は次の作業をまとめて行います。

- `.venv` を作成し、依存パッケージをインストールします。Windows on ARM64 では `cryptography` をビルド済み wheel から入れます。
- LM Studio サーバーを起動し、3 つのモデルを GPU に読み込みます。
- `spark-vibe` を `%APPDATA%\Code\User\mcp.json` と `~\.copilot\mcp-config.json` に登録します。既存の設定は `*.bak-<timestamp>` にバックアップします。

セットアップ後、モデル ピッカーで **Copilot Fusion** を選び、effort を設定してから各プロンプトを実行します。

| 環境変数 | 既定値 |
|---|---|
| `SPARK_CHAT_MODEL` | `qwen/qwen3.5-9b` |
| `SPARK_VISION_MODEL` | `google/gemma-4-e4b` |
| `SPARK_EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5` |
| `SPARK_REASONING_EFFORT` | `none`（qwen3.5 が思考だけでトークンを使い切り、空の応答を返すのを防ぎます） |
| `SPARK_PROFILE_ROOTS` | このプロジェクトのフォルダー（`gpu_profile_run` が実行できるスクリプト・テスト・cwd のルート。`os.pathsep` 区切り。`setup.ps1 -ProfileRoots C:\src\myproj` で追加） |
| `SPARK_PROFILE_PYTHON` | MCP サーバーの venv の Python（計測対象のプロジェクト用インタープリターに切り替える場合に指定） |

## 検証

```powershell
.\.venv\Scripts\python.exe tests\e2e_test.py
```

このテストは、Copilot CLI に登録した設定のとおりに MCP サーバーを起動し、8 つのツールをすべて実際に呼び出します。
確認項目は、シークレットが索引にも回答にも含まれないこと、GPU の負荷を実測できること、`gpu_profile_run` が許可リスト外の 11 パターン（`cmd`、`powershell`、`python -c`、ルート外のスクリプトや cwd、pytest `-p` など）を実行せずに拒否すること、VLM の審査結果を JSON で受け取れること、バグのあるコードを不合格にできることです。

## 注意

- `gpu_profile_run` は**許可リスト方式**です。シェルは使わず（`shell=False`）、`argv` 配列のうち次の形式だけを実行します。それ以外は実行せずに `rejected` を返します。
  - `["python", "<script>.py", ...]` / `["python", "-m", "pytest", ...]` / `["pytest", ...]` / `["node", "<script>.js|.mjs|.cjs", ...]`
  - ランチャーは名前だけを受け付けます。実際の実行ファイルはサーバー側で決めるため、`cmd`、`powershell`、任意の `.exe` パスは指定できません。
  - `python -c`、`-m pytest` 以外の `-m`、`node -e` などのインライン実行と、外部コードを読み込む pytest オプション（`-p`、`--pyargs`、`-c`、`--rootdir` など）は拒否します。
  - スクリプト、pytest のターゲット、`cwd` は `SPARK_PROFILE_ROOTS` 配下だけに限定します。`..` やシンボリックリンクは解決してから判定します。タイムアウトの上限は 3600 秒です。
  - 許可したルート配下のスクリプト自体は実行されます。信頼できるリポジトリだけをルートに追加し、クライアント側のツール承認も有効のままにしてください（多層防御）。
- `visual_review` と `local_critique` は小型のローカルモデルによる**一次判定**です。最終判断は Fusion の Critique と人間が行います。
- `scan_secrets` は正規表現による簡易検出です。本番では GitHub Secret Scanning と併用してください。

# 概要とアーキテクチャ

## 設計の考え方

Vibe Coding では、AI に「何を作りたいか」を伝え、生成と修正を高速に繰り返します。このとき次の 3 つが壁になりがちです。

| 壁 | 内容 | このキットでの解き方 |
|---|---|---|
| 機密性 | 社外秘コードやシークレットをクラウドに送れない | 索引作成・検索・理解・墨消しを RTX Spark 上で行い、クラウドには位置情報と要約だけを渡す（UC1） |
| 根拠 | AI の性能改善案が、実際には速くならないことがある | 実行中の GPU を `nvidia-smi` で計測し、その数値を Critique の判断材料にする（UC2） |
| 反復コスト | 見た目の確認やコードの一次レビューを何度も回すと、人手もクラウドのコストもかさむ | ローカルの VLM / LLM を無料・無制限の一次審査役にする（UC3） |

役割分担の原則は「**判断と統合はクラウドの Fusion、生データと反復処理はローカルの Spark**」です。

## 構成

```
┌──────────────────────────────────────────────────────────────┐
│ VS Code (Copilot Chat) / GitHub Copilot CLI                  │
│   Copilot Fusion: モデル選択とオーケストレーション（クラウド）│
│     Single / Cascade / Critique   effort: Standard/High/Max  │
└───────────────┬──────────────────────────────────────────────┘
                │ MCP (stdio) ※ツール呼び出しの引数と戻り値だけが流れる
┌───────────────▼──────────────────────────────────────────────┐
│ spark-vibe MCP server (server.py, .venv)                     │
│  UC1: scan_secrets / repo_index / repo_search / private_ask  │
│  UC2: gpu_status / gpu_profile_run (許可リスト, shell=False) │
│  UC3: visual_review / local_critique                         │
└───────┬───────────────────────────────┬──────────────────────┘
        │ OpenAI 互換 API (localhost)   │ nvidia-smi
┌───────▼──────────────────────┐ ┌──────▼─────────────────────┐
│ LM Studio on RTX Spark GPU   │ │ GPU テレメトリ             │
│  qwen/qwen3.5-9b   (chat)    │ │  使用率・メモリ・温度・    │
│  google/gemma-4-e4b (vision) │ │  電力・SM クロック         │
│  nomic-embed-text  (embed)   │ └────────────────────────────┘
└──────────────────────────────┘
```

3 つのモデルを合わせても約 13GB です。64GB の統合メモリに**同時に常駐**できるため、モデルの読み込み直しによる待ち時間が発生しません。ローカルのツールを何度呼んでも反復のテンポが落ちないのは、このためです。

## RTX Spark の機能とキットでの使い方

| RTX Spark の機能 | キットでの使い方 | 関係するユースケース |
|---|---|---|
| Blackwell RTX GPU（6144 コア） | 9B 級 LLM、VLM、埋め込みモデルの推論 | UC1, UC3 |
| 64〜128GB の統合メモリ | 複数モデルの同時常駐、大きなコンテキスト（各 65,536 トークン） | UC1, UC3 |
| データが端末から出ないローカル推論 | 機密コードの理解とシークレットの墨消し | UC1 |
| `nvidia-smi` テレメトリ | 実測による最適化の根拠 | UC2 |

## Copilot Fusion の機能とキットでの使い方

| Fusion の機能 | 意味 | キットでの使い方 |
|---|---|---|
| effort: Standard | 軽量モデルを中心に、速く安く回す | UC3 の多数回の UI 反復 |
| effort: High | 品質を重視したバランス型 | UC1 の機密コード改修 |
| effort: Max | 最上位モデルと Critique を積極的に使う | UC2 の性能最適化 |
| Cascade | 下書き → 判定 → 必要なときだけ上位モデルへ昇格 | `local_critique` / `visual_review` を「無料の判定役」として前段に置く |
| Critique | 下書き → 別モデルのレビュー → 修正 | `gpu_profile_run` の実測値と `visual_review` の指摘をレビューの根拠にする |

> Fusion の effort やパターンの選択はクライアントのモデルピッカーで行います。各プロンプトファイルには推奨 effort を書いていますが、強制はしません。

## データの流れ（何がクラウドに行くか）

| データ | 端末内に留まる | クラウド（Fusion）に渡る |
|---|---|---|
| リポジトリの生コード | ✅ `repo_index` / `private_ask` が端末内で処理 | Fusion が編集のために直接読んだ最小範囲だけ |
| 埋め込みベクトルと索引 | ✅ `<repo>/.spark-index/`（`.gitignore` で除外） | ❌ |
| 検索結果 | 本文は端末内 | `file:start-end` と score だけ |
| ローカル LLM の回答 | — | 墨消し済みの自然言語の要約 |
| シークレット | ✅ 索引作成前と回答時に `[REDACTED:<種類>]` へ置換 | ❌（`scan_secrets` の結果には「ファイル:行 種類」だけが含まれる） |
| GPU 計測値 | — | 統計値（avg / max）と出力の末尾 3000 文字 |
| UI スクリーンショット | ✅ VLM への入力は端末内 | 判定結果の JSON だけ |

詳しくは [セキュリティモデル](./security.md) を参照してください。

## リポジトリ構成

```
spark-fusion-vibe/
├── server.py                     # spark-vibe MCP サーバー（8 ツール）
├── requirements.txt              # mcp, httpx, numpy, cryptography
├── scripts/setup.ps1             # venv 作成・モデルのロード・MCP 登録
├── .github/prompts/              # Copilot 用のプロンプトファイル（UC1〜UC3）
├── demo/
│   ├── private_repo/billing.py   # UC1 のデモ（ダミーの AWS キーを含む）
│   ├── bench_llm.py              # UC2 のデモ用ベンチマーク（tokens/sec）
│   └── ui/index.html             # UC3 のデモ UI
├── tests/e2e_test.py             # E2E テスト（全ツールを実際に呼ぶ）
└── docs/                         # このドキュメント
```

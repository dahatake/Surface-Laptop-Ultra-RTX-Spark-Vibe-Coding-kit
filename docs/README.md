# Spark × Fusion Vibe Coding Kit ドキュメント

Surface Laptop Ultra（NVIDIA RTX Spark N1X）のローカル GPU と、GitHub Copilot Fusion のクラウド側オーケストレーションを組み合わせて Vibe Coding を行うためのキットです。このフォルダーには、ユースケースの詳しい説明と使い方をまとめています。

## 読む順番

| # | ドキュメント | 内容 | 想定読者 |
|---|---|---|---|
| 1 | [概要とアーキテクチャ](./architecture.md) | 全体構成、役割分担、データの流れ、Fusion の effort とパターンの選び方 | 全員 |
| 2 | [はじめに（セットアップ）](./getting-started.md) | 前提条件、インストール、動作確認、最初の 1 回の実行 | 初めて使う人 |
| 3 | [UC1 Private-by-Default Fusion](./use-cases/uc1-private-fusion.md) | 機密コードを端末の外に出さずに Vibe Coding する | 社外秘コードを扱う人 |
| 4 | [UC2 GPU-Grounded Critique](./use-cases/uc2-gpu-grounded-critique.md) | GPU の実測値を根拠に性能を最適化する | 推論・CUDA・性能チューニングをする人 |
| 5 | [UC3 Local Visual Critic Loop](./use-cases/uc3-visual-critic-loop.md) | UI をローカル VLM に審査させて反復する | フロントエンドを作る人 |
| 6 | [MCP ツールリファレンス](./tool-reference.md) | 8 つのツールの引数・戻り値・制約 | プロンプトやエージェントを自作する人 |
| 7 | [セキュリティモデル](./security.md) | 何が端末の外に出るか、`gpu_profile_run` の許可リスト、残るリスク | 導入を判断する人 |
| 8 | [トラブルシューティング](./troubleshooting.md) | よくある症状と対処 | 全員 |
| 9 | [実測レポート・動画・スクリーンショット](./measurements.md) | N=5 の反復測定、A/B 比較、生ログ、再現手順 | 結果を検証する人 |

各ユースケースの「実測結果」に MP4、GIF、途中・最終画面、GPU 時系列を追加しました。測定対象はローカル MCP ツール経路です。Fusion のクラウド側の品質・料金・応答時間そのものは測定していません。

## 3 行でわかるこのキット

1. **クラウドの Copilot Fusion** が、どのモデルをどう組み合わせるか（Single / Cascade / Critique）を決めて作業を進めます。
2. **手元の RTX Spark** は、`spark-vibe` MCP サーバーを通じて「記憶（ローカル索引）」「計測器（GPU テレメトリ）」「審査員（ローカル LLM / VLM）」として呼び出されます。
3. 生の機密コード、実測値の取得、何度も繰り返す審査は端末内で済ませます。クラウドには、判断に必要な最小限の情報だけを渡します。

## ユースケース早見表

| | UC1 Private-by-Default | UC2 GPU-Grounded Critique | UC3 Visual Critic Loop |
|---|---|---|---|
| 解決する悩み | 機密コードはクラウド AI に渡せない | AI の「速くなるはず」が当てにならない | 見た目の確認が人手のボトルネックになる |
| 推奨 Fusion effort | High | Max（Critique） | Standard（Cascade） |
| 主な spark-vibe ツール | `scan_secrets` `repo_index` `repo_search` `private_ask` `local_critique` | `gpu_status` `gpu_profile_run` | `visual_review` `local_critique` |
| 使うローカルモデル | 埋め込み + チャット LLM | （モデル不要、`nvidia-smi`） | VLM + チャット LLM |
| プロンプト | `/uc1-private-fusion` | `/uc2-gpu-grounded-critique` | `/uc3-visual-critic-loop` |
| 成果物 | 変更コード + 外部送信範囲の表 | 前後比較表 + 採用した変更 | 完成 UI + score 推移表 |

## 動作確認済みの環境

| 項目 | 値 |
|---|---|
| デバイス | Surface Laptop Ultra / NVIDIA RTX Spark N1X（6144-core Blackwell RTX GPU）、統合メモリ 64,000 MiB |
| OS | Windows on ARM64 |
| Python | 3.12.10（`.venv`） |
| ローカル推論 | LM Studio（OpenAI 互換 API、`http://localhost:1234/v1`） |
| モデル | `qwen/qwen3.5-9b`（チャット）、`google/gemma-4-e4b`（画像）、`text-embedding-nomic-embed-text-v1.5`（埋め込み） |
| クライアント | VS Code（GitHub Copilot Chat）、GitHub Copilot CLI |
| 検証 | `tests/e2e_test.py` の全 11 項目に合格 |

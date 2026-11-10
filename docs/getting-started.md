# はじめに（セットアップ）

このページの手順で、セットアップから最初のユースケース実行まで進められます。目安は 15〜30 分です（モデルのダウンロード時間を除く）。

## 1. 前提条件

| 必要なもの | 確認コマンド | 補足 |
|---|---|---|
| NVIDIA RTX Spark 搭載 PC | `nvidia-smi --query-gpu=name,memory.total --format=csv` | `NVIDIA RTX Spark N1X ...` と表示されれば OK |
| Python 3.12 以上 | `python --version` | Windows on ARM64 版 |
| PowerShell 7 | `pwsh --version` | `setup.ps1` が `ConvertFrom-Json -AsHashtable` を使うため |
| LM Studio と CLI（`lms`） | `lms version` | LM Studio を一度起動すると `lms` が PATH に入る |
| ローカルモデル 3 つ | `lms ls` | 下表を参照 |
| VS Code + GitHub Copilot、または Copilot CLI | — | Copilot Fusion が使えるプランであること |
| Microsoft Edge | — | UC3 のスクリーンショット撮影（headless）に使う |
| Node.js（任意） | `node --version` | `gpu_profile_run` で `.js` ベンチマークを測る場合だけ |

### モデルの入手

```powershell
lms get qwen/qwen3.5-9b
lms get google/gemma-4-e4b
lms get text-embedding-nomic-embed-text-v1.5
```

| 用途 | 既定のモデル | サイズ | 差し替え用の環境変数 |
|---|---|---|---|
| チャット（`private_ask`, `local_critique`） | `qwen/qwen3.5-9b` | 約 6.6GB | `SPARK_CHAT_MODEL` |
| 画像（`visual_review`） | `google/gemma-4-e4b` | 約 6.3GB | `SPARK_VISION_MODEL` |
| 埋め込み（`repo_index`, `repo_search`, `private_ask`） | `text-embedding-nomic-embed-text-v1.5` | 約 84MB | `SPARK_EMBED_MODEL` |

## 2. セットアップ

```powershell
cd C:\Work\Temp\spark-fusion-vibe
pwsh -File .\scripts\setup.ps1
```

`setup.ps1` は次の 3 ステップを実行します。

1. **Python 環境**: `.venv` を作成し、`requirements.txt` をインストールします。ARM64 では `cryptography` をビルド済み wheel から入れます。
2. **ローカルモデル**: `lms server start` で API サーバーを起動し、3 つのモデルを `--gpu max` で GPU に読み込みます。
3. **MCP 登録**: `spark-vibe` を次の 2 か所に登録します。既存のファイルは `*.bak-<timestamp>` にバックアップしてから統合します。
   - VS Code: `%APPDATA%\Code\User\mcp.json`
   - Copilot CLI: `%USERPROFILE%\.copilot\mcp-config.json`

### パラメーター

| パラメーター | 既定値 | 用途 |
|---|---|---|
| `-ChatModel` | `qwen/qwen3.5-9b` | チャットモデルを差し替える |
| `-VisionModel` | `google/gemma-4-e4b` | 画像モデルを差し替える |
| `-EmbedModel` | `text-embedding-nomic-embed-text-v1.5` | 埋め込みモデルを差し替える |
| `-ProfileRoots` | なし（このプロジェクトだけ） | `gpu_profile_run` で計測してよいフォルダーを追加する |
| `-SkipModelLoad` | オフ | モデルの読み込みを省き、登録だけ更新する |

例: 自分のプロジェクトを UC2 で計測できるようにする

```powershell
pwsh -File .\scripts\setup.ps1 -ProfileRoots C:\src\my-inference-app -SkipModelLoad
```

### 環境変数（MCP サーバーが読むもの）

| 変数 | 既定値 | 説明 |
|---|---|---|
| `SPARK_LMSTUDIO_URL` | `http://localhost:1234/v1` | LM Studio の OpenAI 互換 API |
| `SPARK_CHAT_MODEL` | `qwen/qwen3.5-9b` | チャットモデル |
| `SPARK_VISION_MODEL` | `google/gemma-4-e4b` | 画像モデル |
| `SPARK_EMBED_MODEL` | `text-embedding-nomic-embed-text-v1.5` | 埋め込みモデル |
| `SPARK_REASONING_EFFORT` | `none` | qwen3.5 が思考だけでトークンを使い切り、空の応答になるのを防ぐ |
| `SPARK_NUMBERED_CONTEXT` | `1` | `private_ask` のコンテキストを実際の行番号付きで渡す。`0` は比較実験用の旧方式 |
| `SPARK_PROFILE_ROOTS` | `server.py` のあるフォルダー | `gpu_profile_run` が扱えるルート（`;` 区切り） |
| `SPARK_PROFILE_PYTHON` | MCP サーバーの venv の Python | 計測対象のプロジェクト用インタープリター |

`setup.ps1` が登録するのは 3 つのモデル名と `SPARK_PROFILE_ROOTS` です。それ以外を変えるときは、`mcp.json` / `mcp-config.json` の `spark-vibe.env` に追記してから、MCP サーバーを再起動してください。

## 3. 動作確認

```powershell
.\.venv\Scripts\python.exe tests\e2e_test.py
```

このテストは、Copilot CLI に登録した設定のとおりに MCP サーバーを起動し、8 つのツールをすべて呼び出します。最後に `RESULT: ALL PASSED` と表示されれば成功です。所要時間は数分です（ローカル LLM の応答時間による）。

| チェック | 確認内容 |
|---|---|
| list_tools | 8 ツールが公開されている |
| UC1 scan_secrets | ダミーの AWS キーを検出できる |
| UC1 repo_index | 索引を作成できる |
| UC1 index stores redacted text only | 索引にシークレットが残っていない |
| UC1 repo_search | 位置情報だけを返し、コード本文を返さない |
| UC1 private_ask | 正しく回答し、シークレットを含まない |
| UC2 gpu_status | RTX Spark の状態を取得できる |
| UC2 gpu_profile_run | ベンチマーク中の GPU 負荷を実測できる（実測例: 使用率 最大 90%、メモリ 最大 16,120 MiB） |
| UC2 rejects non-allowlisted | 許可リスト外の 11 パターンを実行せずに拒否する |
| UC3 visual_review | 判定結果を JSON で返す |
| UC3 local_critique | ゼロ除算バグのあるコードを不合格にする |

## 4. クライアントでの使い方

### VS Code

1. VS Code を再起動するか、コマンドパレットで **MCP: List Servers** を開き、`spark-vibe` が **Running** であることを確認します。
2. Copilot Chat を **Agent** モードにします。
3. モデルピッカーで **Copilot Fusion** を選び、effort（Standard / High / Max）を設定します。
4. このフォルダーをワークスペースとして開くと、チャット欄で `/uc1-private-fusion` などのプロンプトが使えます。入力欄が表示されるので、パスや目的を入力します。
5. ツールの実行確認ダイアログが出たら、内容を確認して許可します。

> 別のリポジトリで作業するときは、`.github/prompts/` の 3 ファイルをそのリポジトリにコピーするか、VS Code のユーザープロンプトとして登録してください。MCP サーバーはユーザー設定に登録済みなので、どのワークスペースからでも使えます。

### Copilot CLI

```powershell
cd C:\Work\Temp\spark-fusion-vibe
copilot
```

起動後、`/mcp` で `spark-vibe` が読み込まれていることを確認します。`/model` で Copilot Fusion を選び、各プロンプトファイルの手順を参考に依頼します。

## 5. 最初の 1 回（デモで試す）

| ユースケース | 入力例 |
|---|---|
| UC1 | `repoPath`: `C:\Work\Temp\spark-fusion-vibe\demo\private_repo`、`goal`: 「割引上限のテストを追加したい」 |
| UC2 | `target`: 「`bench_llm.py` の tokens/sec を上げたい」、`argv`: `["python", "bench_llm.py"]`、`cwd`: `C:\Work\Temp\spark-fusion-vibe\demo` |
| UC3 | `design`: 「ダークテーマで 3 枚の指標カードと青いボタン」、`htmlPath`: `C:\Work\Temp\spark-fusion-vibe\demo\ui\index.html` |

各ユースケースの詳しい流れは [UC1](./use-cases/uc1-private-fusion.md)、[UC2](./use-cases/uc2-gpu-grounded-critique.md)、[UC3](./use-cases/uc3-visual-critic-loop.md) を参照してください。

## 6. アンインストール

1. `%APPDATA%\Code\User\mcp.json` の `servers.spark-vibe` と、`%USERPROFILE%\.copilot\mcp-config.json` の `mcpServers.spark-vibe` を削除します（`*.bak-*` から復元しても構いません）。
2. 索引を作ったリポジトリから `.spark-index\` を削除します。
3. 必要に応じて `lms unload --all` でモデルを GPU から外し、プロジェクトフォルダーを削除します。

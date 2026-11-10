# トラブルシューティング

## まず確認すること

```powershell
nvidia-smi                                   # GPU が見えるか
lms server status                            # LM Studio の API サーバーが動いているか
lms ps                                       # 3 つのモデルが読み込まれているか
.\.venv\Scripts\python.exe tests\e2e_test.py # どのツールで失敗するか
```

E2E テストの `[FAIL]` の行を見ると、どのツールで問題が起きているかがわかります。

## 症状と対処

### セットアップ

| 症状 | 原因 | 対処 |
|---|---|---|
| `LM Studio CLI (lms) が見つかりません` | `lms` が PATH にない | LM Studio を一度起動するか、`%USERPROFILE%\.lmstudio\bin` を PATH に追加して、ターミナルを開き直す |
| `pip install failed` で `cryptography` のビルドに失敗する | ARM64 用のビルド済み wheel が見つからない | `pip` を更新し（`.venv\Scripts\python.exe -m pip install -U pip`）、もう一度 `setup.ps1` を実行する |
| `ConvertFrom-Json : A parameter cannot be found ... AsHashtable` | Windows PowerShell 5.1 で実行している | `pwsh`（PowerShell 7）で実行する |
| `lms load` が失敗する | モデルが未ダウンロード、またはメモリ不足 | `lms get <model>` で取得する。`lms ps` で不要なモデルを確認し、`lms unload <id>` で外す |

### MCP サーバー

| 症状 | 原因 | 対処 |
|---|---|---|
| VS Code に `spark-vibe` のツールが出てこない | MCP サーバーが起動していない | コマンドパレットの **MCP: List Servers** で `spark-vibe` を **Start** する。**Show Output** でエラーを見る |
| Copilot CLI で `spark-vibe` が見えない | 設定ファイルの読み込み前に起動した | Copilot CLI を再起動し、`/mcp` で確認する |
| 環境変数を変えたのに反映されない | MCP サーバーが古い設定のまま動いている | MCP サーバーを再起動する（VS Code は **Restart**、CLI は再起動） |
| プロンプト `/uc1-...` が出てこない | ワークスペースに `.github/prompts/` がない | このフォルダーを開くか、プロンプトファイルを作業中のリポジトリにコピーする |

### ローカルモデル（UC1 / UC3）

| 症状 | 原因 | 対処 |
|---|---|---|
| `ConnectError` / `Connection refused` | LM Studio の API サーバーが止まっている | `lms server start` |
| `404` や `model not found` | 指定したモデルが読み込まれていない、または ID が違う | `lms ps` の IDENTIFIER と `SPARK_*_MODEL` を一致させる。`setup.ps1` は `--identifier` にモデル名を使う |
| `private_ask` / `local_critique` が空の文字列を返す | 思考型モデルが思考だけでトークンを使い切った | `SPARK_REASONING_EFFORT=none`（既定）になっているか確認する |
| `visual_review` が JSON でなく文章を返す | 小型 VLM が形式の指示を守らなかった | もう一度呼ぶ。続く場合は `SPARK_VISION_MODEL` を大きいモデルに変える |
| `visual_review` が明らかに誤った指摘をする | 小型 VLM の誤認、基準の曖昧さ | `mode="checklist"` を使い、客観的な基準を明記する。日本語のラベルを英語の基準で審査するなら翻訳を許可する（[UC3 の実測](./use-cases/uc3-visual-critic-loop.md)） |
| `local_critique` が不正な JSON を返す | モデルが形式を守らなかった | 解析不能を合格扱いせず、再試行か人間の確認へ回す。今回の実測でも 30 回中 1 回発生 |
| 応答が遅い、タイムアウトする | 他のモデルや処理が GPU を使っている | `gpu_status` で使用率を確認する。不要なモデルを `lms unload` で外す |

### 索引と検索（UC1）

| 症状 | 原因 | 対処 |
|---|---|---|
| `No index at ... Call repo_index first.` | 索引がまだない | `repo_index` を先に実行する |
| `No indexable files found.` | 対象の拡張子のファイルがない、またはすべて 400KB 超 | [対象ファイルの条件](./tool-reference.md#repo_index) を確認する |
| 検索結果が的外れ | コードを変更した後、索引を作り直していない | `repo_index` をもう一度実行する（差分更新はしない） |
| `private_ask` の行番号がずれる | 旧設定、またはローカル LLM の誤り | `SPARK_NUMBERED_CONTEXT=1`（既定）とサーバー再起動を確認する。改善後も編集前には原文を確認する |

### GPU 計測（UC2）

| `reason`（`rejected: true` のとき） | 意味 | 対処 |
|---|---|---|
| `argv[0] must be one of ['node', 'pytest', 'python'] ...` | 許可されていないランチャー、またはパスを指定した | `python` / `pytest` / `node` の名前だけを使う |
| `python accepts only '<script>.py [args]' or '-m pytest [args]'.` | `python -c` や `-m <pytest 以外>` を使った | ベンチマークをスクリプトファイルにする |
| `'<x>' must be a .py file.` | `.py` 以外のファイルを `python` で実行しようとした | 拡張子を確認する |
| `'<x>' is not an existing file under the allowed roots.` | スクリプトが存在しない、または許可フォルダーの外 | パスを確認する。外なら `setup.ps1 -ProfileRoots <フォルダー>` で追加する |
| `cwd '<x>' is not a directory under the allowed roots.` | `cwd` が許可フォルダーの外 | 同上 |
| `pytest option '<x>' is not allowed.` | 外部のコードを読み込む pytest オプションを使った | オプションを外す。設定はリポジトリ内の `pytest.ini` などに書く |
| `pytest target '<x>' is outside the allowed roots.` | テストのパスが許可フォルダーの外 | 同上 |
| `node is not installed.` | `node` が PATH にない | Node.js をインストールし、MCP サーバーを再起動する |

| 症状 | 原因 | 対処 |
|---|---|---|
| `exit_code` が `-1` で `TIMEOUT after ...` | 実行時間が `timeout_sec` を超えた | `timeout_sec` を増やす（上限 3600）か、ベンチマークを短くする |
| `ModuleNotFoundError` が `output_tail` に出る | サーバーの venv に必要なパッケージがない | `SPARK_PROFILE_PYTHON` にプロジェクトの venv の Python を指定する |
| `samples` が 0、統計値が `null` | `nvidia-smi` が使えない、または実行が短すぎる | `nvidia-smi` を確認する。`interval_sec` を小さくするか、ベンチマークを長くする |
| 前後の数値のばらつきが大きい | 他の GPU 負荷、温度によるクロック変動 | 同じ条件で 2〜3 回測る。`gpu_status` で開始時の状態をそろえる |

## それでも解決しないとき

1. `tests\e2e_test.py` の出力全体を保存します。
2. VS Code の **MCP: List Servers** → `spark-vibe` → **Show Output** のログを確認します。
3. `server.py` を直接起動して、インポートエラーがないか確かめます。

```powershell
.\.venv\Scripts\python.exe -c "import server; print('ok')"
```

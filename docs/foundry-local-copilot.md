# Foundry Local で GitHub Copilot をローカル推論させる

**日本語** | [English](./foundry-local-copilot.en.md)

VS Code の Copilot Chat と Copilot CLI が使うモデルを、この PC の RTX GPU 上で動く Foundry Local に切り替える手順です。スクリプトは [scripts/foundry-local/](../scripts/foundry-local/) にあります。

## 構成

```text
VS Code Copilot Chat / Copilot CLI
  -> http://127.0.0.1:5274/v1  直列化プロキシ (foundry_serial_proxy.py)
  -> http://127.0.0.1:5273/v1  Foundry Local CLI 0.13.0
  -> qwen2.5-7b-instruct-trtrtx-gpu:2 (NvTensorRTRTXExecutionProvider, RTX GPU)
```

Azure リソースは作成していません。そのため、このエンドポイントでクラウド推論料金はかかりません（予算 10,000 円/月 に対して 0 円）。電気代と、既存の Copilot プランの料金は別にかかります。

## 前提

| 項目 | 内容 |
|---|---|
| Foundry Local | CLI 0.13.0（`foundry.exe` が PATH 上にあること） |
| NVIDIA ランタイム | CUDA 13.4 / cuDNN 9.27 などの ARM64 再頒布 DLL。リポジトリには含めません。既定の場所は `%LOCALAPPDATA%\Programs\FoundryLocal\runtime` です。別の場所に置く場合は `-RuntimeRoot` 引数または環境変数 `FOUNDRY_LOCAL_RUNTIME` で指定します。 |
| Python | プロキシ用の `pythonw.exe`（標準ライブラリのみ使用） |
| PowerShell | 7 以降（`Test-FoundryLocal.ps1` は `Start-ThreadJob` を使います） |

## 使い方

以下のコマンドは、リポジトリのルートで実行します。

1. 起動します。ログオン時の自動起動は登録していないため、Windows を再起動するたびに実行が必要です。

   ```powershell
   pwsh -File scripts\foundry-local\Start-FoundryLocal.ps1
   ```

2. VS Code では、新しいチャットのモデル選択で **Foundry Local → Qwen2.5 7B - Foundry Local** を選びます。一覧の **Other Models** の下に表示されることがあります。見つからない場合は、作業を保存してから VS Code を再読み込みしてください。あわせて、**Configure Tools** で MCP サーバーのツールを外してください（[制約](#制約) の 1 を参照）。
3. Copilot CLI を使う場合は、次のスクリプトを使います。MCP を自動で無効にしてから起動します。

   ```powershell
   pwsh -File scripts\foundry-local\Start-CopilotLocal.ps1
   pwsh -File scripts\foundry-local\Start-CopilotLocal.ps1 -Prompt "質問"
   ```

4. 動作を検証します。合否は機械的に判定され、結果は [bench/results/foundry-local/verification.json](../bench/results/foundry-local/verification.json) に保存されます。

   ```powershell
   pwsh -File scripts\foundry-local\Test-FoundryLocal.ps1
   ```

## 停止

```powershell
foundry model unload qwen2.5-7b-instruct-trtrtx-gpu:2
foundry server stop
```

プロキシを止めるには、タスク マネージャーで `foundry_serial_proxy.py` を実行している `pythonw.exe` を終了します。

## 調査でわかったこと

2026-11-11 時点、Foundry Local CLI 0.13.0 / ORT GenAI 0.18.0 での結果です。

1. **同時リクエストで GPU 推論が失敗する。** 4 件を並列で送ると、全件が `CUDA error in CopyCompletedLocked` または `GenerateNext` で失敗しました。失敗後は再起動するまでデーモンの異常が続き、約 1.9K～8.2K トークンの入力が失敗し続けることがありました。`onnxruntime-genai.dll` のアクセス違反（`0xc0000005`）で `foundrylocald.exe` が落ちることもありました。TRT-RTX 版、CUDA 版、generic-gpu 版のどれでも同じ症状が出て、CPU 版では起きませんでした。Copilot はリクエストを並列に送るため、ポート 5274 の直列化プロキシで 1 件ずつ処理しています。上記のエラーが返ったときは 1 回だけ再試行し、その記録をログに残します。プロキシ経由なら並列 4 件はすべて成功します。
2. **モデルの選定。** `qwen2.5-1.5b` は API テストには通りました。しかし Copilot CLI のエージェントとして使うと `view` ツールを呼び続け、終わりませんでした。`qwen2.5-7b` は同じ条件で最後まで動作し、3 タスク中 2 タスクに正しく答えました（[copilot-verification.json](../bench/results/foundry-local/copilot-verification.json)）。生成速度は約 55 token/s で、23K トークンの入力を約 12 秒で処理します。
3. **コンテキスト上限。** モデルの上限は 32,768 トークンです（`genai_config.json`）。設定は入力 28,672 + 出力 4,096 にしています。出力上限を 4,096 に抑えているのは、同じ文字列を繰り返し出力し始めたときの待ち時間を短くするためです。

## 制約

1. MCP サーバー（Azure、Playwright、Microsoft Docs など）のツール定義を含めると、`static system messages and tool definitions exceed this model's context budget` のエラーになり、応答しません。Copilot 標準のツールだけなら動作します。
2. 7B モデルの品質は、クラウドのモデルには及びません。誤答、回答言語の揺れ（日本語で指示しても中国語やスペイン語で返る）、同じコマンド文字列の繰り返し出力を確認しています。
3. 画像は入力できません。インライン補完（ゴースト テキスト）は、この設定の対象外です。
4. 推論をローカルで行っても、VS Code と Copilot 全体がオフラインで動くわけではありません。サインイン、テレメトリ、拡張機能などは別に通信します。
5. Foundry Local CLI はプレビュー版です。更新したら `Test-FoundryLocal.ps1` を実行し直してください。

## ファイル

| ファイル | 役割 |
|---|---|
| [Start-FoundryLocal.ps1](../scripts/foundry-local/Start-FoundryLocal.ps1) | NVIDIA ランタイムをプロセスの PATH に追加し、サーバー、モデル、プロキシを起動する |
| [Start-CopilotLocal.ps1](../scripts/foundry-local/Start-CopilotLocal.ps1) | ローカルモデルを使い、MCP を無効にして Copilot CLI を起動する |
| [Test-FoundryLocal.ps1](../scripts/foundry-local/Test-FoundryLocal.ps1) | 通常応答、SSE、ツール呼び出しの往復、並列リクエスト、VS Code 設定を検証する |
| [foundry_serial_proxy.py](../scripts/foundry-local/foundry_serial_proxy.py) | 直列化プロキシ（127.0.0.1 でのみ待ち受け）。ログの既定の場所は `%LOCALAPPDATA%\Programs\FoundryLocal\proxy.log`（`FOUNDRY_PROXY_LOG` で変更可能） |
| [copilot-providers.json](../scripts/foundry-local/copilot-providers.json) | Copilot CLI 用のプロバイダー定義（`COPILOT_PROVIDERS_CONFIG`） |
| [verification.json](../bench/results/foundry-local/verification.json) | API の検証結果 |
| [copilot-verification.json](../bench/results/foundry-local/copilot-verification.json) | Copilot CLI エージェントの検証結果 |

## 設定の場所と元に戻す方法

| 対象 | 場所 |
|---|---|
| VS Code のモデル定義 | `%APPDATA%\Code\User\chatLanguageModels.json` の "Foundry Local" プロバイダー。元の設定は同じフォルダーの `chatLanguageModels.json.bak-foundry-*` に保存しています。 |
| Foundry Local の設定 | `%USERPROFILE%\.foundry\config.json`（`server_port` 5273） |
| モデル キャッシュ | `%USERPROFILE%\.foundry\cache\models`。使わない 1.5B モデルは `foundry cache remove qwen2.5-1.5b-instruct-trtrtx-gpu:2 --force` で削除できます。 |

## 参考（一次情報）

- [Foundry Local CLI 0.13.0 リリース](https://github.com/microsoft/Foundry-Local/releases/tag/cli-preview-0.13.0)
- [Foundry Local CLI リファレンス](https://learn.microsoft.com/azure/foundry-local/reference/reference-cli)
- [VS Code: Language models](https://code.visualstudio.com/docs/agent-customization/language-models)
- [NVIDIA CUDA 13.4.1 redistrib manifest](https://developer.download.nvidia.com/compute/cuda/redist/redistrib_13.4.1.json)
- [NVIDIA cuDNN 9.27.0 redistrib manifest](https://developer.download.nvidia.com/compute/cudnn/redist/redistrib_9.27.0.json)

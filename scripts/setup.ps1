<#
.SYNOPSIS
  Surface Laptop Ultra (NVIDIA RTX Spark) + GitHub Copilot Fusion の Vibe Coding 環境をセットアップします。
.DESCRIPTION
  1. Python venv を作成し spark-vibe MCP サーバーの依存関係をインストール
  2. LM Studio サーバーを起動し、ローカルモデル (chat / vision / embedding) を GPU にロード
  3. VS Code (ユーザー mcp.json) と Copilot CLI (~/.copilot/mcp-config.json) に MCP サーバーを登録
  既存設定は *.bak-<timestamp> にバックアップしてからマージします。
#>
param(
    [string]$ChatModel = "qwen/qwen3.5-9b",
    [string]$VisionModel = "google/gemma-4-e4b",
    [string]$EmbedModel = "text-embedding-nomic-embed-text-v1.5",
    # gpu_profile_run が実行できるスクリプト/テストのルート (既定: このプロジェクトのみ)
    [string[]]$ProfileRoots = @(),
    [switch]$SkipModelLoad
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$server = Join-Path $root "server.py"

Write-Host "==> [1/3] Python venv + 依存関係" -ForegroundColor Cyan
if (-not (Test-Path $venvPy)) { python -m venv (Join-Path $root ".venv") }
# Windows on ARM64: cryptography has no Rust/OpenSSL toolchain here, so force prebuilt wheels.
& $venvPy -m pip install --quiet --no-cache-dir --prefer-binary --only-binary cryptography -r (Join-Path $root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed ($LASTEXITCODE)" }

Write-Host "==> [2/3] LM Studio サーバーとローカルモデル (RTX Spark GPU)" -ForegroundColor Cyan
if (-not (Get-Command lms -ErrorAction SilentlyContinue)) { throw "LM Studio CLI (lms) が見つかりません。LM Studio をインストールしてください。" }
lms server start | Out-Null
if (-not $SkipModelLoad) {
    $loaded = (lms ps --json | ConvertFrom-Json).identifier
    foreach ($m in @($ChatModel, $VisionModel, $EmbedModel)) {
        if ($loaded -notcontains $m) { lms load $m --gpu max --identifier $m -y | Out-Null }
    }
    lms ps
}

Write-Host "==> [3/3] MCP サーバー登録 (VS Code / Copilot CLI)" -ForegroundColor Cyan
$stamp = Get-Date -Format "yyyyMMddHHmmss"
$roots = @($root) + @($ProfileRoots | ForEach-Object { (Resolve-Path $_).Path }) | Select-Object -Unique
$envBlock = @{ SPARK_CHAT_MODEL = $ChatModel; SPARK_VISION_MODEL = $VisionModel; SPARK_EMBED_MODEL = $EmbedModel
               SPARK_PROFILE_ROOTS = ($roots -join [IO.Path]::PathSeparator) }

$vscodeCfg = Join-Path $env:APPDATA "Code\User\mcp.json"
$cfg = if (Test-Path $vscodeCfg) { Copy-Item $vscodeCfg "$vscodeCfg.bak-$stamp"; Get-Content $vscodeCfg -Raw | ConvertFrom-Json -AsHashtable } else { @{} }
if (-not $cfg.ContainsKey("servers")) { $cfg["servers"] = @{} }
$cfg["servers"]["spark-vibe"] = @{ type = "stdio"; command = $venvPy; args = @($server); env = $envBlock }
New-Item -ItemType Directory -Force (Split-Path $vscodeCfg) | Out-Null
$cfg | ConvertTo-Json -Depth 20 | Set-Content $vscodeCfg -Encoding utf8

$cliCfg = Join-Path $env:USERPROFILE ".copilot\mcp-config.json"
$cfg = if (Test-Path $cliCfg) { Copy-Item $cliCfg "$cliCfg.bak-$stamp"; Get-Content $cliCfg -Raw | ConvertFrom-Json -AsHashtable } else { @{} }
if (-not $cfg.ContainsKey("mcpServers")) { $cfg["mcpServers"] = @{} }
$cfg["mcpServers"]["spark-vibe"] = @{ type = "stdio"; command = $venvPy; args = @($server); env = $envBlock; tools = @("*") }
New-Item -ItemType Directory -Force (Split-Path $cliCfg) | Out-Null
$cfg | ConvertTo-Json -Depth 20 | Set-Content $cliCfg -Encoding utf8

Write-Host "完了: VS Code / Copilot CLI で 'spark-vibe' MCP サーバーが使えます。モデルピッカーで Copilot Fusion を選択してください。" -ForegroundColor Green

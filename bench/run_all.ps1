<#
.SYNOPSIS
  Re-run every measurement and recording for the three use cases (third-party reproducibility).
.DESCRIPTION
  Requires LM Studio running with the models from scripts/setup.ps1 and spark-vibe registered in
  ~/.copilot/mcp-config.json. Raw data -> bench/results/<uc>/, media -> docs/media/.
#>
param(
    [int]$N = 5,
    [switch]$SkipBench,
    [switch]$SkipRecord
)
$ErrorActionPreference = 'Stop'
$py = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'
Push-Location $PSScriptRoot
try {
    & $py -c 'import imageio_ffmpeg; import playwright'
    if ($LASTEXITCODE) {
        & $py -m pip install -r requirements.txt
        if ($LASTEXITCODE) { throw 'benchmark dependency installation failed' }
    }
    & $py -m playwright install chromium
    if ($LASTEXITCODE) { throw 'Chromium installation failed' }
    if (-not $SkipBench) {
        foreach ($uc in 'uc1', 'uc2', 'uc3') {
            Write-Host "== $uc bench (N=$N)" -ForegroundColor Cyan
            & $py "$($uc)_bench.py" -n $N
            if ($LASTEXITCODE) { throw "$uc bench failed" }
        }
    }
    if (-not $SkipRecord) {
        Write-Host '== recording live demos (do not cover the demo window)' -ForegroundColor Cyan
        & $py record.py uc1 uc2 uc3
        if ($LASTEXITCODE) { throw 'recording failed' }
    }
    & $py report.py
    if ($LASTEXITCODE) { throw 'report generation failed' }
} finally { Pop-Location }

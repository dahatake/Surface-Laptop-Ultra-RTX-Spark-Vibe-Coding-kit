[CmdletBinding()]
param(
    [switch]$Wait,
    # NVIDIA redistributable DLLs are kept outside the repository (license and size).
    [string]$RuntimeRoot = $(if ($env:FOUNDRY_LOCAL_RUNTIME) { $env:FOUNDRY_LOCAL_RUNTIME } `
        else { Join-Path $env:LOCALAPPDATA 'Programs\FoundryLocal\runtime' })
)

$ErrorActionPreference = 'Stop'
$model = 'qwen2.5-7b-instruct-trtrtx-gpu:2'
$runtimePaths = @(
    'cuda_cudart-windows-arm64-13.4.49-archive\bin\arm64'
    'cuda_nvrtc-windows-arm64-13.4.59-archive\bin\arm64'
    'cudnn-windows-arm64-9.27.0.42_cuda13.4-archive\bin\arm64'
    'libcublas-windows-arm64-13.7.0.27-archive\bin\arm64'
    'libcufft-windows-arm64-12.4.0.34-archive\bin\arm64'
) | ForEach-Object {
    $path = Join-Path $RuntimeRoot $_
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw "Required NVIDIA runtime directory is missing: $path"
    }
    $path
}
$env:PATH = ($runtimePaths -join ';') + ';' + $env:PATH
$foundry = (Get-Command foundry.exe -ErrorAction Stop).Source

& $foundry server start --port 5273 --idle-timeout 0
if ($LASTEXITCODE -ne 0) { throw "Foundry server start failed ($LASTEXITCODE)." }
& $foundry model load $model
if ($LASTEXITCODE -ne 0) { throw "Foundry model load failed ($LASTEXITCODE)." }

$status = & $foundry server status --output json
if ($LASTEXITCODE -ne 0) { throw "Foundry server status failed ($LASTEXITCODE)." }
$status = $status | ConvertFrom-Json
if (-not $status.running -or $status.state -ne 'ready') {
    throw 'Foundry daemon is not ready.'
}
$models = Invoke-RestMethod 'http://127.0.0.1:5273/v1/models' -TimeoutSec 15
if ($model -notin $models.data.id) { throw "The API does not advertise $model." }

# Foundry Local 0.13.0 fails on concurrent GPU requests; Copilot uses the
# serializing proxy on port 5274 instead of calling port 5273 directly.
$proxyUp = $false
try { $null = Invoke-RestMethod 'http://127.0.0.1:5274/v1/models' -TimeoutSec 5; $proxyUp = $true } catch { }
if (-not $proxyUp) {
    $pythonw = (Get-Command pythonw.exe -ErrorAction Stop).Source
    Start-Process -FilePath $pythonw -ArgumentList ('"{0}"' -f (Join-Path $PSScriptRoot 'foundry_serial_proxy.py')) `
        -WindowStyle Hidden | Out-Null
    $deadline = (Get-Date).AddSeconds(15)
    while (-not $proxyUp -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        try { $null = Invoke-RestMethod 'http://127.0.0.1:5274/v1/models' -TimeoutSec 5; $proxyUp = $true } catch { }
    }
    if (-not $proxyUp) { throw 'The serializing proxy on port 5274 did not start.' }
}
Write-Host "Foundry Local ready: http://127.0.0.1:5273/v1/ ($model)"
Write-Host 'Copilot endpoint (serializing proxy): http://127.0.0.1:5274/v1/'
Write-Host 'VS Code Chat model: Foundry Local / Qwen2.5 7B - Foundry Local'
if ($Wait) { Wait-Process -Id $status.pid }

[CmdletBinding()]
param(
    [string]$Prompt,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$CopilotArgs
)

# Launches GitHub Copilot CLI on the Foundry Local model.
# All MCP servers are disabled for this session only: their tool definitions
# exceed the 32K context of the local model ("static system messages and tool
# definitions exceed this model's context budget").

$ErrorActionPreference = 'Stop'
$model = 'qwen2.5-7b-instruct-trtrtx-gpu:2'

$ready = $false
try {
    $models = Invoke-RestMethod 'http://127.0.0.1:5274/v1/models' -TimeoutSec 5
    $ready = $model -in $models.data.id
} catch { }
if (-not $ready) { & (Join-Path $PSScriptRoot 'Start-FoundryLocal.ps1') }

$env:COPILOT_PROVIDERS_CONFIG = Join-Path $PSScriptRoot 'copilot-providers.json'

$disable = @('--disable-builtin-mcps')
foreach ($line in (& copilot mcp list 2>$null)) {
    if ($line -match '^\s+(\S+)\s+\((local|http|sse|remote)\)') {
        $disable += @('--disable-mcp-server', $Matches[1])
    }
}

$arguments = @('--model', "foundry-local/$model") + $disable + @($CopilotArgs | Where-Object { $_ })
if ($Prompt) { $arguments = @('-p', $Prompt) + $arguments }
& copilot @arguments
exit $LASTEXITCODE

[CmdletBinding()]
param([string]$ResultPath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\bench\results\foundry-local\verification.json')))

$ErrorActionPreference = 'Stop'
$model = 'qwen2.5-7b-instruct-trtrtx-gpu:2'
$endpoint = 'http://127.0.0.1:5274/v1/chat/completions'
$checks = [Collections.Generic.List[object]]::new()

function Invoke-Completion {
    param([hashtable]$Body)
    $Body.temperature = 0.6
    $Body.top_p = 0.95
    Invoke-RestMethod -Uri $endpoint -Method Post -ContentType 'application/json; charset=utf-8' `
        -Body ([Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 20 -Compress))) `
        -TimeoutSec 180
}

$clock = [Diagnostics.Stopwatch]::StartNew()
$answer = Invoke-Completion @{
    model = $model
    messages = @(
        @{ role = 'system'; content = 'You are a helpful assistant. Follow the requested output format exactly.' }
        @{ role = 'user'; content = 'What is 19 + 23? Reply with only the integer.' }
    )
    max_tokens = 1024
    temperature = 0
}
$clock.Stop()
if ($answer.choices[0].message.content.Trim() -ne '42') { throw 'Arithmetic response was not 42.' }
$checks.Add(@{
    test = 'chat-completions'
    passed = $true
    response = $answer.choices[0].message.content
    seconds = $clock.Elapsed.TotalSeconds
    usage = $answer.usage
})

$body = @{
    model = $model
    messages = @(@{ role = 'user'; content = 'Reply with exactly this text: LOCAL_STREAM_OK' })
    max_tokens = 1024
    temperature = 0
    stream = $true
}
$stream = Invoke-WebRequest -Uri $endpoint -Method Post -ContentType 'application/json' `
    -Body ($body | ConvertTo-Json -Depth 10 -Compress) -TimeoutSec 180
$content = if ($stream.Content -is [byte[]]) {
    [Text.Encoding]::UTF8.GetString($stream.Content)
} else { [string]$stream.Content }
$text = ''
$done = $false
foreach ($line in ($content -split '\r?\n')) {
    if (-not $line.StartsWith('data:')) { continue }
    $data = $line.Substring(5).Trim()
    if ($data -eq '[DONE]') { $done = $true; continue }
    if ($data) {
        $chunk = $data | ConvertFrom-Json
        $text += $chunk.choices[0].delta.content
    }
}
if (-not $done -or $text.Trim() -ne 'LOCAL_STREAM_OK') {
    throw "Streaming check failed (done=$done, text=$text)."
}
$checks.Add(@{ test = 'sse-streaming'; passed = $true; response = $text; done = $done })

$messages = @(
    @{ role = 'system'; content = 'Use the add function for arithmetic. After its result, reply with only the integer result.' }
    @{ role = 'user'; content = 'Use the add function to add 19 and 23.' }
)
$tool = Invoke-Completion @{
    model = $model
    messages = $messages
    tools = @(@{
        type = 'function'
        function = @{
            name = 'add'
            description = 'Add two integers.'
            parameters = @{
                type = 'object'
                properties = @{ a = @{ type = 'integer' }; b = @{ type = 'integer' } }
                required = @('a', 'b')
            }
        }
    })
    tool_choice = 'auto'
    max_tokens = 2048
    temperature = 0
}
$calls = @($tool.choices[0].message.tool_calls)
if ($calls.Count -ne 1 -or $calls[0].function.name -ne 'add' -or -not $calls[0].id) {
    throw 'The model did not return one structured add tool call.'
}
$arguments = $calls[0].function.arguments | ConvertFrom-Json
if ($arguments.a -ne 19 -or $arguments.b -ne 23) { throw 'Tool arguments were incorrect.' }
$messages += @{ role = 'assistant'; content = $null; tool_calls = $calls }
$messages += @{ role = 'tool'; tool_call_id = $calls[0].id; content = '42' }
$result = Invoke-Completion @{
    model = $model
    messages = $messages
    max_tokens = 1024
    temperature = 0
}
if ($result.choices[0].message.content.Trim() -ne '42') { throw 'Tool round-trip response was not 42.' }
$checks.Add(@{
    test = 'tool-call-round-trip'
    passed = $true
    function = $calls[0].function
    response = $result.choices[0].message.content
})

$parallel = 1..4 | ForEach-Object {
    $size = 300 * $_
    Start-ThreadJob -ArgumentList $endpoint, $model, $size -ScriptBlock {
        param($endpoint, $model, $size)
        $text = "Request $([guid]::NewGuid()) " + ('The quick brown fox jumps over the lazy dog. ' * $size)
        $body = @{
            model = $model
            max_tokens = 16
            temperature = 0
            messages = @(@{ role = 'user'; content = "$text`nWhat is 19 + 23? Reply with only the integer." })
        } | ConvertTo-Json -Depth 5 -Compress
        (Invoke-RestMethod -Uri $endpoint -Method Post -ContentType 'application/json' -Body $body `
            -TimeoutSec 600).choices[0].message.content.Trim()
    }
}
$parallelAnswers = @($parallel | Wait-Job | Receive-Job -ErrorAction Stop)
$parallel | Remove-Job
if ($parallelAnswers.Count -ne 4 -or @($parallelAnswers | Where-Object { $_ -ne '42' }).Count) {
    throw "Concurrent requests through the proxy failed: $($parallelAnswers -join ', ')"
}
$checks.Add(@{ test = 'concurrent-requests-via-proxy'; passed = $true; response = $parallelAnswers })

$configPath = Join-Path $env:APPDATA 'Code\User\chatLanguageModels.json'
$providers = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$configured = @($providers | Where-Object { $_.vendor -eq 'customendpoint' -and $_.name -eq 'Foundry Local' })
if ($configured.Count -ne 1) { throw 'Expected exactly one Foundry Local provider in VS Code.' }
$configuredModel = @($configured[0].models | Where-Object id -eq $model)
if ($configuredModel.Count -ne 1 -or $configuredModel[0].url -ne $endpoint `
    -or -not $configuredModel[0].toolCalling -or -not $configuredModel[0].streaming `
    -or $configuredModel[0].thinking `
    -or $configuredModel[0].contextWindow -ne 32768 `
    -or ($configuredModel[0].maxInputTokens + $configuredModel[0].maxOutputTokens) -gt 32768) {
    throw 'VS Code model configuration does not match the verified API capabilities.'
}
$checks.Add(@{ test = 'vscode-provider-configuration'; passed = $true })

$statusJson = & foundry.exe status --output json
if ($LASTEXITCODE -ne 0) { throw "Foundry status failed ($LASTEXITCODE)." }
$report = @{
    timestamp = [DateTimeOffset]::Now.ToString('o')
    endpoint = $endpoint
    model = $model
    checks = $checks.ToArray()
    foundry = ($statusJson | ConvertFrom-Json)
}
$report | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $ResultPath -Encoding utf8
$checks.ToArray() | ForEach-Object { [pscustomobject]$_ } | Format-Table test, passed
Write-Host "Evidence saved to $ResultPath"

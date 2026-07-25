#Requires -Version 5.1

$ErrorActionPreference = "Stop"

# ============================================================
# HARD-CODE YOUR NARAROUTER API KEY HERE
# ============================================================
$NaraApiKey = "sk-nry-OclNeHh1fqJk04syDWj9LR6ZBdwiiDgZv0gnBCpEZKg"
$Model = "kimi-k2.7-code-free"
$BaseUrl = "https://router.bynara.id"

if ([string]::IsNullOrWhiteSpace($NaraApiKey)) {
    throw "NaraRouter API key is empty."
}

if ($NaraApiKey -like "*REPLACE_WITH_YOUR_REAL_API_KEY*") {
    throw "Replace the placeholder API key inside this PS1 file first."
}

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    throw @"
Claude Code CLI was not found in PATH.

Install it with:
npm install -g @anthropic-ai/claude-code
"@
}

# Preserve existing values so they can be restored after Claude exits.
$PreviousEnvironment = @{
    ANTHROPIC_BASE_URL             = $env:ANTHROPIC_BASE_URL
    ANTHROPIC_AUTH_TOKEN           = $env:ANTHROPIC_AUTH_TOKEN
    ANTHROPIC_API_KEY              = $env:ANTHROPIC_API_KEY
    ANTHROPIC_MODEL                = $env:ANTHROPIC_MODEL
    ANTHROPIC_DEFAULT_OPUS_MODEL   = $env:ANTHROPIC_DEFAULT_OPUS_MODEL
    ANTHROPIC_DEFAULT_SONNET_MODEL = $env:ANTHROPIC_DEFAULT_SONNET_MODEL
    ANTHROPIC_DEFAULT_HAIKU_MODEL  = $env:ANTHROPIC_DEFAULT_HAIKU_MODEL
    ANTHROPIC_REQUEST_TIMEOUT_MS   = $env:ANTHROPIC_REQUEST_TIMEOUT_MS
}

try {
    # These variables exist only in the current PowerShell process
    # and child processes started from it.
    $env:ANTHROPIC_BASE_URL = $BaseUrl
    $env:ANTHROPIC_AUTH_TOKEN = $NaraApiKey

    # Set API_KEY as well for routers that expect Anthropic's x-api-key header.
    # Claude Code normally prioritizes AUTH_TOKEN for custom gateways.
    $env:ANTHROPIC_API_KEY = $NaraApiKey

    # Force every Claude Code model tier to use the selected NaraRouter model.
    $env:ANTHROPIC_MODEL = $Model
    $env:ANTHROPIC_DEFAULT_OPUS_MODEL = $Model
    $env:ANTHROPIC_DEFAULT_SONNET_MODEL = $Model
    $env:ANTHROPIC_DEFAULT_HAIKU_MODEL = $Model

    # Five-minute request timeout for long coding-agent operations.
    $env:ANTHROPIC_REQUEST_TIMEOUT_MS = "300000"

    Write-Host ""
    Write-Host "Starting Claude Code with NaraRouter..."
    Write-Host "Model:    $Model"
    Write-Host "Base URL: $BaseUrl"
    Write-Host ""

    & claude @args

    $ClaudeExitCode = $LASTEXITCODE
}
finally {
    # Restore the environment that existed before this script was executed.
    foreach ($VariableName in $PreviousEnvironment.Keys) {
        $PreviousValue = $PreviousEnvironment[$VariableName]

        if ($null -eq $PreviousValue) {
            Remove-Item "Env:$VariableName" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item "Env:$VariableName" -Value $PreviousValue
        }
    }

    # Remove plaintext key from the PowerShell variable.
    $NaraApiKey = $null
}

exit $ClaudeExitCode
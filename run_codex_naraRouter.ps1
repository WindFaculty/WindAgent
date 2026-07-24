#Requires -Version 5.1

$ErrorActionPreference = "Stop"

# ============================================================
# HARD-CODE YOUR NARAROUTER API KEY HERE
# ============================================================
$NaraApiKey = "sk-nry-OclNeHh1fqJk04syDWj9LR6ZBdwiiDgZv0gnBCpEZKg"

$Model = "kimi-k2.7-code-free"
$BaseUrl = "https://router.bynara.id/v1"

if ([string]::IsNullOrWhiteSpace($NaraApiKey)) {
    throw "NaraRouter API key is empty."
}

if ($NaraApiKey -like "*REPLACE_WITH_YOUR_REAL_API_KEY*") {
    throw "Replace the placeholder API key inside this PS1 file first."
}

# Environment variable exists only in this PowerShell process.
# It is removed when this PowerShell window is closed.
$env:NARA_API_KEY = $NaraApiKey

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw "Codex CLI was not found in PATH. Run: npm install -g @openai/codex"
}

Write-Host ""
Write-Host "Starting Codex with NaraRouter..."
Write-Host "Model:    $Model"
Write-Host "Base URL: $BaseUrl"
Write-Host ""

$CodexArguments = @(
    "-c", "model=`"$Model`""
    "-c", "model_provider=`"nararouter`""
    "-c", "model_providers.nararouter.name=`"NaraRouter`""
    "-c", "model_providers.nararouter.base_url=`"$BaseUrl`""
    "-c", "model_providers.nararouter.env_key=`"NARA_API_KEY`""
    "-c", "model_providers.nararouter.wire_api=`"responses`""
    "-c", "model_providers.nararouter.request_max_retries=4"
    "-c", "model_providers.nararouter.stream_max_retries=8"
    "-c", "model_providers.nararouter.stream_idle_timeout_ms=300000"
)

& codex @CodexArguments

$CodexExitCode = $LASTEXITCODE

# Remove the plaintext values after Codex exits.
$env:NARA_API_KEY = $null
$NaraApiKey = $null

exit $CodexExitCode
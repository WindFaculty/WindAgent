#Requires -Version 5.1

$ErrorActionPreference = "Stop"

$NaraApiKey = "sk-nry-"
$Model = "deepseek/deepseek-v4-flash-0731"
$BaseUrl = "https://openrouter.ai/api"


Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ------------------------------------------------------------
# Validate configuration
# ------------------------------------------------------------

if ([string]::IsNullOrWhiteSpace($NaraApiKey)) {
    throw "NaraRouter API key is empty."
}

if ($NaraApiKey -like "*REPLACE_WITH_YOUR_REAL_API_KEY*") {
    throw "Replace the placeholder API key inside this PS1 file first."
}

if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
    throw "NaraRouter Base URL is empty."
}

if ([string]::IsNullOrWhiteSpace($Model)) {
    throw "NaraRouter model is empty."
}


# ------------------------------------------------------------
# Check Codex CLI
# ------------------------------------------------------------

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw @"
Codex CLI was not found in PATH.

Install it with:

npm install -g @openai/codex

Then restart PowerShell and run this script again.
"@
}


# ------------------------------------------------------------
# Preserve current process environment
# ------------------------------------------------------------

$PreviousEnvironment = @{
    NARA_API_KEY = $env:NARA_API_KEY
}

$CodexExitCode = 1


try {

    # --------------------------------------------------------
    # Temporary environment
    #
    # $env: only modifies the current PowerShell process
    # and child processes created from it.
    #
    # It does NOT modify User or Machine environment variables.
    # --------------------------------------------------------

    $env:NARA_API_KEY = $NaraApiKey


    # --------------------------------------------------------
    # Runtime-only Codex configuration
    #
    # These values are passed with -c.
    # Nothing is written to ~/.codex/config.toml.
    #
    # Codex custom provider:
    #   provider = nara
    #   API key  = NARA_API_KEY
    #   protocol = OpenAI Responses API
    # --------------------------------------------------------

    $CodexRuntimeConfig = @(
        "-c"
        "model=$Model"

        "-c"
        "model_provider=nara"

        "-c"
        "model_providers.nara.name=NaraRouter"

        "-c"
        "model_providers.nara.base_url=$BaseUrl"

        "-c"
        "model_providers.nara.env_key=NARA_API_KEY"

        "-c"
        "model_providers.nara.wire_api=responses"

        "-c"
        "model_providers.nara.requires_openai_auth=false"

        "-c"
        "model_providers.nara.request_max_retries=3"

        # 5-minute streaming idle timeout.
        "-c"
        "model_providers.nara.stream_idle_timeout_ms=300000"
    )


    # --------------------------------------------------------
    # Information
    # --------------------------------------------------------

    Write-Host ""
    Write-Host "Starting Codex CLI with NaraRouter..."
    Write-Host ""
    Write-Host "Model:    $Model"
    Write-Host "Provider: NaraRouter"
    Write-Host "Base URL: $BaseUrl"
    Write-Host "Wire API: responses"
    Write-Host ""
    Write-Host "Configuration scope: CURRENT CODEX PROCESS ONLY"
    Write-Host ""


    # --------------------------------------------------------
    # Start Codex
    #
    # @args forwards arguments supplied to this PS1 file.
    #
    # Examples:
    #
    #   .\codex-nara.ps1 --full-auto
    #
    #   .\codex-nara.ps1 -C D:\code_ca_nhan\WindAgent
    #
    # --------------------------------------------------------

    & codex @CodexRuntimeConfig @args

    $CodexExitCode = $LASTEXITCODE
}
finally {

    # --------------------------------------------------------
    # Restore environment
    # --------------------------------------------------------

    foreach ($VariableName in $PreviousEnvironment.Keys) {

        $PreviousValue = $PreviousEnvironment[$VariableName]

        if ($null -eq $PreviousValue) {
            Remove-Item "Env:$VariableName" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item "Env:$VariableName" -Value $PreviousValue
        }
    }


    # --------------------------------------------------------
    # Remove plaintext API key from PowerShell variable
    # --------------------------------------------------------

    $NaraApiKey = $null
}


exit $CodexExitCode
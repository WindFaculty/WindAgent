# Package Isolation Test Script for windagent_api (Phase 2)
# Verifies that windagent_api can be imported and bootstrapped in a clean isolated virtual environment.

$ErrorActionPreference = "Stop"

$workspaceRoot = Get-Location
$tempVenv = Join-Path $workspaceRoot ".venv_test_api_isolation"

function Assert-NativeSuccess {
    param([Parameter(Mandatory = $true)][string]$Step)

    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

Write-Host "==> Creating clean virtual environment at $tempVenv..." -ForegroundColor Cyan
if (Test-Path $tempVenv) {
    Remove-Item -Recurse -Force $tempVenv
}

uv venv $tempVenv
Assert-NativeSuccess "Creating API isolation virtual environment"
$pythonBin = Join-Path $tempVenv "Scripts\python.exe"

try {
    Write-Host "==> Installing windagent-api and its workspace dependencies into isolated venv..." -ForegroundColor Cyan
    uv pip install --python $pythonBin -e "$workspaceRoot\apps\api"
    Assert-NativeSuccess "Installing windagent-api"

    Write-Host "==> Testing windagent_api import & bootstrap in isolation..." -ForegroundColor Cyan

    $cleanTestCode = "import asyncio`nfrom windagent_api.composition import ApplicationContainer`nasync def test_smoke():`n    container = ApplicationContainer(db_url='sqlite+aiosqlite:///:memory:')`n    await container.bootstrap()`n    assert container.is_initialized`n    await container.shutdown()`n    print('[PASS] API isolated bootstrap & shutdown clean')`nasyncio.run(test_smoke())"

    & $pythonBin -c $cleanTestCode
    Assert-NativeSuccess "Bootstrapping windagent_api in isolation"
}
finally {
    Write-Host "==> Cleaning up isolated venv..." -ForegroundColor Cyan
    if (Test-Path $tempVenv) {
        Remove-Item -Recurse -Force $tempVenv
    }
}

Write-Host "==> API Package Isolation Test: SUCCESS" -ForegroundColor Green

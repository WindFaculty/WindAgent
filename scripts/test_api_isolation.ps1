# Package Isolation Test Script for windagent_api (Phase 2)
# Verifies that windagent_api can be imported and bootstrapped in a clean isolated virtual environment.

$ErrorActionPreference = "Stop"

$workspaceRoot = Get-Location
$tempVenv = Join-Path $workspaceRoot ".venv_test_api_isolation"

Write-Host "==> Creating clean virtual environment at $tempVenv..." -ForegroundColor Cyan
if (Test-Path $tempVenv) {
    Remove-Item -Recurse -Force $tempVenv
}

uv venv $tempVenv
$pythonBin = Join-Path $tempVenv "Scripts\python.exe"

Write-Host "==> Installing windagent-api and its workspace dependencies into isolated venv..." -ForegroundColor Cyan
uv pip install --python $pythonBin -e "$workspaceRoot\apps\api"

Write-Host "==> Testing windagent_api import & bootstrap in isolation..." -ForegroundColor Cyan
$testCode = @"
import asyncio
from windagent_api.composition import ApplicationContainer

async def test_smoke():
    container = ApplicationContainer(db_url="sqlite+aiosqlite:///:memory:")
    await container.bootstrap()
    assert container.is_initialized
    await container.shutdown()
    print("[PASS] API isolated bootstrap & shutdown clean")

asyncio.run(test_smoke())
"@

# Replace double quotes in here-string Python code before passing to python -c
$cleanTestCode = "import asyncio`nfrom windagent_api.composition import ApplicationContainer`nasync def test_smoke():`n    container = ApplicationContainer(db_url='sqlite+aiosqlite:///:memory:')`n    await container.bootstrap()`n    assert container.is_initialized`n    await container.shutdown()`n    print('[PASS] API isolated bootstrap & shutdown clean')`nasyncio.run(test_smoke())"

& $pythonBin -c $cleanTestCode

Write-Host "==> Cleaning up isolated venv..." -ForegroundColor Cyan
Remove-Item -Recurse -Force $tempVenv

Write-Host "==> API Package Isolation Test: SUCCESS" -ForegroundColor Green

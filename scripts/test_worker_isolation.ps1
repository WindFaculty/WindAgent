# Package Isolation Test Script for windagent_worker (Phase 2)
# Verifies that windagent_worker can be imported and bootstrapped in a clean isolated virtual environment.

$ErrorActionPreference = "Stop"

$workspaceRoot = Get-Location
$tempVenv = Join-Path $workspaceRoot ".venv_test_worker_isolation"

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
Assert-NativeSuccess "Creating Worker isolation virtual environment"
$pythonBin = Join-Path $tempVenv "Scripts\python.exe"

try {
    Write-Host "==> Installing windagent-worker and its workspace dependencies into isolated venv..." -ForegroundColor Cyan
    uv pip install --python $pythonBin -e "$workspaceRoot\apps\worker"
    Assert-NativeSuccess "Installing windagent-worker"

    Write-Host "==> Testing windagent_worker import & bootstrap in isolation..." -ForegroundColor Cyan
    $cleanTestCode = "import asyncio`nfrom windagent_worker.composition import WorkerContainer`nfrom windagent_worker.runner import ProductionWorker`nasync def test_smoke():`n    container = WorkerContainer(db_url='sqlite+aiosqlite:///:memory:')`n    await container.bootstrap()`n    assert container.is_initialized`n    worker = ProductionWorker(name='isolated-test', worker_container=container)`n    await worker.start()`n    assert worker.is_ready`n    await worker.stop()`n    await container.shutdown()`n    print('[PASS] Worker isolated bootstrap & runner clean')`nasyncio.run(test_smoke())"

    & $pythonBin -c $cleanTestCode
    Assert-NativeSuccess "Bootstrapping windagent_worker in isolation"
}
finally {
    Write-Host "==> Cleaning up isolated venv..." -ForegroundColor Cyan
    if (Test-Path $tempVenv) {
        Remove-Item -Recurse -Force $tempVenv
    }
}

Write-Host "==> Worker Package Isolation Test: SUCCESS" -ForegroundColor Green

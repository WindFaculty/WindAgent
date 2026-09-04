# Run every Phase 1 gate in order.  Stops on the first failure.
# Usage:  pwsh scripts/run_gates.ps1   (or:  powershell -File scripts/run_gates.ps1)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Invoke-Gate($name, $body) {
    Write-Host ""
    Write-Host "==== $name ====" -ForegroundColor Cyan
    & $body
    if ($LASTEXITCODE -ne 0) {
        Write-Host "GATE FAILED: $name" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "PASS: $name" -ForegroundColor Green
}

Invoke-Gate "uv sync" { uv sync --all-groups }
Invoke-Gate "phase0 manifests" { uv run python scripts/validate_phase0_manifests.py }
Invoke-Gate "ruff" { uv run ruff check . }
Invoke-Gate "mypy (typecheck)" { uv run mypy }
Invoke-Gate "pytest" { uv run pytest }
Invoke-Gate "frontend typecheck" { Push-Location frontend; npm run typecheck; Pop-Location }
Invoke-Gate "frontend test" { Push-Location frontend; npm test; Pop-Location }
Invoke-Gate "frontend build" { Push-Location frontend; npm run build; Pop-Location }

Write-Host ""
Write-Host "ALL PHASE 0-10 LOCAL GATES PASSED" -ForegroundColor Green

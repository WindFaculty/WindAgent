<#
.SYNOPSIS
    scripts/dev_backend.ps1 - Khoi chay FastAPI backend (WindAgent).

.DESCRIPTION
    1. Tim `uv` (uu tien PATH, fallback %USERPROFILE%\.local\bin).
    2. Kiem tra apps/backend/pyproject.toml ton tai.
    3. Tu dong chay `uv sync` neu .venv chua co hoac lock file moi hon.
    4. Xuat bien moi truong (mock / real), khoi dong uvicorn --reload.
    5. Log dong thoi ra console va artifacts/logs/backend.log.
    6. Ctrl+C don dep sach.

.PARAMETER Port
    Cong HTTP cho uvicorn. Mac dinh: 8765.

.PARAMETER BindHost
    Dia chi bind. Mac dinh: 127.0.0.1.

.PARAMETER Mock
    Dung WINDAGENT_MODEL_BACKEND=mock (khong can Ollama). Mac dinh: $true.

.PARAMETER NoSync
    Bo qua buoc `uv sync` (khi deps da cai xong).

.PARAMETER LogsDir
    Thu muc ghi log. Mac dinh: <repo>/artifacts/logs.
#>
[CmdletBinding()]
param(
    [int]    $Port      = 8765,
    [string] $BindHost  = "127.0.0.1",
    [switch] $Mock      = $true,
    [switch] $NoSync,
    [string] $LogsDir   = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# UTF-8 console (tieng Viet khong bi vo tren PS 5.1)
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding           = [System.Text.Encoding]::UTF8
} catch { }

# --- Duong dan ---
$RepoRoot   = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $RepoRoot "apps\backend"
$LogsPath   = if ($LogsDir) { $LogsDir } else { Join-Path $RepoRoot "artifacts\logs" }
$LogFile    = Join-Path $LogsPath "backend.log"

# --- Kiem tra thu muc backend ---
if (-not (Test-Path $BackendDir)) {
    Write-Host "[backend] FAIL: Khong tim thay apps/backend" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $BackendDir "pyproject.toml"))) {
    Write-Host "[backend] FAIL: Thieu apps/backend/pyproject.toml" -ForegroundColor Red
    exit 1
}

# --- Tim uv ---
function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:LOCALAPPDATA\Programs\uv\uv.exe",
        "$env:LOCALAPPDATA\uv\uv.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    return $null
}

$UvPath = Find-Uv
if (-not $UvPath) {
    Write-Host "[backend] FAIL: Chua cai uv." -ForegroundColor Red
    Write-Host "  Cai bang: irm https://astral.sh/uv/install.ps1 | iex" -ForegroundColor Yellow
    exit 1
}
Write-Host "[backend] uv: $UvPath" -ForegroundColor DarkGray

# --- Tao thu muc log ---
if (-not (Test-Path $LogsPath)) {
    New-Item -ItemType Directory -Path $LogsPath -Force | Out-Null
}
Write-Host "[backend] Log: $LogFile" -ForegroundColor DarkGray

# --- uv sync neu can ---
$venvDir  = Join-Path $BackendDir ".venv"
$lockFile = Join-Path $BackendDir "uv.lock"
$pyproj   = Join-Path $BackendDir "pyproject.toml"

$needSync = -not (Test-Path $venvDir)
if (-not $needSync -and (Test-Path $lockFile)) {
    $needSync = (Get-Item $lockFile).LastWriteTime -gt (Get-Item $venvDir).LastWriteTime
}
if (-not $needSync -and (Test-Path $pyproj)) {
    $needSync = (Get-Item $pyproj).LastWriteTime -gt (Get-Item $venvDir).LastWriteTime
}

if (-not $NoSync -and $needSync) {
    Write-Host "[backend] Dong bo dependencies (uv sync --group dev)..." -ForegroundColor Cyan
    Push-Location $BackendDir
    try {
        & $UvPath sync --group dev
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[backend] FAIL: uv sync that bai (exit $LASTEXITCODE)" -ForegroundColor Red
            exit 1
        }
    } finally { Pop-Location }
} else {
    Write-Host "[backend] uv sync: bo qua (deps da san sang)" -ForegroundColor DarkGray
}

# --- Bien moi truong ---
if (-not $env:WINDAGENT_DB_URL) {
    $env:WINDAGENT_DB_URL = "sqlite+aiosqlite:///$BackendDir\windagent.db"
}
if ($Mock) {
    $env:WINDAGENT_MODEL_BACKEND = "mock"
    $env:WINDAGENT_MOCK_GUI      = "1"
    Write-Host "[backend] Mode: MOCK  (model=mock, gui=mock)" -ForegroundColor Yellow
} else {
    Write-Host "[backend] Mode: REAL  (Ollama + PyAutoGUI)" -ForegroundColor Green
}

# --- Khoi dong uvicorn ---
Write-Host ""
Write-Host "[backend] =====================================================" -ForegroundColor Cyan
Write-Host "[backend]  URL     : http://${BindHost}:${Port}" -ForegroundColor Cyan
Write-Host "[backend]  Swagger : http://${BindHost}:${Port}/docs" -ForegroundColor Cyan
Write-Host "[backend]  Log     : $LogFile" -ForegroundColor Cyan
Write-Host "[backend]  Tail    : Get-Content '$LogFile' -Wait" -ForegroundColor DarkGray
Write-Host "[backend]  Dung    : Ctrl+C" -ForegroundColor DarkGray
Write-Host "[backend] =====================================================" -ForegroundColor Cyan
Write-Host ""

Push-Location $BackendDir
$oldErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    & $UvPath run uvicorn main:app `
        --host $BindHost `
        --port $Port `
        --reload `
        2>&1 | Tee-Object -FilePath $LogFile
} finally {
    $ErrorActionPreference = $oldErrorActionPreference
    Pop-Location
    Write-Host "`n[backend] Da tat uvicorn." -ForegroundColor DarkGray
}

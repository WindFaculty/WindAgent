<#
.SYNOPSIS
    scripts/dev_api.ps1 - Khoi chay WindAgent Architecture V2 API.

.DESCRIPTION
    1. Tim `uv` (uu tien PATH, fallback %USERPROFILE%\.local\bin).
    2. Kiem tra root workspace va apps/api/pyproject.toml.
    3. Dong bo package windagent_api trong root workspace.
    4. Xuat bien moi truong (mock / real), khoi dong uvicorn --reload.
    5. Log dong thoi ra console va artifacts/logs/api.log.
    6. Ctrl+C don dep sach.

.PARAMETER Port
    Cong HTTP cho API. Mac dinh: 8765.

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
$ApiManifest = Join-Path $RepoRoot "apps\api\pyproject.toml"
$RootManifest = Join-Path $RepoRoot "pyproject.toml"
$RootLock = Join-Path $RepoRoot "uv.lock"
$LogsPath   = if ($LogsDir) { $LogsDir } else { Join-Path $RepoRoot "artifacts\logs" }
$LogFile    = Join-Path $LogsPath "api.log"

# --- Kiem tra canonical workspace ---
foreach ($requiredPath in @($ApiManifest, $RootManifest, $RootLock)) {
    if (-not (Test-Path $requiredPath)) {
        Write-Host "[api] FAIL: Thieu $requiredPath" -ForegroundColor Red
        exit 1
    }
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
    Write-Host "[api] FAIL: Chua cai uv." -ForegroundColor Red
    Write-Host "  Cai bang: irm https://astral.sh/uv/install.ps1 | iex" -ForegroundColor Yellow
    exit 1
}
Write-Host "[api] uv: $UvPath" -ForegroundColor DarkGray

# --- Tao thu muc log ---
if (-not (Test-Path $LogsPath)) {
    New-Item -ItemType Directory -Path $LogsPath -Force | Out-Null
}
Write-Host "[api] Log: $LogFile" -ForegroundColor DarkGray

# --- uv sync canonical API package ---
if (-not $NoSync) {
    Write-Host "[api] Dong bo windagent_api va workspace dependencies..." -ForegroundColor Cyan
    Push-Location $RepoRoot
    try {
        & $UvPath sync --package windagent_api
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[api] FAIL: uv sync that bai (exit $LASTEXITCODE)" -ForegroundColor Red
            exit 1
        }
    } finally { Pop-Location }
} else {
    Write-Host "[api] uv sync: bo qua theo -NoSync" -ForegroundColor DarkGray
}

# --- Bien moi truong ---
if (-not $env:WINDAGENT_DATABASE_URL) {
    $DatabasePath = (Join-Path $RepoRoot "windagent.db").Replace("\", "/")
    $env:WINDAGENT_DATABASE_URL = "sqlite+aiosqlite:///$DatabasePath"
}
if ($Mock) {
    $env:WINDAGENT_MODEL_BACKEND = "mock"
    $env:WINDAGENT_MOCK_GUI      = "1"
    Write-Host "[api] Mode: MOCK  (model=mock, gui=mock)" -ForegroundColor Yellow
} else {
    Write-Host "[api] Mode: REAL" -ForegroundColor Green
}

# --- Khoi dong uvicorn ---
Write-Host ""
Write-Host "[api] =====================================================" -ForegroundColor Cyan
Write-Host "[api]  URL       : http://${BindHost}:${Port}" -ForegroundColor Cyan
Write-Host "[api]  Liveness  : http://${BindHost}:${Port}/health/live" -ForegroundColor Cyan
Write-Host "[api]  Swagger   : http://${BindHost}:${Port}/docs" -ForegroundColor Cyan
Write-Host "[api]  Database  : $env:WINDAGENT_DATABASE_URL" -ForegroundColor DarkGray
Write-Host "[api]  Log       : $LogFile" -ForegroundColor Cyan
Write-Host "[api]  Tail      : Get-Content '$LogFile' -Wait" -ForegroundColor DarkGray
Write-Host "[api]  Dung      : Ctrl+C" -ForegroundColor DarkGray
Write-Host "[api] =====================================================" -ForegroundColor Cyan
Write-Host ""

Push-Location $RepoRoot
$oldErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    & $UvPath run --package windagent_api uvicorn windagent_api.main:app `
        --host $BindHost `
        --port $Port `
        --reload `
        2>&1 | Tee-Object -FilePath $LogFile
} finally {
    $ErrorActionPreference = $oldErrorActionPreference
    Pop-Location
    Write-Host "`n[api] Da tat uvicorn." -ForegroundColor DarkGray
}

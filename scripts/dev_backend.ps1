<#
scripts/dev_backend.ps1
Phase 9 — Backend launcher cho WindAgent FastAPI sidecar.

Tham số:
  -Port <int>          Port backend (mặc định 8765)
  -Host <string>       Bind host (mặc định 127.0.0.1)
  -Mock                Bật WINDAGENT_MODEL_BACKEND=mock + WINDAGENT_MOCK_GUI=1
  -NoSync              Bỏ qua `uv sync` (dùng khi deps đã cài)
  -LogsDir <path>      Thư mục log (mặc định artifacts/logs)

Hành vi:
  1. Tìm uv (ưu tiên PATH, fallback các đường dẫn thường gặp).
  2. cd apps/backend (tạo nếu chưa có pyproject.toml thì fail rõ).
  3. Nếu chưa có .venv hoặc pyproject.toml/uv.lock mới hơn .venv:
     chạy `uv sync` (cài cả dev group cho pytest).
  4. Khởi động uvicorn trên cổng chỉ định, log ra file + console.
  5. Ctrl+C tắt sạch tiến trình con.
#>
[CmdletBinding()]
param(
    [int]$Port = 8765,
    [string]$BindHost = "127.0.0.1",
    [switch]$Mock = $true,   # Mặc định mock để dev chạy được không cần Ollama
    [switch]$NoSync,
    [string]$LogsDir
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $RepoRoot "apps\backend"
$LogsDirResolved = if ($LogsDir) { $LogsDir } else { Join-Path $RepoRoot "artifacts\logs" }

# PowerShell 5.1 console mặc định cp1252 — set UTF-8 để in đúng tiếng Việt.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

if (-not (Test-Path $BackendDir)) {
    Write-Host "[dev_backend] FAIL: không tìm thấy $BackendDir" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $BackendDir "pyproject.toml"))) {
    Write-Host "[dev_backend] FAIL: thiếu pyproject.toml trong apps/backend" -ForegroundColor Red
    exit 1
}

# --- Tìm uv ---
function Find-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        return (Get-Command uv).Source
    }
    $candidates = @(
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:LOCALAPPDATA\Programs\uv\uv.exe",
        "$env:USERPROFILE\AppData\Local\hermes\hermes-agent\venv\Scripts\uv.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    return $null
}
$UvPath = Find-Uv
if (-not $UvPath) {
    Write-Host "[dev_backend] FAIL: chưa cài uv. Cài bằng: irm https://astral.sh/uv/install.ps1 | iex" -ForegroundColor Red
    exit 1
}
Write-Host "[dev_backend] uv: $UvPath" -ForegroundColor DarkGray

# --- Đảm bảo log dir ---
if (-not (Test-Path $LogsDirResolved)) {
    New-Item -ItemType Directory -Path $LogsDirResolved -Force | Out-Null
}
$LogFile = Join-Path $LogsDirResolved "backend.log"
Write-Host "[dev_backend] log file: $LogFile" -ForegroundColor DarkGray

# --- Đồng bộ deps nếu cần ---
$venvMarker = Join-Path $BackendDir ".venv\.uv-sync-marker"
$lockFile = Join-Path $BackendDir "uv.lock"
$pyproject = Join-Path $BackendDir "pyproject.toml"

$needsSync = $false
if (-not (Test-Path (Join-Path $BackendDir ".venv"))) { $needsSync = $true }
elseif (Test-Path $lockFile) {
    $lockTime = (Get-Item $lockFile).LastWriteTime
    $venvTime = (Get-Item (Join-Path $BackendDir ".venv")).LastWriteTime
    if ($lockTime -gt $venvTime) { $needsSync = $true }
}
elseif (Test-Path $pyproject) {
    $pyTime = (Get-Item $pyproject).LastWriteTime
    $venvTime = (Get-Item (Join-Path $BackendDir ".venv")).LastWriteTime
    if ($pyTime -gt $venvTime) { $needsSync = $true }
}

if (-not $NoSync -and $needsSync) {
    Write-Host "[dev_backend] Đồng bộ deps (uv sync)..." -ForegroundColor Cyan
    Push-Location $BackendDir
    try {
        & $UvPath sync --group dev
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[dev_backend] FAIL: uv sync lỗi" -ForegroundColor Red
            Pop-Location
            exit 1
        }
    } finally {
        Pop-Location
    }
    Get-Date | Out-File -FilePath $venvMarker -Encoding utf8
} else {
    Write-Host "[dev_backend] Bỏ qua uv sync (deps đã sẵn sàng hoặc -NoSync)" -ForegroundColor DarkGray
}

# --- Chạy uvicorn ---
$env:WINDAGENT_DB_URL = if ($env:WINDAGENT_DB_URL) { $env:WINDAGENT_DB_URL } else { "sqlite+aiosqlite:///$BackendDir\windagent.db" }
if ($Mock) {
    $env:WINDAGENT_MODEL_BACKEND = "mock"
    $env:WINDAGENT_MOCK_GUI = "1"
    Write-Host "[dev_backend] Mock mode: WINDAGENT_MODEL_BACKEND=mock, WINDAGENT_MOCK_GUI=1" -ForegroundColor Yellow
}

Write-Host "[dev_backend] Khởi động uvicorn tại http://${BindHost}:${Port}" -ForegroundColor Green
Write-Host "[dev_backend] Tail log: Get-Content '$LogFile' -Wait" -ForegroundColor DarkGray
Write-Host "[dev_backend] Ctrl+C để tắt." -ForegroundColor DarkGray

Push-Location $BackendDir
try {
    & $UvPath run uvicorn main:app --host $BindHost --port $Port 2>&1 | Tee-Object -FilePath $LogFile
} finally {
    Pop-Location
    Write-Host "[dev_backend] Đã tắt uvicorn." -ForegroundColor DarkGray
}

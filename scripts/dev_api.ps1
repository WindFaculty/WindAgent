<#
.SYNOPSIS
    scripts/dev_api.ps1 - Khởi chạy WindAgent V2 Backend API (FastAPI + Uvicorn).

.DESCRIPTION
    1. Kiểm tra môi trường: uv, Docker PostgreSQL (55433).
    2. Cấu hình biến môi trường: WINDAGENT_ENVIRONMENT, WINDAGENT_DATABASE_URL.
    3. Tự động áp dụng Alembic migrations (upgrade head).
    4. Kiểm tra và giải phóng port nếu được yêu cầu (-KillExisting).
    5. Khởi chạy uvicorn với hot-reload (--reload).

.PARAMETER Port
    Cổng HTTP cho API. Mặc định: 8000.

.PARAMETER BindHost
    Địa chỉ bind. Mặc định: 127.0.0.1.

.PARAMETER NoMigrate
    Bỏ qua bước chạy Alembic migration.

.PARAMETER NoSync
    Bỏ qua bước uv sync.

.PARAMETER KillExisting
    Tự động tắt tiến trình cũ nếu cổng đang bị chiếm.
#>
[CmdletBinding()]
param(
    [int]    $Port         = 8000,
    [string] $BindHost     = "127.0.0.1",
    [switch] $NoMigrate,
    [switch] $NoSync,
    [switch] $KillExisting
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# UTF-8 console output
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding           = [System.Text.Encoding]::UTF8
} catch { }

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "   WINDAGENT V2 - BACKEND API DEV SERVER             " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " Thư mục gốc : $RepoRoot" -ForegroundColor DarkGray
Write-Host " Địa chỉ     : http://${BindHost}:${Port}" -ForegroundColor DarkGray
Write-Host " Tài liệu API: http://${BindHost}:${Port}/docs" -ForegroundColor DarkGray
Write-Host " Kiểm tra    : http://${BindHost}:${Port}/health" -ForegroundColor DarkGray
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Kiểm tra công cụ uv ---
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCmd) {
    $cargoUv = Join-Path $env:USERPROFILE ".cargo\bin\uv.exe"
    $localUv = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    if (Test-Path $cargoUv) {
        $env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
    } elseif (Test-Path $localUv) {
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    } else {
        Write-Host "[API ERROR] Không tìm thấy 'uv' trên hệ thống. Vui lòng cài đặt uv (https://astral.sh/uv)." -ForegroundColor Red
        exit 1
    }
}

# --- 2. Cấu hình biến môi trường ---
$env:WINDAGENT_ENVIRONMENT = "development"
if (-not $env:WINDAGENT_DATABASE_URL) {
    $env:WINDAGENT_DATABASE_URL = "postgresql+asyncpg://windagent:windagent@localhost:55433/windagent_v2"
}
$env:WINDAGENT_LOG_LEVEL = "INFO"
$env:WINDAGENT_METRICS_ENABLED = "true"

Write-Host "[1/5] Cấu hình môi trường:" -ForegroundColor Green
Write-Host "      - ENVIRONMENT  : $env:WINDAGENT_ENVIRONMENT" -ForegroundColor DarkGray
Write-Host "      - DATABASE_URL : $env:WINDAGENT_DATABASE_URL" -ForegroundColor DarkGray

# --- 3. Kiểm tra PostgreSQL (Docker) ---
Write-Host "`n[2/5] Kiểm tra PostgreSQL..." -ForegroundColor Green
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if ($dockerCmd) {
    $pgContainer = docker ps --filter "name=windagent-v2-postgres" --format "{{.Status}}" 2>$null
    if (-not $pgContainer) {
        Write-Host "      Đang khởi động PostgreSQL qua Docker Compose..." -ForegroundColor Yellow
        docker compose up -d postgres
        Start-Sleep -Seconds 2
    } else {
        Write-Host "      PostgreSQL container đang chạy ($pgContainer)." -ForegroundColor DarkGray
    }
} else {
    Write-Host "      [CẢNH BÁO] Docker không có sẵn trong PATH. Hãy đảm bảo PostgreSQL trên cổng 55433 đã hoạt động." -ForegroundColor Yellow
}

# --- 4. Đồng bộ dependencies (nếu cần) ---
if (-not $NoSync -and -not (Test-Path (Join-Path $RepoRoot ".venv"))) {
    Write-Host "`n[3/5] Khởi tạo .venv và đồng bộ packages (uv sync)..." -ForegroundColor Green
    uv sync
} else {
    Write-Host "`n[3/5] Python virtual environment (.venv) đã sẵn sàng." -ForegroundColor DarkGray
}

# --- 5. Áp dụng Alembic migrations ---
if (-not $NoMigrate) {
    Write-Host "`n[4/5] Áp dụng database migrations (alembic upgrade head)..." -ForegroundColor Green
    try {
        uv run alembic upgrade head
        Write-Host "      Migrations hoàn tất." -ForegroundColor DarkGray
    } catch {
        Write-Host "      [CẢNH BÁO] Không thể chạy migrations. Chi tiết: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "`n[4/5] Bỏ qua database migrations (-NoMigrate)." -ForegroundColor DarkGray
}

# --- 6. Kiểm tra và giải phóng cổng ---
Write-Host "`n[5/5] Kiểm tra cổng $Port..." -ForegroundColor Green
$occupied = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
if ($occupied) {
    $pids = $occupied.OwningProcess | Select-Object -Unique
    Write-Host "      [!] Phát hiện cổng $Port đang bị chiếm bởi PID: $($pids -join ', ')." -ForegroundColor Yellow
    Write-Host "      Đang giải phóng cổng để khởi động sạch sẽ..." -ForegroundColor Yellow
    foreach ($pidToKill in $pids) {
        Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 600
} else {
    Write-Host "      Cổng $Port đã sẵn sàng." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host ">>> Khởi chạy Uvicorn Dev Server (Nhấn Ctrl+C để dừng)..." -ForegroundColor Cyan
Write-Host ""

# Chạy uvicorn với reload
uv run uvicorn windagent_api.app:app --host $BindHost --port $Port --reload

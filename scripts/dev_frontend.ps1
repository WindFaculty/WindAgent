<#
.SYNOPSIS
    scripts/dev_frontend.ps1 - Khởi chạy WindAgent V2 Frontend App (Vite + React).

.DESCRIPTION
    1. Kiểm tra Node.js và npm.
    2. Tự động chạy npm install nếu node_modules chưa tồn tại.
    3. Kiểm tra và giải phóng port nếu được yêu cầu (-KillExisting).
    4. Khởi chạy Vite dev server kết nối proxy tới Backend (:8000).

.PARAMETER Port
    Cổng Vite dev server. Mặc định: 5175.

.PARAMETER NoInstall
    Bỏ qua bước kiểm tra và chạy npm install.

.PARAMETER KillExisting
    Tự động tắt tiến trình cũ nếu cổng đang bị chiếm.
#>
[CmdletBinding()]
param(
    [int]    $Port         = 5175,
    [switch] $NoInstall,
    [switch] $KillExisting
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# UTF-8 console output
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding           = [System.Text.Encoding]::UTF8
} catch { }

$RepoRoot    = Resolve-Path (Join-Path $PSScriptRoot "..")
$FrontendDir = Join-Path $RepoRoot "frontend"
Set-Location $FrontendDir

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "   WINDAGENT V2 - FRONTEND DEV SERVER (VITE)         " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " Thư mục frontend: $FrontendDir" -ForegroundColor DarkGray
Write-Host " Địa chỉ Web UI  : http://localhost:${Port}" -ForegroundColor DarkGray
Write-Host " API Proxy       : http://localhost:8000 (/api, /health, ...)" -ForegroundColor DarkGray
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Kiểm tra Node.js & npm ---
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
$npmCmd  = Get-Command npm -ErrorAction SilentlyContinue

if (-not $nodeCmd -or -not $npmCmd) {
    # Thử tìm trong các đường dẫn thông dụng trên Windows
    $commonNodePaths = @(
        "$env:ProgramFiles\nodejs",
        "${env:ProgramFiles(x86)}\nodejs",
        "$env:LOCALAPPDATA\Programs\node",
        "$env:APPDATA\npm",
        "$env:LOCALAPPDATA\hermes\node"
    )
    foreach ($p in $commonNodePaths) {
        if (Test-Path (Join-Path $p "node.exe")) {
            $env:Path = "$p;$env:Path"
            break
        }
    }
    $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
    $npmCmd  = Get-Command npm -ErrorAction SilentlyContinue
}

if (-not $nodeCmd -or -not $npmCmd) {
    Write-Host "[FRONTEND ERROR] Không tìm thấy Node.js hoặc npm trong PATH. Vui lòng cài đặt Node.js LTS (https://nodejs.org)." -ForegroundColor Red
    exit 1
}

$nodeVersion = (& node --version).Trim()
Write-Host "[1/3] Node.js $nodeVersion & npm sẵn sàng." -ForegroundColor Green

# --- 2. Kiểm tra dependencies ---
$nodeModules = Join-Path $FrontendDir "node_modules"
if (-not (Test-Path $nodeModules) -and -not $NoInstall) {
    Write-Host "`n[2/3] Chưa có node_modules, đang chạy 'npm install'..." -ForegroundColor Yellow
    npm install
} else {
    Write-Host "`n[2/3] Frontend node_modules đã sẵn sàng." -ForegroundColor DarkGray
}

# --- 3. Kiểm tra và giải phóng cổng ---
Write-Host "`n[3/3] Kiểm tra cổng $Port..." -ForegroundColor Green
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
Write-Host ">>> Khởi chạy Vite Dev Server (Nhấn Ctrl+C để dừng)..." -ForegroundColor Cyan
Write-Host ""

# Chạy vite dev server thông qua workspace @windagent/app
npm run dev --workspace=@windagent/app -- --port $Port

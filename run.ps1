<#
.SYNOPSIS
    run.ps1 - Trình khởi chạy phát triển (Dev Launcher) cho WindAgent V2.

.DESCRIPTION
    Khởi chạy toàn bộ hệ thống WindAgent V2 dưới chế độ dev:
    - PostgreSQL 16 (Docker Compose trên cổng 55433)
    - Backend API (FastAPI + Uvicorn hot-reload trên cổng 8000)
    - Frontend Web App (React + Vite dev server trên cổng 5175)
    - Hỗ trợ chạy tương tác qua Menu hoặc truyền tham số dòng lệnh (-Option, -Dev, -Backend, ...).

.PARAMETER Port
    Cổng HTTP Backend API. Mặc định: 8000.

.PARAMETER FrontendPort
    Cổng Vite Frontend Dev Server. Mặc định: 5175.

.PARAMETER Option
    Lựa chọn menu trực tiếp (1-8, 0).

.PARAMETER Dev
    Phím tắt khởi chạy Full Dev (tương đương -Option 1).

.PARAMETER Backend
    Phím tắt chỉ chạy Backend API (tương đương -Option 2).

.PARAMETER Frontend
    Phím tắt chỉ chạy Frontend UI (tương đương -Option 3).

.PARAMETER Gates
    Phím tắt chạy toàn bộ bộ kiểm thử gates (tương đương -Option 7).

.PARAMETER Health
    Phím tắt kiểm tra Health Check API (tương đương -Option 6).

.PARAMETER KillExisting
    Tự động tắt các tiến trình đang chiếm cổng 8000 hoặc 5175.

.PARAMETER OpenBrowser
    Tự động mở trình duyệt truy cập Frontend UI (http://localhost:5175).

.PARAMETER Help
    Hiển thị thông tin trợ giúp sử dụng.

.EXAMPLE
    .\run.ps1
    Mở menu tương tác (chỉ cần nhấn Enter để khởi chạy Full Dev).

.EXAMPLE
    .\run.ps1 -Dev
    Khởi chạy ngay lập tức Full Dev (Backend + Frontend + DB).

.EXAMPLE
    .\run.ps1 -Backend
    Chỉ khởi chạy Backend API với hot-reload.

.EXAMPLE
    .\run.ps1 -KillExisting -Dev
    Dọn dẹp cổng cũ nếu bị chiếm và khởi chạy Full Dev.
#>
[CmdletBinding()]
param(
    [int]    $Port           = 8000,
    [int]    $FrontendPort   = 5175,
    [string] $Option         = "",
    [switch] $Dev,
    [switch] $Backend,
    [switch] $Frontend,
    [switch] $Gates,
    [switch] $Health,
    [switch] $KillExisting,
    [switch] $OpenBrowser,
    [switch] $Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# UTF-8 console
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding           = [System.Text.Encoding]::UTF8
} catch { }

# --- Đường dẫn hệ thống ---
$RepoRoot       = if ($PSScriptRoot) { $PSScriptRoot } else { Get-Location }
Set-Location $RepoRoot

$ScriptsDir     = Join-Path $RepoRoot "scripts"
$ApiScript      = Join-Path $ScriptsDir "dev_api.ps1"
$FrontendScript = Join-Path $ScriptsDir "dev_frontend.ps1"
$GatesScript    = Join-Path $ScriptsDir "run_gates.ps1"
$HealthScript   = Join-Path $ScriptsDir "healthcheck.py"

if ($Help) {
    Get-Help $PSCommandPath -Detailed
    exit 0
}

# --- Xử lý các switches nhanh ---
if ($Dev)      { $Option = "1" }
if ($Backend)  { $Option = "2" }
if ($Frontend) { $Option = "3" }
if ($Health)   { $Option = "6" }
if ($Gates)    { $Option = "7" }

# --- Hàm mở tiến trình trong cửa sổ PowerShell riêng ---
function Start-InNewWindow {
    param(
        [string]$ScriptPath,
        [string[]]$ScriptArgs,
        [string]$Title = "WindAgent V2"
    )
    $argsCombined = ($ScriptArgs | ForEach-Object { $_ }) -join " "
    $cmd = "`$host.UI.RawUI.WindowTitle = '$Title'; & '$ScriptPath' $argsCombined"
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-NoLogo",
        "-Command", $cmd
    )
}

# --- Hàm dừng tiến trình chiếm port ---
function Stop-PortProcesses {
    param([int[]]$Ports)
    foreach ($p in $Ports) {
        $occupied = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }
        if ($occupied) {
            $pids = $occupied.OwningProcess | Select-Object -Unique
            foreach ($procId in $pids) {
                Write-Host "  -> Đang dừng tiến trình PID $procId (chiếm cổng $p)..." -ForegroundColor Yellow
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            }
        } else {
            Write-Host "  -> Cổng $p đang trống." -ForegroundColor DarkGray
        }
    }
}

# --- Hàm đợi Backend sẵn sàng ---
function Wait-ForBackendReady {
    param(
        [string]$Url = "http://127.0.0.1:8000/health",
        [int]$MaxRetries = 15,
        [int]$DelaySec = 1
    )
    Write-Host "  -> Đang kiểm tra kết nối Backend API..." -ForegroundColor Cyan
    for ($i = 1; $i -le $MaxRetries; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($resp -and $resp.StatusCode -eq 200) {
                Write-Host "  [OK] Backend API đã sẵn sàng tại $Url" -ForegroundColor Green
                return $true
            }
        } catch { }
        Start-Sleep -Seconds $DelaySec
    }
    Write-Host "  [!] Chờ Backend vượt quá thời gian, tiếp tục khởi động Frontend..." -ForegroundColor Yellow
    return $false
}

# --- Hiển thị Menu chính ---
function Show-Menu {
    Clear-Host
    Write-Host ""
    Write-Host "  +======================================================+" -ForegroundColor Cyan
    Write-Host "  |      W I N D A G E N T   V 2   L A U N C H E R       |" -ForegroundColor Cyan
    Write-Host "  +======================================================+" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  -- Chế độ Phát triển (Dev Mode) -------------------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [1]  Khởi chạy Full Dev (Khuyến nghị)" -ForegroundColor Green
    Write-Host "       PostgreSQL (Docker) + Backend API (:8000) + Frontend (:5175)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [2]  Chỉ chạy Backend API (FastAPI uvicorn --reload trên :$Port)" -ForegroundColor Yellow
    Write-Host "  [3]  Chỉ chạy Frontend Web UI (Vite dev trên :$FrontendPort)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  -- Cơ sở dữ liệu & Hạ tầng -----------------------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [4]  Khởi động PostgreSQL container (Docker Compose :55433)" -ForegroundColor Magenta
    Write-Host "  [5]  Chạy Alembic Migrations (upgrade head)" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "  -- Kiểm thử & Tiện ích -----------------------------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [6]  Kiểm tra Health Check (:8000/health & :8000/ready)" -ForegroundColor Cyan
    Write-Host "  [7]  Chạy Bộ kiểm định Local Gates (scripts/run_gates.ps1)" -ForegroundColor Cyan
    Write-Host "  [8]  Dọn dẹp / Giải phóng các port ($Port, $FrontendPort)" -ForegroundColor DarkYellow
    Write-Host ""
    Write-Host "  [0]  Thoát" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  +------------------------------------------------------+" -ForegroundColor DarkGray
    Write-Host "  (Nhấn Enter trực tiếp để chọn [1] Khởi chạy Full Dev)" -ForegroundColor DarkCyan
    Write-Host ""
}

# --- Thực thi lựa chọn ---
function Execute-Option {
    param([string]$SelectedChoice)

    $choice = $SelectedChoice.Trim()
    if ($choice -eq "") {
        $choice = "1" # Mặc định khi ấn Enter là [1] Full Dev
    }

    switch ($choice) {
        "1" {
            Write-Host "`n======================================================" -ForegroundColor Green
            Write-Host "  -> BẮT ĐẦU CHẾ ĐỘ PHÁT TRIỂN TOÀN DIỆN (FULL DEV)  " -ForegroundColor Green
            Write-Host "======================================================" -ForegroundColor Green

            # 1. Tự động kiểm tra và giải phóng cổng cũ tránh xung đột socket (WinError 10013)
            Write-Host "`n[*] Dọn dẹp và giải phóng cổng $Port và $FrontendPort..." -ForegroundColor Cyan
            Stop-PortProcesses -Ports @($Port, $FrontendPort)
            Start-Sleep -Milliseconds 600

            # 2. Khởi động Backend API trong cửa sổ riêng
            Write-Host "`n[*] Đang khởi động Backend API trong cửa sổ riêng..." -ForegroundColor Cyan
            Start-InNewWindow -ScriptPath $ApiScript `
                -ScriptArgs @("-Port", "$Port", "-KillExisting") `
                -Title "WindAgent V2 - Backend API (:$Port)"

            # 3. Đợi backend sẵn sàng
            Wait-ForBackendReady -Url "http://127.0.0.1:${Port}/health" -MaxRetries 15 -DelaySec 1

            # 4. Mở trình duyệt nếu có yêu cầu
            if ($OpenBrowser) {
                Start-Process "http://localhost:${FrontendPort}"
            }

            # 5. Chạy Frontend tại cửa sổ hiện tại (truyền tham số trực tiếp không qua array splatting)
            Write-Host "`n[*] Đang khởi chạy Frontend Web UI tại cửa sổ này..." -ForegroundColor Cyan
            & $FrontendScript -Port $FrontendPort -KillExisting

            return $false
        }

        "2" {
            Write-Host "`n  -> Khởi chạy Backend API độc lập..." -ForegroundColor Yellow
            & $ApiScript -Port $Port -KillExisting
            return $false
        }

        "3" {
            Write-Host "`n  -> Khởi chạy Frontend Web UI độc lập..." -ForegroundColor Yellow
            & $FrontendScript -Port $FrontendPort -KillExisting
            return $false
        }

        "4" {
            Write-Host "`n  -> Khởi động PostgreSQL qua Docker Compose..." -ForegroundColor Magenta
            docker compose up -d postgres
            Start-Sleep -Seconds 2
            docker compose ps postgres
            return $true
        }

        "5" {
            Write-Host "`n  -> Chạy Alembic Migrations..." -ForegroundColor Magenta
            $env:WINDAGENT_ENVIRONMENT = "development"
            if (-not $env:WINDAGENT_DATABASE_URL) {
                $env:WINDAGENT_DATABASE_URL = "postgresql+asyncpg://windagent:windagent@localhost:55433/windagent_v2"
            }
            uv run alembic upgrade head
            Write-Host "`n  [OK] Migrations hoàn tất." -ForegroundColor Green
            return $true
        }

        "6" {
            Write-Host "`n  -> Kiểm tra Health & Readiness Probe..." -ForegroundColor Cyan
            try {
                & uv run python $HealthScript --host 127.0.0.1 --port $Port
            } catch {
                Write-Host "  [LỖI] Không thể kết nối tới Backend tại cổng $Port." -ForegroundColor Red
            }

            try {
                $ready = Invoke-RestMethod -Uri "http://127.0.0.1:${Port}/ready" -ErrorAction Stop
                $readyJson = $ready | ConvertTo-Json -Compress
                Write-Host "  [OK] /ready Probe: $readyJson" -ForegroundColor Green
            } catch {
                Write-Host "  [CẢNH BÁO] Endpoint /ready chưa phản hồi." -ForegroundColor Yellow
            }
            return $true
        }

        "7" {
            Write-Host "`n  -> Chạy Bộ kiểm định Local Gates..." -ForegroundColor Cyan
            & $GatesScript
            return $true
        }

        "8" {
            Write-Host "`n  -> Giải phóng các cổng $Port và $FrontendPort..." -ForegroundColor DarkYellow
            Stop-PortProcesses -Ports @($Port, $FrontendPort)
            return $true
        }

        "0" {
            Write-Host "`n  Tạm biệt!`n" -ForegroundColor Cyan
            exit 0
        }

        default {
            Write-Host "`n  [!] Lựa chọn không hợp lệ: '$SelectedChoice'" -ForegroundColor Red
            Start-Sleep -Milliseconds 700
            return $true
        }
    }
}

# --- Nếu tham số -Option được truyền trực tiếp ---
if ($Option) {
    [void](Execute-Option -SelectedChoice $Option)
    exit 0
}

# --- Vòng lặp menu tương tác ---
while ($true) {
    Show-Menu
    try {
        $choice = Read-Host "  Nhập lựa chọn [Mặc định: 1]"
    } catch {
        Write-Host "`n  [!] Terminal không hỗ trợ nhập tương tác (Non-interactive mode)." -ForegroundColor Yellow
        Write-Host "  -> Tự động khởi chạy Full Dev (-Option 1)..." -ForegroundColor Green
        [void](Execute-Option -SelectedChoice "1")
        exit 0
    }

    $shouldContinue = Execute-Option -SelectedChoice $choice
    if ($shouldContinue) {
        Write-Host "`n  Nhấn phím bất kỳ để quay lại menu..." -ForegroundColor DarkGray
        try {
            $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
        } catch {
            Start-Sleep -Seconds 3
        }
    } else {
        break
    }
}

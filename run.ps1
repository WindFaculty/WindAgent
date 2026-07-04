<#
run.ps1
Bộ khởi chạy WindAgent (Frontend, Backend, Desktop App)
#>

[CmdletBinding()]
param(
    [int]$BackendPort = 8765,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

# Đặt mã hóa UTF-8 cho console để hiển thị tiếng Việt chính xác
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

# Xác định đường dẫn thư mục gốc và thư mục scripts
$RepoRoot = $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = Get-Location }
$ScriptsDir = Join-Path $RepoRoot "scripts"
$BackendScript = Join-Path $ScriptsDir "dev_backend.ps1"
$DesktopScript = Join-Path $ScriptsDir "dev_desktop.ps1"
$HealthScript = Join-Path $ScriptsDir "healthcheck.ps1"

# Kiểm tra sự tồn tại của các script phụ trợ
if (-not (Test-Path $BackendScript) -or -not (Test-Path $DesktopScript)) {
    Write-Host "[Launcher] LỖI: Không tìm thấy thư mục scripts/ hoặc các file khởi chạy cần thiết!" -ForegroundColor Red
    exit 1
}

function Show-Menu {
    Clear-Host
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "                WINDAGENT LAUNCHER SYSTEM" -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " Chọn chế độ khởi chạy của bạn:" -ForegroundColor White
    Write-Host ""
    Write-Host "  [1] Chạy Web Dev (Mock Mode)" -ForegroundColor Green
    Write-Host "      -> Backend (Mock GUI + Mock Model) + Frontend Standalone (Vite)"
    Write-Host ""
    Write-Host "  [2] Chạy Web Dev (Real Mode)" -ForegroundColor Green
    Write-Host "      -> Backend (Real PyAutoGUI + Ollama) + Frontend Standalone (Vite)"
    Write-Host ""
    Write-Host "  [3] Chạy Desktop App (Mock Mode)" -ForegroundColor Yellow
    Write-Host "      -> Backend (Mock GUI + Mock Model) + Tauri Desktop App (React UI)"
    Write-Host ""
    Write-Host "  [4] Chạy Desktop App (Real Mode)" -ForegroundColor Yellow
    Write-Host "      -> Backend (Real PyAutoGUI + Ollama) + Tauri Desktop App (React UI)"
    Write-Host ""
    Write-Host "  [5] Kiểm tra Môi trường (Health Check)" -ForegroundColor Magenta
    Write-Host "      -> Chạy healthcheck.ps1 để kiểm tra môi trường hệ thống"
    Write-Host ""
    Write-Host "  [6] Thoát" -ForegroundColor DarkGray
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host ""
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Nhập lựa chọn của bạn [1-6]"
    
    switch ($choice) {
        "1" {
            Write-Host "`n[Launcher] Đang khởi động Web Dev (Mock Mode)..." -ForegroundColor Green
            # Khởi chạy backend ở cửa sổ mới (Mock mặc định = true)
            Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$BackendScript`"", "-Port", "$BackendPort")
            # Khởi chạy frontend ở cửa sổ hiện tại
            powershell -ExecutionPolicy Bypass -File $DesktopScript -Port $FrontendPort
            break
        }
        "2" {
            Write-Host "`n[Launcher] Đang khởi động Web Dev (Real Mode)..." -ForegroundColor Green
            # Khởi chạy backend ở cửa sổ mới (Mock = false để dùng Ollama/PyAutoGUI thật)
            Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$BackendScript`"", "-Port", "$BackendPort", "-Mock:`$false")
            # Khởi chạy frontend ở cửa sổ hiện tại
            powershell -ExecutionPolicy Bypass -File $DesktopScript -Port $FrontendPort
            break
        }
        "3" {
            Write-Host "`n[Launcher] Đang khởi động Desktop App (Mock Mode)..." -ForegroundColor Yellow
            # Khởi chạy backend ở cửa sổ mới (Mock mặc định = true)
            Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$BackendScript`"", "-Port", "$BackendPort")
            # Khởi chạy Tauri shell ở cửa sổ hiện tại
            powershell -ExecutionPolicy Bypass -File $DesktopScript -Port $FrontendPort -Tauri
            break
        }
        "4" {
            Write-Host "`n[Launcher] Đang khởi động Desktop App (Real Mode)..." -ForegroundColor Yellow
            # Khởi chạy backend ở cửa sổ mới (Mock = false)
            Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$BackendScript`"", "-Port", "$BackendPort", "-Mock:`$false")
            # Khởi chạy Tauri shell ở cửa sổ hiện tại
            powershell -ExecutionPolicy Bypass -File $DesktopScript -Port $FrontendPort -Tauri
            break
        }
        "5" {
            Write-Host "`n[Launcher] Đang chạy Health Check..." -ForegroundColor Magenta
            powershell -ExecutionPolicy Bypass -File $HealthScript
            Write-Host "`nNhấn phím bất kỳ để tiếp tục..." -ForegroundColor DarkGray
            [void]$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        }
        "6" {
            Write-Host "`nTạm biệt!" -ForegroundColor Cyan
            exit 0
        }
        default {
            Write-Host "`nLựa chọn không hợp lệ. Vui lòng thử lại!" -ForegroundColor Red
            Start-Sleep -Seconds 1
        }
    }
}


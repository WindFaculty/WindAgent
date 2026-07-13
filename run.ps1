<#
.SYNOPSIS
    run.ps1 - Menu khoi chay WindAgent (Frontend / Backend / Desktop App).

.DESCRIPTION
    Launcher tong hop voi menu tuong tac.
    Goi cac script con trong thu muc scripts/.

.PARAMETER BackendPort
    Cong HTTP backend. Mac dinh: 8765.

.PARAMETER FrontendPort
    Cong Vite dev server. Mac dinh: 5173.
#>
[CmdletBinding()]
param(
    [int] $BackendPort  = 8765,
    [int] $FrontendPort = 5173
)

$ErrorActionPreference = "Stop"

# UTF-8 console
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding           = [System.Text.Encoding]::UTF8
} catch { }

# --- Duong dan script ---
$RepoRoot       = if ($PSScriptRoot) { $PSScriptRoot } else { Get-Location }
$ScriptsDir     = Join-Path $RepoRoot "scripts"
$BackendScript  = Join-Path $ScriptsDir "dev_backend.ps1"
$FrontendScript = Join-Path $ScriptsDir "dev_frontend.ps1"
$DesktopScript  = Join-Path $ScriptsDir "dev_desktop.ps1"
$HealthScript   = Join-Path $ScriptsDir "healthcheck.ps1"

# --- Kiem tra scripts ton tai ---
$missing = @($BackendScript, $FrontendScript, $DesktopScript) | Where-Object { -not (Test-Path $_) }
if ($missing.Count -gt 0) {
    Write-Host "[Launcher] LOI: Thieu cac script sau:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

# --- Helper: mo cua so PowerShell moi chay script ---
function Start-InNewWindow {
    param([string]$Script, [string[]]$ExtraArgs, [string]$Title = "WindAgent")
    $argStr = ($ExtraArgs | ForEach-Object { $_ }) -join " "
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-NoLogo",
        "-Command", "`$host.UI.RawUI.WindowTitle = '$Title'; & '$Script' $argStr"
    )
}

# --- Menu ---
function Show-Menu {
    Clear-Host
    Write-Host ""
    Write-Host "  +======================================================+" -ForegroundColor Cyan
    Write-Host "  |        W I N D A G E N T   L A U N C H E R          |" -ForegroundColor Cyan
    Write-Host "  +======================================================+" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  -- Che do Web (truy cap qua trinh duyet) ---------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [1]  Web Dev - Mock Mode" -ForegroundColor Green
    Write-Host "       Backend (mock model + mock GUI) + Vite UI" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [2]  Web Dev - Real Mode" -ForegroundColor Green
    Write-Host "       Backend (Ollama + PyAutoGUI) + Vite UI" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  -- Che do Desktop App (Tauri) ---------------------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [3]  Desktop App - Mock Mode" -ForegroundColor Yellow
    Write-Host "       Backend (mock) + Tauri shell" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [4]  Desktop App - Real Mode" -ForegroundColor Yellow
    Write-Host "       Backend (Ollama + PyAutoGUI) + Tauri shell" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  -- Tien ich -----------------------------------------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [5]  Chi chay Backend (Mock)" -ForegroundColor Magenta
    Write-Host "  [6]  Chi chay Frontend (Vite)" -ForegroundColor Magenta
    Write-Host "  [7]  Health Check moi truong" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "  [0]  Thoat" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  +------------------------------------------------------+" -ForegroundColor DarkGray
    Write-Host ""
}

# --- Vong lap menu ---
while ($true) {
    Show-Menu
    $choice = Read-Host "  Nhap lua chon"

    switch ($choice.Trim()) {

        "1" {
            Write-Host "`n  -> Khoi dong Web Dev - Mock Mode..." -ForegroundColor Green
            Start-InNewWindow -Script $BackendScript `
                -ExtraArgs @("-Port $BackendPort") `
                -Title "WindAgent - Backend (Mock)"
            Start-Sleep -Milliseconds 800
            Write-Host "  -> Chay Frontend tai cua so nay..." -ForegroundColor Green
            & powershell -ExecutionPolicy Bypass -File $FrontendScript -Port $FrontendPort
        }

        "2" {
            Write-Host "`n  -> Khoi dong Web Dev - Real Mode..." -ForegroundColor Green
            Start-InNewWindow -Script $BackendScript `
                -ExtraArgs @("-Port $BackendPort -Mock:`$false") `
                -Title "WindAgent - Backend (Real)"
            Start-Sleep -Milliseconds 800
            Write-Host "  -> Chay Frontend tai cua so nay..." -ForegroundColor Green
            & powershell -ExecutionPolicy Bypass -File $FrontendScript -Port $FrontendPort
        }

        "3" {
            Write-Host "`n  -> Khoi dong Desktop App - Mock Mode..." -ForegroundColor Yellow
            Start-InNewWindow -Script $BackendScript `
                -ExtraArgs @("-Port $BackendPort") `
                -Title "WindAgent - Backend (Mock)"
            Start-Sleep -Milliseconds 800
            Write-Host "  -> Chay Tauri shell tai cua so nay..." -ForegroundColor Yellow
            & powershell -ExecutionPolicy Bypass -File $DesktopScript -Port $FrontendPort
        }

        "4" {
            Write-Host "`n  -> Khoi dong Desktop App - Real Mode..." -ForegroundColor Yellow
            Start-InNewWindow -Script $BackendScript `
                -ExtraArgs @("-Port $BackendPort -Mock:`$false") `
                -Title "WindAgent - Backend (Real)"
            Start-Sleep -Milliseconds 800
            Write-Host "  -> Chay Tauri shell tai cua so nay..." -ForegroundColor Yellow
            & powershell -ExecutionPolicy Bypass -File $DesktopScript -Port $FrontendPort
        }

        "5" {
            Write-Host "`n  -> Chi chay Backend (Mock)..." -ForegroundColor Magenta
            & powershell -ExecutionPolicy Bypass -File $BackendScript -Port $BackendPort
        }

        "6" {
            Write-Host "`n  -> Chi chay Frontend (Vite)..." -ForegroundColor Magenta
            & powershell -ExecutionPolicy Bypass -File $FrontendScript -Port $FrontendPort
        }

        "7" {
            if (Test-Path $HealthScript) {
                Write-Host "`n  -> Chay Health Check..." -ForegroundColor Magenta
                & powershell -ExecutionPolicy Bypass -File $HealthScript
            } else {
                Write-Host "`n  [!] Khong tim thay scripts\healthcheck.ps1" -ForegroundColor Red
            }
            Write-Host "`n  Nhan phim bat ky de quay lai menu..." -ForegroundColor DarkGray
            [void]$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        }

        "0" {
            Write-Host "`n  Tam biet!`n" -ForegroundColor Cyan
            exit 0
        }

        default {
            Write-Host "`n  [!] Lua chon khong hop le. Thu lai." -ForegroundColor Red
            Start-Sleep -Milliseconds 700
        }
    }
}

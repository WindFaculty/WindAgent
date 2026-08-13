<#
.SYNOPSIS
    run.ps1 - Menu khoi chay WindAgent (Web UI / API / Desktop App / Tests).

.DESCRIPTION
    Launcher tong hop voi menu tuong tac va ho tro truyen tham so -Option.
    Goi cac script con trong thu muc scripts/.

.PARAMETER BackendPort
    Cong HTTP backend. Mac dinh: 8765.

.PARAMETER FrontendPort
    Cong Vite dev server. Mac dinh: 5173.

.PARAMETER Option
    Lua chon menu khoi chay truc tiep (1-9, 0).
#>
[CmdletBinding()]
param(
    [int]    $BackendPort  = 8765,
    [int]    $FrontendPort = 5173,
    [string] $Option       = ""
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
$ApiScript      = Join-Path $ScriptsDir "dev_api.ps1"
$FrontendScript = Join-Path $ScriptsDir "dev_frontend.ps1"
$DesktopScript  = Join-Path $ScriptsDir "dev_desktop.ps1"
$HealthScript   = Join-Path $ScriptsDir "healthcheck.ps1"

# --- Kiem tra scripts ton tai ---
$missing = @($ApiScript, $FrontendScript, $DesktopScript) | Where-Object { -not (Test-Path $_) }
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
    Write-Host "  -- Che do Web App (apps/web) ----------------------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [1]  Web Dev - Mock Mode" -ForegroundColor Green
    Write-Host "       Backend API (Mock) + Vite Web UI (apps/web)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [2]  Web Dev - Real Mode" -ForegroundColor Green
    Write-Host "       Backend API (Real) + Vite Web UI (apps/web)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  -- Che do Desktop App (apps/desktop - Tauri) ------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [3]  Desktop App - Mock Mode" -ForegroundColor Yellow
    Write-Host "       Backend API (Mock) + Tauri shell (apps/desktop)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [4]  Desktop App - Real Mode" -ForegroundColor Yellow
    Write-Host "       Backend API (Real) + Tauri shell (apps/desktop)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  -- Tien ich & Testing ------------------------------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  [5]  Chi chay Backend API (Mock)" -ForegroundColor Magenta
    Write-Host "  [6]  Chi chay Web UI (Vite apps/web)" -ForegroundColor Magenta
    Write-Host "  [7]  Health Check moi truong" -ForegroundColor Magenta
    Write-Host "  [8]  Chi chay Desktop UI Dev (Vite apps/desktop)" -ForegroundColor Magenta
    Write-Host "  [9]  Chay Test & Typecheck Matrix (Vitest & tsc)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  [0]  Thoat" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  +------------------------------------------------------+ " -ForegroundColor DarkGray
    Write-Host ""
}

# --- Thuc thi khoi chay ---
function Execute-Option {
    param([string]$SelectedChoice)

    switch ($SelectedChoice.Trim()) {

        "1" {
            Write-Host "`n  -> Khoi dong Web Dev - Mock Mode..." -ForegroundColor Green
            Start-InNewWindow -Script $ApiScript `
                -ExtraArgs @("-Port $BackendPort") `
                -Title "WindAgent - API (Mock)"
            Start-Sleep -Milliseconds 800
            Write-Host "  -> Chay Web UI (apps/web) tai cua so nay..." -ForegroundColor Green
            & $FrontendScript -Port $FrontendPort
            return $false
        }

        "2" {
            Write-Host "`n  -> Khoi dong Web Dev - Real Mode..." -ForegroundColor Green
            Start-InNewWindow -Script $ApiScript `
                -ExtraArgs @("-Port $BackendPort -Mock:`$false") `
                -Title "WindAgent - API (Real)"
            Start-Sleep -Milliseconds 800
            Write-Host "  -> Chay Web UI (apps/web) tai cua so nay..." -ForegroundColor Green
            & $FrontendScript -Port $FrontendPort
            return $false
        }

        "3" {
            Write-Host "`n  -> Khoi dong Desktop App - Mock Mode..." -ForegroundColor Yellow
            Start-InNewWindow -Script $ApiScript `
                -ExtraArgs @("-Port $BackendPort") `
                -Title "WindAgent - API (Mock)"
            Start-Sleep -Milliseconds 800
            Write-Host "  -> Chay Tauri shell (apps/desktop) tai cua so nay..." -ForegroundColor Yellow
            & $DesktopScript -Port $FrontendPort
            return $false
        }

        "4" {
            Write-Host "`n  -> Khoi dong Desktop App - Real Mode..." -ForegroundColor Yellow
            Start-InNewWindow -Script $ApiScript `
                -ExtraArgs @("-Port $BackendPort -Mock:`$false") `
                -Title "WindAgent - API (Real)"
            Start-Sleep -Milliseconds 800
            Write-Host "  -> Chay Tauri shell (apps/desktop) tai cua so nay..." -ForegroundColor Yellow
            & $DesktopScript -Port $FrontendPort
            return $false
        }

        "5" {
            Write-Host "`n  -> Chi chay API (Mock)..." -ForegroundColor Magenta
            & $ApiScript -Port $BackendPort
            return $false
        }

        "6" {
            Write-Host "`n  -> Chi chay Web UI (Vite apps/web)..." -ForegroundColor Magenta
            & $FrontendScript -Port $FrontendPort
            return $false
        }

        "7" {
            if (Test-Path $HealthScript) {
                Write-Host "`n  -> Chay Health Check..." -ForegroundColor Magenta
                & $HealthScript
            } else {
                Write-Host "`n  [!] Khong tim thay scripts\healthcheck.ps1" -ForegroundColor Red
            }
            return $true
        }

        "8" {
            Write-Host "`n  -> Chi chay Desktop UI Dev (apps/desktop)..." -ForegroundColor Magenta
            & $DesktopScript -Port $FrontendPort
            return $false
        }

        "9" {
            Write-Host "`n  -> Chay Test & Typecheck Matrix..." -ForegroundColor Cyan
            Push-Location (Join-Path $RepoRoot "frontend\packages\studio-shell")
            Write-Host "  [studio-shell] Running Vitest..." -ForegroundColor DarkGray
            npx vitest run
            Pop-Location

            Push-Location (Join-Path $RepoRoot "frontend\packages\story-ui")
            Write-Host "  [story-ui] Running Vitest..." -ForegroundColor DarkGray
            npx vitest run
            Pop-Location

            Push-Location (Join-Path $RepoRoot "apps\desktop")
            Write-Host "  [apps/desktop] Running Typecheck..." -ForegroundColor DarkGray
            npm run type-check
            Write-Host "  [apps/desktop] Running Vitest..." -ForegroundColor DarkGray
            npm test
            Pop-Location
            return $true
        }

        "0" {
            Write-Host "`n  Tam biet!`n" -ForegroundColor Cyan
            exit 0
        }

        default {
            Write-Host "`n  [!] Lua chon khong hop le: '$SelectedChoice'" -ForegroundColor Red
            Start-Sleep -Milliseconds 700
            return $true
        }
    }
}

# --- Neu tham so -Option duoc truyen ---
if ($Option) {
    [void](Execute-Option -SelectedChoice $Option)
    exit 0
}

# --- Vong lap menu tuong tac ---
while ($true) {
    Show-Menu
    try {
        $choice = Read-Host "  Nhap lua chon"
    } catch {
        Write-Host "`n  [!] Terminal khong ho tro nhap tuong tac (StandardInput unreadable/non-interactive)." -ForegroundColor Yellow
        Write-Host "  Meo: Chay voi tham so: .\run.ps1 -Option <1-9>" -ForegroundColor Cyan
        exit 0
    }

    $shouldContinue = Execute-Option -SelectedChoice $choice
    if ($shouldContinue -and ($choice.Trim() -eq "7" -or $choice.Trim() -eq "9")) {
        Write-Host "`n  Nhan phim bat ky de quay lai menu..." -ForegroundColor DarkGray
        try {
            [void]$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        } catch { }
    }
}

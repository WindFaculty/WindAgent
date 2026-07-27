<#
.SYNOPSIS
    scripts/dev_desktop.ps1 - Khoi chay Tauri desktop app (WindAgent).

.DESCRIPTION
    Chay ung dung desktop Tauri (React UI + Rust shell).
    Yeu cau Rust toolchain va @tauri-apps/cli da duoc cai.

    1. Kiem tra Node >= 18, npm, va Rust/Cargo.
    2. Tu dong `npm install` neu can.
    3. Chay `npm run tauri dev` (Tauri hot-reload + Vite).
    4. Neu Cargo khong co trong PATH: in huong dan cai Rust va thoat.
    5. Ctrl+C tat sach.

.PARAMETER NoInstall
    Bo qua buoc npm install.

.PARAMETER Port
    Cong Vite dev ben trong Tauri. Mac dinh: 5173.

.PARAMETER NoProxy
    Khong in nhac nho ve proxy API.
#>
[CmdletBinding()]
param(
    [switch] $NoInstall,
    [int]    $Port    = 5173,
    [switch] $NoProxy
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# UTF-8 console
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding           = [System.Text.Encoding]::UTF8
} catch { }

# --- Duong dan ---
$RepoRoot   = Resolve-Path (Join-Path $PSScriptRoot "..")
$DesktopDir = Join-Path $RepoRoot "apps\desktop"

# --- Kiem tra thu muc ---
if (-not (Test-Path $DesktopDir)) {
    Write-Host "[desktop] FAIL: Khong tim thay apps/desktop" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $DesktopDir "package.json"))) {
    Write-Host "[desktop] FAIL: Thieu apps/desktop/package.json" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $DesktopDir "src-tauri"))) {
    Write-Host "[desktop] FAIL: Khong tim thay apps/desktop/src-tauri" -ForegroundColor Red
    exit 1
}

# --- Tim Node + npm ---
function Add-NodeToPath {
    $candidates = @(
        "$env:ProgramFiles\nodejs",
        "${env:ProgramFiles(x86)}\nodejs",
        "$env:APPDATA\nvm\current",
        "$env:LOCALAPPDATA\fnm\aliases\default"
    )
    foreach ($c in $candidates) {
        if (Test-Path (Join-Path $c "node.exe")) {
            $env:PATH = "$c;$env:PATH"
            Write-Host "[desktop] Them Node vao PATH: $c" -ForegroundColor DarkGray
            return $true
        }
    }
    return $false
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    if (-not (Add-NodeToPath)) {
        Write-Host "[desktop] FAIL: Chua cai Node.js >= 18" -ForegroundColor Red
        Write-Host "  Tai tai: https://nodejs.org/" -ForegroundColor Yellow
        exit 1
    }
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "[desktop] FAIL: Thieu npm trong PATH" -ForegroundColor Red
    exit 1
}

$nodeVer = (& node --version) -replace '^v', ''
$npmVer  = & npm --version
Write-Host "[desktop] Node: v$nodeVer  |  npm: $npmVer" -ForegroundColor DarkGray

# --- Kiem tra Rust / Cargo ---
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Host "[desktop] FAIL: Chua cai Rust toolchain (cargo khong co trong PATH)." -ForegroundColor Red
    Write-Host ""
    Write-Host "  De cai Rust tren Windows:" -ForegroundColor Yellow
    Write-Host "  1. Tai rustup-init.exe tu https://rustup.rs/" -ForegroundColor Yellow
    Write-Host "  2. Chay installer, chon 'default' (stable toolchain)" -ForegroundColor Yellow
    Write-Host "  3. Khoi dong lai terminal roi chay lai script nay." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Neu chi muon chay UI (khong can Tauri shell):" -ForegroundColor DarkGray
    Write-Host "  -> Dung scripts\dev_frontend.ps1 thay the." -ForegroundColor DarkGray
    exit 1
}
$cargoVer = (& cargo --version) -replace 'cargo ', ''
Write-Host "[desktop] Cargo: $cargoVer" -ForegroundColor DarkGray

# --- npm install neu can ---
$nodeModules = Join-Path $DesktopDir "node_modules"
$packageJson = Join-Path $DesktopDir "package.json"
$needInstall = -not (Test-Path $nodeModules)
if (-not $needInstall) {
    $needInstall = (Get-Item $packageJson).LastWriteTime -gt (Get-Item $nodeModules).LastWriteTime
}

if (-not $NoInstall -and $needInstall) {
    Write-Host "[desktop] Cai npm packages..." -ForegroundColor Cyan
    Push-Location $DesktopDir
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[desktop] FAIL: npm install that bai (exit $LASTEXITCODE)" -ForegroundColor Red
            exit 1
        }
    } finally { Pop-Location }
} else {
    Write-Host "[desktop] npm install: bo qua (node_modules da san sang)" -ForegroundColor DarkGray
}

# --- Them node_modules/.bin vao PATH ---
$env:PATH = "$DesktopDir\node_modules\.bin;$env:PATH"

# --- Nhac nho proxy ---
if (-not $NoProxy) {
    Write-Host "[desktop] Proxy /api + /ws -> http://127.0.0.1:8765" -ForegroundColor DarkGray
    Write-Host "[desktop] Dam bao API dang chay: scripts\dev_api.ps1" -ForegroundColor DarkGray
}

# --- Khoi dong Tauri dev ---
Write-Host ""
Write-Host "[desktop] =====================================================" -ForegroundColor Yellow
Write-Host "[desktop]  Tauri dev  (Vite port: $Port)" -ForegroundColor Yellow
Write-Host "[desktop]  Lan dau build Rust co the mat vai phut..." -ForegroundColor DarkGray
Write-Host "[desktop]  Dung : Ctrl+C" -ForegroundColor DarkGray
Write-Host "[desktop] =====================================================" -ForegroundColor Yellow
Write-Host ""

Push-Location $DesktopDir
try {
    & npm run tauri dev
} finally {
    Pop-Location
    Write-Host "`n[desktop] Da tat Tauri." -ForegroundColor DarkGray
}

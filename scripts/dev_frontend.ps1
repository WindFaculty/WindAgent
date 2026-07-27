<#
.SYNOPSIS
    scripts/dev_frontend.ps1 - Khoi chay Vite dev server (React UI).

.DESCRIPTION
    Chi chay giao dien web (React + Vite) - KHONG mo Tauri shell.
    Dung cho phat trien UI thuan, truy cap qua trinh duyet.

    1. Kiem tra Node >= 18 va npm.
    2. Tu dong `npm install` neu node_modules chua co.
    3. Khoi dong Vite dev server o cong chi dinh.
    4. Ctrl+C tat sach.

.PARAMETER Port
    Cong Vite dev. Mac dinh: 5173.

.PARAMETER NoInstall
    Bo qua buoc npm install.

.PARAMETER NoProxy
    Khong in nhac nho ve proxy API.
#>
[CmdletBinding()]
param(
    [int]    $Port      = 5173,
    [switch] $NoInstall,
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
    Write-Host "[frontend] FAIL: Khong tim thay apps/desktop" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $DesktopDir "package.json"))) {
    Write-Host "[frontend] FAIL: Thieu apps/desktop/package.json" -ForegroundColor Red
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
            Write-Host "[frontend] Them Node vao PATH: $c" -ForegroundColor DarkGray
            return $true
        }
    }
    return $false
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    if (-not (Add-NodeToPath)) {
        Write-Host "[frontend] FAIL: Chua cai Node.js >= 18" -ForegroundColor Red
        Write-Host "  Tai tai: https://nodejs.org/" -ForegroundColor Yellow
        exit 1
    }
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "[frontend] FAIL: Thieu npm trong PATH" -ForegroundColor Red
    exit 1
}

$nodeVer = (& node --version) -replace '^v', ''
$npmVer  = & npm --version
Write-Host "[frontend] Node: v$nodeVer  |  npm: $npmVer" -ForegroundColor DarkGray

# --- npm install neu can ---
$nodeModules = Join-Path $DesktopDir "node_modules"
$packageJson = Join-Path $DesktopDir "package.json"
$needInstall = -not (Test-Path $nodeModules)
if (-not $needInstall) {
    $needInstall = (Get-Item $packageJson).LastWriteTime -gt (Get-Item $nodeModules).LastWriteTime
}

if (-not $NoInstall -and $needInstall) {
    Write-Host "[frontend] Cai npm packages..." -ForegroundColor Cyan
    Push-Location $DesktopDir
    try {
        & npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[frontend] FAIL: npm install that bai (exit $LASTEXITCODE)" -ForegroundColor Red
            exit 1
        }
    } finally { Pop-Location }
} else {
    Write-Host "[frontend] npm install: bo qua (node_modules da san sang)" -ForegroundColor DarkGray
}

# --- Them node_modules/.bin vao PATH ---
$env:PATH = "$DesktopDir\node_modules\.bin;$env:PATH"

# --- Nhac nho proxy ---
if (-not $NoProxy) {
    Write-Host "[frontend] Proxy /api + /ws -> http://127.0.0.1:8765" -ForegroundColor DarkGray
    Write-Host "[frontend] Dam bao API dang chay: scripts\dev_api.ps1" -ForegroundColor DarkGray
}

# --- Khoi dong Vite ---
Write-Host ""
Write-Host "[frontend] =====================================================" -ForegroundColor Cyan
Write-Host "[frontend]  Vite dev -> http://localhost:${Port}" -ForegroundColor Cyan
Write-Host "[frontend]  Dung     :  Ctrl+C" -ForegroundColor DarkGray
Write-Host "[frontend] =====================================================" -ForegroundColor Cyan
Write-Host ""

Push-Location $DesktopDir
try {
    $viteJs = Join-Path $DesktopDir "node_modules\vite\bin\vite.js"
    if (Test-Path $viteJs) {
        & node $viteJs --port $Port --strictPort
    } else {
        & npm run dev -- --port $Port --strictPort
    }
} finally {
    Pop-Location
    Write-Host "`n[frontend] Da tat Vite dev server." -ForegroundColor DarkGray
}

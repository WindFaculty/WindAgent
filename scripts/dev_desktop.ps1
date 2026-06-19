<#
scripts/dev_desktop.ps1
Phase 9 — Frontend launcher cho WindAgent React + Tauri shell.

Tham số:
  -NoInstall          Bỏ qua npm install (dùng khi node_modules đã có)
  -Port <int>         Port Vite dev (mặc định 5173, khớp tauri.conf.json devUrl)
  -Tauri              Cố gắng chạy `npm run tauri dev` (cần Rust + tauri-cli)
  -NoProxy            Không ghi nhắc proxy backend

Hành vi:
  1. Đảm bảo Node + npm có sẵn; nếu node không nằm trong PATH, thử các
     đường dẫn phổ biến trên Windows (Program Files\nodejs).
  2. cd apps/desktop; nếu thiếu node_modules → `npm install --ignore-scripts`
     (flag này tránh esbuild postinstall chạy qua cmd.exe mà thiếu PATH Node
     trên Windows; Phase 6 enhancement đã verify).
  3. Nếu -Tauri: thử `npm run tauri dev`. Nếu thiếu Rust/tauri-cli sẽ in
     hướng dẫn cài và fallback về `npm run dev` (chỉ Vite).
  4. Ctrl+C tắt sạch tiến trình con.
#>
[CmdletBinding()]
param(
    [switch]$NoInstall,
    [int]$Port = 5173,
    [switch]$Tauri = $false,
    [switch]$NoProxy
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DesktopDir = Join-Path $RepoRoot "apps\desktop"

# PowerShell 5.1 console mặc định cp1252 — set UTF-8 để in đúng tiếng Việt.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

if (-not (Test-Path $DesktopDir)) {
    Write-Host "[dev_desktop] FAIL: không tìm thấy $DesktopDir" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $DesktopDir "package.json"))) {
    Write-Host "[dev_desktop] FAIL: thiếu package.json trong apps/desktop" -ForegroundColor Red
    exit 1
}

# --- Node + npm ---
function Add-NodeToPath {
    $candidates = @(
        "$env:ProgramFiles\nodejs",
        "${env:ProgramFiles(x86)}\nodejs",
        "$env:APPDATA\nvm",
        "$env:APPDATA\fnm\node-versions"
    )
    foreach ($c in $candidates) {
        if (Test-Path (Join-Path $c "node.exe")) {
            $env:PATH = "$c;$env:PATH"
            Write-Host "[dev_desktop] Thêm Node vào PATH: $c" -ForegroundColor DarkGray
            return $true
        }
    }
    return $false
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    if (-not (Add-NodeToPath)) {
        Write-Host "[dev_desktop] FAIL: chưa cài Node.js >= 18" -ForegroundColor Red
        Write-Host "  Tải tại: https://nodejs.org/" -ForegroundColor DarkGray
        exit 1
    }
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "[dev_desktop] FAIL: thiếu npm" -ForegroundColor Red
    exit 1
}

$nodeVer = (& node --version) -replace '^v', ''
Write-Host "[dev_desktop] node: $nodeVer, npm: $((& npm --version))" -ForegroundColor DarkGray

# --- npm install nếu cần ---
$nodeModules = Join-Path $DesktopDir "node_modules"
$packageJson = Join-Path $DesktopDir "package.json"
$needsInstall = $false
if (-not (Test-Path $nodeModules)) { $needsInstall = $true }
elseif ((Get-Item $packageJson).LastWriteTime -gt (Get-Item $nodeModules).LastWriteTime) {
    $needsInstall = $true
}

if (-not $NoInstall -and $needsInstall) {
    Write-Host "[dev_desktop] Cài npm packages (--ignore-scripts)..." -ForegroundColor Cyan
    Push-Location $DesktopDir
    try {
        # --ignore-scripts: bỏ esbuild postinstall chạy qua cmd.exe thiếu PATH Node
        & npm install --ignore-scripts
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[dev_desktop] FAIL: npm install lỗi" -ForegroundColor Red
            Pop-Location
            exit 1
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[dev_desktop] Bỏ qua npm install (node_modules đã sẵn sàng)" -ForegroundColor DarkGray
}

# --- Nhắc proxy backend ---
if (-not $NoProxy) {
    Write-Host "[dev_desktop] Lưu ý: Vite proxy /api + /ws tới http://127.0.0.1:8765" -ForegroundColor DarkGray
    Write-Host "[dev_desktop] Đảm bảo backend đang chạy (xem scripts/dev_backend.ps1)" -ForegroundColor DarkGray
}

# Thêm node_modules/.bin vào PATH — npm script trên Windows không tự
# thêm vào PATH cho cmd.exe con, nên 'vite' / 'tauri' không tìm được.
$env:PATH = "$DesktopDir\node_modules\.bin;$env:PATH"
if ($env:ProgramFiles) {
    $nodeExe = Join-Path $env:ProgramFiles "nodejs"
    if (Test-Path (Join-Path $nodeExe "node.exe")) {
        $env:PATH = "$nodeExe;$env:PATH"
    }
}

# --- Chạy Tauri hoặc Vite ---
Push-Location $DesktopDir
try {
    if ($Tauri) {
        Write-Host "[dev_desktop] Chạy Tauri dev (cần Rust + tauri-cli)..." -ForegroundColor Green
        Write-Host "[dev_desktop] Lưu ý: nếu thiếu Rust, Tauri sẽ báo 'cargo not found' và thoát." -ForegroundColor DarkGray
        & npm run tauri dev
    } else {
        Write-Host "[dev_desktop] Chạy Vite dev tại http://localhost:${Port}" -ForegroundColor Green
        Write-Host "[dev_desktop] (Tauri shell yêu cầu Rust — bật flag -Tauri nếu đã cài)" -ForegroundColor DarkGray
        Write-Host "[dev_desktop] Ctrl+C để tắt." -ForegroundColor DarkGray
        # Gọi vite qua node trực tiếp — tránh npm script trên Windows không
        # tự thêm node_modules/.bin vào PATH cho cmd.exe con.
        $viteJs = Join-Path $DesktopDir "node_modules\vite\bin\vite.js"
        if (Test-Path $viteJs) {
            & node $viteJs --port $Port --strictPort
        } else {
            & npm run dev -- --port $Port --strictPort
        }
    }
} finally {
    Pop-Location
    Write-Host "[dev_desktop] Đã tắt." -ForegroundColor DarkGray
}

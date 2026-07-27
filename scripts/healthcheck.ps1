<#
scripts/healthcheck.ps1
Phase 9 — Healthcheck môi trường cho WindAgent MVP.

Kiểm tra:
  [CRIT] Python >= 3.10
  [CRIT] uv (package manager cho workspace)
  [CRIT] node + npm >= 18
  [CRIT] root workspace + apps/api + apps/worker + apps/cli manifests tồn tại
  [CRIT] apps/desktop/package.json tồn tại
  [OPT]  Rust + cargo + tauri CLI (cho Tauri build; Phase 9 defer OK)
  [OPT]  Ollama chạy ở localhost:11434
  [OPT]  Model qwen3:4b-q4 đã pull
  [OPT]  Architecture V2 API /health/live trả OK (chỉ check nếu cổng mở)
  [OPT]  Vite dev server chạy ở :5173
  [WARN] artifacts/logs writable

Tham số:
  -BackendUrl <url>    URL backend để probe /health (mặc định http://127.0.0.1:8765)
  -SkipBackend         Bỏ qua probe backend (khi backend chưa chạy)
  -Quiet               Chỉ in FAIL + summary

Exit code: 0 nếu tất cả CRIT pass; 1 nếu có CRIT fail.
#>
[CmdletBinding()]
param(
    [string]$BackendUrl = "http://127.0.0.1:8765",
    [switch]$SkipBackend,
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ApiDir = Join-Path $RepoRoot "apps\api"
$WorkerDir = Join-Path $RepoRoot "apps\worker"
$CliDir = Join-Path $RepoRoot "apps\cli"
$DesktopDir = Join-Path $RepoRoot "apps\desktop"
$LogsDir = Join-Path $RepoRoot "artifacts\logs"

# PowerShell 5.1 console mặc định cp1252 — set UTF-8 để in đúng tiếng Việt.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

$failCount = 0
$warnCount = 0
$passCount = 0
$skipCount = 0
$results = @()

function Write-Item {
    param([string]$Name, [string]$Status, [string]$Level = "CRIT", [string]$Detail = "")
    $color = switch ($Status) {
        "PASS" { "Green" }
        "WARN" { "Yellow" }
        "FAIL" { "Red" }
        "SKIP" { "DarkGray" }
    }
    $line = "  [{0,-4}] {1,-40} [{2,-4}] {3}" -f $Status, $Name, $Level, $Detail
    if ($Quiet -and $Status -ne "FAIL") { return }
    Write-Host $line -ForegroundColor $color
    $script:results += [PSCustomObject]@{
        Name = $Name; Status = $Status; Level = $Level; Detail = $Detail
    }
    switch ($Status) {
        "PASS" { $script:passCount++ }
        "WARN" { $script:warnCount++ }
        "FAIL" { $script:failCount++ }
        "SKIP" { $script:skipCount++ }
    }
}

function Get-SemverMajorMinor {
    param([string]$VersionString)
    if ($VersionString -match '(\d+)\.(\d+)') {
        return [int]$matches[1], [int]$matches[2]
    }
    return 0, 0
}

Write-Host ""
Write-Host "=== WindAgent MVP Healthcheck ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Write-Host "Backend URL: $BackendUrl"
Write-Host ""

# 1. Python
$pythonCmd = $null
foreach ($c in @("python", "python3", "py")) {
    if (Get-Command $c -ErrorAction SilentlyContinue) { $pythonCmd = $c; break }
}
if ($pythonCmd) {
    $pyVer = & $pythonCmd --version 2>&1
    $maj, $min = Get-SemverMajorMinor $pyVer
    if ($maj -ge 3 -and $min -ge 10) {
        Write-Item "Python" "PASS" "CRIT" "$pyVer ($pythonCmd)"
    } else {
        Write-Item "Python" "FAIL" "CRIT" "$pyVer — cần >= 3.10"
    }
} else {
    Write-Item "Python" "FAIL" "CRIT" "không tìm thấy python trong PATH"
}

# 2. uv
$uvPath = $null
if (Get-Command uv -ErrorAction SilentlyContinue) { $uvPath = (Get-Command uv).Source }
else {
    $candidates = @(
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:LOCALAPPDATA\Programs\uv\uv.exe",
        "$env:USERPROFILE\AppData\Local\hermes\hermes-agent\venv\Scripts\uv.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { $uvPath = $c; break } }
}
if ($uvPath) {
    $uvVer = & $uvPath --version 2>&1
    Write-Item "uv" "PASS" "CRIT" "$uvVer ($uvPath)"
} else {
    Write-Item "uv" "FAIL" "CRIT" "chưa cài — irm https://astral.sh/uv/install.ps1 | iex"
}

# 3. Node + npm
if (Get-Command node -ErrorAction SilentlyContinue) {
    $nodeVer = (& node --version) -replace '^v', ''
    $maj, $min = Get-SemverMajorMinor $nodeVer
    if ($maj -ge 18) {
        if (Get-Command npm -ErrorAction SilentlyContinue) {
            $npmVer = & npm --version
            Write-Item "node + npm" "PASS" "CRIT" "node v$nodeVer, npm $npmVer"
        } else {
            Write-Item "node + npm" "FAIL" "CRIT" "có node nhưng thiếu npm"
        }
    } else {
        Write-Item "node + npm" "FAIL" "CRIT" "node v$nodeVer — cần >= 18"
    }
} else {
    Write-Item "node + npm" "FAIL" "CRIT" "chưa cài — https://nodejs.org/"
}

# 4. Canonical workspace manifests
$workspaceManifests = @(
    (Join-Path $RepoRoot "pyproject.toml"),
    (Join-Path $RepoRoot "uv.lock"),
    (Join-Path $ApiDir "pyproject.toml"),
    (Join-Path $WorkerDir "pyproject.toml"),
    (Join-Path $CliDir "pyproject.toml")
)
$missingManifests = @($workspaceManifests | Where-Object { -not (Test-Path $_) })
if ($missingManifests.Count -eq 0) {
    Write-Item "canonical workspace manifests" "PASS" "CRIT" "root + API + Worker + CLI"
} else {
    Write-Item "canonical workspace manifests" "FAIL" "CRIT" "thiếu: $($missingManifests -join ', ')"
}

# 5. package.json desktop
if (Test-Path (Join-Path $DesktopDir "package.json")) {
    Write-Item "apps/desktop manifest" "PASS" "CRIT" "package.json"
} else {
    Write-Item "apps/desktop manifest" "FAIL" "CRIT" "thiếu package.json"
}

# 7. Rust + Tauri CLI
$hasRust = $false
if (Get-Command cargo -ErrorAction SilentlyContinue) {
    $rustVer = & cargo --version
    $hasRust = $true
    Write-Item "Rust + cargo" "PASS" "OPT" $rustVer
} else {
    Write-Item "Rust + cargo" "WARN" "OPT" "chưa cài — Tauri build defer; dùng Vite dev"
}
$hasTauri = $false
if (& npm exec --no -- tauri --version 2>$null) {
    $tauriVer = & npm exec --no -- tauri --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $hasTauri = $true
        Write-Item "Tauri CLI" "PASS" "OPT" $tauriVer
    }
}
if (-not $hasTauri) {
    Write-Item "Tauri CLI" "WARN" "OPT" "chưa cài — 'npm install -D @tauri-apps/cli' (Phase 9 defer OK)"
}

# 8. Ollama
$ollama = $null
if (Get-Command ollama -ErrorAction SilentlyContinue) { $ollama = (Get-Command ollama).Source }
if ($ollama) {
    $tags = $null
    try {
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 3
        $hasQwen = $false
        if ($tags -and $tags.models) {
            foreach ($m in $tags.models) {
                if ($m.name -like "qwen3*") { $hasQwen = $true; break }
            }
        }
        if ($hasQwen) {
            Write-Item "Ollama" "PASS" "OPT" "running + qwen3:* đã pull"
        } else {
            Write-Item "Ollama" "WARN" "OPT" "running nhưng chưa pull qwen3:* — 'ollama pull qwen3:4b'"
        }
    } catch {
        Write-Item "Ollama" "WARN" "OPT" "$ollama có nhưng không chạy (mở app Ollama)"
    }
} else {
    Write-Item "Ollama" "WARN" "OPT" "chưa cài — backend sẽ dùng mock planner"
}

# 9. Backend /health
if ($SkipBackend) {
        Write-Item "API /health/live" "SKIP" "OPT" "bỏ qua theo -SkipBackend"
} else {
    try {
        $health = Invoke-RestMethod -Uri "$BackendUrl/health/live" -Method Get -TimeoutSec 3
        $status = $health.status
        if ($status -eq "live") {
            Write-Item "API /health/live" "PASS" "OPT" "$BackendUrl/health/live → live"
        } else {
            Write-Item "API /health/live" "WARN" "OPT" "trả $status"
        }
    } catch {
        Write-Item "API /health/live" "WARN" "OPT" "chưa chạy ($BackendUrl) — 'scripts/dev_api.ps1'"
    }
}

# 10. Vite dev server
if (-not $SkipBackend) {
    # Vite mặc định bind ::1 (IPv6 localhost) — thử cả hai
    $viteHosts = @("http://localhost:5173", "http://127.0.0.1:5173")
    $viteOk = $false
    $viteLastErr = ""
    foreach ($url in $viteHosts) {
        try {
            $resp = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 2 -UseBasicParsing
            if ($resp.StatusCode -eq 200) {
                Write-Item "Vite dev :5173" "PASS" "OPT" "$url → running"
                $viteOk = $true
                break
            }
        } catch {
            $viteLastErr = $_.Exception.Message
        }
    }
    if (-not $viteOk) {
        Write-Item "Vite dev :5173" "WARN" "OPT" "chưa chạy — 'scripts/dev_desktop.ps1' (last: $viteLastErr)"
    }
}

# 11. artifacts/logs writable
try {
    if (-not (Test-Path $LogsDir)) { New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null }
    $probe = Join-Path $LogsDir ".healthcheck-probe"
    "probe" | Out-File -FilePath $probe -Encoding utf8 -ErrorAction Stop
    Remove-Item $probe -ErrorAction SilentlyContinue
    Write-Item "artifacts/logs writable" "PASS" "INFO" $LogsDir
} catch {
    Write-Item "artifacts/logs writable" "WARN" "INFO" "không ghi được: $($_.Exception.Message)"
}

# --- Summary ---
Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ("  PASS: {0}    WARN: {1}    SKIP: {2}    FAIL: {3}" -f $passCount, $warnCount, $skipCount, $failCount)

if ($failCount -gt 0) {
    Write-Host ""
    Write-Host "Có $failCount mục CRIT bị FAIL. Sửa các mục trên trước khi chạy MVP." -ForegroundColor Red
    exit 1
} else {
    Write-Host ""
    Write-Host "Tất cả CRIT đã PASS. MVP sẵn sàng khởi động." -ForegroundColor Green
    Write-Host "  scripts/dev_api.ps1        # Terminal 1: API" -ForegroundColor DarkGray
    Write-Host "  scripts/dev_desktop.ps1    # Terminal 2: frontend" -ForegroundColor DarkGray
    exit 0
}


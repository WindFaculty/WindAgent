<#
scripts/healthcheck.ps1
Healthcheck moi truong cho WindAgent.

Kiem tra:
  [CRIT] Python >= 3.10
  [CRIT] uv (package manager cho workspace)
  [CRIT] node + npm >= 18
  [CRIT] root workspace + apps/api + apps/worker + apps/cli manifests ton tai
  [CRIT] apps/web & apps/desktop manifests ton tai
  [OPT]  Rust + cargo + tauri CLI
  [OPT]  Ollama chay o localhost:11434
  [OPT]  Model qwen3:4b-q4 da pull
  [OPT]  Architecture V3 API /health/live tra OK
  [OPT]  Vite dev server chay o :5173
  [WARN] artifacts/logs writable
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
$WebDir = Join-Path $RepoRoot "apps\web"
$LogsDir = Join-Path $RepoRoot "artifacts\logs"

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
        Write-Item "Python" "FAIL" "CRIT" "$pyVer - can >= 3.10"
    }
} else {
    Write-Item "Python" "FAIL" "CRIT" "khong tim thay python trong PATH"
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
    Write-Item "uv" "FAIL" "CRIT" "chua cai - irm https://astral.sh/uv/install.ps1 | iex"
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
            Write-Item "node + npm" "FAIL" "CRIT" "co node nhung thieu npm"
        }
    } else {
        Write-Item "node + npm" "FAIL" "CRIT" "node v$nodeVer - can >= 18"
    }
} else {
    Write-Item "node + npm" "FAIL" "CRIT" "chua cai - https://nodejs.org/"
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
    Write-Item "canonical workspace manifests" "FAIL" "CRIT" "thieu: $($missingManifests -join ', ')"
}

# 5. Frontend manifests (apps/web & apps/desktop)
$hasWebManifest = Test-Path (Join-Path $WebDir "package.json")
$hasDesktopManifest = Test-Path (Join-Path $DesktopDir "package.json")

if ($hasWebManifest -and $hasDesktopManifest) {
    Write-Item "frontend manifests" "PASS" "CRIT" "apps/web & apps/desktop package.json"
} else {
    Write-Item "frontend manifests" "FAIL" "CRIT" "thieu package.json trong apps/web hoac apps/desktop"
}

# 7. Rust + Tauri CLI
$hasRust = $false
if (Get-Command cargo -ErrorAction SilentlyContinue) {
    $rustVer = & cargo --version
    $hasRust = $true
    Write-Item "Rust + cargo" "PASS" "OPT" $rustVer
} else {
    Write-Item "Rust + cargo" "WARN" "OPT" "chua cai - Tauri build defer; dung Vite dev"
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
    Write-Item "Tauri CLI" "WARN" "OPT" "chua cai - 'npm install -D @tauri-apps/cli' (Phase 9 defer OK)"
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
            Write-Item "Ollama" "PASS" "OPT" "running + qwen3:* da pull"
        } else {
            Write-Item "Ollama" "WARN" "OPT" "running nhung chua pull qwen3:* - 'ollama pull qwen3:4b'"
        }
    } catch {
        Write-Item "Ollama" "WARN" "OPT" "$ollama co nhung khong chay (mo app Ollama)"
    }
} else {
    Write-Item "Ollama" "WARN" "OPT" "chua cai - backend se dung mock planner"
}

# 9. Backend /health
if ($SkipBackend) {
    Write-Item "API /health/live" "SKIP" "OPT" "bo qua theo -SkipBackend"
} else {
    try {
        $health = Invoke-RestMethod -Uri "$BackendUrl/health/live" -Method Get -TimeoutSec 3
        $status = $health.status
        if ($status -eq "live") {
            Write-Item "API /health/live" "PASS" "OPT" "$BackendUrl/health/live -> live"
        } else {
            Write-Item "API /health/live" "WARN" "OPT" "tra $status"
        }
    } catch {
        Write-Item "API /health/live" "WARN" "OPT" "chua chay ($BackendUrl) - 'scripts/dev_api.ps1'"
    }
}

# 10. Vite dev server
if (-not $SkipBackend) {
    $viteHosts = @("http://localhost:5173", "http://127.0.0.1:5173")
    $viteOk = $false
    $viteLastErr = ""
    foreach ($url in $viteHosts) {
        try {
            $resp = Invoke-WebRequest -Uri $url -Method Get -TimeoutSec 2 -UseBasicParsing
            if ($resp.StatusCode -eq 200) {
                Write-Item "Vite dev :5173" "PASS" "OPT" "$url -> running"
                $viteOk = $true
                break
            }
        } catch {
            $viteLastErr = $_.Exception.Message
        }
    }
    if (-not $viteOk) {
        Write-Item "Vite dev :5173" "WARN" "OPT" "chua chay - 'scripts/dev_frontend.ps1' (last: $viteLastErr)"
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
    Write-Item "artifacts/logs writable" "WARN" "INFO" "khong ghi duoc: $($_.Exception.Message)"
}

# --- Summary ---
Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
Write-Host ("  PASS: {0}    WARN: {1}    SKIP: {2}    FAIL: {3}" -f $passCount, $warnCount, $skipCount, $failCount)

if ($failCount -gt 0) {
    Write-Host ""
    Write-Host "Co $failCount muc CRIT bi FAIL. Sua cac muc tren truoc khi chay MVP." -ForegroundColor Red
    exit 1
} else {
    Write-Host ""
    Write-Host "Tat ca CRIT da PASS. MVP san sang khoi dong." -ForegroundColor Green
    Write-Host "  scripts/dev_api.ps1        # Terminal 1: API" -ForegroundColor DarkGray
    Write-Host "  scripts/dev_frontend.ps1   # Terminal 2: Web UI (apps/web)" -ForegroundColor DarkGray
    Write-Host "  scripts/dev_desktop.ps1    # Terminal 3: Desktop UI (apps/desktop)" -ForegroundColor DarkGray
    exit 0
}

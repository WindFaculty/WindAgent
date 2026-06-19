<#
scripts/setup_agent_s3.ps1
Agent-S3 installer / setup helper for WindAgent.

Mode:
  -Mode package     Cài PyPI `gui-agents==0.3.2` vào backend venv bằng uv
                    (mặc định, khuyến nghị).
  -Mode external    Clone https://github.com/simular-ai/Agent-S vào
                    external/Agent-S (submodule hoặc plain clone).

Tham số:
  -Mode <pkg|ext>       Chọn install mode. Mặc định "package".
  -PackageVersion       Phiên bản PyPI (mặc định 0.3.2).
  -ExternalPath         Đường dẫn clone (mặc định external/Agent-S).
  -UseSubmodule         Dùng `git submodule add` thay vì `git clone`.
  -NoBackend            Không cài vào backend venv (chỉ clone / submodule).
  -Uninstall            Gỡ `gui-agents` khỏi backend venv (chỉ áp dụng mode=package).
  -BackendDir <path>    Override apps/backend (mặc định tự tìm).
  -PythonExe <path>     Override python.exe dùng để check import (mặc định .venv\Scripts\python.exe).

Hành vi:
  1. Check Python >= 3.10 + uv (nếu cần cài package).
  2. Mode=package:
       uv pip install "gui-agents==<PackageVersion>" (optional-deps).
       Verify import thành công.
  3. Mode=external:
       Tạo thư mục external/ nếu chưa có.
       git submodule add HOẶC git clone vào ExternalPath.
       Verify thư mục gui_agents/ tồn tại trong checkout.
  4. In hướng dẫn các env var cần set trước khi bật Agent-S3:
       WINDAGENT_AGENT_S3_ENABLED=1
       WINDAGENT_AGENT_S3_SOURCE=package|external
       WINDAGENT_AGENT_S3_PROVIDER / MODEL / GROUND_*

Exit code:
  0  thành công
  1  thiếu tool (python/uv/git)
  2  install/clone lỗi
  3  verify thất bại (package không import / clone không có gui_agents/)
#>
[CmdletBinding()]
param(
    [ValidateSet("package", "external")]
    [string]$Mode = "package",
    [string]$PackageVersion = "0.3.2",
    [string]$ExternalPath = "external/Agent-S",
    [switch]$UseSubmodule,
    [switch]$NoBackend,
    [switch]$Uninstall,
    [string]$BackendDir,
    [string]$PythonExe
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $BackendDir) {
    $BackendDir = Join-Path $RepoRoot "apps\backend"
}
if (-not $PythonExe) {
    $PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
}

# PowerShell 5.1 console mặc định cp1252 — set UTF-8.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

function Write-Section {
    param([string]$Text)
    Write-Host ""
    Write-Host "==== $Text ====" -ForegroundColor Cyan
}

function Test-PythonVersion {
    param([string]$Exe)
    if (-not (Test-Path $Exe)) {
        Write-Host "[setup_agent_s3] FAIL: không tìm thấy python tại $Exe" -ForegroundColor Red
        return $false
    }
    $raw = & $Exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if (-not $raw) {
        Write-Host "[setup_agent_s3] FAIL: không chạy được $Exe --version" -ForegroundColor Red
        return $false
    }
    $parts = $raw.Split('.')
    if ($parts.Count -lt 2) { return $false }
    $major = [int]$parts[0]; $minor = [int]$parts[1]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Write-Host "[setup_agent_s3] FAIL: Python $raw < 3.10 (cần >= 3.10 cho gui-agents)." -ForegroundColor Red
        return $false
    }
    Write-Host "[setup_agent_s3] OK: Python $raw" -ForegroundColor Green
    return $true
}

function Find-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        return (Get-Command uv).Source
    }
    $candidates = @(
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:LOCALAPPDATA\Programs\uv\uv.exe",
        "$env:USERPROFILE\AppData\Local\hermes\hermes-agent\venv\Scripts\uv.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    return $null
}

function Find-Git {
    if (Get-Command git -ErrorAction SilentlyContinue) {
        return (Get-Command git).Source
    }
    $candidates = @(
        "$env:ProgramFiles\Git\bin\git.exe",
        "$env:ProgramFiles(x86)\Git\bin\git.exe",
        "C:\Program Files\Git\bin\git.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    return $null
}

# --- Preflight ---
Write-Section "Preflight"

if (-not (Test-PythonVersion -Exe $PythonExe)) {
    exit 1
}

if (-not (Test-Path $BackendDir)) {
    Write-Host "[setup_agent_s3] FAIL: không tìm thấy $BackendDir" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $BackendDir "pyproject.toml"))) {
    Write-Host "[setup_agent_s3] FAIL: thiếu pyproject.toml trong $BackendDir" -ForegroundColor Red
    exit 1
}

# --- Uninstall path ---
if ($Uninstall) {
    if ($Mode -ne "package") {
        Write-Host "[setup_agent_s3] --Uninstall chỉ áp dụng cho -Mode package" -ForegroundColor Yellow
    } else {
        Write-Section "Uninstall package"
        $uv = Find-Uv
        if (-not $uv) {
            Write-Host "[setup_agent_s3] FAIL: cần uv để uninstall" -ForegroundColor Red
            exit 1
        }
        Push-Location $BackendDir
        try {
            & $uv pip uninstall gui-agents
        } finally {
            Pop-Location
        }
        Write-Host "[setup_agent_s3] OK: đã gỡ gui-agents" -ForegroundColor Green
    }
    exit 0
}

# --- Install ---
switch ($Mode) {
    "package" {
        Write-Section "Mode: package (PyPI gui-agents==$PackageVersion)"

        $uv = Find-Uv
        if (-not $uv) {
            Write-Host "[setup_agent_s3] FAIL: thiếu uv. Cài từ https://docs.astral.sh/uv/" -ForegroundColor Red
            exit 1
        }
        Write-Host "[setup_agent_s3] uv: $uv" -ForegroundColor Green

        if (-not $NoBackend) {
            Push-Location $BackendDir
            try {
                # Pin exact version so the safety contract is reproducible.
                & $uv pip install "gui-agents==$PackageVersion"
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "[setup_agent_s3] FAIL: uv pip install lỗi (exit=$LASTEXITCODE)" -ForegroundColor Red
                    exit 2
                }
            } finally {
                Pop-Location
            }
        } else {
            Write-Host "[setup_agent_s3] --NoBackend: bỏ qua cài vào backend venv" -ForegroundColor Yellow
        }

        # Verify import.
        Write-Section "Verify import"
        $verOut = & $PythonExe -c "import gui_agents, sys; print('gui_agents OK', getattr(gui_agents, '__version__', 'unknown'))" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[setup_agent_s3] FAIL: import gui_agents thất bại:" -ForegroundColor Red
            Write-Host $verOut
            exit 3
        }
        Write-Host "[setup_agent_s3] $($verOut.Trim())" -ForegroundColor Green
    }

    "external" {
        Write-Section "Mode: external (clone/submodule Agent-S)"

        $git = Find-Git
        if (-not $git) {
            Write-Host "[setup_agent_s3] FAIL: thiếu git. Cài Git for Windows trước." -ForegroundColor Red
            exit 1
        }
        Write-Host "[setup_agent_s3] git: $git" -ForegroundColor Green

        $externalAbs = Join-Path $RepoRoot "external"
        $targetAbs = Join-Path $RepoRoot $ExternalPath
        if (-not (Test-Path $externalAbs)) {
            New-Item -ItemType Directory -Path $externalAbs -Force | Out-Null
            Write-Host "[setup_agent_s3] Tạo thư mục external/" -ForegroundColor Green
        }

        if ($UseSubmodule) {
            Push-Location $RepoRoot
            try {
                if (Test-Path $targetAbs) {
                    Write-Host "[setup_agent_s3] Đã có $ExternalPath. Bỏ qua submodule add." -ForegroundColor Yellow
                } else {
                    & $git submodule add https://github.com/simular-ai/Agent-S $ExternalPath
                    if ($LASTEXITCODE -ne 0) {
                        Write-Host "[setup_agent_s3] FAIL: git submodule add lỗi" -ForegroundColor Red
                        exit 2
                    }
                }
            } finally {
                Pop-Location
            }
        } else {
            if (Test-Path $targetAbs) {
                Write-Host "[setup_agent_s3] Đã có $ExternalPath. Bỏ qua clone." -ForegroundColor Yellow
            } else {
                Push-Location $externalAbs
                try {
                    & $git clone https://github.com/simular-ai/Agent-S (Split-Path $ExternalPath -Leaf)
                    if ($LASTEXITCODE -ne 0) {
                        Write-Host "[setup_agent_s3] FAIL: git clone lỗi" -ForegroundColor Red
                        exit 2
                    }
                } finally {
                    Pop-Location
                }
            }
        }

        # Verify checkout structure.
        $checkDirs = @(
            (Join-Path $targetAbs "gui_agents"),
            (Join-Path $targetAbs "agent_s")
        )
        $found = $false
        foreach ($d in $checkDirs) {
            if (Test-Path $d) { $found = $true; break }
        }
        if (-not $found) {
            Write-Host "[setup_agent_s3] FAIL: checkout tại $targetAbs không chứa gui_agents/ hoặc agent_s/" -ForegroundColor Red
            exit 3
        }
        Write-Host "[setup_agent_s3] OK: checkout có package directory" -ForegroundColor Green
    }
}

# --- Final hints ---
Write-Section "Cách bật Agent-S3 trong WindAgent"
Write-Host "Thêm các biến môi trường sau trước khi chạy backend:"
Write-Host ""
Write-Host "  `$env:WINDAGENT_AGENT_S3_ENABLED         = '1'"
Write-Host "  `$env:WINDAGENT_AGENT_S3_SOURCE          = '$Mode'"
if ($Mode -eq "external") {
    Write-Host "  `$env:WINDAGENT_AGENT_S3_EXTERNAL_PATH   = '$ExternalPath'"
}
Write-Host "  `$env:WINDAGENT_AGENT_S3_PROVIDER        = 'openai'"
Write-Host "  `$env:WINDAGENT_AGENT_S3_MODEL           = 'gpt-5-2025-08-07'"
Write-Host "  `$env:WINDAGENT_AGENT_S3_GROUND_PROVIDER = 'huggingface'"
Write-Host "  `$env:WINDAGENT_AGENT_S3_GROUND_MODEL    = 'ui-tars-1.5-7b'"
Write-Host "  `$env:WINDAGENT_AGENT_S3_MODEL_API_KEY   = '...'"
Write-Host "  `$env:WINDAGENT_AGENT_S3_GROUND_API_KEY  = '...'"
Write-Host ""
Write-Host "Sau đó chạy:  pwsh scripts/dev_backend.ps1"
Write-Host "Kiểm tra:     GET http://127.0.0.1:8765/agent-s3/health"
Write-Host "Tắt:          `$env:WINDAGENT_AGENT_S3_ENABLED = '0'"
Write-Host ""
Write-Host "Done." -ForegroundColor Green
exit 0
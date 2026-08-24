# Builds the native recording sidecar and stages it for Tauri bundling.
#
# Usage:  npm run build:sidecar   (from apps/desktop)
#
# Tauri `bundle.externalBin` expects the binary at
#   src-tauri/binaries/windagent-recorder-<target-triple>(.exe)
# At install time it is placed beside the host executable, where
# live_record::engine_host::EngineHost::locate_sidecar finds it.

$ErrorActionPreference = "Stop"

$desktopRoot = Split-Path -Parent $PSScriptRoot
$crateDir = Join-Path $desktopRoot "native\recording-engine"
$binDir = Join-Path $desktopRoot "src-tauri\binaries"

cargo build --release --manifest-path (Join-Path $crateDir "Cargo.toml") --bin windagent-recorder
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$triple = & rustc -Vv | Select-String "^host:" | ForEach-Object { $_.Line.Substring(5).Trim() }
if (-not $triple) { Write-Error "Could not detect rustc host target triple."; exit 1 }

$exeName = if ($triple -like "*windows*") { "windagent-recorder.exe" } else { "windagent-recorder" }
$src = Join-Path $crateDir "target\release\$exeName"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$dst = Join-Path $binDir "windagent-recorder-$triple$(if ($triple -like '*windows*') { '.exe' } else { '' })"

Copy-Item -LiteralPath $src -Destination $dst -Force
Write-Output "Staged sidecar: $dst"

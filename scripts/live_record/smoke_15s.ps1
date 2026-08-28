# Smoke test sidecar recorder trên máy thật (RTX 5060): probe capabilities,
# record 15 giây, stop, đối chiếu segment MKV bằng ffprobe.
# Wire protocol khớp EngineRequest (ipc/mod.rs): op = capabilities|prepare|
# start|pause|resume|stop|status|marker|sources.
# Profile V2 nested (EngineProfile, lib.rs) — flat V1 shape với audio_enabled
# đã bị validator fail-closed từ chối.
# Usage: powershell -File scripts/live_record/smoke_15s.ps1
$ErrorActionPreference = "Stop"

$bin = "D:\code_ca_nhan\WindAgent\apps\desktop\native\recording-engine\target\release\windagent-recorder.exe"
$out = "$env:TEMP\windagent_smoke_$(Get-Date -Format yyyyMMdd_HHmmss)"
New-Item -ItemType Directory $out | Out-Null

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $bin
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$p = [System.Diagnostics.Process]::Start($psi)

# Drain stdout/stderr trên thread riêng để pipe không đầy giữa chừng.
$stdoutText = $p.StandardOutput.ReadToEndAsync()
$stderrText = $p.StandardError.ReadToEndAsync()

function Send([string]$json) {
    $p.StandardInput.WriteLine($json)
    $p.StandardInput.Flush()
}

# Windows PowerShell 5.1 injects a UTF-8 BOM as the FIRST bytes written to a
# redirected child stdin, so the engine answers one ENGINE_REQUEST_MALFORMED
# for this warmup line. Harmless here (stdout is dumped, not matched 1:1); the
# soak harness uses Python precisely because of this quirk.
Write-Host "== warmup (swallow PS stdin BOM) =="
Send ''
Start-Sleep -Milliseconds 500

Write-Host "== capabilities =="
# Unit variants carry NO "args" content — serde internally-tagged enum rejects it.
Send '{"op":"capabilities"}'
Start-Sleep -Seconds 3

Write-Host "== prepare + start (15s soak) =="
$dirJson = ($out -replace '\\', '/')
$profileV2 = @{
    capture_source = @{ kind = 'DISPLAY'; id = '' }
    video = @{
        width = 1920; height = 1080; fps = 60
        encoder = 'NVENC'; codec = 'H264'
        rate_control = 'CQP'; cq = 16
        preset = 'P7'; multipass = 'FULL_RES'
        lookahead = 32; spatial_aq = $true; temporal_aq = $true
        b_frames = 3; gop_frames = 120
    }
    audio = @{
        microphone = @{ enabled = $true; device_id = '' }
        system     = @{ enabled = $true; device_id = '' }
        sample_rate = 48000; codec = 'AAC'
    }
    container = @{ format = 'MKV'; segment_minutes = 5 }
}
$prepareArgs = @{
    execution_plan_id   = 'plan_smoke'
    execution_plan_hash = ('0' * 64)
    episode_id          = 'ep_smoke'
    output_dir          = $dirJson
    profile             = $profileV2
}
$prepareJson = (@{ op = 'prepare'; args = $prepareArgs } | ConvertTo-Json -Depth 8 -Compress)
Send $prepareJson
Start-Sleep -Seconds 2
Send '{"op":"start","args":{"execution_plan_id":"plan_smoke","take_id":"take_smoke"}}'
Start-Sleep -Seconds 15

Write-Host "== stop + EOF =="
Send '{"op":"stop"}'
Start-Sleep -Seconds 3
$p.StandardInput.Close()
if (-not $p.WaitForExit(20000)) { Write-Warning "sidecar did not exit after stdin close"; $p.Kill() }

Write-Host "== sidecar stdout =="
$stdoutText.Result

# Products land under the take subdir ($out/<take_id>/), not the prepare
# output_dir itself.
$takeDir = Join-Path $out "take_smoke"

Write-Host "== products in $takeDir =="
Get-ChildItem $takeDir | Format-Table Name, Length

foreach ($mkv in Get-ChildItem $takeDir -Filter *.mkv) {
    ffprobe -v error -show_entries format=duration,size -of default=nw=1 $mkv.FullName
}
Write-Host "== timeline.jsonl (first 8 lines) =="
if (Test-Path "$takeDir\timeline.jsonl") { Get-Content "$takeDir\timeline.jsonl" | Select-Object -First 8 } else { Write-Warning "timeline.jsonl missing" }

# Smoke test sidecar recorder trên máy thật (RTX 5060): probe capabilities,
# record 15 giây, stop, đối chiếu segment MKV bằng ffprobe.
# Wire protocol khớp EngineRequest (ipc/mod.rs): op = capabilities|prepare|
# start|pause|resume|stop|status|marker.
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

Write-Host "== capabilities =="
Send '{"op":"capabilities","args":{}}'
Start-Sleep -Seconds 3

Write-Host "== prepare + start (15s soak) =="
$dirJson = ($out -replace '\\', '/')
Send ("{`"op`":`"prepare`",`"args`":{`"execution_plan_id`":`"plan_smoke`",`"execution_plan_hash`":`"" + ("0" * 64) + "`",`"episode_id`":`"ep_smoke`",`"output_dir`":`"$dirJson`",`"profile`":{`"resolution`":[1920,1080],`"fps`":60,`"codec`":`"H264`",`"segment_minutes`":5,`"audio_enabled`":false}}}")
Start-Sleep -Seconds 2
Send '{"op":"start","args":{"execution_plan_id":"plan_smoke","take_id":"take_smoke"}}'
Start-Sleep -Seconds 15

Write-Host "== stop + EOF =="
Send '{"op":"stop","args":{}}'
Start-Sleep -Seconds 3
$p.StandardInput.Close()
if (-not $p.WaitForExit(20000)) { Write-Warning "sidecar did not exit after stdin close"; $p.Kill() }

Write-Host "== sidecar stdout =="
$stdoutText.Result

Write-Host "== products in $out =="
Get-ChildItem $out | Format-Table Name, Length

foreach ($mkv in Get-ChildItem $out -Filter *.mkv) {
    ffprobe -v error -show_entries format=duration,size -of default=nw=1 $mkv.FullName
}
Write-Host "== timeline.jsonl (first 8 lines) =="
if (Test-Path "$out\timeline.jsonl") { Get-Content "$out\timeline.jsonl" | Select-Object -First 8 } else { Write-Warning "timeline.jsonl missing" }

//! EngineHost — spawns the recording-engine sidecar and bridges its JSONL
//! protocol onto the frozen Tauri surface (Phase 8/9).
//!
//! ```text
//! Tauri command ──► EngineHost.request(EngineRequest) ──► sidecar stdin  (JSONL)
//! Tauri event  ◄── EventSink.emit("recorder://…")     ◄── sidecar stdout (JSONL)
//! ```
//!
//! The host is strictly a bridge: it never interprets frames, never touches
//! ffmpeg itself and adds no fields to the frozen contract. When the sidecar
//! binary is absent (web dev / CI), [`EngineHost::locate_sidecar`] returns
//! `None` and the command layer fail-closes into BLOCKED exactly like Phase 0.

use std::collections::VecDeque;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::Value;
use tauri::{AppHandle, Emitter};

/// Where sidecar events go. Tauri forwards to the frontend via `app.emit`;
/// tests collect into a buffer instead.
pub trait EventSink: Send + Sync {
    fn emit(&self, channel: &str, payload: &Value);
}

impl<R: tauri::Runtime> EventSink for AppHandle<R> {
    fn emit(&self, channel: &str, payload: &Value) {
        // Explicit trait call — `Emitter::emit` would otherwise be ambiguous
        // with the inherent `EventSink::emit` on this same type.
        let _ = Emitter::emit(self, channel, payload.clone());
    }
}

/// Managed Tauri state holding the live sidecar host, if any.
#[derive(Default)]
pub struct EngineHostState(pub Mutex<Option<EngineHost>>);

/// Map an [EngineEvent]-style `{"type": …}` tag onto the frozen
/// `recorder://…` Tauri event names.
pub fn event_name_for(type_tag: &str) -> Option<&'static str> {
    match type_tag {
        "Status" => Some("recorder://status"),
        "Segment" => Some("recorder://segment"),
        "Preview" => Some("recorder://preview"),
        "Warning" => Some("recorder://warning"),
        "Error" => Some("recorder://error"),
        "Timeline" => Some("recorder://timeline"),
        // V2: per-track loudness meters (mic/system kept separate — §11).
        "AudioMeter" => Some("recorder://audio-meter"),
        _ => None,
    }
}

pub struct EngineHost {
    /// Shared with the exit-status reaper so it can `wait()` while requests
    /// keep flowing through stdin (the mutex is only held by teardown paths).
    child: Arc<Mutex<Child>>,
    stdin: Option<std::process::ChildStdin>,
    /// Responses awaiting their request. A queue (not a single slot) plus the
    /// op-match in [`EngineHost::request`] keeps pairing correct even if the
    /// sidecar ever emits an unsolicited response.
    pending_responses: Arc<Mutex<VecDeque<Value>>>,
    dead: Arc<AtomicBool>,
    /// Set before deliberate teardown (`shutdown`/`Drop`) so the reaper does
    /// not report an intentional exit as a crash.
    graceful: Arc<AtomicBool>,
    /// Process exit code once reaped (`None` until then or on signal death).
    exit_code: Arc<Mutex<Option<i32>>>,
    /// Last N stderr lines from the sidecar — attached to crash reports.
    stderr_tail: Arc<Mutex<VecDeque<String>>>,
}

impl EngineHost {
    /// Locate the sidecar binary: explicit env override first, then the
    /// executable's own directory (bundled builds), then cargo target dirs
    /// (dev runs from `src-tauri/target/{debug,release}`).
    pub fn locate_sidecar() -> Option<PathBuf> {
        if let Ok(path) = std::env::var("WINDAGENT_RECORDER_SIDECAR") {
            let p = PathBuf::from(path);
            // An explicit override wins even when missing (fail loud, not silent).
            return p.is_file().then_some(p);
        }

        let exe_name = if cfg!(windows) {
            "windagent-recorder.exe"
        } else {
            "windagent-recorder"
        };

        let mut candidates: Vec<PathBuf> = Vec::new();
        if let Ok(exe) = std::env::current_exe() {
            if let Some(dir) = exe.parent() {
                candidates.push(dir.join(exe_name));
                // Dev: <src-tauri>/target/debug/<exe> → sibling engine target dir.
                for profile in ["debug", "release"] {
                    candidates.push(
                        dir.join("../../native/recording-engine/target")
                            .join(profile)
                            .join(exe_name),
                    );
                }
            }
        }
        candidates.into_iter().find(|c| c.is_file())
    }

    /// Spawn the sidecar with piped stdio and start its pumps: stdout drives
    /// the JSONL protocol, stderr lands in a bounded diagnostic tail, and a
    /// reaper collects the exit code — surfacing any non-graceful death as a
    /// `recorder://error` crash event with the stderr tail attached.
    pub fn spawn(sidecar_path: PathBuf, sink: Arc<dyn EventSink>) -> Result<Self, String> {
        let mut command = Command::new(&sidecar_path);
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
        }

        let mut child = command
            .spawn()
            .map_err(|e| format!("ENGINE_SPAWN_FAILED: {e}"))?;
        let stdin = child.stdin.take().ok_or("ENGINE_STDIN_UNAVAILABLE")?;
        let stdout = child.stdout.take().ok_or("ENGINE_STDOUT_UNAVAILABLE")?;
        let stderr = child.stderr.take().ok_or("ENGINE_STDERR_UNAVAILABLE")?;

        let pending: Arc<Mutex<VecDeque<Value>>> = Arc::new(Mutex::new(VecDeque::new()));
        let dead = Arc::new(AtomicBool::new(false));
        let graceful = Arc::new(AtomicBool::new(false));
        let exit_code: Arc<Mutex<Option<i32>>> = Arc::new(Mutex::new(None));
        let stderr_tail: Arc<Mutex<VecDeque<String>>> = Arc::new(Mutex::new(VecDeque::new()));
        let child = Arc::new(Mutex::new(child));

        spawn_stdout_pump(stdout, sink.clone(), pending.clone(), dead.clone());
        spawn_stderr_capture(stderr, stderr_tail.clone());
        spawn_reaper(
            child.clone(),
            dead.clone(),
            graceful.clone(),
            exit_code.clone(),
            stderr_tail.clone(),
            sink,
        );

        Ok(Self {
            child,
            stdin: Some(stdin),
            pending_responses: pending,
            dead,
            graceful,
            exit_code,
            stderr_tail,
        })
    }

    pub fn is_alive(&self) -> bool {
        !self.dead.load(Ordering::Relaxed)
    }

    /// Exit code once the reaper has collected it.
    pub fn exit_code(&self) -> Option<i32> {
        *self.exit_code.lock().unwrap_or_else(|p| p.into_inner())
    }

    /// Most recent stderr lines (diagnostics for crash reports).
    pub fn recent_stderr(&self, max_lines: usize) -> Vec<String> {
        match self.stderr_tail.lock() {
            Ok(q) => q.iter().rev().take(max_lines).rev().cloned().collect(),
            Err(_) => Vec::new(),
        }
    }

    /// Send one request and wait (15 s deadline) for its response.
    pub fn request(&mut self, request: &Value) -> Result<Value, String> {
        self.request_with_timeout(request, Duration::from_secs(15))
    }

    /// Send one request and wait for its response. Events that arrive while
    /// waiting are forwarded immediately through the sink — the pump keeps
    /// streaming even when no request is in flight. Only a response whose
    /// `op` matches the request's `op` is accepted; anything else stays in
    /// the queue (protocol invariant: one response per request, §16).
    pub fn request_with_timeout(&mut self, request: &Value, timeout: Duration) -> Result<Value, String> {
        if !self.is_alive() {
            return Err("ENGINE_DEAD".into());
        }
        let Some(stdin) = self.stdin.as_mut() else {
            return Err("ENGINE_STDIN_CLOSED".into());
        };
        let line = serde_json::to_string(request)
            .map_err(|e| format!("ENGINE_REQUEST_SERIALIZE_FAILED: {e}"))?;
        writeln!(stdin, "{line}").map_err(|e| format!("ENGINE_WRITE_FAILED: {e}"))?;
        stdin.flush().map_err(|e| format!("ENGINE_FLUSH_FAILED: {e}"))?;

        let want_op = request.get("op").and_then(Value::as_str).unwrap_or("");
        let deadline = Instant::now() + timeout;
        loop {
            if let Ok(mut queue) = self.pending_responses.lock() {
                // Accept the first response that belongs to this op; leave any
                // stale/unsolicited ones queued for their own round-trip.
                if let Some(pos) = queue.iter().position(|resp| {
                    resp.get("op").and_then(Value::as_str) == Some(want_op)
                }) {
                    return Ok(queue.remove(pos).expect("pos is in bounds"));
                }
            }
            if !self.is_alive() {
                return Err("ENGINE_DIED_WHILE_PENDING".into());
            }
            if Instant::now() >= deadline {
                return Err("ENGINE_RESPONSE_TIMEOUT".into());
            }
            std::thread::sleep(Duration::from_millis(5));
        }
    }

    /// Graceful teardown: closing stdin tells the sidecar to stop recording.
    /// Marked graceful first so the reaper reports nothing.
    pub fn shutdown(mut self) {
        self.graceful.store(true, Ordering::Relaxed);
        if let Some(mut stdin) = self.stdin.take() {
            let _ = stdin.flush();
            // Dropping closes the pipe → sidecar drains and exits.
        }
        if let Ok(mut child) = self.child.lock() {
            let _ = child.wait();
        }
    }
}

impl Drop for EngineHost {
    fn drop(&mut self) {
        // Deliberate teardown (host replacement / app exit) — never a crash
        // report, even though we force-kill whatever is still running.
        self.graceful.store(true, Ordering::Relaxed);
        if let Ok(mut child) = self.child.lock() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

/// Bounded diagnostic capture of the sidecar's stderr (last 200 lines).
fn spawn_stderr_capture(stderr: std::process::ChildStderr, tail: Arc<Mutex<VecDeque<String>>>) {
    std::thread::spawn(move || {
        const STDERR_TAIL_CAP: usize = 200;
        for line in BufReader::new(stderr).lines() {
            let Ok(line) = line else { break };
            if let Ok(mut q) = tail.lock() {
                if q.len() >= STDERR_TAIL_CAP {
                    q.pop_front();
                }
                q.push_back(line);
            }
        }
    });
}

/// Reap the sidecar's real exit status. Any non-graceful, non-zero death is
/// surfaced as a crash event with the captured stderr tail attached — the UI
/// learns the engine died even when it dies between requests (§16 liveness).
fn spawn_reaper(
    child: Arc<Mutex<Child>>,
    dead: Arc<AtomicBool>,
    graceful: Arc<AtomicBool>,
    exit_code: Arc<Mutex<Option<i32>>>,
    stderr_tail: Arc<Mutex<VecDeque<String>>>,
    sink: Arc<dyn EventSink>,
) {
    std::thread::spawn(move || {
        // The lock is held for the whole wait — only shutdown/drop contend,
        // and they run after (or cause) process termination anyway.
        let status = child.lock().ok().and_then(|mut c| c.wait().ok());
        let code = status.and_then(|s| s.code());
        if let Ok(mut slot) = exit_code.lock() {
            *slot = code;
        }
        dead.store(true, Ordering::Relaxed);
        let clean = graceful.load(Ordering::Relaxed) || code == Some(0);
        if !clean {
            let tail: Vec<String> = stderr_tail
                .lock()
                .map(|q| q.iter().cloned().collect())
                .unwrap_or_default();
            sink.emit(
                "recorder://error",
                &serde_json::json!({
                    "type": "Error",
                    "message": format!(
                        "ENGINE_EXITED: recording sidecar terminated unexpectedly (exit_code={:?})",
                        code
                    ),
                    "stderr_tail": tail,
                }),
            );
        }
    });
}

fn spawn_stdout_pump(
    stdout: std::process::ChildStdout,
    sink: Arc<dyn EventSink>,
    pending: Arc<Mutex<VecDeque<Value>>>,
    dead: Arc<AtomicBool>,
) {
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines() {
            let Ok(line) = line else { break };
            let Ok(value) = serde_json::from_str::<Value>(&line) else {
                continue;
            };
            if value.get("resp").is_some() {
                if let Ok(mut queue) = pending.lock() {
                    queue.push_back(value);
                }
                continue;
            }
            match value.get("type").and_then(Value::as_str).and_then(event_name_for) {
                Some(channel) => sink.emit(channel, &value),
                None => continue,
            }
        }
        dead.store(true, Ordering::Relaxed);
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn event_names_match_frozen_contract() {
        assert_eq!(event_name_for("Status"), Some("recorder://status"));
        assert_eq!(event_name_for("Segment"), Some("recorder://segment"));
        assert_eq!(event_name_for("Preview"), Some("recorder://preview"));
        assert_eq!(event_name_for("Warning"), Some("recorder://warning"));
        assert_eq!(event_name_for("Error"), Some("recorder://error"));
        assert_eq!(event_name_for("Timeline"), Some("recorder://timeline"));
        assert_eq!(event_name_for("AudioMeter"), Some("recorder://audio-meter"));
        assert_eq!(event_name_for("Mystery"), None);
    }

    #[test]
    fn locate_sidecar_is_total_without_env_or_binary() {
        std::env::remove_var("WINDAGENT_RECORDER_SIDECAR");
        // Only asserts the call is total — presence depends on the machine.
        let _ = EngineHost::locate_sidecar();
    }

    #[test]
    fn explicit_sidecar_env_override_wins_even_when_missing() {
        let unique = std::env::temp_dir()
            .join(format!(
                "no_such_sidecar_{}",
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ))
            .to_string_lossy()
            .into_owned();
        std::env::set_var("WINDAGENT_RECORDER_SIDECAR", &unique);
        assert_eq!(EngineHost::locate_sidecar(), None);
        std::env::remove_var("WINDAGENT_RECORDER_SIDECAR");
    }

    #[derive(Default)]
    struct VecSink(Mutex<Vec<(String, Value)>>);

    impl EventSink for VecSink {
        fn emit(&self, channel: &str, payload: &Value) {
            if let Ok(mut buf) = self.0.lock() {
                buf.push((channel.to_string(), payload.clone()));
            }
        }
    }

    #[test]
    fn spawn_request_roundtrip_against_real_sidecar_if_present() {
        // Build artifact may or may not exist locally; when it does, exercise
        // the full protocol against the real binary (capabilities handshake).
        let Some(sidecar) = EngineHost::locate_sidecar() else {
            return;
        };
        let sink = Arc::new(VecSink::default());
        let mut host = match EngineHost::spawn(sidecar, sink.clone()) {
            Ok(h) => h,
            Err(_) => return,
        };
        for _ in 0..2 {
            let response =
                host.request(&serde_json::json!({"op": "capabilities"})).expect("handshake");
            assert_eq!(response["resp"], "ok");
            assert_eq!(response["op"], "capabilities");
            assert!(response["payload"]["engine_available"].is_boolean());
        }
        // An op that never matches anything must time out rather than steal a
        // queued response from another request.
        let err = host
            .request_with_timeout(&serde_json::json!({"op": "no_such_op_probe"}), Duration::from_millis(300))
            .unwrap_err();
        assert_eq!(err, "ENGINE_RESPONSE_TIMEOUT");
        assert!(!sink.0.lock().unwrap().is_empty(), "events must reach the sink");
        host.shutdown();
    }
}

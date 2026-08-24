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
        _ => None,
    }
}

pub struct EngineHost {
    child: Child,
    stdin: Option<std::process::ChildStdin>,
    pending_response: Arc<Mutex<Option<Value>>>,
    dead: Arc<AtomicBool>,
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

    /// Spawn the sidecar with piped stdio and start its stdout pump.
    pub fn spawn(sidecar_path: PathBuf, sink: Arc<dyn EventSink>) -> Result<Self, String> {
        let mut command = Command::new(&sidecar_path);
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
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

        let pending: Arc<Mutex<Option<Value>>> = Arc::new(Mutex::new(None));
        let dead = Arc::new(AtomicBool::new(false));
        spawn_stdout_pump(stdout, sink, pending.clone(), dead.clone());

        Ok(Self {
            child,
            stdin: Some(stdin),
            pending_response: pending,
            dead,
        })
    }

    pub fn is_alive(&self) -> bool {
        !self.dead.load(Ordering::Relaxed)
    }

    /// Send one request and wait for its response. Events that arrive while
    /// waiting are forwarded immediately through the sink — the pump keeps
    /// streaming even when no request is in flight.
    pub fn request(&mut self, request: &Value) -> Result<Value, String> {
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

        let deadline = Instant::now() + Duration::from_secs(15);
        loop {
            if let Some(response) = self
                .pending_response
                .lock()
                .ok()
                .and_then(|mut slot| slot.take())
            {
                return Ok(response);
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
    pub fn shutdown(mut self) {
        if let Some(mut stdin) = self.stdin.take() {
            let _ = stdin.flush();
            // Dropping closes the pipe → sidecar drains and exits.
        }
        let _ = self.child.wait();
    }
}

impl Drop for EngineHost {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn spawn_stdout_pump(
    stdout: std::process::ChildStdout,
    sink: Arc<dyn EventSink>,
    pending: Arc<Mutex<Option<Value>>>,
    dead: Arc<AtomicBool>,
) {
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines() {
            let Ok(line) = line else { break };
            let Ok(value) = serde_json::from_str::<Value>(&line) else {
                continue;
            };
            if value.get("resp").is_some() {
                if let Ok(mut slot) = pending.lock() {
                    *slot = Some(value);
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
        let mut host = match EngineHost::spawn(sidecar, sink) {
            Ok(h) => h,
            Err(_) => return,
        };
        let response = host.request(&serde_json::json!({"op": "capabilities"})).expect("handshake");
        assert_eq!(response["resp"], "ok");
        assert_eq!(response["op"], "capabilities");
        assert!(response["payload"]["engine_available"].is_boolean());
        host.shutdown();
    }
}

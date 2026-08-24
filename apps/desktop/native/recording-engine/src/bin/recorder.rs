//! WindAgent recorder sidecar — data plane process (Phase 8/9).
//!
//! Protocol (one JSON value per line):
//!   stdin  → `{"op":"capabilities"|"prepare"|"start"|...,"args":{…}}` ([EngineRequest])
//!   stdout → `{"resp":"ok"|"err", …}` per request, then any number of
//!            `{"type":"Status"|"Segment"|…}` events ([EngineResponse]/[EngineEvent]).
//!
//! The control plane (Tauri `engine_host`) spawns this binary with piped
//! stdio; raw frames never travel anywhere except the base64 JPEG preview.

use std::io::{BufRead, Write};
use std::sync::mpsc;

use windagent_recording_engine::ipc::{EngineRequest, EngineResponse};
use windagent_recording_engine::service::RecorderService;

/// Everything the reader thread hands to the main loop. The reader never
/// touches stdout itself — the main loop owns the only `StdoutLock`, so a
/// cross-thread lock wait (Stdout's reentrant lock blocks *across* threads)
/// can never deadlock the reader before it sees EOF.
enum ReaderMsg {
    Request(EngineRequest),
    Malformed { error: String },
}

fn main() {
    // Unbuffered stdout is the protocol contract: every line must reach the
    // host immediately (status heartbeats drive the UI).
    let stdout = std::io::stdout();
    let mut out = stdout.lock();

    let (tx_requests, rx_requests) = mpsc::channel::<ReaderMsg>();

    // Reader thread: stdin lines → requests. EOF drops the sender and ends
    // the loop below (the host closing our stdin means "shut down").
    std::thread::spawn(move || {
        let stdin = std::io::stdin();
        for line in stdin.lock().lines() {
            match line {
                Ok(line) if line.trim().is_empty() => continue,
                Ok(line) => match serde_json::from_str::<EngineRequest>(&line) {
                    Ok(req) => {
                        if tx_requests.send(ReaderMsg::Request(req)).is_err() {
                            break;
                        }
                    }
                    // Unparseable lines (bad JSON *or* an unknown op tag) go
                    // through the channel too — see [ReaderMsg].
                    Err(error) => {
                        if tx_requests
                            .send(ReaderMsg::Malformed {
                                error: error.to_string(),
                            })
                            .is_err()
                        {
                            break;
                        }
                    }
                },
                Err(_) => break,
            }
        }
    });

    let mut service = RecorderService::new();
    // Answer `capabilities` eagerly so the host can preflight without waiting
    // for its first request round-trip.
    let (resp, events) = service.handle(EngineRequest::Capabilities);
    let _ = write_line(&mut out, &resp);
    for event in events {
        let _ = write_line(&mut out, &event);
    }

    loop {
        // 1. Drain background events produced between requests.
        for event in service.tick() {
            if write_line(&mut out, &event).is_err() {
                break;
            }
        }

        // 2. Next request, bounded wait so ticks keep flowing.
        match rx_requests.recv_timeout(std::time::Duration::from_millis(250)) {
            Ok(ReaderMsg::Request(request)) => {
                let (resp, events) = service.handle(request);
                if write_line(&mut out, &resp).is_err() {
                    break;
                }
                for event in events {
                    if write_line(&mut out, &event).is_err() {
                        break;
                    }
                }
            }
            Ok(ReaderMsg::Malformed { error }) => {
                let resp = EngineResponse::err(
                    "unknown",
                    "ENGINE_REQUEST_MALFORMED",
                    format!("unparseable request line: {error}"),
                );
                if write_line(&mut out, &resp).is_err() {
                    break;
                }
            }
            Err(mpsc::RecvTimeoutError::Timeout) => continue,
            Err(mpsc::RecvTimeoutError::Disconnected) => break,
        }

        // writeln! emits '\n' which stdout's LineWriter flushes eagerly; the
        // explicit flush below guards future refactors away from that.
        let _ = out.flush();
    }

    // Best-effort teardown of anything still recording when stdin closed.
    let _ = service.handle(EngineRequest::Stop);
}

fn write_line<T: serde::Serialize>(out: &mut impl Write, value: &T) -> std::io::Result<()> {
    let json = serde_json::to_string(value).map_err(std::io::Error::other)?;
    writeln!(out, "{json}")
}

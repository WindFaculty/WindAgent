//! Sidecar process lifecycle regression tests.
//!
//! Guards the shutdown contract with the Tauri host: closing the sidecar's
//! stdin MUST terminate the process promptly (the host treats "child alive
//! after stdin closed" as a hang and would leak recorder processes).
//!
//! Regression 1: the reader thread once held a long-lived `StdoutLock` while
//! the main loop owned its own — `Stdout`'s reentrant lock blocks *across*
//! threads, so the reader deadlocked before it ever reached EOF. Now the
//! reader never touches stdout; malformed lines travel through the channel.
//!
//! Regression 2: an unknown op tag (`"op":"get_capabilities"` instead of the
//! serde-generated `"capabilities"`) used to hit that same stdout path and
//! hang the sidecar forever; it must answer `ENGINE_REQUEST_MALFORMED` and
//! still exit cleanly on EOF.
//!
//! Regression 3: these scenarios MUST run sequentially inside one test —
//! concurrent spawns inherit each other's still-open stdin pipe write-ends
//! (Windows handle inheritance), so no child would ever see EOF.

use std::io::Write;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

const EXIT_GRACE: Duration = Duration::from_secs(10);

fn spawn_sidecar() -> std::process::Child {
    Command::new(env!("CARGO_BIN_EXE_windagent-recorder"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn windagent-recorder")
}

/// Require a clean exit within ``EXIT_GRACE`` and collect the output.
fn wait_clean_exit(mut child: std::process::Child, context: &str) -> std::process::Output {
    let deadline = Instant::now() + EXIT_GRACE;
    loop {
        match child.try_wait().expect("try_wait") {
            Some(status) => {
                assert!(status.success(), "{context}: exited with {status}");
                return child.wait_with_output().expect("collect output");
            }
            None if Instant::now() > deadline => {
                let _ = child.kill();
                let _ = child.wait();
                panic!("{context}: did not exit within {EXIT_GRACE:?} of stdin close");
            }
            None => std::thread::sleep(Duration::from_millis(50)),
        }
    }
}

#[test]
fn sidecar_lifecycle_eof_shutdown_and_protocol_responses() {
    // Scenario 1: bare spawn → close stdin → prompt clean exit.
    {
        let mut child = spawn_sidecar();
        drop(child.stdin.take()); // EOF == "shut down"
        wait_clean_exit(child, "bare eof");
    }

    // Scenario 2: well-formed request answered, then EOF → clean exit.
    // Wire op is the serde snake_case variant name ("capabilities"); unit
    // variants carry no args (V2 frozen tag+content envelope).
    {
        let mut child = spawn_sidecar();
        {
            let stdin = child.stdin.as_mut().expect("stdin piped");
            writeln!(stdin, r#"{{"op":"capabilities"}}"#).expect("write request");
        }
        drop(child.stdin.take()); // as_mut above only borrows — take() actually closes the pipe
        let output = wait_clean_exit(child, "capabilities round-trip");
        let stdout = String::from_utf8(output.stdout).expect("utf-8 stdout");
        assert!(
            stdout.contains(r#""op":"capabilities""#),
            "expected capabilities responses in: {stdout}"
        );
    }

    // Scenario 3 (regression 2): unknown op tag → ENGINE_REQUEST_MALFORMED,
    // and EOF afterwards still terminates the process.
    {
        let mut child = spawn_sidecar();
        {
            let stdin = child.stdin.as_mut().expect("stdin piped");
            writeln!(stdin, r#"{{"op":"get_capabilities","args":{{}}}}"#)
                .expect("write request");
        }
        drop(child.stdin.take());
        let output = wait_clean_exit(child, "unknown op tag");
        let stdout = String::from_utf8(output.stdout).expect("utf-8");
        assert!(
            stdout.contains("ENGINE_REQUEST_MALFORMED"),
            "expected malformed-request error response in: {stdout}"
        );
    }

    // Scenario 4: raw garbage line → same error contract, clean exit on EOF.
    {
        let mut child = spawn_sidecar();
        {
            let stdin = child.stdin.as_mut().expect("stdin piped");
            writeln!(stdin, "this is not json").expect("write garbage");
        }
        drop(child.stdin.take());
        let output = wait_clean_exit(child, "malformed line");
        let stdout = String::from_utf8(output.stdout).expect("utf-8");
        assert!(
            stdout.contains("ENGINE_REQUEST_MALFORMED"),
            "expected malformed-request error response in: {stdout}"
        );
    }
}

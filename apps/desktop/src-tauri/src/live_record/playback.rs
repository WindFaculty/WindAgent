//! Prepared code playback executor — the Principle C boundary on desktop input.
//!
//! The ONLY content this module ever types into an editor is the operator's
//! own prepared payload delivered by a server dispatch ticket for a FROZEN
//! plan (`prepare_action_dispatch`). It is never fed from model output.
//!
//! Flow (`playback_execute_code`):
//!   1. sha256(current file) must equal `before_hash` — refuse otherwise.
//!   2. TYPE  → synthesize per-character Unicode keystrokes at the frozen
//!      pacing (15–40 chars/s); PASTE → clipboard + Ctrl+V.
//!   3. Ctrl+S to save.
//!   4. Poll until sha256(file) equals `after_hash` (bounded) → SUCCESS,
//!      otherwise FAILURE with the last observed hash.
//!
//! Everything is plain windows-sys (SendInput / clipboard / foreground probe);
//! no heavyweight automation crates.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

/// Frozen pacing window (ban_ke_hoach_v1.md Section 14): readable for the
/// recording, slow enough to look human, fast enough not to stall takes.
pub const MIN_CHARS_PER_SECOND: u32 = 15;
pub const MAX_CHARS_PER_SECOND: u32 = 40;

const VK_CONTROL: u16 = 0x11;
const VK_V: u16 = 0x56;
const VK_S: u16 = 0x53;
const INPUT_KEYBOARD: u32 = 1;
const KEYEVENTF_KEYUP: u32 = 0x0002;
const KEYEVENTF_UNICODE: u32 = 0x0004;
const CF_UNICODETEXT: u32 = 13;
/// How long Ctrl+S has to land before we give up watching the file.
const SAVE_SETTLE_TIMEOUT_MS: u64 = 8_000;
const SAVE_POLL_INTERVAL_MS: u64 = 100;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum PlaybackMode {
    Type,
    Paste,
}

#[derive(Debug, Deserialize)]
pub struct PlaybackExecuteRequest {
    pub file_path: String,
    /// Operator-prepared content from the server ticket — never model output.
    pub content: String,
    pub mode: PlaybackMode,
    #[serde(default = "default_chars_per_second")]
    pub chars_per_second: u32,
    pub before_hash: String,
    pub after_hash: String,
}

fn default_chars_per_second() -> u32 {
    22
}

#[derive(Debug, Serialize)]
pub struct PlaybackResult {
    pub status: String, // SUCCESS | FAILURE
    pub detail: String,
    pub before_hash_observed: Option<String>,
    pub after_hash_observed: Option<String>,
    pub typed_chars: usize,
}

impl PlaybackResult {
    fn failure(detail: impl Into<String>, before: Option<String>) -> Self {
        Self {
            status: "FAILURE".into(),
            detail: detail.into(),
            before_hash_observed: before,
            after_hash_observed: None,
            typed_chars: 0,
        }
    }
}

// ─── Hashing ─────────────────────────────────────────────────────────────────

pub(crate) fn file_sha256_hex(path: &str) -> Result<String, String> {
    let bytes = std::fs::read(path).map_err(|e| format!("FILE_READ_FAILED: {e}"))?;
    Ok(hex_lower(&Sha256::digest(&bytes)))
}

pub(crate) fn hex_lower(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        out.push(char::from_digit((b >> 4) as u32, 16).unwrap_or('0'));
        out.push(char::from_digit((b & 0xF) as u32, 16).unwrap_or('0'));
    }
    out
}

/// Effective pacing clamped into the frozen window (ms between keystrokes).
pub(crate) fn effective_delay_ms(chars_per_second: u32) -> u64 {
    let cps = chars_per_second.clamp(MIN_CHARS_PER_SECOND, MAX_CHARS_PER_SECOND);
    (1000u64 / u64::from(cps.max(1))).max(1)
}

// ─── Keystroke synthesis (windows-sys SendInput) ─────────────────────────────

#[cfg(windows)]
fn send_key(vk: u16, scan: u16, flags: u32) -> Result<(), String> {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_KEYBOARD, KEYBDINPUT,
    };
    let mut input: INPUT = unsafe { std::mem::zeroed() };
    input.r#type = INPUT_KEYBOARD;
    input.Anonymous.ki = KEYBDINPUT {
        wVk: vk,
        wScan: scan,
        dwFlags: flags,
        time: 0,
        dwExtraInfo: 0,
    };
    let sent = unsafe { SendInput(1, &input, std::mem::size_of::<INPUT>() as i32) };
    if sent != 1 {
        return Err("KEYSTROKE_REJECTED".into());
    }
    Ok(())
}

#[cfg(windows)]
fn send_unicode_char(ch: char) -> Result<(), String> {
    let mut buf = [0u16; 2];
    for unit in ch.encode_utf16(&mut buf) {
        send_key(0, *unit, KEYEVENTF_UNICODE)?;
        send_key(0, *unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)?;
    }
    Ok(())
}

#[cfg(windows)]
fn send_ctrl_combo(vk: u16) -> Result<(), String> {
    let pause = std::time::Duration::from_millis(15);
    send_key(VK_CONTROL, 0, 0)?;
    std::thread::sleep(pause);
    send_key(vk, 0, 0)?;
    std::thread::sleep(pause);
    send_key(vk, 0, KEYEVENTF_KEYUP)?;
    std::thread::sleep(pause);
    send_key(VK_CONTROL, 0, KEYEVENTF_KEYUP)
}

// ─── Clipboard paste (windows-sys, no extra crates) ──────────────────────────

#[cfg(windows)]
pub(crate) fn set_clipboard_text(text: &str) -> Result<(), String> {
    use windows_sys::Win32::System::DataExchange::{
        CloseClipboard, EmptyClipboard, OpenClipboard, SetClipboardData,
    };
    use windows_sys::Win32::System::Memory::{
        GlobalAlloc, GlobalLock, GlobalUnlock, GMEM_MOVEABLE,
    };

    unsafe {
        if OpenClipboard(std::ptr::null_mut()) == 0 {
            return Err("CLIPBOARD_OPEN_FAILED".into());
        }
        // Always close, even on failure paths below.
        let result = (|| {
            let utf16: Vec<u16> = text.encode_utf16().chain(Some(0)).collect();
            let byte_len = utf16.len() * 2;
            let handle = GlobalAlloc(GMEM_MOVEABLE, byte_len);
            if handle.is_null() {
                return Err("CLIPBOARD_ALLOC_FAILED".into());
            }
            let dest = GlobalLock(handle) as *mut u16;
            if dest.is_null() {
                return Err("CLIPBOARD_LOCK_FAILED".into());
            }
            std::ptr::copy_nonoverlapping(utf16.as_ptr(), dest, utf16.len());
            let _ = GlobalUnlock(handle);

            if EmptyClipboard() == 0 {
                return Err("CLIPBOARD_EMPTY_FAILED".into());
            }
            // Ownership of the allocation transfers to the system on success.
            if SetClipboardData(CF_UNICODETEXT, handle as _).is_null() {
                return Err("CLIPBOARD_SET_FAILED".into());
            }
            Ok(())
        })();
        CloseClipboard();
        result
    }
}

// ─── Core execution ──────────────────────────────────────────────────────────

/// Inject the operator's prepared content into the focused editor.
#[cfg(windows)]
fn inject_content(request: &PlaybackExecuteRequest, delay_ms: u64) -> Result<usize, String> {
    match request.mode {
        PlaybackMode::Type => {
            let mut typed = 0usize;
            for ch in request.content.chars() {
                send_unicode_char(ch)?;
                typed += ch.len_utf8(); // report bytes, matching hash semantics
                std::thread::sleep(std::time::Duration::from_millis(delay_ms));
            }
            Ok(typed)
        }
        PlaybackMode::Paste => {
            set_clipboard_text(&request.content)?;
            std::thread::sleep(std::time::Duration::from_millis(50));
            send_ctrl_combo(VK_V)?;
            Ok(request.content.len())
        }
    }
}

#[cfg(not(windows))]
fn inject_content(_request: &PlaybackExecuteRequest, _delay_ms: u64) -> Result<usize, String> {
    Err("PLAYBACK_INPUT_UNAVAILABLE_ON_PLATFORM".into())
}

#[cfg(windows)]
fn save_file() -> Result<(), String> {
    send_ctrl_combo(VK_S)
}

#[cfg(not(windows))]
fn save_file() -> Result<(), String> {
    Err("PLAYBACK_SAVE_UNAVAILABLE_ON_PLATFORM".into())
}

/// Poll until the file's hash matches `expected`, bounded by the settle
/// timeout (editors debounce writes).
fn wait_for_after_hash(file_path: &str, expected: &str) -> Option<String> {
    let deadline = std::time::Instant::now()
        + std::time::Duration::from_millis(SAVE_SETTLE_TIMEOUT_MS);
    loop {
        match file_sha256_hex(file_path) {
            Ok(hash) if hash.eq_ignore_ascii_case(expected) => return Some(hash),
            _ => {}
        }
        if std::time::Instant::now() >= deadline {
            return file_sha256_hex(file_path).ok();
        }
        std::thread::sleep(std::time::Duration::from_millis(SAVE_POLL_INTERVAL_MS));
    }
}

pub(crate) fn execute_core(request: &PlaybackExecuteRequest) -> PlaybackResult {
    let before = match file_sha256_hex(&request.file_path) {
        Ok(h) => h,
        Err(e) => return PlaybackResult::failure(e, None),
    };
    if !before.eq_ignore_ascii_case(&request.before_hash) {
        return PlaybackResult::failure(
            format!("BEFORE_HASH_MISMATCH: editor state drifted from the frozen plan"),
            Some(before),
        );
    }

    let delay_ms = effective_delay_ms(request.chars_per_second);
    let typed_chars = match inject_content(request, delay_ms) {
        Ok(n) => n,
        Err(e) => return PlaybackResult::failure(e, Some(before)),
    };

    if let Err(e) = save_file() {
        return PlaybackResult::failure(e, Some(before));
    }

    match wait_for_after_hash(&request.file_path, &request.after_hash) {
        Some(hash) if hash.eq_ignore_ascii_case(&request.after_hash) => PlaybackResult {
            status: "SUCCESS".into(),
            detail: "file content verified against frozen plan".into(),
            before_hash_observed: Some(before),
            after_hash_observed: Some(hash),
            typed_chars,
        },
        Some(last) => PlaybackResult::failure(
            "AFTER_HASH_MISMATCH: saved content drifted from the prepared payload",
            Some(before),
        )
        .with_after(last),
        None => PlaybackResult::failure("AFTER_HASH_UNREADABLE", Some(before)),
    }
}

impl PlaybackResult {
    fn with_after(mut self, hash: String) -> Self {
        self.after_hash_observed = Some(hash);
        self
    }
}

/// Tauri command — execute one prepared CODE_PLAYBACK dispatch ticket.
#[tauri::command]
pub fn playback_execute_code(request: PlaybackExecuteRequest) -> PlaybackResult {
    execute_core(&request)
}

// ─── Environment probe (preflight "is VS Code in focus?") ────────────────────

#[derive(Debug, Serialize)]
pub struct ForegroundProbe {
    pub process_name: Option<String>,
    pub window_title: Option<String>,
    /// True when the probe itself ran on a supported platform.
    pub supported: bool,
}

#[tauri::command]
pub fn playback_probe_environment() -> ForegroundProbe {
    #[cfg(windows)]
    {
        probe_foreground_windows()
    }
    #[cfg(not(windows))]
    {
        ForegroundProbe {
            process_name: None,
            window_title: None,
            supported: false,
        }
    }
}

#[cfg(windows)]
fn probe_foreground_windows() -> ForegroundProbe {
    use windows_sys::Win32::System::Threading::{
        OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_WIN32,
        PROCESS_QUERY_LIMITED_INFORMATION,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetForegroundWindow, GetWindowTextW, GetWindowThreadProcessId,
    };

    let mut probe = ForegroundProbe {
        process_name: None,
        window_title: None,
        supported: true,
    };
    unsafe {
        let hwnd = GetForegroundWindow();
        if hwnd.is_null() {
            return probe;
        }

        // Window title (bounded buffer — titles can be long).
        let mut title_buf = [0u16; 512];
        let len = GetWindowTextW(hwnd, title_buf.as_mut_ptr(), 512);
        if len > 0 {
            probe.window_title =
                Some(String::from_utf16_lossy(&title_buf[..(len as usize).min(511)]));
        }

        // Owning process image name.
        let mut pid: u32 = 0;
        GetWindowThreadProcessId(hwnd, &mut pid);
        if pid == 0 {
            return probe;
        }
        let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if handle.is_null() {
            return probe;
        }
        let mut path_buf = [0u16; 1024];
        let mut size: u32 = 1024;
        if QueryFullProcessImageNameW(handle, PROCESS_NAME_WIN32, path_buf.as_mut_ptr(), &mut size)
            != 0
        {
            let full = String::from_utf16_lossy(&path_buf[..size as usize]);
            probe.process_name = full.rsplit(['\\', '/']).next().map(str::to_string);
        }
        let _ = windows_sys::Win32::Foundation::CloseHandle(handle);
    }
    probe
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_lower_matches_known_vectors() {
        assert_eq!(hex_lower(&[]), "");
        assert_eq!(hex_lower(&[0x00, 0x0f, 0xff]), "000fff");
        // sha2 integration: empty digest is the well-known constant.
        assert_eq!(
            hex_lower(&Sha256::digest(b"")),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }

    #[test]
    fn pacing_clamps_into_frozen_window() {
        assert_eq!(effective_delay_ms(1), 1000 / u64::from(MIN_CHARS_PER_SECOND));
        assert_eq!(effective_delay_ms(999), 1000 / u64::from(MAX_CHARS_PER_SECOND));
        assert_eq!(effective_delay_ms(22), 45); // 1000/22 → 45 ms
        assert_eq!(effective_delay_ms(0), 1000 / u64::from(MIN_CHARS_PER_SECOND));
    }

    #[test]
    fn request_defaults_and_mode_deserialization() {
        let raw = serde_json::json!({
            "file_path": "src/demo.py",
            "content": "print('x')\n",
            "mode": "TYPE",
            "before_hash": &"a".repeat(64),
            "after_hash": &"b".repeat(64),
        });
        let req: PlaybackExecuteRequest = serde_json::from_value(raw).unwrap();
        assert_eq!(req.chars_per_second, 22);
        assert_eq!(req.mode, PlaybackMode::Type);

        let paste = serde_json::json!({ "mode": "PASTE" });
        assert_eq!(
            serde_json::from_value::<PlaybackExecuteRequest>(paste).is_err(),
            true,
            "missing required fields must be rejected"
        );
    }

    #[test]
    fn before_hash_mismatch_refuses_to_type() {
        // The core safety gate: drifted editor state → no keystrokes ever sent.
        let dir = std::env::temp_dir().join(format!(
            "windagent_playback_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let file = dir.join("demo.py");
        std::fs::write(&file, b"original\n").unwrap();

        let request = PlaybackExecuteRequest {
            file_path: file.to_string_lossy().into_owned(),
            content: "print('prepared')\n".into(),
            mode: PlaybackMode::Type,
            chars_per_second: 40,
            before_hash: hex_lower(&Sha256::digest(b"stale-content")),
            after_hash: hex_lower(&Sha256::digest(b"print('prepared')\n")),
        };
        let result = execute_core(&request);
        assert_eq!(result.status, "FAILURE");
        assert!(result.detail.contains("BEFORE_HASH_MISMATCH"), "{result:?}");
        // File untouched by the refusal path.
        assert_eq!(std::fs::read(&file).unwrap(), b"original\n");
        let _ = std::fs::remove_dir_all(&dir);
    }
}

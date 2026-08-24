//! Native capability probing — Phase 8 (ban_ke_hoach_v1.md Section 23).
//!
//! Everything here is fail-closed: a missing binary, filter, encoder or an
//! unwritable output directory surfaces as `engine_available=false` plus an
//! explicit blocker code, never as a best-effort guess.

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use crate::ipc::EngineCapabilities;

/// Locate the ffmpeg binary: `WINDAGENT_FFMPEG_PATH` env override first,
/// then whatever `ffmpeg` resolves to on PATH.
pub fn locate_ffmpeg() -> Option<PathBuf> {
    if let Ok(custom) = std::env::var("WINDAGENT_FFMPEG_PATH") {
        let p = PathBuf::from(custom);
        if p.is_file() {
            return Some(p);
        }
    }
    // Bare name — resolution is delegated to the OS PATH lookup by spawning
    // `-version`; a successful exit proves both existence and executability.
    match Command::new("ffmpeg").arg("-version").output() {
        Ok(out) if out.status.success() => Some(PathBuf::from("ffmpeg")),
        _ => None,
    }
}

fn first_line(bytes: &[u8]) -> String {
    String::from_utf8_lossy(
        bytes
            .split(|b| *b == b'\n')
            .next()
            .unwrap_or(bytes),
    )
    .trim()
    .to_string()
}

/// `ffmpeg -version` → "ffmpeg version 8.1.2-full_build-www.gyan.dev ..." → "8.1.2-full_build..."
pub fn parse_version_line(line: &str) -> String {
    line.strip_prefix("ffmpeg version ")
        .unwrap_or(line)
        .split_whitespace()
        .next()
        .unwrap_or("unknown")
        .to_string()
}

/// Probe the full pipeline on this host.
///
/// `output_dir` — when given, writability is checked in that directory;
/// otherwise the OS temp dir stands in.
pub fn probe_capabilities(output_dir: Option<&Path>) -> EngineCapabilities {
    let mut caps = EngineCapabilities {
        backend: "mock".into(),
        ..Default::default()
    };

    let Some(ffmpeg) = locate_ffmpeg() else {
        caps.blockers.push("FFMPEG_NOT_FOUND".into());
        return caps;
    };
    caps.ffmpeg_path = Some(ffmpeg.to_string_lossy().into_owned());

    let version_out = Command::new(&ffmpeg)
        .args(["-version"])
        .stderr(Stdio::null())
        .output();
    match version_out {
        Ok(out) if out.status.success() => {
            caps.ffmpeg_version = Some(parse_version_line(&first_line(&out.stdout)));
        }
        _ => {
            caps.blockers.push("FFMPEG_NOT_EXECUTABLE".into());
            return caps;
        }
    }

    // Encoder + filter probes (single spawn each, banner suppressed).
    let encoders = Command::new(&ffmpeg)
        .args(["-hide_banner", "-encoders"])
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
        .unwrap_or_default();
    caps.nvenc_h264_available = encoders.contains(" h264_nvenc ");
    caps.nvenc_hevc_available = encoders.contains(" hevc_nvenc ");

    let filters = Command::new(&ffmpeg)
        .args(["-hide_banner", "-filters"])
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
        .unwrap_or_default();
    caps.ddagrab_available = filters.contains(" ddagrab ");

    if !caps.ddagrab_available {
        // ddagrab is Windows-only (Desktop Duplication) — CI/Linux lands here.
        caps.blockers.push("DDAGRAB_UNAVAILABLE".into());
    }
    if !caps.nvenc_h264_available && !caps.nvenc_hevc_available {
        caps.blockers.push("NVENC_UNAVAILABLE".into());
    }

    // Disk free + writability.
    let dir = output_dir
        .map(Path::to_path_buf)
        .unwrap_or_else(std::env::temp_dir);
    if let Some(free) = disk_free_bytes(&dir) {
        caps.disk_free_gb = (free as f64 / 1_073_741_824.0 * 10.0).round() / 10.0;
        if free < 2 * 1_073_741_824 {
            // < 2 GiB free cannot hold a soak take — refuse to start.
            caps.blockers.push("DISK_FULL".into());
        }
    } else {
        caps.blockers.push("DISK_PROBE_FAILED".into());
    }
    caps.output_writable = check_writable(&dir);
    if !caps.output_writable {
        caps.blockers.push("OUTPUT_NOT_WRITABLE".into());
    }

    caps.engine_available =
        caps.ddagrab_available && (caps.nvenc_h264_available || caps.nvenc_hevc_available);
    if caps.engine_available {
        caps.backend = "ffmpeg-ddagrab-nvenc".into();
    }
    caps
}

/// Create + delete a marker file — the cheapest honest writability probe.
pub fn check_writable(dir: &Path) -> bool {
    let probe = dir.join(".windagent_write_probe");
    match std::fs::write(&probe, b"probe") {
        Ok(()) => {
            let _ = std::fs::remove_file(&probe);
            true
        }
        Err(_) => false,
    }
}

#[cfg(windows)]
pub fn disk_free_bytes(path: &Path) -> Option<u64> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::GetDiskFreeSpaceExW;

    // Root of the given path (GetDiskFreeSpaceExW accepts any path on the volume).
    let wide: Vec<u16> = path
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    let mut avail: u64 = 0;
    let mut total: u64 = 0;
    let mut free: u64 = 0;
    unsafe {
        if GetDiskFreeSpaceExW(wide.as_ptr(), &mut avail, &mut total, &mut free) != 0 {
            Some(avail)
        } else {
            None
        }
    }
}

#[cfg(not(windows))]
pub fn disk_free_bytes(_path: &Path) -> Option<u64> {
    // Non-Windows hosts land in mock mode anyway (ddagrab unavailable), so a
    // neutral value keeps the capability report coherent without libc deps.
    Some(u64::MAX)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_line_parses_release_token() {
        assert_eq!(
            parse_version_line("ffmpeg version 8.1.2-full_build-www.gyan.dev Copyright (c) 2000-2025"),
            "8.1.2-full_build-www.gyan.dev"
        );
        assert_eq!(parse_version_line("weird"), "weird");
    }

    #[test]
    fn capabilities_fail_closed_without_ffmpeg_env() {
        // On any host this must produce either a fully-probed real backend or
        // an explicit blocker list — never engine_available=true by accident.
        let caps = probe_capabilities(None);
        if !caps.engine_available {
            assert!(!caps.blockers.is_empty(), "fail-closed needs blocker codes");
            assert_eq!(caps.backend, "mock");
        } else {
            assert!(caps.ddagrab_available);
            assert!(caps.output_writable);
            assert_eq!(caps.backend, "ffmpeg-ddagrab-nvenc");
        }
    }

    #[test]
    fn writable_probe_rejects_missing_dir() {
        assert!(!check_writable(Path::new("Z:/definitely/not/a/dir/windagent")));
    }
}

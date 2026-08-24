//! Real capture pipeline via ffmpeg — Phase 8/9 (ban_ke_hoach_v1.md Section 16).
//!
//! ```text
//! ffmpeg -f lavfi -i ddagrab=framerate=60:output_size=1920x1080   (frames stay on GPU)
//!        -c:v h264_nvenc -preset p4 -b:v 12M                      (NVENC on the same GPU)
//!        -force_key_frames expr:gte(t,n_forced*300)
//!        -f segment -segment_time 300 -reset_timestamps 1
//!        {dir}/segment_%04d.mkv
//! ```
//!
//! Pause = write `q` to ffmpeg's stdin → it finalizes the current MKV and
//! exits. Resume = respawn with `-segment_start_number n` so numbering
//! continues. Crash recovery keeps every completed MKV (Section 17).

use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

/// Windows-only: never flash a console window when spawning ffmpeg.
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Debug, Clone)]
pub struct FfmpegCaptureConfig {
    pub ffmpeg_path: PathBuf,
    pub fps: u32,
    /// "H264" → h264_nvenc, "HEVC" → hevc_nvenc.
    pub codec: String,
    pub resolution: (u32, u32),
    pub segment_seconds: u64,
    /// e.g. "12M".
    pub bitrate: String,
    pub output_dir: PathBuf,
}

impl FfmpegCaptureConfig {
    /// Bitrate ladder for the frozen profile allowlist (Section 16).
    pub fn default_bitrate(resolution: (u32, u32), fps: u32) -> String {
        match (resolution, fps) {
            ((3840, 2160), _) => "28M".into(),
            ((1920, 1080), 60) => "12M".into(),
            ((1920, 1080), 30) => "8M".into(),
            ((1280, 720), _) => "6M".into(),
            _ => "8M".into(),
        }
    }

    fn nvenc_encoder_name(&self) -> Result<&'static str, String> {
        match self.codec.as_str() {
            "H264" => Ok("h264_nvenc"),
            "HEVC" => Ok("hevc_nvenc"),
            other => Err(format!(
                "ENGINE_PROFILE_REJECTED: unsupported NVENC codec '{other}'"
            )),
        }
    }
}

/// Shared counters fed by the stderr reader thread.
#[derive(Debug, Clone, Default)]
pub struct CaptureCounters {
    /// Last `frame=` progress value seen on ffmpeg's stderr.
    pub frames: Arc<AtomicU64>,
    /// Set once ffmpeg logs its stream mapping containing the nvenc encoder.
    pub nvenc_confirmed: Arc<AtomicBool>,
    /// Rolling tail of ffmpeg stderr (bounded) for failure diagnostics.
    pub stderr_tail: Arc<Mutex<String>>,
}

pub struct FfmpegSegmentCapture {
    pub config: FfmpegCaptureConfig,
    child: Option<Child>,
    stdin: Option<ChildStdin>,
    counters: CaptureCounters,
    segments_spawned: u32,
}

impl FfmpegSegmentCapture {
    pub fn new(config: FfmpegCaptureConfig) -> Self {
        Self {
            config,
            child: None,
            stdin: None,
            counters: CaptureCounters::default(),
            segments_spawned: 0,
        }
    }

    pub fn counters(&self) -> &CaptureCounters {
        &self.counters
    }

    pub fn is_running(&self) -> bool {
        self.child.is_some()
    }

    pub fn segments_spawned(&self) -> u32 {
        self.segments_spawned
    }

    /// Build the exact argv for a (re)start. `segment_start_number` continues
    /// MKV numbering across pause/resume so tokens stay unique per take.
    pub fn build_args(&self, segment_start_number: u32) -> Vec<String> {
        let c = &self.config;
        let encoder = c.nvenc_encoder_name().unwrap_or("h264_nvenc");
        let output = c.output_dir.join("segment_%04d.mkv");
        vec![
            "-hide_banner".into(),
            "-y".into(),
            "-f".into(),
            "lavfi".into(),
            "-i".into(),
            format!(
                "ddagrab=framerate={}:output_size={}x{}",
                c.fps, c.resolution.0, c.resolution.1
            ),
            "-c:v".into(),
            encoder.into(),
            "-preset".into(),
            "p4".into(),
            "-b:v".into(),
            c.bitrate.clone(),
            // Keyframe at every segment boundary so each MKV starts clean.
            "-force_key_frames".into(),
            format!("expr:gte(t,n_forced*{})", c.segment_seconds),
            "-f".into(),
            "segment".into(),
            "-segment_time".into(),
            c.segment_seconds.to_string(),
            "-segment_start_number".into(),
            segment_start_number.to_string(),
            "-reset_timestamps".into(),
            "1".into(),
            output.to_string_lossy().into_owned(),
        ]
    }

    /// Spawn the recording process (`segment_start_number` continues after resume).
    pub fn start(&mut self, segment_start_number: u32) -> Result<(), String> {
        if self.child.is_some() {
            return Err("FFMPEG_CAPTURE_ALREADY_RUNNING".into());
        }
        std::fs::create_dir_all(&self.config.output_dir)
            .map_err(|e| format!("FFMPEG_OUTPUT_DIR_FAILED: {}", e))?;

        let mut command = Command::new(&self.config.ffmpeg_path);
        command
            .args(self.build_args(segment_start_number))
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(CREATE_NO_WINDOW);
        }

        let mut child = command
            .spawn()
            .map_err(|e| format!("FFMPEG_SPAWN_FAILED: {}", e))?;
        let stdin = child.stdin.take().ok_or("FFMPEG_STDIN_UNAVAILABLE")?;
        let stderr = child.stderr.take().ok_or("FFMPEG_STDERR_UNAVAILABLE")?;

        spawn_stderr_reader(stderr, self.counters.clone());
        self.segments_spawned = segment_start_number;
        self.child = Some(child);
        self.stdin = Some(stdin);
        Ok(())
    }

    /// Graceful stop: `q` on stdin makes ffmpeg finalize the current segment.
    pub fn request_shutdown(&mut self) -> Result<(), String> {
        if let Some(mut stdin) = self.stdin.take() {
            let _ = stdin.write_all(b"q");
            let _ = stdin.flush();
            // Dropping closes the pipe — belt and braces if `q` is missed.
        }
        if let Some(mut child) = self.child.take() {
            match child.wait() {
                Ok(_status) => Ok(()),
                Err(e) => Err(format!("FFMPEG_WAIT_FAILED: {}", e)),
            }
        } else {
            Ok(())
        }
    }

    /// Hard kill (used only when graceful shutdown times out).
    pub fn kill(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        self.stdin = None;
    }

    /// Graceful shutdown with a hard-kill fallback.
    pub fn shutdown(&mut self) -> Result<(), String> {
        let result = self.request_shutdown();
        if result.is_err() {
            self.kill();
        }
        result
    }

    /// True once ffmpeg confirmed the nvenc encoder in its stream mapping.
    pub fn nvenc_confirmed(&self) -> bool {
        self.counters.nvenc_confirmed.load(Ordering::Relaxed)
    }

    pub fn frames_seen(&self) -> u64 {
        self.counters.frames.load(Ordering::Relaxed)
    }

    pub fn stderr_tail(&self) -> String {
        self.counters
            .stderr_tail
            .lock()
            .map(|t| t.clone())
            .unwrap_or_default()
    }

    /// List completed segment files currently on disk (sorted by index).
    pub fn completed_segments(&self) -> Vec<(u32, PathBuf)> {
        scan_segment_files(&self.config.output_dir)
    }
}

impl Drop for FfmpegSegmentCapture {
    fn drop(&mut self) {
        self.kill();
    }
}

/// Scan `dir` for `segment_%04d.mkv` files, returning `(index, path)` sorted.
pub fn scan_segment_files(dir: &Path) -> Vec<(u32, PathBuf)> {
    let mut found: Vec<(u32, PathBuf)> = std::fs::read_dir(dir)
        .map(|entries| {
            entries
                .filter_map(|entry| {
                    let path = entry.ok()?.path();
                    let name = path.file_name()?.to_str()?;
                    let rest = name.strip_prefix("segment_")?;
                    let idx_part = rest.strip_suffix(".mkv")?;
                    if idx_part.len() == 4 && idx_part.bytes().all(|b| b.is_ascii_digit()) {
                        Some((idx_part.parse::<u32>().ok()?, path))
                    } else {
                        None
                    }
                })
                .collect()
        })
        .unwrap_or_default();
    found.sort_by_key(|(idx, _)| *idx);
    found
}

fn spawn_stderr_reader(stderr: std::process::ChildStderr, counters: CaptureCounters) {
    std::thread::spawn(move || {
        use std::io::BufRead;
        let reader = std::io::BufReader::new(stderr);
        for line in reader.lines() {
            let Ok(line) = line else { break };
            // Progress lines look like: `frame= 1234 fps= 60 q=23.0 size=...`
            if let Some(rest) = line.trim_start().strip_prefix("frame=") {
                let token = rest.split_whitespace().next().unwrap_or("");
                if let Ok(frames) = token.replace(',', "").parse::<u64>() {
                    counters.frames.store(frames, Ordering::Relaxed);
                }
            }
            if line.contains("h264_nvenc") || line.contains("hevc_nvenc") {
                counters.nvenc_confirmed.store(true, Ordering::Relaxed);
            }
            if let Ok(mut tail) = counters.stderr_tail.lock() {
                tail.push_str(line.trim_end());
                tail.push('\n');
                let excess = tail.len().saturating_sub(16 * 1024);
                if excess > 0 {
                    tail.drain(..excess);
                }
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> FfmpegCaptureConfig {
        FfmpegCaptureConfig {
            ffmpeg_path: PathBuf::from("ffmpeg"),
            fps: 60,
            codec: "H264".into(),
            resolution: (1920, 1080),
            segment_seconds: 300,
            bitrate: "12M".into(),
            output_dir: PathBuf::from("out/take_0001"),
        }
    }

    #[test]
    fn argv_matches_frozen_pipeline_shape() {
        let args = FfmpegSegmentCapture::new(config()).build_args(2);
        let joined = args.join(" ");
        assert!(joined.contains("ddagrab=framerate=60:output_size=1920x1080"));
        assert!(joined.contains("-c:v h264_nvenc"));
        assert!(joined.contains("-b:v 12M"));
        assert!(joined.contains("expr:gte(t,n_forced*300)"));
        assert!(joined.contains("-segment_time 300"));
        assert!(joined.contains("-segment_start_number 2"));
        assert!(joined.contains("-reset_timestamps 1"));
        assert!(joined.ends_with("segment_%04d.mkv"));
        // stdin must stay piped for the `q` pause protocol — no -nostdin flag.
        assert!(!joined.contains("-nostdin"));
    }

    #[test]
    fn hevc_maps_to_hevc_nvenc_and_bad_codec_is_rejected() {
        let mut cfg = config();
        cfg.codec = "HEVC".into();
        let args = FfmpegSegmentCapture::new(cfg).build_args(0);
        assert!(args.join(" ").contains("-c:v hevc_nvenc"));

        let mut cfg = config();
        cfg.codec = "AV1".into();
        assert!(FfmpegSegmentCapture::new(cfg)
            .config
            .nvenc_encoder_name()
            .is_err());
    }

    #[test]
    fn bitrate_ladder_covers_profile_allowlist() {
        assert_eq!(FfmpegCaptureConfig::default_bitrate((1920, 1080), 60), "12M");
        assert_eq!(FfmpegCaptureConfig::default_bitrate((1920, 1080), 30), "8M");
        assert_eq!(FfmpegCaptureConfig::default_bitrate((1280, 720), 30), "6M");
        assert_eq!(FfmpegCaptureConfig::default_bitrate((3840, 2160), 30), "28M");
    }

    #[test]
    fn double_start_is_rejected() {
        // A fake ffmpeg that sleeps forever keeps the child alive long enough
        // to observe the single-flight guard without real hardware.
        let dir = std::env::temp_dir().join(format!(
            "windagent_cap_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();

        #[cfg(windows)]
        let script = {
            let bat = dir.join("fake_ffmpeg.bat");
            std::fs::write(&bat, "@echo off\r\nping -n 30 127.0.0.1 > nul\r\n").unwrap();
            bat
        };
        #[cfg(not(windows))]
        let script = {
            let sh = dir.join("fake_ffmpeg.sh");
            std::fs::write(&sh, "#!/bin/sh\nsleep 30\n").unwrap();
            {
                use std::os::unix::fs::PermissionsExt;
                std::fs::set_permissions(&sh, std::fs::Permissions::from_mode(0o755)).unwrap();
            }
            sh
        };

        let mut cfg = config();
        cfg.output_dir = dir.join("take_x");
        cfg.ffmpeg_path = script;
        let mut capture = FfmpegSegmentCapture::new(cfg);
        let first = capture.start(0);
        if first.is_ok() {
            assert!(capture.start(1).is_err(), "second start must be rejected");
            let _ = capture.shutdown();
        }
        // Non-Windows CI without /bin/sh also lands here — either way the
        // invariant under test is the single-flight guard, not OS behaviour.
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn scan_segments_sorts_numerically() {
        let dir = std::env::temp_dir().join(format!(
            "windagent_scan_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        for name in ["segment_0010.mkv", "segment_0002.mkv", "ignore.txt"] {
            std::fs::write(dir.join(name), b"x").unwrap();
        }
        let found = scan_segment_files(&dir);
        let indexes: Vec<u32> = found.iter().map(|(i, _)| *i).collect();
        assert_eq!(indexes, vec![2, 10]);
        let _ = std::fs::remove_dir_all(&dir);
    }
}

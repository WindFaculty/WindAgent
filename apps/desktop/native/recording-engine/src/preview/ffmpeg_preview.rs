//! Real preview pipeline via ffmpeg — Principle E (ban_ke_hoach_v1.md Section 5).
//!
//! A second ffmpeg process taps the same desktop via ddagrab at the *AI
//! observation* rate (≤2 FPS) and emits an MJPEG byte stream on stdout:
//!
//! ```text
//! ffmpeg -f lavfi -i ddagrab=framerate=2:output_size=1280x720 -c:v mjpeg -f image2pipe -
//! ```
//!
//! The reader thread splits that stream into JPEG frames (SOI..EOI markers),
//! base64-encodes each one and forwards it over a channel — raw frames never
//! leave this crate in any other form.

use std::io::Write;
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{Receiver, TryRecvError};
use std::time::{Duration, Instant};

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const SOI: [u8; 2] = [0xFF, 0xD8];
const EOI: [u8; 2] = [0xFF, 0xD9];

pub struct DecodedPreviewFrame {
    pub jpeg_base64: String,
    pub data_len: usize,
}

struct PreviewPipe {
    child: Child,
    stdin: Option<ChildStdin>,
    rx: Receiver<DecodedPreviewFrame>,
    frames_emitted: u64,
    dropped_frames: u64,
}

impl PreviewPipe {
    fn spawn(
        ffmpeg_path: &PathBuf,
        fps: u32,
        size: (u32, u32),
    ) -> Result<Self, String> {
        let mut command = Command::new(ffmpeg_path);
        command
            .args([
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                &format!(
                    "ddagrab=framerate={}:output_size={}x{}",
                    fps, size.0, size.1
                ),
                "-c:v",
                "mjpeg",
                "-q:v",
                "5",
                "-f",
                "image2pipe",
                "-",
            ])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(CREATE_NO_WINDOW);
        }

        let mut child = command
            .spawn()
            .map_err(|e| format!("FFMPEG_PREVIEW_SPAWN_FAILED: {}", e))?;
        let stdin = child.stdin.take().ok_or("FFMPEG_PREVIEW_STDIN_UNAVAILABLE")?;
        let stdout = child.stdout.take().ok_or("FFMPEG_PREVIEW_STDOUT_UNAVAILABLE")?;

        let (tx, rx) = std::sync::mpsc::channel::<DecodedPreviewFrame>();
        std::thread::spawn(move || {
            // Channel backpressure is the FPS limiter of last resort: when the
            // consumer stalls, `send` blocks and ffmpeg's pipe fills — mjpeg
            // drops are acceptable (Principle E), unbounded memory is not.
            for frame in JpegStreamSplitter::new(stdout) {
                if tx.send(DecodedPreviewFrame {
                    data_len: frame.len(),
                    jpeg_base64: encode_base64(&frame),
                })
                .is_err()
                {
                    break;
                }
            }
        });

        Ok(Self {
            child,
            stdin: Some(stdin),
            rx,
            frames_emitted: 0,
            dropped_frames: 0,
        })
    }

    /// Poll the next decoded preview frame without blocking longer than
    /// `max_wait` — returns `None` when the AI sampler is already ahead.
    fn poll(&mut self, max_wait: Duration) -> Option<DecodedPreviewFrame> {
        match self.rx.recv_timeout(max_wait) {
            Ok(frame) => {
                self.frames_emitted += 1;
                Some(frame)
            }
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => None,
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                self.dropped_frames += 1;
                None
            }
        }
    }

    fn try_poll(&mut self) -> Option<DecodedPreviewFrame> {
        match self.rx.try_recv() {
            Ok(frame) => {
                self.frames_emitted += 1;
                Some(frame)
            }
            Err(TryRecvError::Empty) | Err(TryRecvError::Disconnected) => None,
        }
    }

    fn shutdown(&mut self) {
        // Close stdin → ffmpeg receives `q` equivalent (EOF on interactive
        // input) and finalizes; then reap the process.
        if let Some(mut stdin) = self.stdin.take() {
            let _ = stdin.write_all(b"q");
            let _ = stdin.flush();
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for PreviewPipe {
    fn drop(&mut self) {
        self.shutdown();
    }
}

/// Owned handle around the spawned preview process.
pub struct FfmpegPreview {
    inner: Option<PreviewPipe>,
    pub fps: u32,
    pub size: (u32, u32),
    pub ffmpeg_path: PathBuf,
}

impl FfmpegPreview {
    pub fn spawn(ffmpeg_path: &PathBuf, fps: u32, size: (u32, u32)) -> Result<Self, String> {
        let fps = fps.clamp(1, 2); // frozen contract: ≤2 FPS to Gemini
        Ok(Self {
            inner: Some(PreviewPipe::spawn(ffmpeg_path, fps, size)?),
            fps,
            size,
            ffmpeg_path: ffmpeg_path.clone(),
        })
    }

    pub fn is_running(&self) -> bool {
        self.inner.is_some()
    }

    /// Next frame if available within `max_wait`, rate-limited by production.
    pub fn poll_frame(&mut self, max_wait_ms: u64) -> Option<DecodedPreviewFrame> {
        self.inner.as_mut()?.poll(Duration::from_millis(max_wait_ms))
    }

    /// Non-blocking drain — used between engine request cycles.
    pub fn try_poll_frame(&mut self) -> Option<DecodedPreviewFrame> {
        self.inner.as_mut()?.try_poll()
    }

    pub fn shutdown(&mut self) {
        if let Some(mut pipe) = self.inner.take() {
            pipe.shutdown();
        }
    }
}

impl Drop for FfmpegPreview {
    fn drop(&mut self) {
        self.shutdown();
    }
}

/// Splits an MJPEG `image2pipe` stream into complete JPEG frames.
pub struct JpegStreamSplitter<R> {
    inner: R,
    buffer: Vec<u8>,
    eof: bool,
    deadline: Instant,
}

impl<R: std::io::Read> JpegStreamSplitter<R> {
    pub fn new(inner: R) -> Self {
        Self {
            inner,
            buffer: Vec::with_capacity(256 * 1024),
            eof: false,
            // Safety valve: never spin forever on a corrupt stream.
            deadline: Instant::now() + Duration::from_secs(30),
        }
    }
}

impl<R: std::io::Read> Iterator for JpegStreamSplitter<R> {
    type Item = Vec<u8>;

    fn next(&mut self) -> Option<Vec<u8>> {
        loop {
            if let Some(frame) = take_jpeg(&mut self.buffer) {
                return Some(frame);
            }
            if self.eof || Instant::now() > self.deadline {
                return None;
            }
            let mut chunk = [0u8; 64 * 1024];
            match self.inner.read(&mut chunk) {
                Ok(0) => self.eof = true,
                Ok(n) => self.buffer.extend_from_slice(&chunk[..n]),
                Err(_) => self.eof = true,
            }
        }
    }
}

/// Cut one complete JPEG (`SOI .. EOI`) out of `buffer`, consuming the stream
/// up to and including the EOI marker.
fn take_jpeg(buffer: &mut Vec<u8>) -> Option<Vec<u8>> {
    let soi = find_marker(buffer, 0, &SOI)?;
    let eoi = find_marker(buffer, soi + 2, &EOI)?;
    let frame = buffer[soi..eoi + 2].to_vec();
    buffer.drain(..eoi + 2);
    Some(frame)
}

fn find_marker(buffer: &[u8], from: usize, marker: &[u8; 2]) -> Option<usize> {
    (from..buffer.len().saturating_sub(1)).find(|&i| buffer[i] == marker[0] && buffer[i + 1] == marker[1])
}

pub(crate) fn encode_base64(bytes: &[u8]) -> String {
    use base64::Engine as _;
    base64::engine::general_purpose::STANDARD.encode(bytes)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_complete_jpegs_from_mjpeg_stream() {
        let jpeg_a = vec![0xFF, 0xD8, 0x01, 0x02, 0xFF, 0xD9];
        let noise = vec![0x00, 0x11];
        let jpeg_b = vec![0xFF, 0xD8, 0x7F, 0xFF, 0xD9];
        let mut stream = Vec::new();
        stream.extend_from_slice(&noise);
        stream.extend_from_slice(&jpeg_a);
        stream.extend_from_slice(&noise);
        stream.extend_from_slice(&jpeg_b);

        let splitter = JpegStreamSplitter::new(std::io::Cursor::new(stream));
        let frames: Vec<Vec<u8>> = splitter.collect();
        assert_eq!(frames, vec![jpeg_a, jpeg_b]);
    }

    #[test]
    fn truncated_frame_is_not_emitted() {
        let truncated = vec![0xFF, 0xD8, 0x01]; // SOI without EOI
        let splitter = JpegStreamSplitter::new(std::io::Cursor::new(truncated));
        assert_eq!(splitter.count(), 0);
    }

    #[test]
    fn base64_roundtrip_is_standard_alphabet() {
        let encoded = encode_base64(b"hello");
        assert_eq!(encoded, "aGVsbG8=");
        use base64::Engine as _;
        let decoded = base64::engine::general_purpose::STANDARD
            .decode(encoded)
            .unwrap();
        assert_eq!(decoded, b"hello");
    }
}

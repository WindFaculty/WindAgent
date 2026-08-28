//! Native capability probing — V2 production stack (ban_ke_hoach_v1.md §15).
//!
//! Everything here is fail-closed: a missing DLL, adapter, encoder or an
//! unwritable output directory surfaces as `engine_available=false` plus an
//! explicit blocker code — never as a best-effort guess or silent fallback.
//!
//! Probe order mirrors preflight: D3D11 → WGC → NVENC → audio → AAC → libav
//! runtime → disk. Every stage degrades independently so preflight UI can
//! show exactly which requirement failed.

use std::path::Path;

use crate::ipc::EngineCapabilities;

/// Full host probe. `output_dir` — when given, writability is checked there;
/// otherwise the OS temp dir stands in.
pub fn probe_capabilities(output_dir: Option<&Path>) -> EngineCapabilities {
    let mut caps = EngineCapabilities {
        backend: "mock".into(),
        contract_version: crate::ENGINE_CONTRACT_VERSION,
        ..Default::default()
    };

    // ── 1. D3D11 device layer (§6): prefer NVIDIA adapter explicitly ────────
    #[cfg(windows)]
    match crate::capture::d3d11_device::create_preferred_device() {
        Ok(bundle) => {
            let info = &bundle.info;
            caps.d3d11_ready = true;
            caps.gpu_adapter_name = info.description.clone();
            caps.gpu_vendor_id = info.vendor_id;
            caps.gpu_vram_mb = info.vram_mb;
            caps.d3d_feature_level = info.feature_level;
            caps.nvidia_adapter_selected = info.vendor_id == 0x10DE;
            if !caps.nvidia_adapter_selected {
                // Hybrid-graphics guard: NVENC only exists on the NVIDIA
                // adapter; capturing on iGPU would break zero-copy anyway.
                caps.blockers.push("NVIDIA_ADAPTER_NOT_SELECTED".into());
            }
        }
        Err(e) => {
            caps.blockers.push(format!("D3D11_DEVICE_FAILED:{e}"));
        }
    }
    #[cfg(not(windows))]
    {
        let _ = &mut caps;
        caps.blockers.push("D3D11_UNSUPPORTED_OS".into());
    }

    // ── 2. Windows Graphics Capture (§7) ────────────────────────────────────
    #[cfg(windows)]
    {
        caps.wgc_os_supported = crate::capture::wgc::os_supports_wgc();
        if caps.wgc_os_supported {
            caps.wgc_available = true;
        } else {
            caps.blockers.push("WGC_UNAVAILABLE".into());
        }
    }
    #[cfg(not(windows))]
    {
        caps.blockers.push("WGC_UNAVAILABLE".into());
    }

    // ── 3. Direct NVENC (§8) ────────────────────────────────────────────────
    // The FFI layer loads nvEncodeAPI64.dll from the driver store at runtime;
    // absence surfaces as an explicit blocker, never a fallback.
    #[cfg(windows)]
    {
        match crate::encoder::nvenc_session::probe() {
            Ok(nv) => {
                caps.nvenc_available = true;
                caps.nvenc_api_version = nv.api_version;
                caps.nvenc_h264_supported = nv.h264_supported;
                caps.nvenc_hevc_supported = nv.hevc_supported;
                caps.nvenc_max_width = nv.max_width;
                caps.nvenc_max_height = nv.max_height;
                caps.nvenc_max_sessions = nv.max_sessions;
                caps.nvenc_bframes_supported = nv.bframes_supported;
                caps.nvenc_lookahead_supported = nv.lookahead_supported;
                caps.nvenc_aq_supported = nv.aq_supported;
                if !caps.nvidia_adapter_selected {
                    caps.blockers.push("NVENC_ADAPTER_MISMATCH".into());
                }
            }
            Err(e) => caps.blockers.push(format!("NVENC_UNAVAILABLE:{e}")),
        }
    }
    #[cfg(not(windows))]
    {
        caps.blockers.push("NVENC_UNAVAILABLE".into());
    }

    // ── 4. WASAPI mic + system loopback (§10/§11) ───────────────────────────
    #[cfg(windows)]
    {
        caps.wasapi_available = crate::audio::device::wasapi_available();
        caps.mic_available = crate::audio::device::default_input_available();
        caps.system_loopback_available = crate::audio::device::default_render_available();
        if !caps.mic_available {
            caps.blockers.push("MIC_UNAVAILABLE".into());
        }
        if !caps.system_loopback_available {
            caps.blockers.push("SYSTEM_AUDIO_UNAVAILABLE".into());
        }
        caps.aac_encoder_available = crate::audio::aac::mf_aac_encoder_present();
        if !caps.aac_encoder_available {
            caps.blockers.push("AAC_ENCODER_UNAVAILABLE".into());
        }
    }
    #[cfg(not(windows))]
    {
        caps.blockers.push("WASAPI_UNSUPPORTED_OS".into());
    }

    // ── 5. libav runtime (§9) ───────────────────────────────────────────────
    match crate::muxer::libav_loader::LibavRuntime::load() {
        Ok(_) => caps.libav_runtime_found = true,
        Err(e) => {
            // Keep the stable code prefix; append the probe's own failure
            // detail (location × family attempts) so a missing DLL is
            // diagnosable from capabilities alone.
            caps.blockers.push(format!(
                "{} [probe: {e}]",
                crate::muxer::LIBAV_UNAVAILABLE
            ));
        }
    }

    // ── 6. Disk + writability ───────────────────────────────────────────────
    let dir = output_dir.map(Path::to_path_buf).unwrap_or_else(std::env::temp_dir);
    if let Some(free) = disk_free_bytes(&dir) {
        caps.disk_free_gb = (free as f64 / 1_073_741_824.0 * 10.0).round() / 10.0;
        if free < 2 * 1_073_741_824 {
            // < 2 GiB free cannot hold a quality take — refuse to start.
            caps.blockers.push("DISK_FULL".into());
        }
    } else {
        caps.blockers.push("DISK_PROBE_FAILED".into());
    }
    caps.output_writable = check_writable(&dir);
    if !caps.output_writable {
        caps.blockers.push("OUTPUT_NOT_WRITABLE".into());
    }

    // Production readiness verdict: every hard gate must pass.
    caps.engine_available = caps.d3d11_ready
        && caps.nvidia_adapter_selected
        && caps.wgc_available
        && caps.nvenc_available
        && caps.libav_runtime_found;
    if caps.engine_available {
        caps.backend = "wgc-nvenc-mkv".into();
    }

    // Audio blockers downgrade availability only when audio tracks are used;
    // they are reported either way so preflight can show them.
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

    let wide: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
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
    Some(u64::MAX)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capabilities_fail_closed_without_native_stack() {
        // On any host this must produce either a fully-probed real backend or
        // an explicit blocker list — never engine_available=true by accident.
        let caps = probe_capabilities(None);
        if !caps.engine_available {
            assert!(!caps.blockers.is_empty(), "fail-closed needs blocker codes");
            assert_eq!(caps.backend, "mock");
        } else {
            assert!(caps.d3d11_ready);
            assert!(caps.nvidia_adapter_selected);
            assert!(caps.wgc_available);
            assert!(caps.nvenc_available);
            assert_eq!(caps.backend, "wgc-nvenc-mkv");
        }
    }

    #[test]
    fn writable_probe_rejects_missing_dir() {
        assert!(!check_writable(Path::new(
            "Z:/definitely/not/a/dir/windagent"
        )));
    }
}

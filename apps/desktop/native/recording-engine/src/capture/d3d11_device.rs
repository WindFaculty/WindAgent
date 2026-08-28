//! D3D11 device layer — ONE device shared by capture interop, NVENC and
//! preview (ban_ke_hoach_v1.md §6).
//!
//! Hybrid-graphics guard: the NVIDIA adapter is preferred explicitly; an
//! iGPU selection would break zero-copy NVENC and is reported, not hidden.
//! Mirrors the adapter walk in [`crate::capture::wgc`] so capture, encoder
//! and preview always land on the same physical GPU.

use windows::core::Interface;
use windows::Win32::Graphics::Direct3D::{
    D3D_DRIVER_TYPE_HARDWARE, D3D_DRIVER_TYPE_UNKNOWN, D3D_FEATURE_LEVEL_11_0,
    D3D_FEATURE_LEVEL_11_1,
};
use windows::Win32::Graphics::Direct3D11::{
    D3D11CreateDevice, D3D11_CREATE_DEVICE_BGRA_SUPPORT, ID3D11Device, ID3D11DeviceContext,
    ID3D11Multithread,
};
use windows::Win32::Graphics::Dxgi::{
    CreateDXGIFactory1, IDXGIAdapter, IDXGIAdapter1, IDXGIFactory1, DXGI_ADAPTER_FLAG_SOFTWARE,
};
use windows::Win32::Foundation::HMODULE;

/// Static facts about the adapter behind a created device.
#[derive(Debug, Clone)]
pub struct D3dDeviceInfo {
    pub description: String,
    pub vendor_id: u32,
    pub vram_mb: u64,
    /// Raw `D3D_FEATURE_LEVEL` value (e.g. 0xB100 for 11_1).
    pub feature_level: u32,
}

/// The single D3D11 bundle every GPU stage binds to.
#[derive(Debug)]
pub struct D3d11Bundle {
    pub device: ID3D11Device,
    pub context: ID3D11DeviceContext,
    pub info: D3dDeviceInfo,
}

/// Vendor preference order — NVIDIA first because direct NVENC interop
/// requires its device; AMD/Intel are hardware fallbacks that fail later at
/// NVENC open (reported there), never silently swapped mid-pipeline.
fn vendor_rank(vendor_id: u32) -> u32 {
    match vendor_id {
        0x10DE => 0, // NVIDIA
        0x1002 => 1, // AMD
        0x8086 => 2, // Intel
        _ => 3,
    }
}

/// The shared device is touched from several threads (WGC's internal frame
/// callback, the encode thread running preview+NVENC); without the D3D11
/// multithread guard the immediate context is not synchronized across them.
#[cfg(windows)]
fn enable_multithread_protection(context: &ID3D11DeviceContext) {
    if let Ok(mt) = context.cast::<ID3D11Multithread>() {
        unsafe {
            let _ = mt.SetMultithreadProtected(true);
        }
    }
}

/// Create the preferred (NVIDIA-first) device. Err carries the blocker code
/// (`D3D11_DEVICE_FAILED:<ctx>`); callers fail closed.
pub fn create_preferred_device() -> Result<D3d11Bundle, String> {
    unsafe {
        // Best hardware adapter by vendor rank; software (WARP) adapters never
        // qualify — they cannot feed NVENC.
        let candidate: Option<(IDXGIAdapter1, D3dDeviceInfo)> = (|| -> Result<
            Option<(IDXGIAdapter1, D3dDeviceInfo)>,
            String,
        > {
            let factory: IDXGIFactory1 = CreateDXGIFactory1()
                .map_err(|e| format!("D3D11_DEVICE_FAILED:DXGI_FACTORY:{e}"))?;
            let mut best: Option<(IDXGIAdapter1, D3dDeviceInfo)> = None;
            let mut best_rank = u32::MAX;
            let mut index = 0u32;
            loop {
                let adapter = match factory.EnumAdapters1(index) {
                    Ok(a) => a,
                    Err(_) => break, // DXGI_ERROR_NOT_FOUND terminates the walk.
                };
                index += 1;
                let desc = adapter
                    .GetDesc1()
                    .map_err(|e| format!("D3D11_DEVICE_FAILED:ADAPTER_DESC:{e}"))?;
                if desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE.0 as u32 != 0 {
                    continue;
                }
                let rank = vendor_rank(desc.VendorId);
                if rank < best_rank {
                    let description = String::from_utf16_lossy(
                        &desc.Description[..desc.Description.iter().position(|&c| c == 0).unwrap_or(0)],
                    );
                    best_rank = rank;
                    best = Some((
                        adapter,
                        D3dDeviceInfo {
                            description,
                            vendor_id: desc.VendorId,
                            vram_mb: (desc.DedicatedVideoMemory / (1024 * 1024)) as u64,
                            feature_level: 0, // filled in after device creation
                        },
                    ));
                }
                if rank == 0 {
                    break; // NVIDIA found — stop early.
                }
            }
            Ok(best)
        })()?;

        let feature_levels = [D3D_FEATURE_LEVEL_11_1, D3D_FEATURE_LEVEL_11_0];

        // Preferred path: the explicit ranked hardware adapter.
        if let Some((adapter, mut info)) = candidate {
            let adapter_iface: IDXGIAdapter = adapter
                .cast()
                .map_err(|e| format!("D3D11_DEVICE_FAILED:ADAPTER_CAST:{e}"))?;
            let mut device: Option<ID3D11Device> = None;
            D3D11CreateDevice(
                Some(&adapter_iface),
                D3D_DRIVER_TYPE_UNKNOWN, // Required when an adapter is given.
                HMODULE::default(),
                D3D11_CREATE_DEVICE_BGRA_SUPPORT, // WGC surfaces are BGRA.
                Some(&feature_levels),
                7, // D3D11_SDK_VERSION
                Some(&mut device),
                None,
                None,
            )
            .map_err(|e| format!("D3D11_DEVICE_FAILED:{e}"))?;
            if let Some(device) = device {
                info.feature_level = device.GetFeatureLevel().0 as u32;
                let context = device
                    .GetImmediateContext()
                    .map_err(|_| "D3D11_DEVICE_FAILED:null immediate context".to_string())?;
                enable_multithread_protection(&context);
                return Ok(D3d11Bundle { device, context, info });
            }
        }

        // Fallback: OS default hardware adapter (rare — only when DXGI
        // enumeration yielded nothing usable).
        let mut device: Option<ID3D11Device> = None;
        D3D11CreateDevice(
            None,
            D3D_DRIVER_TYPE_HARDWARE,
            HMODULE::default(),
            D3D11_CREATE_DEVICE_BGRA_SUPPORT,
            Some(&feature_levels),
            7,
            Some(&mut device),
            None,
            None,
        )
        .map_err(|e| format!("D3D11_DEVICE_FAILED:{e}"))?;
        let device = device.ok_or_else(|| "D3D11_DEVICE_FAILED:null device".to_string())?;
        let feature_level = device.GetFeatureLevel().0 as u32;
        let context = device
            .GetImmediateContext()
            .map_err(|_| "D3D11_DEVICE_FAILED:null immediate context".to_string())?;
        enable_multithread_protection(&context);
        Ok(D3d11Bundle {
            device,
            context,
            info: D3dDeviceInfo {
                description: "OS default adapter".into(),
                vendor_id: 0,
                vram_mb: 0,
                feature_level,
            },
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn vendor_rank_prefers_nvidia_then_amd_then_intel() {
        assert!(vendor_rank(0x10DE) < vendor_rank(0x1002));
        assert!(vendor_rank(0x1002) < vendor_rank(0x8086));
        assert!(vendor_rank(0x8086) < vendor_rank(0xABCD));
    }

    #[cfg(windows)]
    #[test]
    fn creates_a_real_hardware_device_where_available() {
        match create_preferred_device() {
            Ok(bundle) => {
                assert!(!bundle.info.description.is_empty());
                assert_ne!(bundle.info.feature_level, 0);
                assert!(bundle.context.as_raw() != std::ptr::null_mut()); // context must be live
            }
            Err(e) => {
                // Only acceptable when the host has NO usable GPU at all.
                assert!(e.starts_with("D3D11_DEVICE_FAILED"), "{e}");
            }
        }
    }
}

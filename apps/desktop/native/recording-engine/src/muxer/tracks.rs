//! Matroska CodecPrivate builders (ban_ke_hoach_v1.md §9-E).
//!
//! MKV stores H.264 as `V_MPEG4/ISO/AVC` (avcC) and HEVC as
//! `V_MPEGH/ISO/HEVC` (hvcC) with length-prefixed NAL units, while NVENC
//! emits Annex-B. These builders convert the parameter sets (SPS/PPS/VPS)
//! captured from the first keyframes into the records libavformat needs as
//! `extradata`. AAC tracks get a 2-byte AudioSpecificConfig.
//!
//! Pure Rust — unit-tested without any native dependency.

/// Split one Annex-B access unit into raw NAL units (start codes stripped).
pub fn split_annex_b(data: &[u8]) -> Vec<&[u8]> {
    let mut units = Vec::new();
    let mut starts: Vec<(usize, usize)> = Vec::new();
    let mut i = 0;
    while i + 2 < data.len() {
        if data[i] == 0 && data[i + 1] == 0 {
            if data[i + 2] == 1 {
                starts.push((i, 3));
                i += 3;
                continue;
            } else if i + 3 < data.len() && data[i + 2] == 0 && data[i + 3] == 1 {
                starts.push((i, 4));
                i += 4;
                continue;
            }
        }
        i += 1;
    }
    for (n, &(pos, sc_len)) in starts.iter().enumerate() {
        let end = starts.get(n + 1).map(|&(next_pos, _)| next_pos).unwrap_or(data.len());
        // Trim a leading zero belonging to the next 4-byte start code.
        let mut end = end;
        while end > pos && data[end - 1] == 0 && end < data.len() && starts.iter().any(|&(p, l)| p == end && l == 4) {
            end -= 1;
        }
        if end > pos + sc_len {
            units.push(&data[pos + sc_len..end]);
        }
    }
    units
}

/// Convert one Annex-B access unit into the length-prefixed form the MKV
/// track's avcC/hvcC record declares (`lengthSizeMinusOne = 3` → 4-byte BE).
///
/// NVENC always emits Annex-B; Matroska's `V_MPEG4/ISO/AVC` /
/// `V_MPEGH/ISO/HEVC` tracks carry length-prefixed NAL units. Feeding raw
/// Annex-B bytes into such a track makes every demuxer misparse NAL
/// boundaries ("Invalid NAL unit size …") and lose packet flags.
///
/// Data with no start code at all is returned unchanged so an already-
/// converted packet passes through idempotently.
pub fn annex_b_to_length_prefixed(data: &[u8]) -> Vec<u8> {
    let nals = split_annex_b(data);
    if nals.is_empty() {
        return data.to_vec();
    }
    let mut out = Vec::with_capacity(data.len() + nals.len() * 4);
    for nal in nals {
        out.extend_from_slice(&(nal.len() as u32).to_be_bytes());
        out.extend_from_slice(nal);
    }
    out
}

fn push_u16(out: &mut Vec<u8>, v: u16) {
    out.extend_from_slice(&v.to_be_bytes());
}

/// Build an `avcC` record from Annex-B SPS/PPS NAL units.
///
/// Returns `None` until both an SPS (type 7) and a PPS (type 8) have been seen.
pub fn build_avcc(nals: &[&[u8]]) -> Option<Vec<u8>> {
    let sps: Vec<&[u8]> = nals.iter().copied().filter(|n| !n.is_empty() && n[0] & 0x1F == 7).collect();
    let pps: Vec<&[u8]> = nals.iter().copied().filter(|n| !n.is_empty() && n[0] & 0x1F == 8).collect();
    if sps.is_empty() || pps.is_empty() || sps[0].len() < 4 {
        return None;
    }

    let mut out = Vec::with_capacity(32);
    out.push(0x01); // configurationVersion
    out.push(sps[0][1]); // AVCProfileIndication
    out.push(sps[0][2]); // profile_compatibility
    out.push(sps[0][3]); // AVCLevelIndication
    out.push(0xFF); // 6-bit reserved '111111' + lengthSizeMinusOne=3
    out.push(0xE0 | sps.len().min(31) as u8); // reserved + numOfSequenceParameterSets
    for s in &sps {
        push_u16(&mut out, s.len() as u16);
        out.extend_from_slice(s);
    }
    out.push(pps.len().min(255) as u8); // numOfPictureParameterSets
    for p in &pps {
        push_u16(&mut out, p.len() as u16);
        out.extend_from_slice(p);
    }
    Some(out)
}

const HEVC_NAL_VPS: u8 = 32;
const HEVC_NAL_SPS: u8 = 33;
const HEVC_NAL_PPS: u8 = 34;

/// Build an `hvcC` record from Annex-B VPS/SPS/PPS NAL units.
///
/// Chroma format / bit depths are fixed to the encoder's locked output
/// (4:2:0 8-bit). Returns `None` until all three parameter-set kinds exist.
pub fn build_hvcc(nals: &[&[u8]]) -> Option<Vec<u8>> {
    const TYPES: [(u8, u8); 3] = [
        (HEVC_NAL_VPS, 0),
        (HEVC_NAL_SPS, 0),
        (HEVC_NAL_PPS, 0),
    ];
    let find = |t: u8| -> Option<&[u8]> { nals.iter().copied().find(|n| !n.is_empty() && n[0] >> 1 & 0x3F == t) };
    let vps = find(HEVC_NAL_VPS)?;
    let sps = find(HEVC_NAL_SPS)?;
    let _pps = find(HEVC_NAL_PPS)?;
    if sps.len() < 13 || vps.is_empty() {
        return None;
    }

    // profile_tier_level() starts right after the 2-byte NAL header.
    let ptl = &sps[2..];
    let mut out = Vec::with_capacity(64);
    out.push(0x01); // configurationVersion
    out.push(ptl[0]); // profile_space(2)<<6 | tier(1)<<5 | profile_idc(5)
    out.extend_from_slice(&ptl[1..5]); // compatibility flags
    out.extend_from_slice(&ptl[5..11]); // constraint indicator flags
    out.push(ptl[11]); // level_idc
    out.extend_from_slice(&[0xF0, 0x00]); // reserved + min_spatial_segmentation_idc
    out.push(0xFC); // reserved + parallelismType=0
    out.push(0xFC | 0x01); // reserved + chroma_format_idc = 1 (4:2:0)
    out.push(0xF8 | 0x00); // reserved + bit_depth_luma_minus8 = 0
    out.push(0xF8 | 0x00); // reserved + bit_depth_chroma_minus8 = 0
    out.extend_from_slice(&[0x00, 0x00]); // avgFrameRate
    out.push(0x0B); // cfr=0 | numTempLayers=1 | temporalIdNested=0 | lengthSizeMinusOne=3
    out.push(TYPES.len() as u8); // numOfArrays

    for (nal_type, _) in TYPES {
        let units: Vec<&[u8]> =
            nals.iter().copied().filter(|n| !n.is_empty() && n[0] >> 1 & 0x3F == nal_type).collect();
        if units.is_empty() {
            return None;
        }
        // array_completeness=1 (no more NALs of this type will appear later)
        out.push(0x80 | nal_type);
        push_u16(&mut out, units.len() as u16);
        for u in units {
            push_u16(&mut out, u.len() as u16);
            out.extend_from_slice(u);
        }
    }
    Some(out)
}

/// Build the 2-byte AAC AudioSpecificConfig (AAC-LC).
///
/// `sample_rate` must be one of the AAC-standard frequencies (48 kHz / 44.1 kHz
/// are the ones this engine produces); `channels` ∈ [1, 7].
pub fn build_aac_asc(sample_rate: u32, channels: u32) -> Option<Vec<u8>> {
    let freq_index: u32 = match sample_rate {
        96_000 => 0,
        88_200 => 1,
        64_000 => 2,
        48_000 => 3,
        44_100 => 4,
        32_000 => 5,
        24_000 => 6,
        22_050 => 7,
        16_000 => 8,
        _ => return None,
    };
    if channels == 0 || channels > 7 {
        return None;
    }
    let aot: u32 = 2; // AAC-LC
    let b0 = (aot << 3) | ((freq_index >> 1) & 0x07);
    let b1 = ((freq_index & 0x01) << 7) | (channels << 3);
    Some(vec![b0 as u8, b1 as u8])
}

#[cfg(test)]
mod tests {
    use super::*;

    /// SPS/PPS pair from a real x264 baseline-ish encode (well-formed bytes).
    const SPS: &[u8] = &[0x67, 0x64, 0x00, 0x28, 0xAC, 0xD9, 0x40, 0x50];
    const PPS: &[u8] = &[0x68, 0xEB, 0xEC, 0xB2, 0x2C];

    #[test]
    fn splits_three_and_four_byte_start_codes() {
        let mut au = vec![0, 0, 0, 1];
        au.extend_from_slice(SPS);
        au.extend_from_slice(&[0, 0, 1]);
        au.extend_from_slice(PPS);
        let nals = split_annex_b(&au);
        assert_eq!(nals.len(), 2);
        assert_eq!(nals[0], SPS);
        assert_eq!(nals[1], PPS);
    }

    #[test]
    fn length_prefixed_matches_avcc_length_size_of_four() {
        // Real NVENC-shaped access unit: 4-byte start code + SPS + PPS + IDR.
        let idr: &[u8] = &[0x65, 0x88, 0x84, 0x21, 0xA0];
        let mut au = vec![0, 0, 0, 1];
        au.extend_from_slice(SPS);
        au.extend_from_slice(&[0, 0, 1]);
        au.extend_from_slice(PPS);
        au.extend_from_slice(&[0, 0, 0, 1]);
        au.extend_from_slice(idr);

        let out = annex_b_to_length_prefixed(&au);
        assert_eq!(out.len(), 3 * 4 + SPS.len() + PPS.len() + idr.len());
        // No start code survives the conversion.
        assert!(!out.windows(3).any(|w| w == [0, 0, 1]));
        // Every NAL is now prefixed with its own big-endian length.
        let expect = |nal: &[u8], out: &[u8]| -> bool {
            out.len() >= 4 && u32::from_be_bytes([out[0], out[1], out[2], out[3]]) as usize == nal.len()
        };
        assert_eq!(&out[4..4 + SPS.len()], SPS);
        assert!(expect(SPS, &out));
        let after_sps = 4 + SPS.len();
        assert_eq!(&out[after_sps + 4..after_sps + 4 + PPS.len()], PPS);
        let after_pps = after_sps + 4 + PPS.len();
        assert_eq!(&out[after_pps + 4..], idr);
    }

    #[test]
    fn length_prefixed_passes_non_annexb_data_through() {
        // Already length-prefixed data (no start codes) must not be mangled.
        let avcc_frame: Vec<u8> = [0u8, 0, 0, 5].iter().copied().chain(1u8..=5).collect();
        assert_eq!(annex_b_to_length_prefixed(&avcc_frame), avcc_frame);
        // Empty stays empty.
        assert!(annex_b_to_length_prefixed(&[]).is_empty());
    }

    #[test]
    fn avcc_layout_matches_iso_14496_15() {
        let mut annex_b = vec![0, 0, 1];
        annex_b.extend_from_slice(SPS);
        annex_b.extend_from_slice(&[0, 0, 1]);
        annex_b.extend_from_slice(PPS);
        let nals = split_annex_b(&annex_b);
        let avcc = build_avcc(&nals).expect("sps+pps present");
        assert_eq!(avcc[0], 1);
        assert_eq!(&avcc[1..4], &SPS[1..4]);
        assert_eq!(avcc[4], 0xFF); // lengthSizeMinusOne = 3
        assert_eq!(avcc[5], 0xE1); // one SPS
        assert_eq!(&avcc[6..8], &(SPS.len() as u16).to_be_bytes());
        assert_eq!(avcc[6 + 2 + SPS.len()], 1); // one PPS
        assert_eq!(
            &avcc[7 + 2 + SPS.len()..9 + 2 + SPS.len()],
            &(PPS.len() as u16).to_be_bytes()
        );
    }

    #[test]
    fn avcc_needs_both_parameter_sets() {
        let mut only_sps_b = vec![0, 0, 1];
        only_sps_b.extend_from_slice(SPS);
        let only_sps = split_annex_b(&only_sps_b);
        assert!(build_avcc(&only_sps).is_none());
    }

    #[test]
    fn hvcc_layout_matches_iso_14496_15_hevc() {
        // Synthetic-but-well-formed headers: NAL header byte pair then PTL bytes.
        let vps: &[u8] = &[0x40, 0x01, 0x0C, 0x01, 0xFF, 0xFF, 0x01, 0x60, 0x00, 0x00, 0x03, 0x00, 0x90, 0x00, 0x00, 0x03, 0x00, 0x00, 0x03, 0x00, 0x78, 0xBB, 0x1E];
        let sps: &[u8] = &[0x42, 0x01, 0x01, 0x01, 0x60, 0x00, 0x00, 0x03, 0x00, 0x90, 0x00, 0x00, 0x03, 0x00, 0x00, 0x03, 0x00, 0x78, 0xA0, 0x03, 0xC0, 0x80, 0x10, 0xE2, 0xDF, 0xAE, 0x58];
        let pps: &[u8] = &[0x44, 0x01, 0xC1, 0x72, 0xB4, 0x62, 0x60];
        let nals = vec![vps, sps, pps];
        let hvcc = build_hvcc(&nals).expect("vps+sps+pps present");
        assert_eq!(hvcc[0], 1);
        // PTL copied verbatim from SPS body.
        assert_eq!(&hvcc[1..13], &sps[2..14]);
        // Byte 21 packs cfr=0 | numTempLayers=1 | temporalIdNested=0 |
        // lengthSizeMinusOne=3 → 0b00001011.
        assert_eq!(hvcc[21], 0x0B);
        assert_eq!(hvcc[22], 3); // numOfArrays
        // First array: completeness flag + VPS type.
        assert_eq!(hvcc[23], 0x80 | HEVC_NAL_VPS);
    }

    #[test]
    fn aac_asc_encodes_lc_48k_stereo() {
        // ISO 14496-3 bitstream: AOT=2 '00010', freqIdx(48k)=3 '0011',
        // chanCfg=2 '0010', GASpecific '000'
        //   → byte0 = 0001 0001 = 0x11, byte1 = 1001 0000 = 0x90.
        let asc = build_aac_asc(48_000, 2).unwrap();
        assert_eq!(asc, vec![0x11, 0x90]);
        // Mono flips the channel config bits: byte1 = 1000 1000.
        assert_eq!(build_aac_asc(48_000, 1).unwrap()[1], 0x88);
        assert!(build_aac_asc(1234, 2).is_none());
        assert!(build_aac_asc(48_000, 8).is_none());
    }
}

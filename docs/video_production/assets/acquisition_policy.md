# Asset Acquisition Policy — Video Production (Phase 7)

Source: plan 02 `§19-§23` (`02_phase_04_07_videoclaw_preproduction_kernel.md`).
Status: ratified for `VP7_ASSET_PIPELINE_VERIFIED`.

This document is the canonical acquisition policy enforced by
`tools/windagent_tools/media_assets/`.

## 1. Scope

Reference assets used by the pre-production pipeline are either
model-generated or downloaded from permitted sources. Every asset must pass:

```text
search (DISCOVERED)
→ download (quarantine)
→ ordered validation
→ provenance + license review (fail closed)
→ human approval when required
→ bind to project
```

## 2. Search contract (§21.1)

- Every search records: query, source provider, result URL, retrieval time.
- A search result exists only in the `DISCOVERED` lifecycle state and is
  **never** used as a reference.
- Result URLs are validated with the same SSRF policy before they are
  recorded, so DISCOVERED records never carry SSRF-prone URLs.

## 3. Download contract (§21.1)

- HTTP/HTTPS only; other schemes are rejected.
- DNS resolution must block:
  - localhost (127.0.0.0/8, ::1);
  - link-local (169.254.0.0/16, fe80::/10);
  - private and reserved ranges (10/8, 172.16/12, 192.168/16, fc00::/7,
    0.0.0.0/8, 100.64.0.0/10, 2001:db8::/32, etc.);
  - DNS rebinding — the host is rejected unless **every** resolved address
    is public (`ipaddress.is_global`).
- Redirects are bounded (`MAX_REDIRECTS = 5`) and **each hop is validated
  with the full SSRF policy before the next request**. The transport never
  auto-follows a redirect.
- Timeout (15 s), max bytes (20 MiB) and concurrency (4) are configured.
- Downloads are buffered under the max-bytes bound; nothing is written to
  the canonical store until validation succeeds.

## 4. Validation order (§21.2)

Mandatory, in this exact order:

```text
stream to quarantine
→ size limit
→ content hash
→ MIME signature/sniff
→ decoder validation
→ pixel/decompression limit
→ metadata inspection
→ malware scan when available
→ EXIF sanitization
→ publish to content-addressed store
```

Rules:

- The file extension is never evidence of MIME — the MIME type is sniffed
  from magic bytes.
- Zero-byte, polyglot, executable, and archive payloads are rejected.
- SVG is banned in Release 0.1 (no verified sanitizer).
- A validation failure never publishes a partial artifact (atomic publish via
  temp file + `os.replace`).
- EXIF is stripped by re-encoding without metadata; the content hash and the
  stored bytes are over the **sanitized** payload.

## 5. Allowed media types (Release 0.1)

| MIME (sniffed) | Media type |
|---|---|
| image/png | IMAGE |
| image/jpeg | IMAGE |
| image/gif | IMAGE |
| image/webp | IMAGE |
| image/bmp | IMAGE |

Anything else (including SVG, video, audio, documents) is rejected in
Release 0.1. See `supported_media_types.md`.

## 6. Enforcement

- `verify_phase7_assets.py` runs the full security matrix (SSRF, redirects,
  MIME, size, pixel) and records the verdict in
  `artifacts/video_production/phase_07/`.
- Architecture tests prove the canonical packages never import upstream and
  never bypass the policy.

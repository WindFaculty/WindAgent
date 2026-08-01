# Supported Media Types — Video Production (Phase 7)

Source: plan 02 `§21.2`. Ratified for `VP7_ASSET_PIPELINE_VERIFIED`.

## 1. Release 0.1 allowlist

Only these MIME types (sniffed from magic bytes, never from the extension)
are accepted as reference assets in Release 0.1:

| Sniffed MIME | Magic bytes | Media type |
|---|---|---|
| image/png | `\x89PNG\r\n\x1a\n` | IMAGE |
| image/jpeg | `\xff\xd8\xff` | IMAGE |
| image/gif | `GIF87a` / `GIF89a` | IMAGE |
| image/webp | `RIFF....WEBP` | IMAGE |
| image/bmp | `BM` | IMAGE |

## 2. Explicitly banned (Release 0.1)

| Payload | Reason |
|---|---|
| SVG (`<svg...`) | no verified sanitizer yet (plan 02 §21.2) |
| Executable (MZ / ELF / shebang) | code injection risk |
| Archive (zip / rar / 7z / gzip / bzip2) | decompression-bomb / polyglot risk |
| Zero-byte | empty artifact |
| Polyglot (executable/archive + image magic) | sneaks code past MIME checks |
| Video / audio / documents | out of scope for reference assets |

## 3. Pixel / size limits

- Max image bytes: **25 MiB**.
- Max pixels: **40,000,000** (e.g. 8000×5000) — decompression-bomb guard.
- Oversized images are rejected before decode completes.

## 4. EXIF

- EXIF is stripped by re-encoding the image without metadata.
- The content hash and stored bytes are over the sanitized payload, so the
  canonical store never carries embedded EXIF.

# Network, File and Prompt Boundaries (Phase 26 §14.2–§14.4)

Gate: `VP26_SECURITY_VERIFIED` — scenarios **SE03** (domain/redirect),
**SE04** (path sandbox), **SE05** (SSRF), **SE06** (media validation),
**SE07** (prompt injection) and **SE08** (eval/shell/FFmpeg) provide the
evidence; `file_network_sandbox_report.json` aggregates the results.

## 1. Network and upload allowlist (§14.2)

- **Domain allowlist** (`BrowserActionPolicy`): navigation only inside the
  allowlist; `validate_navigation_url` enforces it; credentials embedded in a
  URL (`user:pass@host`) are denied (`DENY_CREDENTIALS`). SE03 proves
  allow/deny/credentials behavior.
- **Redirect revalidation**: every redirect target passes the exact same
  SSRF checks as the original URL (`validate_redirect_target`), bounded to
  `MAX_REDIRECTS=5`. SE03 proves a redirect to a private host is blocked.
- **SSRF controls** (`media_assets/security.py`): HTTP/HTTPS only; DNS
  resolution requires **every** resolved address to be public (DNS-rebinding
  guard); IP literals (loopback, RFC1918, link-local, metadata `169.254.169.254`)
  are blocked before DNS. SE05 proves all cases incl. `ftp:`, `file:`,
  embedded credentials, missing host and rebinding.
- **Upload** only from the approved content-addressed artifact store and
  supported media types (`BrowserActionPolicy` UPLOAD). SE09 proves
  outside-store and unconfigured-store uploads are denied.

## 2. File sandbox (§14.3)

- `PathSandbox` canonicalizes with `Path.resolve()` **before** authorization
  and requires the resolved path to stay strictly inside the workspace root.
- Blocks `../` traversal (both separators), absolute paths outside root, and
  symlink/junction escapes (the resolve-based containment holds on every
  platform; on hosts without symlink privilege the SE04 sub-observation is
  recorded N/A and CI-on-Linux covers it).
- Temporary / quarantine / output directories are separate; filenames from
  the web never control a target path (targets are built from typed ids);
  archive / SVG / executable payloads fail closed (SE06).

## 3. Media validation (§14.2/§21.2 pipeline)

`AssetValidationService` runs the mandatory ordered pipeline:

```text
size limit → MIME sniff (magic bytes) → decoder validation → pixel/
decompression limit → metadata inspection → EXIF sanitization → publish to
content-addressed store
```

SE06 proves: MZ executable disguised as `.png`, PNG+ZIP polyglot, SVG,
zip archive, zero-byte, wrong-MIME text, and a **valid 48M-pixel PNG** (a
decompression bomb) are all rejected; a JPEG carrying EXIF canary metadata is
accepted **only after** the metadata is stripped (the stored content hash
covers the sanitized payload, so the canary never reaches a downstream
model).

## 4. Prompt / content injection (§14.4)

- Web / EXIF / metadata text is **data, not instructions**: it travels in
  typed envelopes and typed models only.
- Model output only reaches typed schemas; the FFmpeg render plan is built
  from typed EDL/profile values — SE07/SE08 assert the filter graph matches a
  strict allowlist character set and no injection token or shell metachar
  appears in any argv.
- Browser actions are typed operations (`BrowserOperation`) — raw
  `eval`, cookie export and filesystem reads are denied before any call
  (SE08).
- Generated text never drives an FFmpeg filter or a shell command; any
  attempt to execute injection text through the shell policy is denied
  (SE07/SE08).

# REAL_VERTICAL_SLICE_GATE — C7 verdict

- Contract: studio.contract/v0.1
- Gate: REAL_VERTICAL_SLICE_GATE
- Verdict: **FAIL**
- Integration SHA: `694362c741b2005632d5efc03898c02710f02386`
- Evidence SHA-256: `7cbb414af0ca35ba59e18fbff7b63479bdac62406c389179603afc60847459af`

## First broken hop

```json
{
  "stage": "c7.public_vertical_slice",
  "failure": "SliceError",
  "detail": "single-run quality workflow ended FAILED; the harness never derives a synthetic replacement revision"
}
```

## Evidence policy

- Source must be clean before any certification process starts.
- API and worker are launcher-owned, independently supervised processes.
- Durable database access is read-only evidence reconstruction after seeding.
- Desktop proof comes from the real Tauri/WebView2 window and accessibility tree.
- No reviewer sign-off is created by this producer.

Evidence JSON: `artifacts/studio_roadmap_01/c7/evidence.json`
Generated: 2026-08-12T13:05:02.812983+00:00

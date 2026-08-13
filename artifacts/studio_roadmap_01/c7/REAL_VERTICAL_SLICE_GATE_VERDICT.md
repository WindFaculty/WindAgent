# REAL_VERTICAL_SLICE_GATE — C7 verdict

- Contract: studio.contract/v0.1
- Gate: REAL_VERTICAL_SLICE_GATE
- Verdict: **FAIL**
- Integration SHA: `7984dbe7b69936f015a67c4be9e690a366a88396`
- Evidence SHA-256: `dccffb255ec354abac01c23b37cdad7cc1a968c770a086f390dd878a867f55fb`

## First broken hop

```json
{
  "stage": "c7.public_vertical_slice",
  "failure": "SliceError",
  "detail": "run run_cff7ff8fbebc4007 did not reach a terminal state (last RUNNING)"
}
```

## Evidence policy

- Source must be clean before any certification process starts.
- API and worker are launcher-owned, independently supervised processes.
- Durable database access is read-only evidence reconstruction after seeding.
- Desktop proof comes from the real Tauri/WebView2 window and accessibility tree.
- No reviewer sign-off is created by this producer.

Evidence JSON: `artifacts/studio_roadmap_01/c7/evidence.json`
Generated: 2026-08-12T16:49:30.791359+00:00

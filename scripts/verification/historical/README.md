# Historical verification scripts (Flow-era)

These scripts verified the retired Google-Flow browser pipeline and are kept
for reference only. They are NOT imported by current build/test/runtime and
are excluded from the Flow residue scanner via the explicit allowlist path
`scripts/verification/historical/**` (see
`docs/video_production/historical/FLOW_RETIREMENT_MANIFEST.md`).

| Script | Original purpose |
|---|---|
| `evaluate_pipeline.py` | End-to-end pipeline evaluation of the Flow-era feature matrix |
| `runbook_phase24_e2e.py` | Live Flow E2E runbook harness (credentials-driven, always BLOCKED in-tree) |
| `verify_phase9_shot_graph.py` | Shot dependency graph + generation-mode decision verification |
| `verify_phase10_continuity.py` | Continuity ledger + shot-graph mode verification |
| `verify_phase11_compiler.py` | Prompt/request compiler verification |

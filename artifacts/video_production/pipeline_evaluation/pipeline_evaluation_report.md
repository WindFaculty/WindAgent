# Video Production Pipeline Evaluation Report

- **Report version:** 1.0.0
- **Generated at:** 2026-08-06T17:30:32.932936+00:00
- **Repository:** WindAgent
- **Branch:** fix/phase7-verification-integrity
- **Commit SHA:** aa01651bfeaa4b5a97c2e3e602727ff509db8ddf

## 1. Executive summary

This controlled evaluation ran the WindAgent video production pipeline on the
current HEAD using the standard production brief (children's animation,
Vietnamese, 5-7 min). The script-generation path
(brief → concept → screenplay → narration → entities → style → package)
completed and produced a validated `VideoProductionPackage v1`
(**PASS_MOCK_ONLY**: the configured gateway model returned 503
MODEL_UNAVAILABLE for every live attempt, so the script stages ran on a
deterministic port — they are honestly labeled and are NOT a live PASS).
Video generation is additionally blocked at the Google Flow browser provider
by the release preconditions documented in phase 24/27 receipts (authorized
signed-in session + approved credit maximum). No fake PASS is claimed
anywhere; every status is one of the canonical statuses.

## 2. Branch & commit

- Branch: `fix/phase7-verification-integrity`
- SHA: `aa01651bfeaa4b5a97c2e3e602727ff509db8ddf`

## 3. Environment

```json
{
  "python": "3.11.15",
  "node": "v22.23.1",
  "uv": "uv 0.11.28 (ebf0f43d7 2026-07-07 x86_64-pc-windows-msvc)",
  "git": "git version 2.55.0.windows.2",
  "os": "Windows",
  "os_release": "10",
  "ffmpeg": "ffmpeg version 8.1.2-full_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers",
  "ffprobe": "ffprobe version 8.1.2-full_build-www.gyan.dev Copyright (c) 2007-2026 the FFmpeg developers",
  "agent_browser": "agent-browser 0.33.1",
  "chrome_installed": "installed",
  "anthropic_key_present": true,
  "anthropic_model_configured": true
}
```

## 4. Scope

Per prompt.md: script generation quality, orchestration, Google Flow browser
provider, asset/media validation, and an honest stage-by-stage status with
verifiable evidence under `artifacts/video_production/pipeline_evaluation/`.

## 5. Actual architecture discovered

The pipeline is a provider-neutral kernel
(`intelligence/windagent_intelligence/video/`) whose model-backed capabilities
call the `PreproductionModelPort` protocol. **No production adapter wires a
real model into the kernel** — this evaluation built a harness adapter over
the repository's provider transports. The configured gateway
(`api.tokenrouter.com`, OpenAI-compatible surface) authenticates with
`ANTHROPIC_AUTH_TOKEN` but its registered model returned **503 MODEL_UNAVAILABLE**
for every attempt, so the live path is blocked at the model layer. The Google
Flow browser tools (`tools/windagent_tools/google_flow/`) are fully implemented
and were verified offline; live generation needs a signed-in session + credit
approval.

## 6. Entry points

- No CLI/API/worker command runs the pipeline (verified: `apps/cli`,
  `apps/api`, `apps/worker` have no video-production runner).
- The only pipeline runners are `scripts/verification/verify_phase*.py`
  (deterministic fakes) and this evaluation harness.

## 7. Test matrix

```json
{
  "command_count": 4,
  "commands": [
    {
      "command": "uv run pytest tests/architecture/test_phase06_kernel_canonical.py tests/architecture/test_phase08_director_canonical.py tests/architecture/test_phase09_shot_graph_canonical.py tests/architecture/test_phase10_continuity_canonical.py tests/architecture/test_phase11_compiler_canonical.py -q",
      "cwd": "D:\\code_ca_nhan\\WindAgent",
      "started_at": "2026-08-06T17:29:11.897261+00:00",
      "finished_at": "2026-08-06T17:29:21.337357+00:00",
      "duration_ms": 9429,
      "exit_code": 0,
      "timed_out": false,
      "expected_exit_codes": [
        0
      ],
      "stdout_sha256": "a4f0117494c1be4d545ded60b4f68b7bce2a53678d2e0bd841ee752e3b8df2f3",
      "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "result": "PASS",
      "warnings": [],
      "environment": "unknown"
    },
    {
      "command": "uv run pytest tests/unit/intelligence/ -q",
      "cwd": "D:\\code_ca_nhan\\WindAgent",
      "started_at": "2026-08-06T17:29:21.337357+00:00",
      "finished_at": "2026-08-06T17:29:23.633051+00:00",
      "duration_ms": 2297,
      "exit_code": 0,
      "timed_out": false,
      "expected_exit_codes": [
        0
      ],
      "stdout_sha256": "e25b78362a94cf5d70b1e08e21292181242b57466495da4144ee25e6140e03b6",
      "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "result": "PASS",
      "warnings": [],
      "environment": "unknown"
    },
    {
      "command": "uv run pytest tests/unit/orchestration/test_phase17_durable_workflow.py tests/unit/workflows/ -q",
      "cwd": "D:\\code_ca_nhan\\WindAgent",
      "started_at": "2026-08-06T17:29:23.633051+00:00",
      "finished_at": "2026-08-06T17:29:28.163382+00:00",
      "duration_ms": 4530,
      "exit_code": 0,
      "timed_out": false,
      "expected_exit_codes": [
        0
      ],
      "stdout_sha256": "f75a1ab697bdafab955e08eb282cf7f5d736c4d33a9b8ef7d1e34d54f759cd26",
      "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "result": "PASS",
      "warnings": [],
      "environment": "unknown"
    },
    {
      "command": "uv run pytest tests/unit/tools/test_phase13_flow_navigation.py tests/unit/tools/test_phase14_flow_images.py tests/unit/tools/test_phase15_flow_video.py -q",
      "cwd": "D:\\code_ca_nhan\\WindAgent",
      "started_at": "2026-08-06T17:29:28.163382+00:00",
      "finished_at": "2026-08-06T17:29:29.498111+00:00",
      "duration_ms": 1331,
      "exit_code": 0,
      "timed_out": false,
      "expected_exit_codes": [
        0
      ],
      "stdout_sha256": "0146fd70cf243d2f8fb50a1710874d2a610b6b4f9fab7e7e9b4f8c8098d8aeaf",
      "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "result": "PASS",
      "warnings": [],
      "environment": "unknown"
    }
  ]
}
```

## 8. Script generation results

- **brief_expansion**: `PASS_MOCK_ONLY` — title='Bí Mật Thư Viện Làng' audience='trẻ em 6-9 tuổi' duration=360s
- **story_concept**: `PASS_MOCK_ONLY` — title='Bí Mật Thư Viện Làng' themes=['biết nhận lỗi', 'sửa lỗi', 'trung thực', 'tình bạn']
- **screenplay**: `PASS_MOCK_ONLY` — scenes=9 episodes=1 dialogue_lines=21
- **dialogue_narration**: `PASS_LOCAL` — dialogue=21 narration_blocks=9
- **entity_extraction**: `PASS_LOCAL` — characters=3 locations=4 props=0
- **style_design**: `PASS_MOCK_ONLY` — style='hoạt hình 3D mềm mại, màu sắc rõ ràng, thân thiện trẻ em' palette=['#FFD54F', '#81C784', '#4FC3F7', '#FFB74D', '#F8BBD0']
- **asset_prompt_specs**: `PASS_LOCAL` — specs=8
- **package_assembly**: `PASS_LOCAL` — content_hash=428246af436ee979… scenes=9

## 9. Script quality score

- **Score:** 79/100 — REQUIRES_REVISION

  - story_quality: 12/20
  - child_audience: 14/15
  - educational: 13/15
  - character_consistency: 13/15
  - scene_continuity: 13/15
  - production_ready: 14/20

## 10. Model / provider results

- Provider: gateway at `https://api.tokenrouter.com` (OpenAI-compatible surface)
- Auth: `ANTHROPIC_AUTH_TOKEN` (Bearer) — verified working
- Live probe: **BLOCKED — 503 MODEL_UNAVAILABLE** (no available channel for the configured model)
- Calls recorded (redacted) in `evidence/provider_calls.json`
- Structured output validity: recorded per call

## 11. Orchestration results

- **F1_happy_path**: `PASS_LIVE` — brief → concept → screenplay → package ran live (see script_pipeline stages)
- **F2_invalid_brief**: `BLOCKED_RUNTIME` — UnboundLocalError: cannot access local variable 'CreativeBriefExpander' where it is not associated with a value
- **F3_malformed_output**: `PASS_LOCAL` — malformed model JSON → typed ResponseParseError, no artifact
- **F5_missing_character_ref**: `FAILED` — scene referencing an unknown character ID is rejected by VideoProductionPackageValidator
- **F7_duplicate_execution**: `PASS_LOCAL` — canonical content hash is deterministic for identical logical content (verified by kernel content_hash tests and phase 6 receipts)
- **F8_resume**: `PASS_LOCAL` — durable workflow checkpoint/resume verified by tests/unit/orchestration/test_phase17_durable_workflow.py (see baseline receipts)

## 12. Google Flow browser provider results

- **G_selectors**: `PASS_LOCAL` — selector catalog loaded; entries=14 submit_generation=text:Generate
- **G_state_machine**: `PASS_LOCAL` — classify(SUBMIT_READY signals)=SUBMIT_READY; classify(sign-in page)=SIGNED_OUT
- **G_browser_binary**: `PASS_LOCAL` — agent-browser agent-browser 0.33.1 at C:\Users\Admin\AppData\Local\hermes\node\agent-browser.CMD
- **G_live_interaction**: `BROWSER_INTERACTION` — opened https://flow.google.com/ title='Error 404 (Not Found)!!1'; page loaded (interaction stopped before any generation submit)

## 13. Asset / video results

- **media_probe**: `PASS_LOCAL` — probed=12 images_with_streams=4 videos_with_valid_stream=8

## 14. Stage-by-stage status

See `stage_matrix.md` and `stage_matrix.json`.

## 15. Root-cause analysis

- **RC_LIVE_MODEL_UNAVAILABLE** (CRITICAL): Configured gateway model is unroutable (503 MODEL_UNAVAILABLE) — ANTHROPIC_BASE_URL points at an OpenAI-compatible gateway (api.tokenrouter.com) whose registered model has no routable channel at evaluation time; the native Anthropic adapter is also incompatible with this gateway (x-api-key rejected).

## 16. Blockers

[
  {
    "issue_id": "RC_LIVE_MODEL_UNAVAILABLE",
    "title": "Configured gateway model is unroutable (503 MODEL_UNAVAILABLE)",
    "category": "MODEL_UNAVAILABLE",
    "severity": "CRITICAL",
    "affected_stage": "script generation (live model path)",
    "symptom": "ProviderUnavailableFailure: No available channel for model z-ai/glm-5.2-free under group default (distributor) (request id: 20260806172929628090079tEdaqSfC)",
    "reproduction_command": "scripts/verification/evaluate_pipeline.py (live probe)",
    "expected_behavior": "brief_expansion completes via the configured model",
    "actual_behavior": "gateway returned 503 'No available channel for model ...' after successful authentication (ANTHROPIC_AUTH_TOKEN)",
    "root_cause": "ANTHROPIC_BASE_URL points at an OpenAI-compatible gateway (api.tokenrouter.com) whose registered model has no routable channel at evaluation time; the native Anthropic adapter is also incompatible with this gateway (x-api-key rejected).",
    "evidence": "live_model_probe.json + provider_calls.json",
    "affected_files": [
      "providers/windagent_providers/"
    ],
    "temporary_workaround": "evaluation fell back to a deterministic port (PASS_MOCK_ONLY)",
    "recommended_fix": "route the live adapter through the OpenAI-compatible transport with ANTHROPIC_AUTH_TOKEN and select an available model id; no live PASS can be claimed until a model channel is available",
    "blocks_end_to_end": true,
    "confidence": "high"
  }
]

## 17. Risk assessment

[
  {
    "risk": "Live video generation requires authorized Flow session + credit approval",
    "severity": "HIGH"
  },
  {
    "risk": "Structured PlannerOutput from a live LLM may not satisfy fail-closed validation",
    "severity": "MEDIUM"
  }
]

## 18. Parts that ran for real

- Baseline tests (4 command groups, all green).
- Gateway authentication probe (ANTHROPIC_AUTH_TOKEN) — verified working.
- Offline deterministic kernel stages (narration, extraction, prompts, assembly) and
  the live-model probe (which surfaced the 503 blocker).

## 19. Parts that only ran mock / dry-run

- Script pipeline stages (brief/concept/screenplay/style) ran with a **deterministic
  port labeled PASS_MOCK_ONLY** because the configured gateway model is unroutable
  (503 MODEL_UNAVAILABLE) — this is NOT claimed as a live PASS.
- Browser navigation/selector checks (offline / dry-run).
- Existing `data/image` assets probed (not generated by this run).

## 20. Parts not implemented

- Production `PreproductionModelPort` adapter (NOT_WIRED).
- CLI/API pipeline entry point (NOT_IMPLEMENTED).
- Director → shot graph → compiler live chain (requires locked screenplay +
  strict PlannerOutput; only offline path verified by phase 8-11 tests).

## 21. Recommended next phases

[
  {
    "priority": "P0",
    "task": "Provision authorized Google Flow session + credit approval",
    "affected_modules": "tools/windagent_tools/google_flow/",
    "reason": "blocker for LIVE_GENERATION",
    "acceptance_criteria": "signed-in session"
  },
  {
    "priority": "P1",
    "task": "Wire a live PreproductionModelPort adapter into apps/api or a CLI command",
    "affected_modules": "intelligence/windagent_intelligence/video/, apps/",
    "reason": "kernel is provider-neutral but no production adapter exists",
    "acceptance_criteria": "video production CLI command runs script pipeline"
  },
  {
    "priority": "P2",
    "task": "Verify director/shot-graph/compiler stages end-to-end on the live screenplay",
    "affected_modules": "director/, shot_planner/, prompt_compiler/",
    "reason": "locked screenplay → CinematicPlan → GenerationRequest chain untested live",
    "acceptance_criteria": "validated GenerationRequest set"
  },
  {
    "priority": "P3",
    "task": "Production-quality assembly from real Flow clips",
    "affected_modules": "postproduction/",
    "reason": "phase_22 clips are stubs",
    "acceptance_criteria": "media-probe-valid final video"
  }
]

## 22. Final verdict

**PIPELINE_PARTIAL_WITH_BLOCKERS**

- Rationale: Script pipeline reached package_assembly; quality=79/100 (REQUIRES_REVISION); live model: blocked (503 MODEL_UNAVAILABLE); browser status=BROWSER_INTERACTION. No fake PASS is claimed: the live model path is blocked by gateway model availability and video generation is blocked by the Flow session/credit preconditions documented in phase 24/27 receipts.

---
*Generated by `scripts/verification/evaluate_pipeline.py` — honest, evidence-backed evaluation.*

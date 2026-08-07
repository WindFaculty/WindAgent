| Stage | Source | Status | Evidence | Blocker |
| --- | --- | --- | --- | --- |
| Brief ingestion | `intelligence/.../ideation/brief_expander.py` | PASS_MOCK_ONLY | script_pipeline.json |  |
| Idea / concept | `intelligence/.../ideation/outliner.py` | PASS_MOCK_ONLY | script_pipeline.json |  |
| Screenplay | `intelligence/.../screenplay/writer.py` | PASS_MOCK_ONLY | script_pipeline.json |  |
| Dialogue narration | `intelligence/.../screenplay/narration.py` | PASS_LOCAL | script_pipeline.json |  |
| Entity extraction | `intelligence/.../entity_extraction/extractor.py` | PASS_LOCAL | script_pipeline.json |  |
| Style bible | `intelligence/.../style_design/designer.py` | PASS_MOCK_ONLY | script_pipeline.json |  |
| Asset prompt specs | `intelligence/.../asset_prompts/builder.py` | PASS_LOCAL | script_pipeline.json |  |
| Package assembly | `intelligence/.../assembly/assembler.py` | PASS_LOCAL | script_pipeline.json |  |
| Cinematic plan (director) | `intelligence/.../director/service.py` | NOT_TESTED | script_pipeline.json | requires locked screenplay + strict PlannerOutput JSON; deterministic path verified by phase 8 tests |
| Shot graph | `intelligence/.../shot_planner/service.py` | NOT_TESTED | script_pipeline.json | requires locked CinematicPlan |
| Continuity ledger | `intelligence/.../continuity/service.py` | NOT_TESTED | script_pipeline.json | requires shot graph |
| Reference binding | `intelligence/.../reference_selector/service.py` | NOT_TESTED | script_pipeline.json | requires APPROVED reference assets |
| Prompt compiler | `intelligence/.../prompt_compiler/service.py` | NOT_TESTED | script_pipeline.json | requires bound graph |
| Google Flow payload | `tools/windagent_tools/google_flow/` | PASS_LOCAL | browser_checks.json |  |
| Browser startup | `tools/windagent_tools/browser/` | PASS_LOCAL | browser_checks.json |  |
| Browser navigation (Flow) | `tools/windagent_tools/google_flow/navigation.py` | BROWSER_INTERACTION | browser_checks.json | signed-out session blocks generation without human sign-in |
| Asset generation (Flow) | `tools/windagent_tools/google_flow/` | NOT_TESTED | browser_checks.json | requires authorized signed-in Flow session + credit approval |
| Asset download/validation | `tools/windagent_tools/media_assets/` | PASS_LOCAL | media_checks.json |  |
| Timeline assembly | `intelligence/.../postproduction/` | NOT_TESTED | media_checks.json | requires generated clips; prior phase_22 stubs are 0-byte placeholders |
| Final video export | `intelligence/.../postproduction/` | NOT_TESTED | media_checks.json | no real end-to-end clips produced in this evaluation |
| Production report | `pipeline_evaluation/` | PASS_LOCAL | pipeline_evaluation_report.md |  |

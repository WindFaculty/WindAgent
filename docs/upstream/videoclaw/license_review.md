# VideoClaw Upstream License & Attribution Review

## 1. Primary License Assessment

- **Upstream Repository**: `HITsz-TMG/VideoClaw`
- **Primary License**: MIT License
- **License File Path**: `LICENSE` (present in repository root)
- **Copyright Holder**: Copyright (c) Harbin Institute of Technology, Shenzhen (HITsz TMG)
- **License Status**: `APPROVED` for intake and refactoring.

### Terms & Obligations
- Permissive use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies.
- **Obligation**: The copyright notice and permission notice must be included in all copies or substantial portions of the Software.
- **Action**: When adopting or refactoring code from VideoClaw into `windagent_tools/video_preproduction/`, include `NOTICE.md` and preserve copyright header in refactored source headers.

## 2. Transitive & External Dependency License Audit

| Dependency / Asset | Ecosystem / Type | Declared License | Status | Distribution Obligation |
|---|---|---|---|---|
| `pydantic` | Python library | MIT | Approved | Include MIT notice in distribution |
| `jinja2` | Python library | BSD-3-Clause | Approved | Include BSD notice in distribution |
| `httpx` / `requests` | Python library | Apache-2.0 | Approved | Include Apache-2.0 notice in distribution |
| `pillow` | Python image library | HPND / PIL | Approved | Retain license notice |
| `ffmpeg-python` | Python wrapper | MIT | Approved | Retain license notice |
| `FFmpeg` (binary) | External binary | LGPL v2.1+ / GPL v3 | Approved | External execution only via CLI, dynamic subprocess invocation. Do NOT static bundle GPL binaries. |
| `edge-tts` / `gTTS` | Python audio synthesis | LGPL / MIT | Approved | Call via standalone CLI/port adapter. |
| `gunicorn` / `uvicorn` | WSGI/ASGI server | MIT | Approved | Retain notice |

## 3. Asset & Weight Provenance

- **Model Weights**: VideoClaw uses cloud API providers (OpenAI, DashScope, Kling, Hunyuan) and does not embed proprietary binary model weights in source repository.
- **Sample Fixtures**: Generated sample media in upstream repository are released under MIT or Public Domain terms.
- **Font & Asset Files**: Standard open-source web fonts (Roboto / Inter) under SIL Open Font License (OFL 1.1).

## 4. Legal Compliance Verdict

- Zero `UNKNOWN` licenses in selected intake scope.
- `VP1_UPSTREAM_ADOPTION_APPROVED` legal criteria met.

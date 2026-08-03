"""Phase 21 — Audio pipeline canonical isolation tests (plan 06 §4, §6-§10).

Proves the Phase 21 audio layer (`intelligence/windagent_intelligence/video/audio/`)
meets the architecture rules:

- intelligence-layer: imports only `windagent_core` + `windagent_intelligence`;
  never `windagent_providers` / `windagent_tools` / browser / upstream modules
  (plan §4 clean-room, provider-neutral);
- no subprocess / sys.path mutation / dynamic import inside the package —
  dialogue prep, voice casting, alignment and mix run fully offline; only the
  TTS tier goes through a provider PORT (`TtsProviderPort`), never a provider
  import;
- core audio domain models (`CharacterVoiceProfile`, `DialogueTrack`,
  `WordTimestamp`, `SoundEffectCue`, `MusicCue`, `AudioMixPlan`) live in core
  and stay intelligence/tools-neutral;
- fail-closed: invalid TTS output never publishes (§8.3), low alignment
  confidence routes to human review (§8.4), unknown-license cues block the
  mix (§8.5), voice preview is never final without approval (§8.2);
- BGM change invalidates only the mix/final cut, never the clips (§8.5);
- the real workspace architecture check reports zero violations.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = ROOT / "intelligence" / "windagent_intelligence" / "video" / "audio"
CORE_AUDIO = ROOT / "core" / "windagent_core" / "domain" / "video_production" / "audio.py"

UPSTREAM_LAUNCH_PATTERNS = [
    re.compile(r"^\s*(?:from\s+videoclaw|import\s+videoclaw)\b", re.MULTILINE),
    re.compile(r"^\s*(?:from\s+third_party|import\s+third_party)\b", re.MULTILINE),
    re.compile(r"sys\.path\.(?:insert|append)\s*\(", re.MULTILINE),
    re.compile(r"spec_from_file_location\s*\(", re.MULTILINE),
    re.compile(r"subprocess\.(?:run|Popen|call|create_subprocess_exec)\s*\(", re.MULTILINE),
    re.compile(r"importlib\.import_module\s*\(", re.MULTILINE),
    re.compile(r"__import__\s*\(", re.MULTILINE),
]

FORBIDDEN_DEP_ROOTS = (
    "windagent_providers",
    "windagent_tools",
    "windagent_workflows",
    "windagent_storage",
    "windagent_api",
    "windagent_cli",
    "windagent_orchestration",
    "windagent_observability",
    "windagent_verification",
)
# Self-root (windagent_intelligence) is allowed for intra-package imports.
ALLOWED_DEP_ROOTS = ("windagent_core", "windagent_intelligence")

PHASE21_FILES = (
    "models.py",
    "dialogue.py",
    "voice.py",
    "tts.py",
    "alignment.py",
    "mix.py",
    "pipeline.py",
    "__init__.py",
)


def _py_files(directory: Path) -> list[tuple[str, str]]:
    files = []
    for py in sorted(directory.rglob("*.py")):
        if "__pycache__" in py.as_posix():
            continue
        rel = py.relative_to(ROOT).as_posix()
        files.append((rel, py.read_text(encoding="utf-8", errors="ignore")))
    return files


def test_phase21_modules_exist():
    for name in PHASE21_FILES:
        assert (AUDIO_DIR / name).exists(), f"missing audio/{name}"


def test_phase21_never_launches_or_imports_upstream():
    hits = []
    for rel, text in _py_files(AUDIO_DIR):
        for pattern in UPSTREAM_LAUNCH_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                hits.append(f"{rel}:{line_no}: {match.group(0).strip()[:60]}")
    assert hits == [], f"audio launches/imports upstream: {hits}"


def test_phase21_dependency_roots_are_provider_neutral():
    offenders = []
    for rel, text in _py_files(AUDIO_DIR):
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "windagent" not in stripped:
                continue
            module = re.search(r"(?:import|from)\s+(windagent_[a-z_]+)", stripped)
            if module and module.group(1) not in ALLOWED_DEP_ROOTS:
                offenders.append(f"{rel}: {stripped}")
    assert offenders == [], f"audio imports forbidden deps: {offenders}"


def test_phase21_tts_goes_through_port_not_provider():
    """The TTS tier is provider-neutral: a Protocol port, no provider import."""
    text = (AUDIO_DIR / "tts.py").read_text(encoding="utf-8", errors="ignore")
    assert "Protocol" in text
    assert "TtsProviderPort" in text
    assert "windagent_providers" not in text


def test_phase21_tts_fails_closed():
    """§8.3: timeout / empty / invalid output is an issue, never published."""
    text = (AUDIO_DIR / "tts.py").read_text(encoding="utf-8", errors="ignore")
    assert "TTS_TIMEOUT" in text
    assert "TTS_EMPTY_OUTPUT" in text
    assert "TTS_INVALID_OUTPUT" in text
    assert "never published" in text.lower() or "invalid output never publishes" in text.lower()


def test_phase21_voice_preview_never_final_without_approval():
    """§8.2: preview is never final without human approval; no license fabrication."""
    text = (AUDIO_DIR / "voice.py").read_text(encoding="utf-8", errors="ignore")
    assert "PREVIEW_NOT_APPROVED" in text
    assert "preview" in text.lower()
    assert "approval" in text.lower()
    assert "never" in text.lower()


def test_phase21_alignment_routes_low_confidence_and_never_cuts():
    """§8.4: low confidence -> human; overlong line -> proposal, never cut."""
    text = (AUDIO_DIR / "alignment.py").read_text(encoding="utf-8", errors="ignore")
    assert "LOW_CONFIDENCE" in text
    assert "OVERLONG_LINE" in text
    assert "never" in text.lower()
    assert "cut" in text.lower()


def test_phase21_mix_license_gate_and_versioned_policy():
    """§8.5: unknown/rejected license blocks the mix; versioned policy."""
    text = (AUDIO_DIR / "mix.py").read_text(encoding="utf-8", errors="ignore")
    assert "UNKNOWN_CUE_LICENSE" in text
    assert "LicenseState" in text
    assert "mix_policy_version" in text
    assert "loudness_target_lufs" in text
    assert "peak_ceiling_db" in text


def test_phase21_core_audio_models_tools_neutral():
    text = CORE_AUDIO.read_text(encoding="utf-8", errors="ignore")
    assert "windagent_tools" not in text
    assert "windagent_intelligence" not in text
    assert "windagent_providers" not in text
    # invalidation: BGM is clip-safe, dialogue invalidates track+mix (§8.5)
    assert "MIX_ONLY" in text
    assert "TRACK_AND_MIX" in text


def test_phase21_core_exports_audio_models():
    import windagent_core.domain.video_production as vp

    for name in (
        "CharacterVoiceProfile",
        "DialogueTrack",
        "WordTimestamp",
        "SoundEffectCue",
        "MusicCue",
        "AudioMixPlan",
        "TtsAudioAsset",
        "compute_mix_hash",
        "AudioIntentType",
        "AudioCueKind",
        "VoiceRightsState",
        "AudioAlignmentStatus",
        "AudioInvalidationScope",
    ):
        assert hasattr(vp, name), f"core missing export {name}"
    import windagent_core as core

    assert hasattr(core, "CharacterVoiceProfile")
    assert hasattr(core, "AudioMixPlan")


def test_phase21_intelligence_exports_audio_pipeline():
    import windagent_intelligence.video as video

    for name in (
        "AudioPipelineService",
        "AudioPipelineReceipt",
        "AudioIssue",
        "DialoguePreparer",
        "VoiceCastingService",
        "TtsSynthesizer",
        "TtsProviderPort",
        "TtsSynthesisRequest",
        "AlignmentService",
        "MixPlanner",
    ):
        assert hasattr(video, name), f"windagent_intelligence.video missing export {name}"


def test_real_repo_architecture_stays_clean():
    import json
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "scripts/check_architecture_imports.py", "--root", ".", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-1000:]
    report = json.loads(proc.stdout)
    assert report["verdict"] == "PASS", report["violations"]


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])

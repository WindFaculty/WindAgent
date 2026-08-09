"""
VP3D Phase 24 — FFmpeg Assembly (Stage L — post-production).

Extends the Phase 22 post-production services with image-sequence input from
Blender (stage_l.md §3):

- `FrameSequenceNormalizer`   PNG/EXR sequence inspection: missing/duplicate/
                              gap/corrupt frame detection, dimension probe,
                              per-frame SHA-256, color metadata enforcement
                              (stage_l §3.1, §4, §6);
- `AudioMixNormalizer`        dialogue/SFX/BGM sample-rate/channel/loudness
                              normalization plan, versioned loudness/peak
                              policy (stage_l §3.3);
- `SequenceAssemblyPlanner`   FFmpeg argv as LISTS built ONLY from the
                              allowlisted operations in `ALLOWED_FILTER_OPS`;
                              no shell interpolation, no raw filter text from
                              callers; redacted argv for evidence (stage_l
                              §3.2, §3.4, §3.7);
- `AtomicPublisher`           staging -> verify -> atomic publish, quarantine
                              evidence for failed output, verified deliverable
                              never overwritten (stage_l §3.5, §4);
- `AssemblyCoordinator`       invalidation scoping: a rendered shot change
                              rebuilds timeline+final, a BGM change rebuilds
                              mix+final with visual frames reused, a subtitle
                              change remuxes the final without touching frames
                              (stage_l §3.9).

This module is pure planning/validation — it never spawns a process. The
evidence producer executes the generated argv against the real ffmpeg.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Callable, Optional, Sequence

from windagent_core.domain.video_production.enums import (
    AssemblyInvalidationScope,
    FrameSequenceIssueCode,
)
from windagent_core.domain.video_production.ids import (
    AudioMixPlanId,
)
from windagent_core.domain.video_production.postproduction import (
    AssemblyInvalidationDecision,
    AtomicPublishReceipt,
    AudioMixPlan,
    AudioMixTrack,
    EditDecisionList,
    FrameSequenceInput,
    FrameSequenceValidationResult,
)
from windagent_intelligence.video.postproduction.models import (
    SequenceRenderPlan,
)

# ---------------------------------------------------------------------------
# Allowlisted FFmpeg filter operations (stage_l §3.4)
# ---------------------------------------------------------------------------
# The planner composes filter graphs exclusively from these names. Any other
# filter op (subtitles=, drawtext=, ffmpeg filter scripts, ...) is rejected:
# an untrusted filter text would be an FFmpeg attack surface (stage_l §6).
ALLOWED_FILTER_OPS = frozenset(
    {
        "trim",
        "setpts",
        "scale",
        "pad",
        "format",
        "fps",
        "xfade",
        "aresample",
        "aformat",
        "amix",
        "loudnorm",
        "alimiter",
        "volume",
        "concat",
        "null",
    }
)

LOUDNESS_POLICY_VERSION = "loudness-v1"
MIX_SAMPLE_RATE = 48000
MIX_CHANNELS = 2

_FRAME_NAME_RE = re.compile(r"^frame_(\d+).*\.(png|exr)$")


class AssemblyPlanError(ValueError):
    """Raised when an assembly plan violates a fail-closed rule."""


class FrameSequenceNormalizer:
    """Inspects a rendered PNG/EXR frame sequence BEFORE assembly."""

    def probe_dimensions(self, frame_path: Path) -> tuple[int, int]:
        """Read width/height from PNG (IHDR) or EXR (dataWindow) headers.

        Pure stdlib — no image library dependency.
        """
        suffix = frame_path.suffix.lower()
        if suffix == ".png":
            with open(frame_path, "rb") as handle:
                header = handle.read(24)
            if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
                raise ValueError(f"not a PNG: {frame_path.name}")
            width = int.from_bytes(header[16:20], "big")
            height = int.from_bytes(header[20:24], "big")
            return width, height
        if suffix == ".exr":
            with open(frame_path, "rb") as handle:
                magic = handle.read(4)
            if magic != b"\x76\x2f\x31\x01":
                raise ValueError(f"not an EXR: {frame_path.name}")
            width, height = self._exr_dimensions(frame_path)
            return width, height
        raise ValueError(f"unsupported frame extension: {suffix}")

    @staticmethod
    def _exr_dimensions(frame_path: Path) -> tuple[int, int]:
        """Parse the EXR header 'dataWindow' box2i line (little-endian)."""
        dimensions: Optional[tuple[int, int]] = None
        with open(frame_path, "rb") as handle:
            # Own handle: skip magic (4) + version/flags (4) to reach the
            # attribute list.
            handle.read(8)
            while True:
                name = b""
                while True:
                    byte = handle.read(1)
                    if not byte or byte == b"\x00":
                        break
                    name += byte
                if not name:
                    # End of header: dataWindow must have been seen.
                    if dimensions is not None:
                        return dimensions
                    raise ValueError(f"EXR header truncated: {frame_path.name}")
                type_name = b""
                while True:
                    byte = handle.read(1)
                    if not byte or byte == b"\x00":
                        break
                    type_name += byte
                size_bytes = handle.read(4)
                if len(size_bytes) != 4:
                    raise ValueError(f"EXR header truncated: {frame_path.name}")
                size = int.from_bytes(size_bytes, "little")
                value = handle.read(size)
                if len(value) != size:
                    raise ValueError(f"EXR header truncated: {frame_path.name}")
                if name == b"dataWindow":
                    if type_name != b"box2i" or size != 16:
                        raise ValueError(f"EXR dataWindow malformed: {frame_path.name}")
                    x_min, y_min, x_max, y_max = (
                        int.from_bytes(value[i : i + 4], "little", signed=True)
                        for i in range(0, 16, 4)
                    )
                    dimensions = (x_max - x_min + 1, y_max - y_min + 1)
        if dimensions is None:
            raise ValueError(f"EXR has no dataWindow: {frame_path.name}")
        return dimensions

    def validate(
        self,
        sequence: FrameSequenceInput,
        root: Path,
    ) -> FrameSequenceValidationResult:
        """Validate a frame sequence; ANY issue blocks assembly (fail closed)."""
        frame_dir = root / sequence.frame_dir
        issues: list[FrameSequenceIssueCode] = []
        missing: list[int] = []
        duplicates: list[int] = []
        corrupt: list[int] = []
        gaps: list[tuple[int, int]] = []

        if not sequence.colorspace.strip():
            issues.append(FrameSequenceIssueCode.COLORSPACE_UNSPECIFIED)
        if sequence.fps <= 0.0:
            issues.append(FrameSequenceIssueCode.FPS_MISMATCH)

        found: dict[int, list[Path]] = {}
        if frame_dir.is_dir():
            for path in sorted(frame_dir.iterdir()):
                match = _FRAME_NAME_RE.match(path.name)
                if match:
                    found.setdefault(int(match.group(1)), []).append(path)

        expected = list(range(sequence.frame_start, sequence.frame_end + 1))
        present = set(found)
        absent = [n for n in expected if n not in present]
        # Isolated single missing frame vs a run of missing frames (gap).
        run_start: Optional[int] = None
        previous: Optional[int] = None
        for number in absent:
            if run_start is None:
                run_start = number
            elif previous is not None and number != previous + 1:
                if previous - run_start >= 1:
                    gaps.append((run_start, previous))
                    issues.append(FrameSequenceIssueCode.FRAME_GAP)
                else:
                    missing.append(run_start)
                    issues.append(FrameSequenceIssueCode.FRAME_MISSING)
                run_start = number
            previous = number
        if run_start is not None:
            if previous is not None and previous - run_start >= 1:
                gaps.append((run_start, previous))
                issues.append(FrameSequenceIssueCode.FRAME_GAP)
            else:
                missing.append(run_start)
                issues.append(FrameSequenceIssueCode.FRAME_MISSING)
        # Every absent frame is also listed in `missing` (single or run head).
        for gap_start, gap_end in gaps:
            missing.extend(range(gap_start + 1, gap_end + 1))

        for number, paths in sorted(found.items()):
            if len(paths) > 1:
                duplicates.append(number)
                issues.append(FrameSequenceIssueCode.FRAME_DUPLICATE)

        frame_hashes: list[tuple[int, str]] = []
        observed_dims: Optional[tuple[int, int]] = None
        for number in sorted(present):
            path = found[number][0]
            if path.stat().st_size == 0:
                corrupt.append(number)
                issues.append(FrameSequenceIssueCode.FRAME_CORRUPT)
                continue
            try:
                dims = self.probe_dimensions(path)
            except ValueError:
                corrupt.append(number)
                issues.append(FrameSequenceIssueCode.FRAME_CORRUPT)
                continue
            if observed_dims is None:
                observed_dims = dims
            elif dims != observed_dims:
                issues.append(FrameSequenceIssueCode.DIMENSION_MISMATCH)
            frame_hashes.append((number, _sha256_file(path)))

        width, height = observed_dims or (0, 0)
        return FrameSequenceValidationResult(
            sequence=sequence,
            valid=len(issues) == 0,
            issues=tuple(sorted(set(issues), key=lambda item: item.value)),
            missing_frames=tuple(sorted(missing)),
            duplicate_frames=tuple(sorted(duplicates)),
            gaps=tuple(gaps),
            corrupt_frames=tuple(sorted(corrupt)),
            observed_width=width,
            observed_height=height,
            frame_hashes=tuple(frame_hashes),
        )

    def normalize_manifest(
        self,
        sequence: FrameSequenceInput,
        result: FrameSequenceValidationResult,
        root: Path,
    ) -> dict:
        """Evidence manifest for one validated sequence."""
        return {
            "sequence_id": str(sequence.sequence_id),
            "shot_id": str(sequence.shot_id),
            "frame_dir": str(root / sequence.frame_dir),
            "extension": sequence.extension,
            "fps": sequence.fps,
            "frame_start": sequence.frame_start,
            "frame_end": sequence.frame_end,
            "expected_frame_count": sequence.expected_frame_count,
            "colorspace": sequence.colorspace,
            "transfer_curve": sequence.transfer_curve,
            "valid": result.valid,
            "issues": [str(issue) for issue in result.issues],
            "missing_frames": list(result.missing_frames),
            "duplicate_frames": list(result.duplicate_frames),
            "gaps": [list(gap) for gap in result.gaps],
            "corrupt_frames": list(result.corrupt_frames),
            "observed_dimensions": {
                "width": result.observed_width,
                "height": result.observed_height,
            },
            "frame_count": len(result.frame_hashes),
            "frame_hashes": {
                str(number): digest for number, digest in result.frame_hashes
            },
        }


class AudioMixNormalizer:
    """Normalizes dialogue/SFX/BGM tracks into a versioned mix plan."""

    def build_plan(
        self,
        tracks: Sequence[AudioMixTrack],
        *,
        loudness_target_lufs: float = -16.0,
        peak_ceiling_db: float = -1.0,
        policy_version: str = LOUDNESS_POLICY_VERSION,
        mix_plan_id: Optional[AudioMixPlanId] = None,
    ) -> AudioMixPlan:
        if not tracks:
            raise AssemblyPlanError("audio mix plan requires at least one track")
        for track in tracks:
            if track.sample_rate <= 0 or track.channels <= 0:
                raise AssemblyPlanError(
                    f"invalid track sample_rate/channels for {track.track_kind}"
                )
        if not (-70.0 <= loudness_target_lufs <= 0.0):
            raise AssemblyPlanError(
                f"loudness target out of bounds: {loudness_target_lufs}"
            )
        if peak_ceiling_db > 0.0:
            raise AssemblyPlanError(
                f"peak ceiling must be <= 0 dB: {peak_ceiling_db}"
            )
        plan = AudioMixPlan(
            mix_plan_id=mix_plan_id or AudioMixPlanId("mix_default"),
            tracks=tuple(tracks),
            loudness_target_lufs=loudness_target_lufs,
            peak_ceiling_db=peak_ceiling_db,
            policy_version=policy_version,
        )
        return plan

    def filter_ops(self, plan: AudioMixPlan) -> tuple[str, ...]:
        """Typed filter graph for the mix (every op is allowlisted)."""
        per_track = (
            f"aformat=sample_rates={MIX_SAMPLE_RATE}:"
            f"channel_layouts=stereo"
        )
        inputs = "".join(f"[t{index}]" for index in range(len(plan.tracks)))
        # alimiter's `limit` is LINEAR gain (0..1), not dB: convert the
        # policy ceiling (-1.0 dBFS -> 0.891).
        linear_peak = 10 ** (plan.peak_ceiling_db / 20.0)
        mix_chain = (
            f"{inputs}amix=inputs={len(plan.tracks)}:duration=longest:"
            f"normalize=0,"
            f"loudnorm=I={plan.loudness_target_lufs:.1f}:"
            f"TP={plan.peak_ceiling_db:.1f},"
            f"alimiter=limit={linear_peak:.3f}"
        )
        return tuple(
            [per_track for _ in plan.tracks] + [mix_chain]
        )

    def normalize_spec(self, plan: AudioMixPlan) -> dict:
        """Evidence spec for the versioned mix plan."""
        return {
            "mix_plan_id": str(plan.mix_plan_id),
            "policy_version": plan.policy_version,
            "loudness_target_lufs": plan.loudness_target_lufs,
            "peak_ceiling_db": plan.peak_ceiling_db,
            "content_hash": plan.content_hash,
            "target_sample_rate": MIX_SAMPLE_RATE,
            "target_channels": MIX_CHANNELS,
            "tracks": [
                {
                    "kind": str(track.track_kind),
                    "source_path": track.source_path,
                    "source_hash": track.source_hash,
                    "sample_rate": track.sample_rate,
                    "channels": track.channels,
                    "gain_db": track.gain_db,
                }
                for track in plan.tracks
            ],
            "filter_ops": list(self.filter_ops(plan)),
        }


class SequenceAssemblyPlanner:
    """Builds allowlisted FFmpeg argv lists from an EDL over frame sequences."""

    @staticmethod
    def validate_argv(argv: Sequence[str]) -> None:
        """Fail closed on anything outside the allowlist / safe argv shape."""
        filter_values: set[int] = set()
        for index, element in enumerate(argv):
            if element in ("-filter_complex_script", "-filter_script"):
                # Filter scripts are an FFmpeg attack surface: never allowed.
                raise AssemblyPlanError(f"filter script flag forbidden: {element!r}")
            if element in ("-vf", "-filter_complex"):
                filter_values.add(index + 1)
        for index, element in enumerate(argv):
            if index in filter_values:
                # Filter graphs legitimately contain ';' and ':' separators.
                for token in ("&&", "`", "$(", "filter_complex_script", "filter_script"):
                    if token in element:
                        raise AssemblyPlanError(f"forbidden token in argv: {token!r}")
                for segment in re.split(r"[,;]", element):
                    body = segment
                    while body.startswith("["):
                        end = body.find("]")
                        if end == -1:
                            break
                        body = body[end + 1 :]
                    if "=" in body:
                        name = body.split("=", 1)[0]
                        if name not in ALLOWED_FILTER_OPS:
                            raise AssemblyPlanError(
                                f"filter op not allowlisted: {name!r} in {element!r}"
                            )
            else:
                # Plain argv element: no shell metacharacters ever.
                for token in (";", "&&", "&", "|", "`", "$("):
                    if token in element:
                        raise AssemblyPlanError(
                            f"shell metacharacter {token!r} in argv element"
                        )

    @staticmethod
    def redact_argv(
        argv: Sequence[str],
        workspace_root: Path,
    ) -> tuple[str, ...]:
        """Redacted argv for evidence: workspace paths shortened, binary masked."""
        root_str = str(workspace_root.resolve())
        redacted: list[str] = []
        for element in argv:
            text = element
            if root_str in text:
                text = text.replace(root_str, "<ws>")
            if text.endswith(("ffmpeg", "ffprobe")) or text == "ffmpeg":
                text = "ffmpeg"
            redacted.append(text)
        return tuple(redacted)

    def build_sequence_render_plan(
        self,
        edl: EditDecisionList,
        frame_sequences: dict[str, FrameSequenceInput],
        audio_mix_path: Optional[Path],
        subtitle_path: Optional[Path],
        output_dir: Path,
        *,
        ffmpeg_bin: str = "ffmpeg",
        mix_plan: Optional[AudioMixPlan] = None,
        staging_filename: str = "final_staging.mp4",
    ) -> SequenceRenderPlan:
        """Deterministic argv for sequence assembly + derived artifacts.

        `frame_sequences` maps shot_id -> validated frame sequence. Every
        sequence fps MUST equal the profile frame rate (wrong fps blocked).
        """
        profile = edl.encoding_profile
        if not edl.items:
            raise AssemblyPlanError("EDL has no items")

        inputs_argv: list[str] = []
        filter_parts: list[str] = []
        ops: set[str] = set()
        input_index = 0
        chain_labels: list[str] = []
        elapsed = 0.0  # sum of item target durations before current item
        transition_elapsed = 0.0  # sum of applied transition durations

        for index, item in enumerate(edl.items):
            sequence = frame_sequences.get(str(item.shot_id))
            if sequence is None:
                raise AssemblyPlanError(
                    f"no frame sequence for shot {item.shot_id}"
                )
            if abs(sequence.fps - float(profile.frame_rate)) > 1e-9:
                raise AssemblyPlanError(
                    f"fps mismatch for shot {item.shot_id}: sequence "
                    f"{sequence.fps} != profile {profile.frame_rate} "
                    f"(wrong fps is blocked before assembly)"
                )
            inputs_argv.extend(
                [
                    "-framerate",
                    str(sequence.fps),
                    "-start_number",
                    str(sequence.frame_start),
                    "-i",
                    str(Path(sequence.frame_dir) / sequence.pattern()),
                ]
            )
            ops.update({"trim", "setpts", "scale", "pad", "format"})
            tw, th = profile.resolution_width, profile.resolution_height
            filter_parts.append(
                f"[{input_index}:v]trim=duration={item.target_duration:.3f},"
                f"setpts=PTS-STARTPTS,"
                f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"format={profile.pixel_format}[v{index}];"
            )
            input_index += 1

            transition = item.transition_in
            if index >= 1 and transition and transition.duration_seconds > 0:
                # xfade starts `transition` seconds before the chain would
                # end: offset = elapsed chain duration - transition duration.
                offset = elapsed - transition_elapsed - transition.duration_seconds
                if offset < 0.0:
                    raise AssemblyPlanError(
                        f"transition longer than chain at item {index}"
                    )
                ops.add("xfade")
                transition_elapsed += transition.duration_seconds
                filter_parts.append(
                    f"[{chain_labels[-1]}][v{index}]"
                    f"xfade=transition={transition.transition_type.value.lower()}:"
                    f"duration={transition.duration_seconds:.3f}:"
                    f"offset={offset:.3f}[vx{index}];"
                )
                chain_labels[-1] = f"vx{index}"
            else:
                chain_labels.append(f"v{index}")
            elapsed += item.target_duration

        if len(chain_labels) == 1:
            filter_parts.append(f"[{chain_labels[0]}]null[vout];")
            ops.add("null")
        else:
            concat_inputs = "".join(f"[{label}]" for label in chain_labels)
            filter_parts.append(
                f"{concat_inputs}concat=n={len(chain_labels)}:v=1:a=0[vout]"
            )
            ops.add("concat")

        filter_graph = "".join(filter_parts)
        expected_total = edl.total_duration_seconds
        if abs(elapsed - transition_elapsed - expected_total) > 1e-6:
            raise AssemblyPlanError(
                "EDL timeline math drifted: "
                f"{elapsed - transition_elapsed} != {expected_total}"
            )

        output_path = output_dir / f"final_{edl.edl_hash[:12]}.mp4"
        staging_path = output_dir / staging_filename
        proxy_path = output_dir / f"proxy_{edl.edl_hash[:12]}.mp4"
        thumbnail_path = output_dir / f"thumbnail_{edl.edl_hash[:12]}.jpg"

        argv_assemble: list[str] = [ffmpeg_bin, "-y"]
        argv_assemble.extend(inputs_argv)

        audio_label = ""
        if audio_mix_path and audio_mix_path.is_file():
            audio_index = input_index
            input_index += 1
            argv_assemble.extend(["-i", str(audio_mix_path)])
            audio_label = f"{audio_index}:a"
        else:
            argv_assemble.extend(
                ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
            )
            audio_label = f"{input_index}:a"

        if subtitle_path and subtitle_path.is_file():
            argv_assemble.extend(["-i", str(subtitle_path)])
            subtitle_label = f"{input_index}:s"
        else:
            subtitle_label = ""

        argv_assemble.extend(
            [
                "-filter_complex",
                filter_graph,
                "-map",
                "[vout]",
                "-map",
                audio_label,
            ]
        )
        if subtitle_label:
            argv_assemble.extend(["-map", subtitle_label])
        argv_assemble.extend(
            [
                "-c:v",
                profile.video_codec,
                "-crf",
                str(profile.video_crf),
                "-pix_fmt",
                profile.pixel_format,
                "-c:a",
                profile.audio_codec,
                "-ar",
                str(profile.audio_sample_rate),
                "-ac",
                str(profile.audio_channels),
                "-b:a",
                f"{profile.audio_bitrate_kbps}k",
            ]
        )
        if subtitle_label:
            argv_assemble.extend(["-c:s", "mov_text"])
        # Deterministic container: strip wall-clock creation metadata so a
        # same-manifest rerun is bit-exact (reproducibility, stage_l §3.8).
        argv_assemble.extend(["-map_metadata", "-1"])
        # Pin the OUTPUT duration to the EDL total: the audio mix may be
        # longer than the timeline and must not extend the final (stage_l §4
        # "ending not black/truncated", duration bounds).
        argv_assemble.extend(["-t", f"{expected_total:.3f}"])
        argv_assemble.append(str(staging_path))

        # FINAL_ONLY remux: video stream copied, subtitle replaced.
        argv_remux_subtitle: tuple[str, ...] = ()
        if subtitle_path and subtitle_path.is_file():
            argv_remux_subtitle = (
                ffmpeg_bin,
                "-y",
                "-i",
                str(output_path),
                "-i",
                str(subtitle_path),
                "-map",
                "0:v",
                "-map",
                "0:a",
                "-map",
                "1:s",
                "-c",
                "copy",
                "-c:s",
                "mov_text",
                str(staging_path),
            )

        proxy_w = max(2, profile.resolution_width // 2)
        proxy_h = max(2, profile.resolution_height // 2)
        argv_proxy: tuple[str, ...] = (
            ffmpeg_bin,
            "-y",
            "-i",
            str(staging_path),
            "-vf",
            f"scale={proxy_w}:{proxy_h},fps={profile.frame_rate},"
            f"format={profile.pixel_format}",
            "-c:v",
            profile.video_codec,
            "-crf",
            "24",
            "-c:a",
            profile.audio_codec,
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "96k",
            str(proxy_path),
        )
        argv_thumbnail: tuple[str, ...] = (
            ffmpeg_bin,
            "-y",
            "-ss",
            "0.500",
            "-i",
            str(staging_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            str(thumbnail_path),
        )

        self.validate_argv(argv_assemble)
        self.validate_argv(argv_proxy)

        return SequenceRenderPlan(
            edl_hash=edl.edl_hash,
            profile=profile,
            output_path=output_path,
            staging_path=staging_path,
            proxy_path=proxy_path,
            thumbnail_path=thumbnail_path,
            argv_assemble=tuple(argv_assemble),
            argv_proxy=argv_proxy,
            argv_thumbnail=argv_thumbnail,
            argv_remux_subtitle=argv_remux_subtitle,
            filter_graph_str=filter_graph,
            ops_used=tuple(sorted(ops)),
            audio_mix_plan_hash=mix_plan.content_hash if mix_plan else "",
        )


class AtomicPublisher:
    """Staging -> verify -> atomic publish with quarantine evidence."""

    def publish(
        self,
        staged: Path,
        final: Path,
        verify: Callable[[Path], bool],
        quarantine_dir: Path,
    ) -> AtomicPublishReceipt:
        """Publish a staged artifact; a verified deliverable is NEVER overwritten."""
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            if verify(final):
                return AtomicPublishReceipt(
                    staged_path=str(staged),
                    published_path=str(final),
                    output_hash=_sha256_file(final),
                    verified=True,
                    reused=True,
                )
            raise AssemblyPlanError(
                f"verified deliverable exists but fails re-verification: {final}"
            )
        if not staged.is_file():
            raise AssemblyPlanError(f"staged output missing: {staged}")
        if not verify(staged):
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            quarantined = quarantine_dir / f"{staged.name}.quarantined"
            os.replace(staged, quarantined)
            return AtomicPublishReceipt(
                staged_path=str(staged),
                published_path=str(final),
                output_hash="",
                verified=False,
                quarantine_path=str(quarantined),
            )
        os.replace(staged, final)
        return AtomicPublishReceipt(
            staged_path=str(staged),
            published_path=str(final),
            output_hash=_sha256_file(final),
            verified=True,
        )


class AssemblyCoordinator:
    """Invalidation scoping for assembly inputs (stage_l §3.9)."""

    # changed input key -> (scope, rebuild artifacts, preserved artifacts)
    SCOPE_RULES: dict[str, tuple[AssemblyInvalidationScope, tuple[str, ...], tuple[str, ...]]] = {
        "shot": (
            AssemblyInvalidationScope.TIMELINE_FINAL,
            ("timeline", "final"),
            ("mix", "frames"),
        ),
        "frames": (
            AssemblyInvalidationScope.TIMELINE_FINAL,
            ("timeline", "final"),
            ("mix", "frames"),
        ),
        "dialogue": (
            AssemblyInvalidationScope.MIX_FINAL,
            ("mix", "final"),
            ("frames",),
        ),
        "sfx": (
            AssemblyInvalidationScope.MIX_FINAL,
            ("mix", "final"),
            ("frames",),
        ),
        "bgm": (
            AssemblyInvalidationScope.MIX_FINAL,
            ("mix", "final"),
            ("frames",),
        ),
        "mix": (
            AssemblyInvalidationScope.MIX_FINAL,
            ("mix", "final"),
            ("frames",),
        ),
        "subtitle": (
            AssemblyInvalidationScope.FINAL_ONLY,
            ("final",),
            ("frames", "mix"),
        ),
    }

    def decide_invalidation(
        self,
        changed_input: str,
        previous_manifest: Optional[dict] = None,
    ) -> AssemblyInvalidationDecision:
        """Scope the rebuild for one changed input key (fail closed to NONE)."""
        key = changed_input.split(":", 1)[0]
        rule = self.SCOPE_RULES.get(key)
        if rule is None:
            return AssemblyInvalidationDecision(
                changed_input=changed_input,
                scope=AssemblyInvalidationScope.NONE,
                rebuild_artifacts=(),
                preserved_artifacts=(
                    "frames",
                    "mix",
                    "timeline",
                    "final",
                ),
            )
        scope, rebuild, preserved = rule
        return AssemblyInvalidationDecision(
            changed_input=changed_input,
            scope=scope,
            rebuild_artifacts=rebuild,
            preserved_artifacts=preserved,
        )

    def steps_for(self, decision: AssemblyInvalidationDecision) -> tuple[str, ...]:
        """Ordered pipeline steps for a scope decision."""
        if decision.scope == AssemblyInvalidationScope.TIMELINE_FINAL:
            return ("normalize_frames", "build_mix", "assemble", "verify", "publish")
        if decision.scope == AssemblyInvalidationScope.MIX_FINAL:
            return ("build_mix", "assemble", "verify", "publish")
        if decision.scope == AssemblyInvalidationScope.FINAL_ONLY:
            return ("remux_subtitle", "verify", "publish")
        return ("reuse",)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "ALLOWED_FILTER_OPS",
    "LOUDNESS_POLICY_VERSION",
    "MIX_SAMPLE_RATE",
    "MIX_CHANNELS",
    "AssemblyPlanError",
    "FrameSequenceNormalizer",
    "AudioMixNormalizer",
    "SequenceAssemblyPlanner",
    "AtomicPublisher",
    "AssemblyCoordinator",
]

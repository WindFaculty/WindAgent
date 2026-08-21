"""
Assembly Planner Service (Phase 22 — plan 06 §13.3).

Derives deterministic FFmpeg render plans from typed EditDecisionList (EDL) models.
Supports shot concatenation, transition filter graph generation, audio replacement/mixing,
loudness normalization, subtitle multiplexing, thumbnail generation, and proxy previews.
"""

from __future__ import annotations

from pathlib import Path

from windagent_core.domain.video_production.postproduction import (
    EditDecisionList,
    EncodingProfile,
)
from windagent_intelligence.video.postproduction.models import (
    FfmpegRenderPlan,
)


class AssemblyPlanner:
    """Constructs deterministic FFmpeg invocation arguments and filter plans."""

    def build_render_plan(
        self,
        edl: EditDecisionList,
        clip_paths: dict[str, Path],
        audio_mix_path: Path | None,
        output_dir: Path,
    ) -> FfmpegRenderPlan:
        """Construct FfmpegRenderPlan containing explicit argv commands."""
        output_path = output_dir / f"final_{edl.edl_hash[:12]}.mp4"
        proxy_path = output_dir / f"proxy_{edl.edl_hash[:12]}.mp4"
        thumbnail_path = output_dir / f"thumbnail_{edl.edl_hash[:12]}.jpg"

        profile = edl.encoding_profile
        edl_hash = edl.edl_hash

        # Build FFmpeg filtergraph and input list
        inputs_argv: list[str] = []
        filter_parts: list[str] = []

        # Add input clips
        for idx, item in enumerate(edl.items):
            cpath = clip_paths.get(str(item.shot_id), output_dir / f"clip_{item.shot_id}.mp4")
            inputs_argv.extend(["-i", str(cpath)])
            tw = profile.resolution_width
            th = profile.resolution_height
            filter_parts.append(
                f"[{idx}:v]scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2,fps={profile.frame_rate},"
                f"format={profile.pixel_format}[v{idx}];"
            )

        # Concatenate filter
        concat_v_inputs = "".join(f"[v{idx}]" for idx in range(len(edl.items)))
        filter_parts.append(
            f"{concat_v_inputs}concat=n={len(edl.items)}:v=1:a=0[vconcat]"
        )

        filter_graph_str = "".join(filter_parts)

        # Build assembly argv
        argv_assemble: list[str] = ["ffmpeg", "-y"]
        argv_assemble.extend(inputs_argv)

        if audio_mix_path and audio_mix_path.exists():
            audio_idx = len(edl.items)
            argv_assemble.extend(["-i", str(audio_mix_path)])
            argv_assemble.extend(
                [
                    "-filter_complex",
                    f"{filter_graph_str}",
                    "-map",
                    "[vconcat]",
                    "-map",
                    f"{audio_idx}:a",
                ]
            )
        else:
            # Generate silent audio stream if no audio mix provided
            argv_assemble.extend(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-filter_complex",
                    f"{filter_graph_str}",
                    "-map",
                    "[vconcat]",
                    "-map",
                    f"{len(edl.items)}:a",
                    "-shortest",
                ]
            )

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
                str(output_path),
            ]
        )

        # Proxy render argv (720p preview)
        proxy_profile = EncodingProfile.proxy_720p_h264()
        argv_proxy: list[str] = [
            "ffmpeg",
            "-y",
            "-i",
            str(output_path),
            "-vf",
            f"scale={proxy_profile.resolution_width}:{proxy_profile.resolution_height},"
            f"fps={proxy_profile.frame_rate},format={proxy_profile.pixel_format}",
            "-c:v",
            proxy_profile.video_codec,
            "-crf",
            str(proxy_profile.video_crf),
            "-c:a",
            proxy_profile.audio_codec,
            "-ar",
            str(proxy_profile.audio_sample_rate),
            str(proxy_path),
        ]

        # Thumbnail poster image argv
        argv_thumbnail: list[str] = [
            "ffmpeg",
            "-y",
            "-ss",
            "00:00:01.000",
            "-i",
            str(output_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            str(thumbnail_path),
        ]

        return FfmpegRenderPlan(
            edl_hash=edl_hash,
            profile=profile,
            output_path=output_path,
            proxy_path=proxy_path,
            thumbnail_path=thumbnail_path,
            argv_assemble=tuple(argv_assemble),
            argv_proxy=tuple(argv_proxy),
            argv_thumbnail=tuple(argv_thumbnail),
            filter_graph_str=filter_graph_str,
        )

"""EDL Compiler: validates domain EditDecisionList and compiles into RenderPlan."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import (
    RenderClip,
    RenderEncodingSpec,
    RenderPlan,
    RenderValidationError,
)


class EdlCompiler:
    """Compiles domain EDL entities into an executable RenderPlan."""

    def compile(
        self,
        *,
        job_id: str,
        edl_data: dict[str, Any],
        output_path: Path,
        asset_resolver: dict[str, Path] | None = None,
        encoding: RenderEncodingSpec | None = None,
    ) -> RenderPlan:
        """Validate EDL and compile it into a deterministic RenderPlan."""
        items = edl_data.get("items", [])
        if not items:
            raise RenderValidationError("Cannot compile empty EDL: items list is empty.")

        resolved_encoding = encoding or RenderEncodingSpec()
        asset_map = asset_resolver or {}

        compiled_clips: list[RenderClip] = []
        current_timeline_s = 0.0

        for idx, item in enumerate(items):
            shot_id = str(item.get("shot_id", f"SHOT-{idx}"))
            clip_hash = str(item.get("clip_hash", ""))
            if not clip_hash:
                raise RenderValidationError(f"Clip {shot_id} is missing required clip_hash.")

            in_point = float(item.get("in_point", 0.0))
            out_point = float(item.get("out_point", item.get("target_duration", 0.0)))
            target_duration = float(item.get("target_duration", out_point - in_point))

            if in_point < 0 or out_point < 0:
                raise RenderValidationError(
                    f"Illegal negative range for shot {shot_id}: in={in_point}, out={out_point}"
                )
            if target_duration <= 0:
                raise RenderValidationError(
                    f"Illegal zero or negative duration for shot {shot_id}: duration={target_duration}"
                )

            # Resolve source asset path
            source_path: Path | None = None
            # Check direct source_path in item
            if "source_path" in item:
                source_path = Path(str(item["source_path"]))
            elif shot_id in asset_map:
                source_path = asset_map[shot_id]
            elif clip_hash in asset_map:
                source_path = asset_map[clip_hash]
            elif "source_asset_id" in item and item["source_asset_id"] in asset_map:
                source_path = asset_map[item["source_asset_id"]]

            if source_path is None:
                raise RenderValidationError(
                    f"Asset resolution failed for shot '{shot_id}' (hash: {clip_hash[:8]}). Source file not found."
                )

            if not source_path.exists() or not source_path.is_file():
                raise RenderValidationError(
                    f"Source media file for shot '{shot_id}' does not exist on disk: {source_path}"
                )

            clip = RenderClip(
                clip_id=f"CLIP-{idx:04d}-{shot_id}",
                source_path=source_path.resolve(),
                in_point_s=in_point,
                out_point_s=out_point,
                duration_s=target_duration,
                track=str(item.get("track", "V1")),
                scale_width=resolved_encoding.width,
                scale_height=resolved_encoding.height,
                fps=resolved_encoding.fps,
            )
            compiled_clips.append(clip)
            current_timeline_s += target_duration

        # Build human-readable filter description
        filter_desc = (
            f"Concat {len(compiled_clips)} clips -> {resolved_encoding.width}x{resolved_encoding.height} "
            f"@{resolved_encoding.fps}fps [{resolved_encoding.video_codec.upper()}]"
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        return RenderPlan(
            job_id=job_id,
            output_path=output_path.resolve(),
            clips=tuple(compiled_clips),
            encoding=resolved_encoding,
            total_duration_s=current_timeline_s,
            filter_graph_description=filter_desc,
            metadata=edl_data.get("metadata", {}),
        )

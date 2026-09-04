"""Worker job handlers for Studio.

Thin adapters that bind the ambient ``StudioServices`` and delegate to the
application service.  Job payloads are plain dicts so the worker runtime stays
decoupled from HTTP DTOs.
"""

from __future__ import annotations

from ..application.handlers import StoryGenerateJobHandler

# Re-export the story job handler as the canonical job.
STUDIO_STORY_GENERATE = "studio.story.generate"


class StudioStoryGenerateHandler(StoryGenerateJobHandler):
    """Compatibility alias — registered under the same job_type."""

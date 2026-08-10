"""Plan B B3+ runtime task handlers (registered per phase; wired in B9)."""

from windagent_intelligence.story.runtime_handlers.bible import (
    BIBLE_HANDLER_REGISTRY,
    BibleGenerateHandler,
)
from windagent_intelligence.story.runtime_handlers.idea import (
    HANDLER_REGISTRY as _IDEA_HANDLER_REGISTRY,
    IdeaEvaluateHandler,
    IdeaGenerateHandler,
)
from windagent_intelligence.story.runtime_handlers.outline import (
    OUTLINE_HANDLER_REGISTRY,
    BeatGenerateHandler,
    OutlineGenerateHandler,
)
from windagent_intelligence.story.runtime_handlers.screenplay import (
    SCREENPLAY_HANDLER_REGISTRY,
    ScreenplayGenerateHandler,
)

#: Combined handler surface (B3 idea + B4 bible + B5 outline + B6 screenplay);
#: grows per phase.
HANDLER_REGISTRY: dict = {
    **_IDEA_HANDLER_REGISTRY,
    **BIBLE_HANDLER_REGISTRY,
    **OUTLINE_HANDLER_REGISTRY,
    **SCREENPLAY_HANDLER_REGISTRY,
}


def registered_story_task_types() -> list[str]:
    return sorted(t.value for t in HANDLER_REGISTRY)


__all__ = [
    "HANDLER_REGISTRY",
    "IdeaGenerateHandler",
    "IdeaEvaluateHandler",
    "BibleGenerateHandler",
    "BeatGenerateHandler",
    "OutlineGenerateHandler",
    "ScreenplayGenerateHandler",
    "registered_story_task_types",
]

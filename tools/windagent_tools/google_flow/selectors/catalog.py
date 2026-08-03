"""
Phase 13 — Flow selector catalog (plan 04 §13.4).

Selector strategy, in priority order:

    accessibility role → label → visible text → stable URL → semantic region

CSS class, DOM index and coordinates are NEVER primary selectors. The catalog
is versioned, carries a locale assumption, a confidence, and fallbacks.
Fallbacks must never click a destructive or payment control (plan 04 §13.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence


class SelectorKind(str, Enum):
    ROLE = "role"  # accessibility role, e.g. button
    LABEL = "label"  # accessible label
    TEXT = "text"  # visible text
    URL = "url"  # stable URL / path
    REGION = "region"  # semantic region


# Selector kinds that are stable semantic signals (allowed as PRIMARY).
_SEMANTIC_KINDS = frozenset(
    {SelectorKind.ROLE, SelectorKind.LABEL, SelectorKind.TEXT, SelectorKind.URL, SelectorKind.REGION}
)
# Selector kinds that are NOT allowed as a primary selector (plan 04 §13.4).
_FORBIDDEN_PRIMARY_KINDS = frozenset({"css_class", "dom_index", "coordinate"})


class SelectorCatalogError(RuntimeError):
    """Raised for unknown or misconfigured selector entries."""


@dataclass(frozen=True)
class SelectorEntry:
    """One versioned selector with confidence and fallbacks."""

    name: str
    kind: SelectorKind
    value: str
    locale: str = "en"
    confidence: float = 0.9
    fallback: tuple[str, ...] = ()
    destructive: bool = False  # True => never auto-clicked by fallback

    def __post_init__(self) -> None:
        kind = self.kind
        if isinstance(kind, str):
            if kind in _FORBIDDEN_PRIMARY_KINDS:
                raise SelectorCatalogError(
                    f"selector {self.name!r} uses forbidden primary kind {kind}"
                )
            try:
                kind = SelectorKind(kind)
            except ValueError as exc:
                raise SelectorCatalogError(
                    f"selector {self.name!r} has unknown kind {kind!r}"
                ) from exc
            object.__setattr__(self, "kind", kind)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "value": self.value,
            "locale": self.locale,
            "confidence": self.confidence,
            "fallback": list(self.fallback),
            "destructive": self.destructive,
        }


class SelectorCatalog:
    """Versioned catalog of semantic Flow UI selectors (plan 04 §13.4)."""

    def __init__(
        self,
        *,
        version: str = "1.0.0",
        locale: str = "en",
        entries: Optional[Sequence[SelectorEntry]] = None,
    ) -> None:
        self.version = version
        self.locale = locale
        self._entries: dict[str, SelectorEntry] = {}
        for entry in entries or self._default_entries():
            self._register(entry)

    # ------------------------------------------------------------------
    def _register(self, entry: SelectorEntry) -> None:
        # kind validation (forbidden kinds, unknown kinds) is enforced in
        # SelectorEntry.__post_init__; here only name/value/confidence checks.
        if not entry.name.strip() or not entry.value.strip():
            raise SelectorCatalogError(f"selector {entry.name!r} needs name and value")
        if not 0.0 <= entry.confidence <= 1.0:
            raise SelectorCatalogError(
                f"selector {entry.name!r} confidence must be in [0, 1]"
            )
        self._entries[entry.name] = entry

    def get(self, name: str) -> SelectorEntry:
        try:
            return self._entries[name]
        except KeyError as exc:
            raise SelectorCatalogError(f"unknown selector {name!r}") from exc

    def has(self, name: str) -> bool:
        return name in self._entries

    def entries(self) -> list[SelectorEntry]:
        return sorted(self._entries.values(), key=lambda e: e.name)

    def selectors_for_state(self, state_name: str) -> list[SelectorEntry]:
        """Selectors relevant to a UI state (by name prefix convention)."""
        return [
            e
            for e in self.entries()
            if e.name.startswith(state_name.lower().replace("_", "_"))
        ]

    # ------------------------------------------------------------------
    @staticmethod
    def _default_entries() -> list[SelectorEntry]:
        return [
            SelectorEntry("sign_in_button", SelectorKind.ROLE, "button", locale="en"),
            SelectorEntry("create_project", SelectorKind.TEXT, "Create", locale="en"),
            SelectorEntry("import_project", SelectorKind.TEXT, "Import", locale="en"),
            SelectorEntry(
                "open_project",
                SelectorKind.URL,
                "/projects",
                locale="en",
                fallback=("project canvas",),
            ),
            SelectorEntry(
                "create_workspace",
                SelectorKind.TEXT,
                "Create workspace",
                locale="en",
                fallback=("New workspace", "Workspace"),
            ),
            SelectorEntry("generation_mode", SelectorKind.ROLE, "combobox", locale="en"),
            SelectorEntry("reference_upload", SelectorKind.ROLE, "button", locale="en"),
            SelectorEntry("prompt_field", SelectorKind.ROLE, "textbox", locale="en"),
            SelectorEntry("model_select", SelectorKind.ROLE, "combobox", locale="en"),
            SelectorEntry("duration_select", SelectorKind.ROLE, "combobox", locale="en"),
            SelectorEntry("aspect_ratio_select", SelectorKind.ROLE, "combobox", locale="en"),
            SelectorEntry("submit_generation", SelectorKind.TEXT, "Generate", locale="en"),
            SelectorEntry("download_result", SelectorKind.TEXT, "Download", locale="en"),
            SelectorEntry(
                "payment_confirm",
                SelectorKind.TEXT,
                "Confirm payment",
                locale="en",
                destructive=True,
            ),
        ]


__all__ = [
    "SelectorCatalog",
    "SelectorCatalogError",
    "SelectorEntry",
    "SelectorKind",
]

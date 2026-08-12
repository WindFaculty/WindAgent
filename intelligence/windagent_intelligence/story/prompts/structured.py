"""
Structured model boundary (B2) — schema-first invocation over the frozen
provider-neutral model port.

Flow per generation call:
1. Look up the catalog entry (unknown prompt ID fails closed).
2. Render the template, build a ``ModelCompletionRequest`` carrying the
   entry's PromptSpec (id/version/hash provenance).
3. Enforce safety constraints BEFORE parsing (size bounds, prohibited
   patterns) — model output is untrusted input.
4. Parse JSON against the declared output schema with AT MOST ONE bounded
   format-repair attempt (fenced-block extraction), counted in provenance.
   Semantic repair is a separate orchestrated task and never happens here.
5. Classify failures per the B0 error taxonomy: transient provider/empty
   errors vs terminal schema/safety failures. Provenance records
   route/prompt/model/usage only — never raw content, prompts, or secrets.

``STORY_PARSE_TRANSIENT`` is raised only when ``repair=False`` (caller chose
to retry the provider instead of repairing); the default path repairs once
internally and fails terminal on a second failure.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from jsonschema import Draft202012Validator

from windagent_core.contracts.studio.errors import StudioValidationError
from windagent_intelligence.story.prompts.registry import (
    OUTPUT_FORMAT_JSON,
    OUTPUT_FORMAT_TEXT,
    STORY_PROMPT_REGISTRY,
    SafetyConstraints,
    StoryPromptEntry,
)
from windagent_intelligence.video.ports import (
    ModelCompletionRequest,
    ModelCompletionResult,
    PreproductionModelPort,
)

# ---------------------------------------------------------------------------
# Error taxonomy (B0 quality_and_error_taxonomy.md §3)
# ---------------------------------------------------------------------------


class StoryModelError(Exception):
    """Base class for Story model-boundary failures."""

    code = "STORY_UNKNOWN_ERROR"

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = details or {}


class StoryProviderTransientError(StoryModelError):
    """Provider I/O/route failure; retryable within the provider budget."""

    code = "STORY_PROVIDER_TRANSIENT"


class StoryEmptyResponseError(StoryModelError):
    """Empty/blank model output; retryable (transient)."""

    code = "STORY_EMPTY_RESPONSE"


class StoryParseTransientError(StoryModelError):
    """Broken-but-repairable output when repair was explicitly bypassed."""

    code = "STORY_PARSE_TRANSIENT"


class StorySchemaFailure(StoryModelError):
    """Output does not match the declared schema after the bounded repair."""

    code = "STORY_SCHEMA_FAILURE"


class StorySafetyFailure(StoryModelError):
    """Output violates declared safety constraints (size/prohibited content)."""

    code = "STORY_SAFETY_FAILURE"


def story_error_code(exc: BaseException) -> str:
    """Map any exception to a B0 taxonomy code (unknown -> UNKNOWN)."""
    if isinstance(exc, StoryModelError):
        return exc.code
    if isinstance(exc, StudioValidationError):
        return "STORY_VALIDATION_FAILURE"
    return "STORY_UNKNOWN_ERROR"


# ---------------------------------------------------------------------------
# Provenance + result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StoryModelProvenance:
    """Route/prompt/model/usage provenance — never raw content or secrets."""

    prompt_id: str
    prompt_version: str
    prompt_hash: str
    capability: str
    provider: str
    finish_reason: str
    usage: Dict[str, Any] = field(default_factory=dict)
    repair_count: int = 0
    route_lock_id: Optional[str] = None
    canonical_model_id: Optional[str] = None
    provider_model_id: Optional[str] = None
    endpoint_id: Optional[str] = None
    provider_binding_id: Optional[str] = None
    provider_attempt_id: Optional[str] = None
    provider_request_id: Optional[str] = None
    output_schema_contract: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "prompt_hash": self.prompt_hash,
            "capability": self.capability,
            "provider": self.provider,
            "finish_reason": self.finish_reason,
            "usage": dict(self.usage),
            "repair_count": self.repair_count,
            "route_lock_id": self.route_lock_id,
            "canonical_model_id": self.canonical_model_id,
            "provider_model_id": self.provider_model_id,
            "endpoint_id": self.endpoint_id,
            "provider_binding_id": self.provider_binding_id,
            "provider_attempt_id": self.provider_attempt_id,
            "provider_request_id": self.provider_request_id,
            "output_schema_contract": self.output_schema_contract,
        }


@dataclass(frozen=True)
class StructuredModelResult:
    """Validated structured output + provenance."""

    data: Dict[str, Any]
    provenance: StoryModelProvenance


# ---------------------------------------------------------------------------
# Bounded repair (syntax only — never semantic)
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n?```", re.DOTALL | re.IGNORECASE)


def _extract_fenced_json(content: str) -> Optional[str]:
    """Extract the first ```json fenced block (single bounded repair)."""
    match = _FENCE_RE.search(content)
    return match.group(1).strip() if match else None


def _loads_or_repair(content: str) -> tuple[Optional[Dict[str, Any]], int]:
    """Parse JSON; on direct failure try exactly ONE bounded repair.

    Repair options (first that yields valid JSON, still one repair):
    1. fence-extraction (```json block);
    2. leading-object extraction: models sometimes append commentary after a
       complete JSON object — ``raw_decode`` takes the JSON prefix and drops
       the trailing junk, never guessing what the junk means.

    Returns ``(data, repair_count)`` or ``(None, attempts)`` when both fail.
    """
    try:
        return json.loads(content), 0
    except (json.JSONDecodeError, TypeError):
        pass
    fenced = _extract_fenced_json(content)
    if fenced is not None:
        try:
            return json.loads(fenced), 1
        except (json.JSONDecodeError, TypeError):
            pass
    try:
        obj, _idx = json.JSONDecoder().raw_decode(content.lstrip())
        if isinstance(obj, dict):
            return obj, 1
    except (json.JSONDecodeError, TypeError):
        pass
    return None, 1


# ---------------------------------------------------------------------------
# Structured invocation service
# ---------------------------------------------------------------------------


class StoryModelBoundary:
    """Schema-first invocation over ``PreproductionModelPort`` (frozen seam)."""

    def __init__(
        self,
        model_port: PreproductionModelPort,
        *,
        registry: Optional[Dict[str, StoryPromptEntry]] = None,
    ) -> None:
        self.model_port = model_port
        self.registry = registry if registry is not None else STORY_PROMPT_REGISTRY

    def _entry(self, prompt_id: str) -> StoryPromptEntry:
        try:
            return self.registry[prompt_id]
        except KeyError as exc:
            raise KeyError(f"no prompt registered for {prompt_id!r}") from exc

    async def invoke(
        self,
        prompt_id: str,
        *,
        variables: Dict[str, Any],
        route_lock_id: Optional[str] = None,
        repair: bool = True,
    ) -> StructuredModelResult:
        """Invoke one catalog prompt and return validated structured output."""
        entry = self._entry(prompt_id)
        rendered = entry.render(**variables)
        request = ModelCompletionRequest(
            capability=entry.capability,
            system=entry.system,
            user=rendered,
            temperature=entry.temperature,
            max_tokens=entry.max_tokens,
            prompt_spec=entry.to_prompt_spec(),
            structured_output_schema=(
                entry.output_schema if entry.output_format == OUTPUT_FORMAT_JSON else None
            ),
            metadata={"prompt_id": entry.prompt_id},
        )
        try:
            result = await self.model_port.complete(request)
        except StoryModelError:
            raise
        except Exception as exc:  # port contract: never raises; fakes may
            raise StoryProviderTransientError(
                "provider port raised during completion.",
                details={"prompt_id": prompt_id, "error": str(exc)[:200]},
            ) from exc
        return self._process(entry, result, route_lock_id=route_lock_id, repair=repair)

    # -- processing --------------------------------------------------------
    def _process(
        self,
        entry: StoryPromptEntry,
        result: ModelCompletionResult,
        *,
        route_lock_id: Optional[str],
        repair: bool,
    ) -> StructuredModelResult:
        content = result.content or ""
        if not content.strip():
            raise StoryEmptyResponseError(
                "model returned an empty response.",
                details={"prompt_id": entry.prompt_id},
            )
        self._check_safety(entry, content)
        if entry.output_format == OUTPUT_FORMAT_TEXT:
            data: Dict[str, Any] = {"text": content}
            repair_count = 0
        else:
            data, repair_count = self._parse_structured(entry, content, repair=repair)
        usage = dict(result.usage or {})
        schema_hash = hashlib.sha256(
            json.dumps(
                entry.output_schema,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        provenance = StoryModelProvenance(
            prompt_id=entry.prompt_id,
            prompt_version=entry.version,
            prompt_hash=entry.content_hash,
            capability=entry.capability,
            provider=result.provider,
            finish_reason=result.finish_reason,
            usage=usage,
            repair_count=repair_count,
            route_lock_id=route_lock_id or usage.get("route_lock_id"),
            canonical_model_id=usage.get("canonical_model_id"),
            provider_model_id=usage.get("provider_model_id"),
            endpoint_id=usage.get("endpoint_id"),
            provider_binding_id=usage.get("provider_binding_id"),
            provider_attempt_id=usage.get("provider_attempt_id"),
            provider_request_id=usage.get("provider_request_id"),
            output_schema_contract=f"{entry.output_format}:sha256:{schema_hash}",
        )
        return StructuredModelResult(data=data, provenance=provenance)

    def _check_safety(self, entry: StoryPromptEntry, content: str) -> None:
        safety: SafetyConstraints = entry.safety
        if len(content) > safety.max_output_chars:
            raise StorySafetyFailure(
                "model output exceeds the declared size bound.",
                details={
                    "prompt_id": entry.prompt_id,
                    "max_output_chars": safety.max_output_chars,
                    "received_chars": len(content),
                },
            )
        for pattern in safety.prohibited_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                raise StorySafetyFailure(
                    "model output matches a prohibited pattern.",
                    details={"prompt_id": entry.prompt_id, "pattern": pattern},
                )

    def _parse_structured(
        self, entry: StoryPromptEntry, content: str, *, repair: bool
    ) -> tuple[Dict[str, Any], int]:
        if repair:
            data, repair_count = _loads_or_repair(content)
        else:
            try:
                data, repair_count = json.loads(content), 0
            except (json.JSONDecodeError, TypeError) as exc:
                raise StoryParseTransientError(
                    "model output is not valid JSON and repair was bypassed.",
                    details={"prompt_id": entry.prompt_id, "error": str(exc)[:200]},
                ) from exc
        if data is None:
            raise StorySchemaFailure(
                "model output is not valid JSON after the bounded repair.",
                details={
                    "prompt_id": entry.prompt_id,
                    "repair_attempts": repair_count,
                    "preview": content[:200],
                },
            )
        errors = self._schema_errors(entry.output_schema, data)
        if errors:
            raise StorySchemaFailure(
                "model output does not match the declared schema.",
                details={
                    "prompt_id": entry.prompt_id,
                    "repair_attempts": repair_count,
                    "schema_errors": errors[:5],
                },
            )
        return data, repair_count

    @staticmethod
    def _schema_errors(schema: Dict[str, Any], data: Any) -> list[str]:
        if not schema:
            return []
        validator = Draft202012Validator(schema)
        return [err.message for err in validator.iter_errors(data)]


__all__ = [
    "StoryModelError",
    "StoryProviderTransientError",
    "StoryEmptyResponseError",
    "StoryParseTransientError",
    "StorySchemaFailure",
    "StorySafetyFailure",
    "story_error_code",
    "StoryModelProvenance",
    "StructuredModelResult",
    "StoryModelBoundary",
]

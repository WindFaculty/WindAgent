"""
C0 contract round-trip: the frozen studio.contract/v0.1 fixtures under
frontend/packages/studio-contracts/fixtures validate against the JSON Schema
definitions in schemas/. The same instances and schemas are validated from
TypeScript in @windagent/studio-contracts, proving one source of truth.

All fixtures are fixture_only: true per the manifest; none may be used by
production composition or injected as real-slice run output.
"""

import json
from pathlib import Path

import jsonschema
from referencing import Registry, Resource

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "frontend" / "packages" / "studio-contracts"
SCHEMAS_DIR = CONTRACTS_DIR / "schemas"
FIXTURES_DIR = CONTRACTS_DIR / "fixtures"

CANONICAL_NS = "https://windagent.io/schemas/"

METADATA_KEYS = ("fixture_id", "purpose", "expected_consumer_behavior")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonicalize_refs(node):
    """Rewrite relative file refs into absolute canonical URIs so the
    referencing.Registry resolves them independently of each schema $id."""
    if isinstance(node, list):
        return [_canonicalize_refs(item) for item in node]
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and ".schema.json" in value:
                filename = value.split("#")[0]
                fragment = value.split("#", 1)[1] if "#" in value else ""
                out[key] = f"{CANONICAL_NS}{filename}#{fragment}"
            else:
                out[key] = _canonicalize_refs(value)
        return out
    return node


def _build_registry() -> tuple[Registry, dict[str, dict]]:
    schemas: dict[str, dict] = {}
    resources = []
    for schema_file in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        schema = _load_json(schema_file)
        schemas[schema_file.name] = schema
        canonical = dict(schema)
        canonical.pop("$id", None)
        resources.append(
            (f"{CANONICAL_NS}{schema_file.name}", Resource.from_contents(_canonicalize_refs(canonical)))
        )
    return Registry().with_resources(resources), schemas


def _strip_metadata(instance: dict) -> dict:
    return {key: value for key, value in instance.items() if key not in METADATA_KEYS}


REGISTRY, SCHEMAS = _build_registry()
MANIFEST = _load_json(FIXTURES_DIR / "manifest.json")


def _validator(schema_name: str):
    return jsonschema.Draft202012Validator(
        {"$ref": f"{CANONICAL_NS}{schema_name}"},
        registry=REGISTRY,
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
    )


def test_manifest_is_frozen_at_contract_version():
    assert MANIFEST["contract_version"] == "studio.contract/v0.1"
    assert MANIFEST["artifact_schema_version"] == "studio.artifact/v1alpha1"


def test_every_fixture_resolves_a_known_schema():
    for entry in MANIFEST["fixtures"]:
        fixture_path = FIXTURES_DIR / entry["file"]
        assert fixture_path.exists(), f"missing fixture {entry['file']}"
        assert entry["schema"] in SCHEMAS, f"unknown schema {entry['schema']}"
        assert _load_json(fixture_path)


def test_valid_fixtures_validate_against_their_schema():
    for entry in MANIFEST["fixtures"]:
        if entry["kind"] != "valid":
            continue
        instance = _strip_metadata(_load_json(FIXTURES_DIR / entry["file"]))
        validator = _validator(entry["schema"])
        errors = list(validator.iter_errors(instance))
        assert not errors, f"{entry['id']} should validate: {[e.message for e in errors]}"


def test_vocabulary_fixtures_stay_within_frozen_enums():
    episode_states = SCHEMAS["studio.episode-state.schema.json"]["$defs"]["state"]["enum"]
    run_statuses = SCHEMAS["studio.run-status.schema.json"]["enum"]
    approval_modes = SCHEMAS["studio.approval-mode.schema.json"]["properties"]["mode"]["enum"]
    checkpoints = SCHEMAS["studio.approval-mode.schema.json"]["properties"]["checkpoint"]["enum"]

    progression = _load_json(FIXTURES_DIR / "episode-state.progression.json")
    for state in [*progression["states"], *progression["terminal_states"]]:
        assert state in episode_states, f"unknown episode state {state}"
    assert progression["states"][-1] == "READY_FOR_PRODUCTION"

    run_status = _load_json(FIXTURES_DIR / "run-status.valid.json")
    assert run_status["status"] in run_statuses
    assert all(s in run_statuses for s in run_status["all_statuses"])

    approval = _load_json(FIXTURES_DIR / "approval-mode.all.json")
    assert all(m in approval_modes for m in approval["modes"])
    assert all(c in checkpoints for c in approval["checkpoints"])
    for policy in approval["policy"]:
        assert policy["checkpoint"] in checkpoints
        assert policy["mode"] in approval_modes

    headers = _load_json(FIXTURES_DIR / "idempotency-headers.valid.json")
    validator = _validator("studio.idempotency-headers.schema.json")
    assert not list(validator.iter_errors(headers["headers"]))


def test_negative_malformed_fixture_fails_validation():
    entry = next(e for e in MANIFEST["fixtures"] if e["kind"] == "negative-malformed")
    instance = _strip_metadata(_load_json(FIXTURES_DIR / entry["file"]))
    validator = _validator(entry["schema"])
    errors = list(validator.iter_errors(instance))
    assert errors, f"{entry['id']} must fail validation"


def test_negative_unsupported_version_validates_at_envelope_level():
    entry = next(e for e in MANIFEST["fixtures"] if e["kind"] == "negative-unsupported-version")
    instance = _strip_metadata(_load_json(FIXTURES_DIR / entry["file"]))
    validator = _validator(entry["schema"])
    errors = list(validator.iter_errors(instance))
    assert not errors, "envelope must remain forward-compatible"
    assert instance["artifact_type"]
    assert instance["schema_version"]


def test_frozen_vocabulary_matches_cross_plan_contract():
    states = json.dumps(SCHEMAS["studio.episode-state.schema.json"])
    assert "READY_FOR_PRODUCTION" in states
    assert "STORY_BIBLE_REVIEW" in states

    run_status = json.dumps(SCHEMAS["studio.run-status.schema.json"])
    assert "WAITING_FOR_APPROVAL" in run_status

    approval = json.dumps(SCHEMAS["studio.approval-mode.schema.json"])
    assert "HUMAN_REQUIRED" in approval
    assert "QUALITY_GATE_ONLY" in approval

    errors = json.dumps(SCHEMAS["studio.error-payload.schema.json"])
    assert "IDEMPOTENCY_MISMATCH" in errors
    assert "CAPABILITY_UNAVAILABLE" in errors


def test_error_mapping_matrix_matches_frozen_bootstrap_contract():
    """Error codes/statuses must match the frozen bootstrap fixture
    docs/plans/studio_roadmap_01/fixtures/studio_contract_v0.1/errors.json."""
    bootstrap = _load_json(
        REPO_ROOT / "docs" / "plans" / "studio_roadmap_01" / "fixtures" / "studio_contract_v0.1" / "errors.json"
    )
    frozen_codes = {entry["code"] for entry in bootstrap["errors"]}
    frozen_statuses = {entry["http_status"] for entry in bootstrap["errors"]}

    codes = SCHEMAS["studio.error-payload.schema.json"]["properties"]["code"]["enum"]
    statuses = SCHEMAS["studio.error-payload.schema.json"]["properties"]["status"]["enum"]
    assert set(codes) == frozen_codes
    assert set(statuses) == frozen_statuses

    frozen_map = {entry["code"]: entry["http_status"] for entry in bootstrap["errors"]}
    for code in codes:
        assert code in frozen_map, f"code {code} missing from bootstrap errors.json"


def test_artifact_types_match_frozen_bootstrap_contract():
    """Known artifact types must match studio_contract_v0.1/artifact_envelope.json."""
    bootstrap = _load_json(
        REPO_ROOT / "docs" / "plans" / "studio_roadmap_01" / "fixtures" / "studio_contract_v0.1" / "artifact_envelope.json"
    )
    frozen_types = set(bootstrap["artifact_types"])
    known = SCHEMAS["studio.artifact-envelope.schema.json"]["properties"]["artifact_type"]["description"]
    for artifact_type in frozen_types:
        assert artifact_type in known, f"artifact type {artifact_type} missing from envelope schema"


def test_episode_state_vocabulary_matches_frozen_bootstrap_contract():
    """State values and approval checkpoints/modes must match episode_lifecycle.json."""
    bootstrap = _load_json(
        REPO_ROOT / "docs" / "plans" / "studio_roadmap_01" / "fixtures" / "studio_contract_v0.1" / "episode_lifecycle.json"
    )
    states = SCHEMAS["studio.episode-state.schema.json"]["$defs"]["state"]["enum"]
    assert set(states) == set(bootstrap["states"])
    assert bootstrap["single_terminal_success_rule"]
    assert bootstrap["ready_event_rule"]

    approval = SCHEMAS["studio.approval-mode.schema.json"]
    modes = approval["properties"]["mode"]["enum"]
    checkpoints = approval["properties"]["checkpoint"]["enum"]
    assert set(modes) == set(bootstrap["approval_modes"])
    assert set(checkpoints) == set(bootstrap["approval_checkpoints"])

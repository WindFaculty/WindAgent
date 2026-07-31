# Prompt Versioning — Video Pre-production Kernel (Phase 6)

Source: plan 02 `§16.1`/`§18`; protocol `provider_port_contract.md`.
Every model-backed capability in the video kernel records the exact prompt
that produced its output.

## 1. The PromptSpec contract

A `PromptSpec` (`intelligence/windagent_intelligence/video/prompts.py`) is an
immutable, frozen dataclass:

```text
capability: str      # e.g. "screenplay_generation"
version: str         # semantic version, e.g. "1.0.0"
template: str        # prompt text with {placeholder} slots
description: str     # human-readable intent
metadata: dict       # optional parameters
content_hash: str    # SHA-256 over capability::version::template
```

`content_hash` is computed deterministically over the resolved contract
(`f"{capability}::{version}::{template}"`). Any edit to the template, the
capability name, or the version changes the hash — so an artifact can always
be traced to the exact prompt bytes that produced it.

`render(**kwargs)` uses a safe mapping: unknown `{placeholders}` are left
intact instead of raising `KeyError`, so a template drift fails loudly at the
hash boundary, not silently at render time.

## 2. Where versioning is recorded

Every model-backed capability returns, alongside its domain object:

```text
prompt_version: <spec.version>
prompt_hash:    <spec.content_hash>
capability:     <spec.capability>
```

These are persisted in the domain object's `metadata` where it is meaningful:

- `Screenplay.metadata["prompt_version"]` / `["prompt_hash"]`
- `StyleBible.metadata["prompt_version"]` / `["prompt_hash"]`
- `ContinuationResult.prompt_version` / `.prompt_hash`
- package `provenance.metadata["asset_prompt_specs"]` carries per-asset
  `prompt_version` + `prompt_hash` for every asset prompt spec bound to the
  package (via `PackageAssembler`).

## 3. Version policy

- Start every new capability at `1.0.0`.
- **Patch** (`1.0.0 → 1.0.1`): typo / formatting fix that does not change the
  semantics of the output contract. Output remains comparable under the same
  equivalence policy.
- **Minor** (`1.0.x → 1.1.0`): added optional instruction; artifacts may
  change but the domain contract and blocking equivalence fields are stable.
- **Major** (`1.x.y → 2.0.0`): changed output contract / schema; old
  artifacts are no longer traceable to the new prompt. Requires updating
  `capability_contracts.md` and the equivalence policy before use.

## 4. Golden comparison behavior

The Phase 6 verifier's golden comparison checks *semantic* fields (see
`equivalence_policy.md`), NOT `content_hash`. A hash change alone never fails
equivalence — it only records that a new prompt version produced the output.
Prompt hash stability is asserted separately (a fixed template must hash
identically across processes and platforms).

## 5. Registered prompt specs (v1.0.0)

| Capability | Spec constant |
|---|---|
| brief_expansion | `BRIEF_EXPANSION_PROMPT_V1` |
| story_outline | `OUTLINE_PROMPT_V1` |
| screenplay_generation | `SCREENPLAY_PROMPT_V1` |
| style_design | `STYLE_DESIGN_PROMPT_V1` |
| continuation | `CONTINUATION_PROMPT_V1` |
| asset_prompt.character_portrait | `CHARACTER_PORTRAIT_PROMPT_V1` |
| asset_prompt.location | `LOCATION_PROMPT_V1` |
| asset_prompt.style | `STYLE_PROMPT_V1` |

## 6. Enforcement

- The verifier (`verify_phase6_kernel.py`) imports every registered spec and
  asserts: (a) `version` is semantic, (b) `content_hash` is 64-char SHA-256,
  (c) hash is stable across two render calls, (d) every model-backed
  capability's output dict carries `prompt_version` + `prompt_hash`.
- Architecture test `test_phase06_kernel_canonical.py` blocks any template
  edit that forgets to bump the version (checked by the verifier's
  capability matrix).

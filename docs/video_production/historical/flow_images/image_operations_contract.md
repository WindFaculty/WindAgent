# Flow Image Operations Contract (Phase 14)

**Gate:** `VP14_FLOW_IMAGE_GENERATION_VERIFIED`
**Plan:** [04_phase_12_16_flow_browser_provider.md](../plans/04_phase_12_16_flow_browser_provider.md) §16–§17
**Location:** `tools/windagent_tools/google_flow/image_operations.py`

## 1. Purpose

Each image operation maps a typed `FlowImageRequest` to typed configuration
steps (`FlowUiAction`), never to raw browser instructions (plan 04 §17).

## 2. Operations (8)

```text
CREATE_CHARACTER_REFERENCE
CREATE_LOCATION_REFERENCE
CREATE_PROP_REFERENCE
CREATE_STORYBOARD_FRAME
CREATE_FIRST_FRAME
CREATE_LAST_FRAME
EDIT_IMAGE
UPSCALE_IMAGE
```

## 3. Typed request

```python
FlowImageRequest(
    operation: FlowImageOperation
    request_hash: str          # 64-hex sha256 from the compiled request
    project_id / revision_id / shot_id
    prompt
    reference_bindings         # (role, content_hash) tuples
    candidate_limit            # bounded (default 4)
    max_cost_credits           # cost/quota policy
    idempotency_token          # internal token (submit-once, §18.2)
)
```

## 4. Mapper policy facts

| Fact | Meaning |
|---|---|
| `supported(op)` | provider capability gate (fail closed) |
| `is_character_master(op)` | `CREATE_CHARACTER_REFERENCE` → human approval always (§18.4) |
| `requires_reference(op)` | identity/location/prop/first/last frame ops need an approved reference |
| `requires_source_image(op)` | `EDIT_IMAGE` / `UPSCALE_IMAGE` consume an approved source |
| `configuration_actions(req)` | typed `FlowUiAction`s: mode → model → ratio → prompt → uploads |

## 5. Contract

- Exactly 8 operations; every configuration step is a typed `FlowUiAction`
  (`select` / `fill` / `upload`) — never `eval`, `click_xy`, or raw commands.
- No operation is executed unless the provider capability matrix says so.

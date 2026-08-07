# Flow Selector Catalog (Phase 13)

**Gate:** `VP13_FLOW_NAVIGATION_VERIFIED`
**Plan:** [04_phase_12_16_flow_browser_provider.md](../plans/04_phase_12_16_flow_browser_provider.md) §13.4
**Location:** `tools/windagent_tools/google_flow/selectors/catalog.py`

## 1. Purpose

`SelectorCatalog` is the versioned, semantic-first catalog of Flow UI
selectors (plan 04 §13.4). It is the **only** place where UI locators live —
navigation code never hardcodes a CSS class, DOM index or coordinate.

## 2. Selector strategy (priority order)

```text
accessibility role
label
visible text
stable URL
semantic region
```

CSS class, DOM index and coordinates are **never primary selectors**. A
`SelectorEntry` built with a forbidden primary kind raises
`SelectorCatalogError` at registration time (fail fast, in the catalog
constructor).

## 3. SelectorEntry

| Field | Meaning |
|---|---|
| `name` | stable selector id (e.g. `submit_generation`) |
| `kind` | `SelectorKind`: ROLE / LABEL / TEXT / URL / REGION |
| `value` | semantic locator value |
| `locale` | locale assumption (default `en`) |
| `confidence` | float in [0, 1] |
| `fallback` | ordered fallback semantics |
| `destructive` | True → never auto-clicked by a fallback |

## 4. Built-in catalog (v1.0.0, en)

```text
sign_in_button       role:button
create_project       text:Create
import_project       text:Import
open_project         url:/projects            fallback: project canvas
create_workspace     text:Create workspace    fallback: New workspace, Workspace
generation_mode      role:combobox
reference_upload     role:button
prompt_field         role:textbox
model_select         role:combobox
duration_select      role:combobox
aspect_ratio_select  role:combobox
submit_generation    text:Generate
download_result      text:Download
payment_confirm      text:Confirm payment     destructive: True
```

## 5. Safety rules

- `payment_confirm` and any other `destructive=True` selector are never
  auto-clicked by a fallback (plan 04 §13.4).
- Locale mismatch is explicit: the catalog carries a `locale` assumption; a
  locale mismatch is surfaced as drift, never silently re-resolved.
- Duplicate / unknown selector names raise `SelectorCatalogError` — a
  duplicate label cannot silently shadow the primary selector.

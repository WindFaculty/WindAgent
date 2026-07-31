# VideoProductionPackage v1

The `VideoProductionPackage v1` is the canonical, portable, immutable artifact
that is the single source of truth between pre-production, the Director layer,
orchestration, and media providers.

## Location

```text
core/windagent_core/domain/video_production/package.py
```

Machine-readable JSON Schema: `docs/video_production/protocol/video_production_package_v1.schema.json`

## Canonical structure

```json
{
  "schema_version": "1.0.0",
  "project_id": "vp_01",
  "revision_id": "rev_03",
  "creative_brief": {},
  "story_concept": {},
  "screenplay": {"scenes": []},
  "characters": [],
  "locations": [],
  "props": [],
  "style_bible": {},
  "dialogue": [],
  "production_constraints": {},
  "cinematic_plan": {},
  "continuity": [],
  "assets": [],
  "generation_records": [],
  "approvals": {},
  "final_deliverable": {},
  "provenance": {}
}
```

## Field semantics

| Field | Required | Nullable | Default |
|---|---|---|---|
| `schema_version` | yes | no | `"1.0.0"` |
| `project_id` | yes | no | — |
| `revision_id` | yes | no | — |
| `creative_brief` | no | yes | `null` |
| `story_concept` | no | yes | `null` |
| `screenplay` | no | yes | `null` |
| `characters` | no | no | `[]` |
| `locations` | no | no | `[]` |
| `props` | no | no | `[]` |
| `style_bible` | no | yes | `null` |
| `dialogue` | no | no | `[]` |
| `cinematic_plan` | no | yes | `null` |
| `continuity` | no | no | `[]` |
| `assets` | no | no | `[]` |
| `generation_records` | no | no | `[]` |
| `approvals` | no | no | `{}` |
| `final_deliverable` | no | yes | `null` |
| `provenance` | no | no | `created_by="system"` |

## Identity rules

- All IDs are opaque, stable strings (never derived from display names).
- Scene and shot order is an explicit integer.
- References between objects use IDs only.
- Deleted/renamed entities never reuse an old ID.

## Canonical serialization & content hash

- `content_hash()` = SHA-256 over the canonical JSON serialization.
- Canonical serialization uses sorted keys, compact separators, and UTC ISO
  timestamps, so the same logical content always yields the same hash.
- The package is immutable (`frozen=True`); any content change creates a new
  revision.

## Invariants

- ID ổn định, không dùng tên làm khóa.
- Scene và shot có thứ tự xác định.
- Asset luôn có hash (64-char SHA-256).
- Asset tải từ internet có provenance (acquisition record).
- Mọi revision immutable.
- Thay đổi screenplay tạo revision mới với invalidation intent.
- Không sửa artifact đã được khóa.
- Mọi generated output truy ngược được về prompt và reference.

## Validation

Use `VideoProductionPackageValidator` from
`core/windagent_core/domain/video_production/validation.py`. It enforces the
six required invalid-fixture categories plus approval-target integrity.

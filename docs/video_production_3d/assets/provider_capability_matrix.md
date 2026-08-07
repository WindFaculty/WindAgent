# Provider Capability Matrix (VP3D Phase 5)

Ma trận capability của từng adapter — dùng cho pre-call matching. Mọi giá trị được khai báo trong `AssetProviderCapability` và được `CapabilityMatcher` so với `AssetRequirement` TRƯỚC khi adapter được gọi.

## 1. Adapter registry (adapter_id mặc định)

| adapter_id | Kind | Version | Availability mặc định |
|---|---|---|---|
| `local.library` | LOCAL | 1.0.0 | READY khi library dir tồn tại, else UNAVAILABLE |
| `internet.search` | INTERNET | 1.0.0 | REQUIRES_CONFIG cho tới khi inject search+acquisition backend |
| `mesh.api.v1` | MESH_API | 1.0.0 | REQUIRES_CONFIG cho tới khi inject transport |
| `mesh.mcp.v1` | MESH_MCP | 1.0.0 | REQUIRES_CONFIG cho tới khi inject transport |
| `generator.future` | GENERATOR | 1.0.0 | REQUIRES_CONFIG cho tới khi inject backend |

CI/fakes: `fake.local.library`, `fake.internet.search`, `fake.mesh.api.v1`, `fake.mesh.mcp.v1`, `fake.generator.future` (luôn READY, deterministic).

## 2. Capability khai báo

| Capability | local.library | internet.search | mesh.api.v1 | mesh.mcp.v1 | generator.future |
|---|---|---|---|---|---|
| supported_kinds | mọi AssetKind | mọi AssetKind | CHARACTER, PROP, ENVIRONMENT, VEHICLE, CREATURE, TEXTURE | mọi AssetKind | CHARACTER, PROP, ENVIRONMENT, VEHICLE, CREATURE, TEXTURE, MATERIAL |
| supported_styles | mọi AssetStyle | mọi AssetStyle | mọi AssetStyle | mọi AssetStyle | mọi AssetStyle |
| rig_supported | true | true | true | true | true |
| max_texture_resolution | 16384 | 8192 | 8192 | 8192 | 4096 |
| license_constraints | ANY_PERMISSIVE, COMMERCIAL_ALLOWED, NO_ATTRIBUTION, ATTRIBUTION_REQUIRED | + 4 constraint | COMMERCIAL_ALLOWED, ANY_PERMISSIVE | COMMERCIAL_ALLOWED, ANY_PERMISSIVE, ATTRIBUTION_REQUIRED | ANY_PERMISSIVE, COMMERCIAL_ALLOWED, NO_ATTRIBUTION |
| max_polygons | unlimited (None) | unlimited (None) | 5,000,000 | 5,000,000 | 3,000,000 |
| max_file_bytes | unlimited (None) | unlimited (None) | 1 GiB | 1 GiB | 512 MiB |
| supports_generation | false | false | false | false | true |

## 3. Budget mặc định (AssetBudget)

| Budget | Giá trị mặc định |
|---|---|
| max_polygons | 1,000,000 |
| max_texture_resolution | 4096 |
| max_file_bytes | 512 MiB |
| max_vram_estimate_bytes | 4 GiB (preview VRAM bound; Phase 7 dùng cho BLOCKED check) |

## 4. Ý nghĩa fail-closed

- Availability != READY → `CapabilityRejectedError` được ghi vào attempts; adapter KHÔNG được gọi.
- `license_constraints` KHÔNG chứa constraint của requirement → rejection (UNSPECIFIED luôn khớp).
- `texture_resolution` / `max_polygons` / `max_file_bytes` vượt bound → rejection.

## 5. Mở rộng

Thêm provider mới: implement `AssetAdapter` (adapter_id + version + capability + discover/acquire), đăng ký vào `AssetAdapterRegistry`, chạy `AssetAdapterContractSuite`. Contract test chung đảm bảo semantics đồng nhất.

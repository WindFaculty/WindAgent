# Chỉ mục tài liệu WindAgent

Thư mục này được tổ chức theo **phạm vi hệ thống** và **mức độ hiệu lực**. Khi cần xác định nguồn chuẩn, ưu tiên tài liệu hợp đồng, giao thức, hoặc ADR; tài liệu trong `plans/` là kế hoạch và bằng chứng triển khai, không tự động thay thế hợp đồng chuẩn.

## Phân loại nhanh

| Nhóm | Đường dẫn | Mục đích | Trạng thái |
| --- | --- | --- | --- |
| Kiến trúc nền tảng | [`architecture/`](architecture/) | Quyết định kiến trúc và mô hình frontend | Chuẩn thiết kế |
| Hợp đồng nền tảng | Các tệp `.md` tại đây | API, sự kiện, registry nhà cung cấp, an toàn | Chuẩn giao tiếp/chính sách |
| Kế hoạch Studio | [`plans/studio_roadmap_01/`](plans/studio_roadmap_01/) | Lộ trình, phân công, cổng nghiệm thu và bằng chứng | Kế hoạch lịch sử + fixture kiểm thử |
| Sản xuất video | [`video_production/`](video_production/) | Hợp đồng và chính sách cho chuỗi sản xuất video | Chuẩn miền nghiệp vụ |
| Sản xuất video 3D | [`video_production_3d/`](video_production_3d/) | Phần mở rộng chuyên biệt cho assets và audio 3D | Chuẩn miền nghiệp vụ |

## Tài liệu nền tảng

- [`api_contract.md`](api_contract.md): hợp đồng API kiến trúc V2.
- [`event_protocol.md`](event_protocol.md): định dạng và quy tắc sự kiện V2.
- [`model_provider_registry.md`](model_provider_registry.md): đăng ký và khả năng của nhà cung cấp mô hình.
- [`safety_policy.md`](safety_policy.md): chính sách bảo mật, an toàn và phân quyền.

## Kiến trúc

- [`architecture/adr/`](architecture/adr/): Architecture Decision Records cho mô hình dữ liệu, workflow, versioning và memory/database.
- [`architecture/frontend_v3/`](architecture/frontend_v3/): từ vựng chuẩn, định danh tài nguyên, aggregate map và hướng dẫn migration cho frontend V3.

## Video production

| Miền | Nội dung |
| --- | --- |
| [`preproduction/`](video_production/preproduction/) | Khả năng đầu vào, prompt versioning và retirement. |
| [`director/`](video_production/director/) | Kế hoạch điện ảnh, shot, continuity và revision. |
| [`assets/`](video_production/assets/) | Thu thập, quyền likeness, provenance, retention và định dạng media. |
| [`audio/`](video_production/audio/) | TTS, voice profile, quyền, đồng bộ và mix. |
| [`generation_review/`](video_production/generation_review/) | Review bằng VLM, tính liên tục và các cổng quyết định. |
| [`postproduction/`](video_production/postproduction/) | EDL, encoding, an toàn FFmpeg và kiểm định media cuối. |
| [`artifact_storage/`](video_production/artifact_storage/) | Artifact, dependency graph, invalidation, publish và reuse. |
| [`durable_workflow/`](video_production/durable_workflow/) | Workflow, checkpoint, approval, cancellation và recovery. |
| [`protocol/`](video_production/protocol/) | Package V1, schema, event, provider port, khóa và versioning. |
| [`workspace/`](video_production/workspace/) | API, UX phê duyệt, information architecture và event projection. |
| [`browser_runtime/`](video_production/browser_runtime/) | Runtime, browser action, pinning và redaction. |
| [`cost_quota/`](video_production/cost_quota/) | Budget, estimate, quota, catalog và circuit breaker. |
| [`reliability/`](video_production/reliability/) | Recovery, reconciliation, invariants và failure injection. |
| [`security/`](video_production/security/) | Threat model, audit, privacy, secret và action confirmation. |
| [`3d_animation_plans/`](video_production/3d_animation_plans/) | Lộ trình A–Q cho pipeline 3D/Blender/Unreal. |

## Video production 3D

- [`video_production_3d/assets/`](video_production_3d/assets/): normalisation, provenance, resolver và ma trận năng lực nhà cung cấp.
- [`video_production_3d/audio/`](video_production_3d/audio/): voice identity, forced alignment, timing và concurrency.

## Kế hoạch Studio và dữ liệu đi kèm

`plans/studio_roadmap_01/` được chia làm ba lớp rõ ràng:

1. Các tệp đánh số `00`–`90` và `PLAN_*`: phân tích hiện trạng, kế hoạch thực hiện, ownership, rủi ro và acceptance gates.
2. `evidence/`: bằng chứng/gate report phục vụ việc xác nhận từng kế hoạch.
3. `fixtures/studio_contract_v0.1/`: mẫu JSON, schema, golden case và invalid case phục vụ kiểm thử hợp đồng; đây là dữ liệu kiểm thử, không phải tài liệu chuẩn để đọc đầu tiên.

## Quy ước bảo trì

- Thêm quyết định kiến trúc mới vào `architecture/adr/` với mã ADR kế tiếp.
- Thêm hợp đồng liên miền vào `video_production/protocol/` hoặc một miền sở hữu rõ ràng; tránh tạo tệp `.md` mới ở gốc `docs/` nếu đã có miền phù hợp.
- Đặt schema, golden fixture và invalid fixture cạnh nhau dưới `plans/.../fixtures/` hoặc thư mục fixture dành riêng; không trộn chúng với tài liệu quy phạm.
- Khi một kế hoạch được thay thế, giữ nó trong `plans/` và đánh dấu trạng thái trong chính tài liệu thay vì di chuyển hoặc xóa dữ liệu tham chiếu.

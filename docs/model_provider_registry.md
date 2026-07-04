# Model Provider Registry

Tài liệu này chi tiết hóa cấu hình đăng ký của 8 API Providers được tích hợp sẵn trong hệ thống quản lý mô hình (Model Registry) của **WindAgent**.

| Provider ID | Site Name | API Source | Base URL | Quota Mode | Key Env | Discovery | Recommended Router Usage | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **agentrouter** | AgentRouter | `agentrouter` | `https://agentrouter.org/v1` | `ONE_TIME_CREDIT` | `AGENTROUTER_API_KEY` | Không | Chỉ dùng làm dự phòng (fallback) hoặc tác vụ cực khó. | Cần kích hoạt thủ công sau khi thêm key và probe thành công. |
| **bluesminds** | BluesMinds | `bluesminds` | `https://api.bluesminds.com/v1` | `ONE_TIME_CREDIT` | `BLUESMINDS_API_KEY` | Có | Dự phòng (fallback), không dùng cho request lặp lại hoặc chat nhẹ. | Unified LLM Gateway. Quản lý hạn mức dạng Credit. |
| **zenmux** | ZenMux PAYG | `zenmux` | `https://api.zenmux.ai/v1` | `TOKEN_BUDGET` | `ZENMUX_API_KEY` | Có | Thích hợp cho các tác vụ xử lý hàng loạt (batch) hoặc context dài. | Hỗ trợ Management API kiểm tra số dư. |
| **mistral** | Mistral.ai | `mistral` | `https://api.mistral.ai/v1` | `TOKEN_BUDGET` | `MISTRAL_API_KEY` | Có | Định tuyến các tác vụ Lập trình (Coding) thông qua model Codestral. | Hạn mức tính theo giây, phút, tháng tùy theo gói đăng ký. |
| **nararouter** | NaraRouter | `nararouter` | `https://router.bynara.id/v1` | `TOKEN_BUDGET` | `NARAROUTER_API_KEY` | Có | Thích hợp cho các tác vụ chạy hàng ngày có chu kỳ. | Hạn mức Tokens reset theo ngày (Daily token budget). |
| **openrouter** | OpenRouter | `openrouter` | `https://openrouter.ai/api/v1` | `RPM_RPD` | `OPENROUTER_API_KEY` | Có | Ưu tiên các model free (đuôi `:free`) cho các tác vụ chat thông thường. | Free quota phụ thuộc vào Credit trong tài khoản. |
| **nvidia_nim** | NVIDIA NIM | `nvidia` | `https://integrate.api.nvidia.com/v1` | `RPM_RPD` | `NVIDIA_API_KEY` | Có | Định tuyến cho tác vụ suy luận nặng (heavy reasoning/research). | Tốc độ cao nhưng giới hạn RPM nghiêm ngặt. |
| **google_ai_studio** | Google AI Studio | `google` | `https://generativelanguage.googleapis.com` | `RPM_RPD` | `GOOGLE_AI_STUDIO_API_KEY` | Có | Thích hợp cho GUI Agent (Vision) và các tác vụ context lớn (Flash). | Cần dùng client Google API riêng biệt. Có Free tier rất lớn. |

---

## Nguyên tắc định tuyến mặc định của Router:
1. **Local/Ollama**: Ưu tiên cao nhất cho chat thông thường, lập kế hoạch đơn giản để đảm bảo bảo mật dữ liệu và không tiêu tốn quota.
2. **Google Gemini Flash / Lite (Free tier)**: Phân hệ GUI (Vision) và xử lý ngữ cảnh cực dài (long-context) nhờ vào token limit khổng lồ và tốc độ nhanh.
3. **OpenRouter Free models**: Dành cho tác vụ phụ trợ (general chat / fallback chains) khi các mô hình cục bộ hoặc Free Gemini bị nghẽn.
4. **NVIDIA NIM / Google Pro**: Dành cho các tác vụ Nghiên cứu/Suy luận nâng cao (Researcher, Reasoner) cần độ chính xác cao.
5. **Mistral / Codestral**: Chỉ định riêng cho các tác vụ viết code hoặc review code (Coder).

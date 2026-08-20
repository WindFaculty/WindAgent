# VIDEO 02 — KỊCH BẢN TIMECODE QUAY & LỒNG TIẾNG (70 PHÂN CẢNH)
**Video ID:** video-02 | **Milestone:** Agentic Studio v0.1 — Simple Agent Core
**Total Duration:** 22:12.000 | **Scenes:** 70

---

## [00:00.000 -> 00:25.000] S01 — COLD OPEN: CHO XEM THÀNH QUẢ TRƯỚC
**Visual Mode:** `FULL_TERMINAL` | **Take:** `S01_T01` | **Thời lượng:** `25.0s`

**Chỉ đạo hình ảnh (Visual):**
```text
Terminal full screen.

```bash
python -m src.main
```

Terminal:

```text
Agentic Studio v0.1

You: Giải thích recursion cho một người mới học lập trình.

Agent:
Recursion là khi một hàm gọi lại chính nó...
```

Cut cực nhanh:

```python
agent.run(...)
```

↓

```python
class Agent:
```

↓

```python
class LLMClient(Protocol):
```

↓

```text
2 passed
```

↓

Architecture:

```text
User → Agent → LLM → Answer
```
```


**Lời thoại thuyết minh (Voice):**
> > Đây là AI Agent đầu tiên mà chúng ta sẽ build trong series này.
>
> Nó chưa có Tool.
>
> Chưa có Memory.
>
> Chưa Planning.
>
> Chưa Multi-Agent.
>
> Thậm chí nếu dùng định nghĩa thật chặt, nó còn chưa phải một autonomous agent hoàn chỉnh.
>
> Nhưng chính bốn abstraction trong video hôm nay sẽ trở thành nền móng cho toàn bộ hệ thống chúng ta xây trong sáu tháng tới.

Title card.

# BUILD YOUR FIRST AI AGENT

### FROM SCRATCH. NO FRAMEWORK.

---

## [00:25.000 -> 00:50.000] S02 — NỐI TRỰC TIẾP VỚI VIDEO 01
**Visual Mode:** `DIAGRAM` | **Take:** `S02_T01` | **Thời lượng:** `25.0s`

**Chỉ đạo hình ảnh (Visual):**
```text
Master diagram Video 01:

```text
Goal
 ↓
Observe
 ↓
Decide
 ↓
Act
 ↓
Observe
 └──────────↺
```
```


**Lời thoại thuyết minh (Voice):**
> > Ở video trước, chúng ta đã nhìn Agent ở cấp độ kiến trúc.
>
> Một Agent hoàn chỉnh có goal.
>
> Nó quan sát môi trường.
>
> Nó quyết định.
>
> Nó hành động.
>
> Sau đó lại quan sát kết quả và tiếp tục vòng lặp.

Diagram dần fade.

Chỉ còn:

```text
User
 ↓
Agent
 ↓
LLM
 ↓
Answer
```

> Nhưng nếu video thứ hai chúng ta lập tức xây Tool Registry, Memory, Planner, State Machine và Agent Loop…
>
> chúng ta sẽ mắc đúng sai lầm mà tôi muốn tránh trong cả series này.

Text lớn:

# TOO MUCH COMPLEXITY TOO EARLY

> Chúng ta sẽ build từng capability đúng vào thời điểm nó trở nên cần thiết.

---

## [00:50.000 -> 01:12.000] S03 — ĐẶT CÂU HỎI QUAN TRỌNG NHẤT
**Visual Mode:** `SPLIT` | **Take:** `S03_T01` | **Thời lượng:** `22.0s`

**Lời thoại thuyết minh (Voice):**
> > Bây giờ có một câu hỏi.
>
> Nếu mục tiêu hôm nay chỉ là:

```text
User → LLM → Answer
```

> tại sao chúng ta không viết đúng năm dòng Python gọi API rồi kết thúc video?

---

## [01:12.000 -> 01:35.000] S04 — VIẾT PHIÊN BẢN “NGÂY THƠ” NHẤT
**Visual Mode:** `FULL_CODE` | **Take:** `S04_T01` | **Thời lượng:** `23.0s`

**Chỉ đạo hình ảnh (Visual):**
```text
Code:

```python
client = SomeLLMClient(api_key="...")

response = client.generate(
    model="some-model",
    prompt="Explain recursion."
)

print(response)
```

Run.

Output chạy thành công.
```


**Lời thoại thuyết minh (Voice):**
> > Và đây là điều thú vị.
>
> Đoạn code này hoàn toàn chạy được.
>
> Không có gì sai nếu mục tiêu của bạn chỉ là prototype vài phút.

Text:

```text
IT WORKS.
```

Pause.

Text đổi:

```text
BUT...
```

---

## [01:35.000 -> 02:00.000] S05 — “CHẠY ĐƯỢC” KHÔNG CÓ NGHĨA LÀ “THIẾT KẾ ĐƯỢC”
**Visual Mode:** `SPLIT` | **Take:** `S05_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Nhưng hãy nhìn hệ thống mà chúng ta muốn có sau sáu tháng.

Full future architecture xuất hiện mờ:

```text
Web / CLI
    ↓
API
    ↓
Orchestrator
    ↓
Planner
    ↓
Agents
    ↓
Tools
    ↓
Providers
```

> Đoạn code năm dòng vừa rồi đang làm ba việc cùng một chỗ.

Highlight:

```text
1. Application logic
2. Provider integration
3. Configuration
```

> Và đó là vấn đề đầu tiên.

---

## [02:00.000 -> 02:25.000] S06 — VẤN ĐỀ 1: PROVIDER COUPLING
**Visual Mode:** `FULL_CODE` | **Take:** `S06_T01` | **Thời lượng:** `25.0s`

**Chỉ đạo hình ảnh (Visual):**
```text
Code xấu:

```python
class Agent:
    def run(self, prompt):
        google_client = GoogleSDK(...)
        ...
```
```


**Lời thoại thuyết minh (Voice):**
> > Nếu Agent tự biết Google SDK…
>
> chuyện gì xảy ra khi tuần sau chúng ta muốn dùng model khác?

Diagram:

```text
Agent
 ├── Google SDK
 ├── OpenAI SDK
 ├── Local SDK
 └── OpenRouter SDK
```

> Agent bắt đầu biến thành một nơi chứa tất cả integration logic.

Text lớn:

# WRONG BOUNDARY

---

## [02:25.000 -> 02:50.000] S07 — TẠO NGUYÊN TẮC ĐẦU TIÊN
**Visual Mode:** `SPLIT` | **Take:** `S07_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Tôi muốn đặt một nguyên tắc ngay từ video đầu tiên có code.

Text:

# AGENT SHOULD NOT KNOW THE PROVIDER

Diagram:

```text
Agent
 ↓
???
 ↓
Provider
```

> Agent chỉ nên biết nó cần khả năng gửi message đến một language model.
>
> Còn model đó nằm ở Google, OpenAI, OpenRouter, Ollama hay chạy ngay trên laptop…
>
> Agent không cần biết.

---

## [02:50.000 -> 03:07.000] S08 — CHƯA CODE VỘI: ĐỊNH NGHĨA BOUNDARY
**Visual Mode:** `SPLIT` | **Take:** `S08_T01` | **Thời lượng:** `17.0s`

**Lời thoại thuyết minh (Voice):**
> > Trước khi viết class, hãy định nghĩa dependency tối thiểu mà Agent thật sự cần.

```text
INPUT
list of messages

OUTPUT
text
```

> Chỉ vậy thôi.

---

## [03:07.000 -> 03:32.000] S09 — TẠO REPOSITORY
**Visual Mode:** `SPLIT` | **Take:** `S09_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Đây sẽ không phải repository demo rồi bỏ đi sau video.
>
> Đây là repository mà chúng ta sẽ phát triển xuyên suốt toàn bộ Season 1.

Visual:

```text
v0.1
 ↓
v0.2
 ↓
v0.3
 ↓
...
 ↓
v1.0
```

> Mỗi video sẽ làm architecture lớn thêm một chút.

---

## [03:32.000 -> 03:57.000] S10 — TẠI SAO REPOSITORY NÀY CỐ Ý RẤT NHỎ?
**Visual Mode:** `SPLIT` | **Take:** `S10_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Nếu bạn quen với những project Python có 30 folder ngay khi tạo repository…
>
> project này có thể trông quá đơn giản.

Tree vẫn chỉ vài file.

> Đó là chủ ý.

Text:

# DON'T DESIGN FOR IMAGINARY REQUIREMENTS

> Chúng ta chỉ tạo structure khi requirement xuất hiện.
>
> Video hôm nay chưa có Tools.
>
> Vì vậy chưa cần folder `tools`.
>
> Chưa có Memory.
>
> Không có `memory`.
>
> Chưa Planning.
>
> Không có `planning`.

---

## [03:57.000 -> 04:22.000] S11 — VẤN ĐỀ 2: MESSAGE LÀ GÌ?
**Visual Mode:** `SPLIT` | **Take:** `S11_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Bây giờ quay lại input của LLM.
>
> Hầu hết API model đều nhận một dạng message.
>
> Chúng ta có thể dùng dictionary trực tiếp.

Highlight typo example:

```python
{
    "rol": "user",
    "contnet": "Hello"
}
```

> Nhưng khi dữ liệu này bắt đầu đi qua nhiều lớp của hệ thống…
>
> dictionary tự do sẽ trở thành một nguồn lỗi rất dễ bỏ sót.

---

## [04:22.000 -> 04:45.000] S12 — TẠO `Message`
**Visual Mode:** `SPLIT` | **Take:** `S12_T01` | **Thời lượng:** `23.0s`

**Lời thoại thuyết minh (Voice):**
> > Vì vậy abstraction đầu tiên của Agentic Studio là `Message`.

Diagram:

```text
Message
├── role
└── content
```

> Nó không thông minh.
>
> Nó không gọi model.
>
> Nó chỉ cho hệ thống một representation rõ ràng của conversation data.

---

## [04:45.000 -> 05:10.000] S13 — TẠI SAO `frozen=True`?
**Visual Mode:** `SPLIT` | **Take:** `S13_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Tôi làm Message immutable.
>
> Không phải vì immutable lúc nào cũng tốt.
>
> Mà vì một message đã được tạo ra đại diện cho một fact đã xảy ra trong conversation.
>
> Nếu một component khác vô tình sửa message cũ…
>
> debugging sau này sẽ cực kỳ khó.

Visual:

```text
User message
    ↓
created
    ↓
should remain stable
```

---

## [05:10.000 -> 05:35.000] S14 — NHƯNG ĐỪNG OVERENGINEER MESSAGE
**Visual Mode:** `SPLIT` | **Take:** `S14_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Và đây là một cạm bẫy khác.
>
> Chúng ta hoàn toàn có thể đoán rằng sau này Message sẽ cần tool calls, images, metadata hay multimodal content.
>
> Nhưng hôm nay chưa cần.
>
> Vì vậy chúng ta không thêm.

Text:

# BUILD WHAT THE CURRENT ARCHITECTURE REQUIRES

---

## [05:35.000 -> 05:58.000] S15 — VẤN ĐỀ 3: CONFIGURATION ĐANG NẰM Ở ĐÂU?
**Visual Mode:** `SPLIT` | **Take:** `S15_T01` | **Thời lượng:** `23.0s`

**Lời thoại thuyết minh (Voice):**
> > Chúng ta còn một nhóm dữ liệu khác.
>
> Model nào?
>
> Temperature bao nhiêu?
>
> Agent tên gì?
>
> System instruction là gì?

> Nếu hard-code tất cả bên trong Agent, chúng ta đang trộn configuration với behavior.

---

## [05:58.000 -> 06:12.000] S16 — TẠO `AgentConfig`
**Visual Mode:** `SPLIT` | **Take:** `S16_T01` | **Thời lượng:** `14.0s`

**Lời thoại thuyết minh (Voice):**
> > Vì vậy component thứ hai là `AgentConfig`.

Diagram:

```text
AgentConfig
├── name
├── system_prompt
├── model
└── temperature
```

---

## [06:12.000 -> 06:36.000] S17 — TẠI SAO TÁCH CONFIG RA KHỎI AGENT?
**Visual Mode:** `SPLIT` | **Take:** `S17_T01` | **Thời lượng:** `24.0s`

**Lời thoại thuyết minh (Voice):**
> > Một runtime có thể được cấu hình thành nhiều behavior khác nhau.
>
> Và đây chính là điều chúng ta sẽ tận dụng khi series chuyển sang Multi-Agent.
>
> Nhưng Agent runtime không cần thay đổi chỉ vì tên hay system instruction thay đổi.

---

## [06:36.000 -> 06:59.000] S18 — RETENTION HOOK: CHÚNG TA ĐÃ TẠO HAI CLASS NHƯNG CHƯA CÓ AGENT
**Visual Mode:** `SPLIT` | **Take:** `S18_T01` | **Thời lượng:** `23.0s`

**Lời thoại thuyết minh (Voice):**
> > Đến đây chúng ta đã viết code…
>
> nhưng Agent vẫn chưa tồn tại.

Visual:

```text
Message ✅
AgentConfig ✅
Agent ❌
LLM ❌
```

> Và component tiếp theo là quyết định architecture quan trọng nhất của toàn bộ video.

---

## [06:59.000 -> 07:15.000] S19 — VẤN ĐỀ 4: AGENT NÊN PHỤ THUỘC VÀO CÁI GÌ?
**Visual Mode:** `SPLIT` | **Take:** `S19_T01` | **Thời lượng:** `16.0s`

**Lời thoại thuyết minh (Voice):**
> > Nếu chọn A, Agent của chúng ta là một Google Agent.
>
> Nếu chọn B, Agent chỉ phụ thuộc vào một capability.

Highlight B.

---

## [07:15.000 -> 07:29.000] S20 — ĐỊNH NGHĨA `LLMClient`
**Visual Mode:** `SPLIT` | **Take:** `S20_T01` | **Thời lượng:** `14.0s`

**Lời thoại thuyết minh (Voice):**
> > Đây là `LLMClient`.
>
> Và interface của nó cố ý rất nhỏ.

Highlight:

```text
messages
model
temperature
        ↓
text
```

---

## [07:29.000 -> 07:54.000] S21 — GIẢI THÍCH `Protocol` KHÔNG SA ĐÀ
**Visual Mode:** `SPLIT` | **Take:** `S21_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Nếu bạn chưa dùng `Protocol`, chỉ cần hiểu nó như một contract.
>
> Một object không cần kế thừa class này.
>
> Nó chỉ cần có method phù hợp với contract này.

Diagram:

```text
Anything implementing:

generate(...)

can behave as LLMClient
```

> Chúng ta không cần đi sâu vào type system ở video này.
>
> Điều quan trọng là boundary.

---

## [07:54.000 -> 08:18.000] S22 — ĐIỂM NHẤN KIẾN TRÚC
**Visual Mode:** `SPLIT` | **Take:** `S22_T01` | **Thời lượng:** `24.0s`

**Lời thoại thuyết minh (Voice):**
> > Đây là ranh giới đầu tiên rất quan trọng của repository.
>
> Phía trên là logic của Agentic Studio.
>
> Phía dưới là chi tiết integration.

> Chúng ta có thể đổi infrastructure.
>
> Nhưng core không nên biết việc đó.

---

## [08:18.000 -> 08:34.000] S23 — GIẢI THÍCH BẰNG THÍ NGHIỆM THAY PROVIDER
**Visual Mode:** `SPLIT` | **Take:** `S23_T01` | **Thời lượng:** `16.0s`

**Lời thoại thuyết minh (Voice):**
> > Nếu architecture đúng, việc đổi model provider sẽ chỉ thay implementation ở phía dưới.
>
> Class `Agent` không cần sửa.

Text:

# CORE STAYS STABLE

---

## [08:34.000 -> 08:59.000] S24 — VẤN ĐỀ 5: LÀM SAO TEST?
**Visual Mode:** `SPLIT` | **Take:** `S24_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Nhưng abstraction này đem lại một lợi ích còn quan trọng hơn việc đổi provider.
>
> Testing.

Code xấu:

```python
def test_agent():
    client = RealLLM(api_key=...)
```

## Voice

> Nếu mỗi unit test gọi model thật…
>
> chúng ta sẽ gặp ít nhất năm vấn đề.

Visual từng dòng:

```text
Slow
Network dependent
Costs money
Non-deterministic
Provider may fail
```

---

## [08:59.000 -> 09:20.000] S25 — TẠO FAKE LLM
**Visual Mode:** `SPLIT` | **Take:** `S25_T01` | **Thời lượng:** `21.0s`

**Lời thoại thuyết minh (Voice):**
> > Vì Agent chỉ biết `LLMClient`, chúng ta có thể đưa một fake object vào.

Diagram:

```text
Agent
 ↓
LLMClient
 ↓
FakeLLMClient
```

> Không Internet.
>
> Không API key.
>
> Không token.
>
> Không randomness.

---

## [09:20.000 -> 09:34.000] S26 — CHẠY FAKE TRƯỚC KHI TẠO AGENT
**Visual Mode:** `SPLIT` | **Take:** `S26_T01` | **Thời lượng:** `14.0s`

**Lời thoại thuyết minh (Voice):**
> > Dependency đầu tiên đã hoạt động.
>
> Bây giờ chúng ta mới có đủ pieces để xây Agent.

---

## [09:34.000 -> 09:49.000] S27 — CUỐI CÙNG TẠO `Agent`
**Visual Mode:** `SPLIT` | **Take:** `S27_T01` | **Thời lượng:** `15.0s`

**Lời thoại thuyết minh (Voice):**
> > Agent nhận hai thứ.
>
> Configuration.
>
> Và khả năng gọi language model.

Diagram:

```text
AgentConfig ──► Agent ◄── LLMClient
```

---

## [09:49.000 -> 10:14.000] S28 — DEPENDENCY INJECTION BẰNG NGÔN NGỮ ĐƠN GIẢN
**Visual Mode:** `SPLIT` | **Take:** `S28_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Đôi khi khái niệm này được gọi là Dependency Injection.
>
> Nhưng đừng để thuật ngữ làm nó phức tạp.
>
> Thay vì Agent tự đi tạo dependency…

Code xấu:

```python
self.llm = GoogleClient(...)
```

> chúng ta đưa dependency vào từ bên ngoài.

Code đúng:

```python
Agent(config=config, llm=llm)
```

> Chỉ vậy thôi.

---

## [10:14.000 -> 10:32.000] S29 — AGENT NHẬN USER INPUT
**Visual Mode:** `SPLIT` | **Take:** `S29_T01` | **Thời lượng:** `18.0s`

**Lời thoại thuyết minh (Voice):**
> > V0.1 chỉ cần một entry point.
>
> `run`.
>
> User gửi một task vào.
>
> Agent trả lại một answer.

Diagram:

```text
string
 ↓
Agent.run()
 ↓
string
```

---

## [10:32.000 -> 10:57.000] S30 — AGENT KHÔNG GỬI RAW STRING THẲNG ĐẾN LLM
**Visual Mode:** `SPLIT` | **Take:** `S30_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Agent biến input thành context tối thiểu.

Visual:

```text
System instruction
+
Current user input
=
Current context
```

> Chúng ta chưa có chat history.
>
> Chưa memory.
>
> Chưa RAG.
>
> Chưa tool descriptions.
>
> Những thứ đó sẽ xuất hiện khi Context Engine được build ở tháng hai.

---

## [10:57.000 -> 11:20.000] S31 — GIẢI THÍCH SYSTEM MESSAGE
**Visual Mode:** `SPLIT` | **Take:** `S31_T01` | **Thời lượng:** `23.0s`

**Lời thoại thuyết minh (Voice):**
> > System message mô tả behavior của Agent.
>
> Ví dụ:

```text
You are a concise software engineering assistant.
```

> Nó không phải memory.
>
> Không phải user task.
>
> Nó là instruction nền của Agent trong run này.

---

## [11:20.000 -> 11:38.000] S32 — GIẢI THÍCH USER MESSAGE
**Visual Mode:** `SPLIT` | **Take:** `S32_T01` | **Thời lượng:** `18.0s`

**Lời thoại thuyết minh (Voice):**
> > Message thứ hai là yêu cầu hiện tại.

Example:

```text
Explain recursion with a Python example.
```

> Hai message này tạo thành context nhỏ nhất mà Agent cần.

---

## [11:38.000 -> 11:54.000] S33 — GỌI `LLMClient`
**Visual Mode:** `SPLIT` | **Take:** `S33_T01` | **Thời lượng:** `16.0s`

**Lời thoại thuyết minh (Voice):**
> > Đây là toàn bộ hành vi của Agent v0.1.

Animation:

```text
User Input
   ↓
Agent
   ↓
Build Messages
   ↓
LLMClient
   ↓
Text
   ↓
Return Answer
```

---

## [11:54.000 -> 12:09.000] S34 — CHẠY TOÀN BỘ VỚI FAKE LLM
**Visual Mode:** `SPLIT` | **Take:** `S34_T01` | **Thời lượng:** `15.0s`

**Lời thoại thuyết minh (Voice):**
> > Agent runtime đã hoạt động.
>
> Và lưu ý:
>
> đến thời điểm này chúng ta vẫn chưa cần API key.

---

## [12:09.000 -> 12:23.000] S35 — TEST 1: OUTPUT
**Visual Mode:** `SPLIT` | **Take:** `S35_T01` | **Thời lượng:** `14.0s`

**Lời thoại thuyết minh (Voice):**
> > Test đầu tiên rất đơn giản.
>
> Nếu LLM trả một response…
>
> Agent phải trả response đó.

---

## [12:23.000 -> 12:41.000] S36 — TEST 2: AGENT CÓ GỬI ĐÚNG MESSAGE KHÔNG?
**Visual Mode:** `SPLIT` | **Take:** `S36_T01` | **Thời lượng:** `18.0s`

**Lời thoại thuyết minh (Voice):**
> > Nhưng output đúng chưa đủ.
>
> Chúng ta cũng muốn kiểm tra Agent có build context đúng không.

Check:

```text
Message 1 = system
Message 2 = user
```

---

## [12:41.000 -> 13:03.000] S37 — TEST 3: CONFIG ĐƯỢC FORWARD ĐÚNG
**Visual Mode:** `SPLIT` | **Take:** `S37_T01` | **Thời lượng:** `22.0s`

**Lời thoại thuyết minh (Voice):**
> > Và chúng ta kiểm tra model cùng temperature có được truyền xuống LLM client đúng hay không.

> Đây mới thực sự là unit test của Agent.
>
> Chúng ta đang test behavior của core.
>
> Không test provider.

---

## [13:03.000 -> 13:23.000] S38 — CHẠY TEST
**Visual Mode:** `SPLIT` | **Take:** `S38_T01` | **Thời lượng:** `20.0s`

**Lời thoại thuyết minh (Voice):**
> > Ba test.
>
> Không network.
>
> Không model.
>
> Không API.
>
> Đây là lý do chúng ta tạo abstraction trước khi integration.

Text:

# TEST THE CORE WITHOUT THE WORLD

---

## [13:23.000 -> 13:42.000] S39 — BÂY GIỜ MỚI KẾT NỐI PROVIDER THẬT
**Visual Mode:** `SPLIT` | **Take:** `S39_T01` | **Thời lượng:** `19.0s`

**Lời thoại thuyết minh (Voice):**
> > Core đã chạy.
>
> Bây giờ chúng ta mới cho nó nói chuyện với thế giới thật.

Diagram:

```text
Agent
 ↓
LLMClient
 ↓
Provider Adapter
 ↓
Provider SDK
 ↓
Model
```

---

## [13:42.000 -> 14:02.000] S40 — PROVIDER ADAPTER LÀM GÌ?
**Visual Mode:** `SPLIT` | **Take:** `S40_T01` | **Thời lượng:** `20.0s`

**Lời thoại thuyết minh (Voice):**
> > Adapter này có đúng hai trách nhiệm chính.

Visual:

```text
1. Translate our Message
   → provider format

2. Translate provider response
   → our text
```

> Agent không cần biết hai bước này tồn tại.

---

## [14:02.000 -> 14:22.000] S41 — ĐIỂM NHẤN: PROVIDER OBJECT KHÔNG ĐƯỢC RÒ RỈ VÀO CORE
**Visual Mode:** `SPLIT` | **Take:** `S41_T01` | **Thời lượng:** `20.0s`

**Lời thoại thuyết minh (Voice):**
> > Nếu Agent bắt đầu thao tác trực tiếp với response object của provider…
>
> abstraction của chúng ta đã bị xuyên thủng.

Correct:

```text
Provider-specific world
        ↓
Adapter
──────────── Boundary
        ↓
Our domain
```

---

## [14:22.000 -> 14:47.000] S42 — API KEY
**Visual Mode:** `SPLIT` | **Take:** `S42_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Và vì repository này sẽ public trên GitHub…
>
> có một rule không được phép phá vỡ.

Text cực lớn:

# NEVER COMMIT API KEYS

> API key không được hard-code.
>
> Không nằm trong source.
>
> Không nằm trong README.
>
> Không nằm trong screenshot nếu bạn có thể tránh.

---

## [14:47.000 -> 15:05.000] S43 — PHÂN BIỆT CONFIG VÀ SECRET
**Visual Mode:** `SPLIT` | **Take:** `S43_T01` | **Thời lượng:** `18.0s`

**Lời thoại thuyết minh (Voice):**
> > Một điểm dễ nhầm:
>
> model name và temperature là application configuration.
>
> API key là secret.
>
> Không phải mọi configuration đều nên nằm cùng một nơi.

---

## [15:05.000 -> 15:19.000] S44 — KHỞI TẠO PROVIDER
**Visual Mode:** `SPLIT` | **Take:** `S44_T01` | **Thời lượng:** `14.0s`

**Lời thoại thuyết minh (Voice):**
> > Provider được khởi tạo bên ngoài Agent.
>
> Sau đó adapter được đưa vào Agent thông qua `LLMClient`.

---

## [15:19.000 -> 15:41.000] S45 — COMPOSITION ROOT
**Visual Mode:** `SPLIT` | **Take:** `S45_T01` | **Thời lượng:** `22.0s`

**Lời thoại thuyết minh (Voice):**
> > Đây là nơi các thành phần của application được ghép lại.
>
> Có thể gọi đây là composition root.
>
> Nhưng tên gọi không quan trọng.
>
> Quan trọng là Agent không tự tạo dependency của chính mình.

---

## [15:41.000 -> 15:55.000] S46 — CHẠY REQUEST THẬT ĐẦU TIÊN
**Visual Mode:** `SPLIT` | **Take:** `S46_T01` | **Thời lượng:** `14.0s`

**Lời thoại thuyết minh (Voice):**
> > Và lần đầu tiên…
>
> Agentic Studio đang nói chuyện với một model thật.

Pause để output chạy.

---

## [15:55.000 -> 16:20.000] S47 — KHÔNG ĂN MỪNG QUÁ SỚM
**Visual Mode:** `SPLIT` | **Take:** `S47_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Nhưng đừng để output này đánh lừa chúng ta.
>
> Model trả lời được không chứng minh architecture tốt.
>
> Thứ quan trọng hơn là điều chúng ta vừa xây ở phía sau.

Diagram:

```text
               AgentConfig
                    │
                    ▼
User ──► Message ─► Agent
                    │
                    ▼
                 LLMClient
                    │
                    ▼
             Provider Adapter
                    │
                    ▼
                   LLM
                    │
                    ▼
                 Answer
```

---

## [16:20.000 -> 16:45.000] S48 — TRACE MỘT REQUEST TỪ ĐẦU ĐẾN CUỐI
**Visual Mode:** `SPLIT` | **Take:** `S48_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Hãy trace một request.

### Step 1

```text
User
"Explain recursion"
```

### Step 2

```text
Agent.run()
```

### Step 3

```text
Message(system)
Message(user)
```

### Step 4

```text
LLMClient.generate()
```

### Step 5

```text
Provider Adapter
```

### Step 6

```text
Provider API
```

### Step 7

```text
Model generates response
```

### Step 8

```text
Provider Adapter
```

### Step 9

```text
Agent
```

### Step 10

```text
User receives Answer
```

> Không có magic.
>
> Chỉ là một chuỗi abstraction rất nhỏ.

---

## [16:45.000 -> 17:02.000] S49 — CÂU HỎI GÂY TRANH LUẬN: ĐÂY CÓ PHẢI AGENT KHÔNG?
**Visual Mode:** `SPLIT` | **Take:** `S49_T01` | **Thời lượng:** `17.0s`

**Lời thoại thuyết minh (Voice):**
> > Và bây giờ đến câu hỏi mà tôi nghĩ chúng ta không nên né tránh.
>
> Thứ vừa build có thực sự là một AI Agent không?

---

## [17:02.000 -> 17:27.000] S50 — TRẢ LỜI RÕ RÀNG
**Visual Mode:** `SPLIT` | **Take:** `S50_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Nếu dùng định nghĩa rộng, chúng ta đã có một Agent abstraction nhận task và dùng model để sinh response.
>
> Nhưng nếu dùng định nghĩa chặt hơn mà chúng ta đã đặt ở Video 01…
>
> **chưa.**

Text:

```text
No Tool
No Environment Action
No Observation
No Autonomous Loop
```

> Nó chưa thể hành động lên environment.
>
> Chưa thể quan sát kết quả hành động.
>
> Chưa thể tự lặp lại quá trình quyết định.

---

## [17:27.000 -> 17:52.000] S51 — VẬY TẠI SAO LẠI GỌI NÓ LÀ AGENT?
**Visual Mode:** `SPLIT` | **Take:** `S51_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Vậy tại sao chúng ta vẫn tạo class tên `Agent`?

Diagram:

```text
Agent v0.1
    ↓
Agent v0.2
    ↓
AgentLoop
    ↓
State
    ↓
Memory
    ↓
Planning
```

> Bởi vì đây là runtime core mà các capability đó sẽ gắn vào.
>
> Nó là hạt giống của Agent mà chúng ta sẽ hoàn thiện dần.

Text:

# AGENT CORE ≠ COMPLETE AUTONOMOUS AGENT

---

## [17:52.000 -> 18:11.000] S52 — SO SÁNH CHAT COMPLETION VỚI AGENT CORE
**Visual Mode:** `SPLIT` | **Take:** `S52_T01` | **Thời lượng:** `19.0s`

**Lời thoại thuyết minh (Voice):**
> > Output hôm nay có thể giống một chatbot.
>
> Nhưng architecture đã bắt đầu khác.
>
> Chúng ta đã tạo một runtime có boundary rõ ràng để tiếp tục mở rộng.

---

## [18:11.000 -> 18:30.000] S53 — NHỮNG THỨ CHÚNG TA CỐ Ý KHÔNG BUILD
**Visual Mode:** `SPLIT` | **Take:** `S53_T01` | **Thời lượng:** `19.0s`

**Lời thoại thuyết minh (Voice):**
> > Nếu nhìn roadmap sáu tháng, danh sách thứ chúng ta chưa có dài hơn rất nhiều thứ đã có.

Pause.

> Đó không phải thiếu sót.
>
> Đó là thiết kế.

---

## [18:30.000 -> 18:55.000] S54 — NGUYÊN TẮC LỚN CỦA SERIES
**Visual Mode:** `SPLIT` | **Take:** `S54_T01` | **Thời lượng:** `25.0s`

**Lời thoại thuyết minh (Voice):**
> > Tôi muốn giữ một nguyên tắc xuyên suốt series:
>
> **Complexity phải được kiếm bằng một problem thực sự.**
>
> Không tạo retry trước khi chúng ta có failure.
>
> Không tạo memory trước khi Agent cần nhớ.
>
> Không tạo orchestrator trước khi chúng ta có nhiều task.
>
> Và không tạo multi-agent chỉ vì multi-agent nghe thú vị.

---

## [18:55.000 -> 19:08.000] S55 — MINH HỌA ROADMAP BẰNG PROBLEM-DRIVEN DEVELOPMENT
**Visual Mode:** `SPLIT` | **Take:** `S55_T01` | **Thời lượng:** `13.0s`

**Lời thoại thuyết minh (Voice):**
> > Mỗi capability sẽ xuất hiện vì architecture hiện tại không còn giải quyết được bài toán tiếp theo.

---

## [19:08.000 -> 19:16.000] S56 — REVIEW BỐN ABSTRACTION
**Visual Mode:** `SPLIT` | **Take:** `S56_T01` | **Thời lượng:** `8.0s`
---

## [19:16.000 -> 19:24.000] S57 — KIẾN TRÚC V0.1
**Visual Mode:** `SPLIT` | **Take:** `S57_T01` | **Thời lượng:** `8.0s`
---

## [19:24.000 -> 19:43.000] S58 — REPOSITORY REVIEW
**Visual Mode:** `SPLIT` | **Take:** `S58_T01` | **Thời lượng:** `19.0s`

**Lời thoại thuyết minh (Voice):**
> > Và đây là toàn bộ repository.
>
> Không 40 directories.
>
> Không framework.
>
> Không magic.

> Mọi thứ vẫn đủ nhỏ để chúng ta hiểu từng dòng code.

---

## [19:43.000 -> 19:57.000] S59 — README ARCHITECTURE
**Visual Mode:** `SPLIT` | **Take:** `S59_T01` | **Thời lượng:** `14.0s`

**Lời thoại thuyết minh (Voice):**
> > README cũng phải phản ánh architecture hiện tại.
>
> Không document architecture tương lai như thể nó đã tồn tại.

---

## [19:57.000 -> 20:09.000] S60 — VERSIONING
**Visual Mode:** `SPLIT` | **Take:** `S60_T01` | **Thời lượng:** `12.0s`

**Lời thoại thuyết minh (Voice):**
> > Đây là checkpoint đầu tiên của toàn bộ series.

Visual:

```text
video-02
v0.1
```

---

## [20:09.000 -> 20:23.000] S61 — TẠO CẢM GIÁC “HỆ THỐNG ĐANG LỚN LÊN”
**Visual Mode:** `SPLIT` | **Take:** `S61_T01` | **Thời lượng:** `14.0s`

**Lời thoại thuyết minh (Voice):**
> > Từ đây trở đi, chúng ta sẽ không reset repository.
>
> Mỗi video tiếp tục từ chính architecture này.

---

## [20:23.000 -> 20:33.000] S62 — DEMO GIỚI HẠN CỦA AGENT HIỆN TẠI
**Visual Mode:** `SPLIT` | **Take:** `S62_T01` | **Thời lượng:** `10.0s`

**Lời thoại thuyết minh (Voice):**
> > Và bây giờ hãy cố tình làm Agent thất bại.

---

## [20:33.000 -> 20:50.000] S63 — THỬ MỘT TASK CẦN HÀNH ĐỘNG
**Visual Mode:** `SPLIT` | **Take:** `S63_T01` | **Thời lượng:** `17.0s`

**Lời thoại thuyết minh (Voice):**
> > Đây là limitation quan trọng.
>
> Agent của chúng ta có thể **mô tả hành động**.
>
> Nhưng nó chưa thể **thực hiện hành động**.

---

## [20:50.000 -> 21:10.000] S64 — ĐIỂM NHẤN VIDEO
**Visual Mode:** `SPLIT` | **Take:** `S64_T01` | **Thời lượng:** `20.0s`

**Lời thoại thuyết minh (Voice):**
> > Và đây chính là nơi rất nhiều người mới học Agent bị nhầm.
>
> Language model không tự chui vào Python process của bạn rồi gọi function.
>
> Nó chỉ sinh output.

---

## [21:10.000 -> 21:18.000] S65 — ĐẶT VẤN ĐỀ CHO VIDEO 03
**Visual Mode:** `SPLIT` | **Take:** `S65_T01` | **Thời lượng:** `8.0s`
---

## [21:18.000 -> 21:26.000] S66 — BA CÂU HỎI CHO VIDEO SAU
**Visual Mode:** `SPLIT` | **Take:** `S66_T01` | **Thời lượng:** `8.0s`
---

## [21:26.000 -> 21:34.000] S67 — TEASER CODE
**Visual Mode:** `SPLIT` | **Take:** `S67_T01` | **Thời lượng:** `8.0s`
---

## [21:34.000 -> 21:42.000] S68 — TEASER ARCHITECTURE
**Visual Mode:** `SPLIT` | **Take:** `S68_T01` | **Thời lượng:** `8.0s`
---

## [21:42.000 -> 22:04.000] S69 — KẾT LUẬN BẰNG MỘT CÂU
**Visual Mode:** `SPLIT` | **Take:** `S69_T01` | **Thời lượng:** `22.0s`

**Lời thoại thuyết minh (Voice):**
> > Hôm nay chúng ta đã cho Agent một **bộ não để trả lời**.
>
> Video tiếp theo, chúng ta sẽ bắt đầu cho nó **đôi tay để hành động**.

Pause.

Title:

# NEXT

## HOW TOOL CALLING REALLY WORKS

---

## [22:04.000 -> 22:12.000] S70 — END CARD
**Visual Mode:** `TITLE_CARD` | **Take:** `S70_T01` | **Thời lượng:** `8.0s`
---

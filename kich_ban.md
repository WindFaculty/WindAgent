# VIDEO 02 — TỰ XÂY AI AGENT ĐẦU TIÊN BẰNG PYTHON

## Series

# ZERO TO PRODUCTION AGENTIC SYSTEMS

**24 Weeks. 48 Builds. One Production System.**

---

# 1. VAI TRÒ CỦA VIDEO 02 TRONG TOÀN SERIES

Video 01 đã trả lời:

> **AI Agent thực sự là gì?**

Video 02 phải trả lời câu hỏi tiếp theo:

> **Nếu không dùng framework, thành phần nhỏ nhất mà chúng ta phải tự xây để bắt đầu một Agentic System là gì?**

Đây không phải video:

> “Cách gọi API của một LLM bằng Python.”

Mà là:

> **“Cách thiết kế Agent Core đầu tiên sao cho nó có thể tiếp tục lớn lên trong 6 tháng mà không phải đập đi xây lại.”**

Architecture đầu video:

```text
README.md
```

Architecture cuối video:

```text
User
 ↓
Agent
 ↓
LLMClient
 ↓
Provider
 ↓
LLM
 ↓
Answer
```

Domain abstraction:

```text
Message
AgentConfig
LLMClient
Agent
```

Milestone:

```text
Agentic Studio v0.1
Simple Agent Core
```

---

# 2. CÂU CHUYỆN XUYÊN SUỐT VIDEO

Video phải liên tục đặt ra vấn đề rồi giải quyết vấn đề đó.

```text
Muốn AI trả lời
        ↓
Gọi API trực tiếp
        ↓
Chạy được
        ↓
Nhưng đó chưa phải architecture
        ↓
Code bị dính provider
        ↓
Tách LLMClient
        ↓
Dữ liệu message chưa rõ ràng
        ↓
Tạo Message
        ↓
Configuration đang hard-code
        ↓
Tạo AgentConfig
        ↓
Cần một runtime điều phối
        ↓
Tạo Agent
        ↓
Cần test mà không gọi API
        ↓
FakeLLMClient
        ↓
Cần provider thật
        ↓
Provider Adapter
        ↓
Chạy end-to-end
        ↓
Agent nói được
        ↓
Nhưng chưa hành động được
        ↓
Video 03: Tool Calling
```

---

# 3. NGUYÊN TẮC DỰNG VIDEO

Mỗi phân cảnh nên trả lời một câu hỏi.

Không nói lý thuyết liên tục quá lâu.

Luân phiên:

```text
Question
↓
Diagram
↓
Code
↓
Run
↓
Problem
↓
Architecture decision
↓
Code
↓
Result
```

Người xem phải liên tục cảm thấy:

> “À, hóa ra chúng ta tạo component này vì vấn đề vừa xuất hiện.”

Không được có cảm giác:

> “Tác giả đang tạo hàng loạt class vì thích clean architecture.”

---

# PHÂN CẢNH 01 — COLD OPEN: CHO XEM THÀNH QUẢ TRƯỚC

## Visual

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

## Voice

> Đây là AI Agent đầu tiên mà chúng ta sẽ build trong series này.
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

# PHÂN CẢNH 02 — NỐI TRỰC TIẾP VỚI VIDEO 01

## Visual

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

## Voice

> Ở video trước, chúng ta đã nhìn Agent ở cấp độ kiến trúc.
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

# PHÂN CẢNH 03 — ĐẶT CÂU HỎI QUAN TRỌNG NHẤT

Camera hoặc slide tối giản.

## Voice

> Bây giờ có một câu hỏi.
>
> Nếu mục tiêu hôm nay chỉ là:

```text
User → LLM → Answer
```

> tại sao chúng ta không viết đúng năm dòng Python gọi API rồi kết thúc video?

---

# PHÂN CẢNH 04 — VIẾT PHIÊN BẢN “NGÂY THƠ” NHẤT

## Visual

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

## Voice

> Và đây là điều thú vị.
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

# PHÂN CẢNH 05 — “CHẠY ĐƯỢC” KHÔNG CÓ NGHĨA LÀ “THIẾT KẾ ĐƯỢC”

## Voice

> Nhưng hãy nhìn hệ thống mà chúng ta muốn có sau sáu tháng.

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

# PHÂN CẢNH 06 — VẤN ĐỀ 1: PROVIDER COUPLING

## Visual

Code xấu:

```python
class Agent:
    def run(self, prompt):
        google_client = GoogleSDK(...)
        ...
```

## Voice

> Nếu Agent tự biết Google SDK…
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

# PHÂN CẢNH 07 — TẠO NGUYÊN TẮC ĐẦU TIÊN

## Voice

> Tôi muốn đặt một nguyên tắc ngay từ video đầu tiên có code.

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

# PHÂN CẢNH 08 — CHƯA CODE VỘI: ĐỊNH NGHĨA BOUNDARY

Whiteboard.

```text
Agent wants:

messages
   ↓
LLM
   ↓
text
```

## Voice

> Trước khi viết class, hãy định nghĩa dependency tối thiểu mà Agent thật sự cần.

```text
INPUT
list of messages

OUTPUT
text
```

> Chỉ vậy thôi.

---

# PHÂN CẢNH 09 — TẠO REPOSITORY

Terminal.

```bash
mkdir agentic-studio
cd agentic-studio
git init
```

Visual tree:

```text
agentic-studio/
├── src/
├── tests/
├── README.md
├── pyproject.toml
├── .gitignore
└── .env.example
```

## Voice

> Đây sẽ không phải repository demo rồi bỏ đi sau video.
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

# PHÂN CẢNH 10 — TẠI SAO REPOSITORY NÀY CỐ Ý RẤT NHỎ?

## Voice

> Nếu bạn quen với những project Python có 30 folder ngay khi tạo repository…
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

# PHÂN CẢNH 11 — VẤN ĐỀ 2: MESSAGE LÀ GÌ?

Visual:

```python
[
    {
        "role": "user",
        "content": "Hello"
    }
]
```

## Voice

> Bây giờ quay lại input của LLM.
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

# PHÂN CẢNH 12 — TẠO `Message`

Code:

```python
from dataclasses import dataclass
from typing import Literal

Role = Literal["system", "user", "assistant"]

@dataclass(frozen=True)
class Message:
    role: Role
    content: str
```

## Voice

> Vì vậy abstraction đầu tiên của Agentic Studio là `Message`.

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

# PHÂN CẢNH 13 — TẠI SAO `frozen=True`?

Zoom:

```python
@dataclass(frozen=True)
```

## Voice

> Tôi làm Message immutable.
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

# PHÂN CẢNH 14 — NHƯNG ĐỪNG OVERENGINEER MESSAGE

Visual tương lai:

```text
Message
├── role
├── content
├── tool_calls
├── attachments
├── metadata
├── token_count
├── provider_payload
└── ...
```

X đỏ.

## Voice

> Và đây là một cạm bẫy khác.
>
> Chúng ta hoàn toàn có thể đoán rằng sau này Message sẽ cần tool calls, images, metadata hay multimodal content.
>
> Nhưng hôm nay chưa cần.
>
> Vì vậy chúng ta không thêm.

Text:

# BUILD WHAT THE CURRENT ARCHITECTURE REQUIRES

---

# PHÂN CẢNH 15 — VẤN ĐỀ 3: CONFIGURATION ĐANG NẰM Ở ĐÂU?

Code:

```python
model = "model-x"
temperature = 0.2
system_prompt = "You are..."
```

## Voice

> Chúng ta còn một nhóm dữ liệu khác.
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

# PHÂN CẢNH 16 — TẠO `AgentConfig`

Code:

```python
@dataclass(frozen=True)
class AgentConfig:
    name: str
    system_prompt: str
    model: str
    temperature: float = 0.2
```

## Voice

> Vì vậy component thứ hai là `AgentConfig`.

Diagram:

```text
AgentConfig
├── name
├── system_prompt
├── model
└── temperature
```

---

# PHÂN CẢNH 17 — TẠI SAO TÁCH CONFIG RA KHỎI AGENT?

Visual:

```text
Same Agent runtime
        │
        ├── Coding config
        ├── Research config
        └── Reviewer config
```

## Voice

> Một runtime có thể được cấu hình thành nhiều behavior khác nhau.
>
> Và đây chính là điều chúng ta sẽ tận dụng khi series chuyển sang Multi-Agent.
>
> Nhưng Agent runtime không cần thay đổi chỉ vì tên hay system instruction thay đổi.

---

# PHÂN CẢNH 18 — RETENTION HOOK: CHÚNG TA ĐÃ TẠO HAI CLASS NHƯNG CHƯA CÓ AGENT

Camera.

## Voice

> Đến đây chúng ta đã viết code…
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

# PHÂN CẢNH 19 — VẤN ĐỀ 4: AGENT NÊN PHỤ THUỘC VÀO CÁI GÌ?

Whiteboard.

Option A:

```text
Agent
 ↓
GoogleGenerativeAI
```

Option B:

```text
Agent
 ↓
LLMClient
 ↓
Google
```

## Voice

> Nếu chọn A, Agent của chúng ta là một Google Agent.
>
> Nếu chọn B, Agent chỉ phụ thuộc vào một capability.

Highlight B.

---

# PHÂN CẢNH 20 — ĐỊNH NGHĨA `LLMClient`

Code:

```python
from typing import Protocol

class LLMClient(Protocol):
    def generate(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float,
    ) -> str:
        ...
```

## Voice

> Đây là `LLMClient`.
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

# PHÂN CẢNH 21 — GIẢI THÍCH `Protocol` KHÔNG SA ĐÀ

## Voice

> Nếu bạn chưa dùng `Protocol`, chỉ cần hiểu nó như một contract.
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

# PHÂN CẢNH 22 — ĐIỂM NHẤN KIẾN TRÚC

Full screen.

```text
DOMAIN
──────────────────
Agent
Message
AgentConfig
LLMClient

        │

INFRASTRUCTURE
──────────────────
Google SDK
OpenAI SDK
HTTP
API Keys
Provider Response
```

## Voice

> Đây là ranh giới đầu tiên rất quan trọng của repository.
>
> Phía trên là logic của Agentic Studio.
>
> Phía dưới là chi tiết integration.

> Chúng ta có thể đổi infrastructure.
>
> Nhưng core không nên biết việc đó.

---

# PHÂN CẢNH 23 — GIẢI THÍCH BẰNG THÍ NGHIỆM THAY PROVIDER

Visual animation.

```text
Agent
 ↓
LLMClient
 ↓
Provider A
```

Switch:

```text
Agent
 ↓
LLMClient
 ↓
Provider B
```

Agent không đổi.

## Voice

> Nếu architecture đúng, việc đổi model provider sẽ chỉ thay implementation ở phía dưới.
>
> Class `Agent` không cần sửa.

Text:

# CORE STAYS STABLE

---

# PHÂN CẢNH 24 — VẤN ĐỀ 5: LÀM SAO TEST?

Camera.

## Voice

> Nhưng abstraction này đem lại một lợi ích còn quan trọng hơn việc đổi provider.
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

# PHÂN CẢNH 25 — TẠO FAKE LLM

Code:

```python
class FakeLLMClient:
    def generate(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float,
    ) -> str:
        return "Hello from Fake LLM"
```

## Voice

> Vì Agent chỉ biết `LLMClient`, chúng ta có thể đưa một fake object vào.

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

# PHÂN CẢNH 26 — CHẠY FAKE TRƯỚC KHI TẠO AGENT

Quick test:

```python
fake = FakeLLMClient()

print(
    fake.generate(
        [],
        model="test",
        temperature=0.0,
    )
)
```

Output:

```text
Hello from Fake LLM
```

## Voice

> Dependency đầu tiên đã hoạt động.
>
> Bây giờ chúng ta mới có đủ pieces để xây Agent.

---

# PHÂN CẢNH 27 — CUỐI CÙNG TẠO `Agent`

Code:

```python
class Agent:
    def __init__(
        self,
        config: AgentConfig,
        llm: LLMClient,
    ) -> None:
        self.config = config
        self.llm = llm
```

## Voice

> Agent nhận hai thứ.
>
> Configuration.
>
> Và khả năng gọi language model.

Diagram:

```text
AgentConfig ──► Agent ◄── LLMClient
```

---

# PHÂN CẢNH 28 — DEPENDENCY INJECTION BẰNG NGÔN NGỮ ĐƠN GIẢN

## Voice

> Đôi khi khái niệm này được gọi là Dependency Injection.
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

# PHÂN CẢNH 29 — AGENT NHẬN USER INPUT

Code:

```python
def run(self, user_input: str) -> str:
```

## Voice

> V0.1 chỉ cần một entry point.
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

# PHÂN CẢNH 30 — AGENT KHÔNG GỬI RAW STRING THẲNG ĐẾN LLM

Code:

```python
messages = [
    Message(
        role="system",
        content=self.config.system_prompt,
    ),
    Message(
        role="user",
        content=user_input,
    ),
]
```

## Voice

> Agent biến input thành context tối thiểu.

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

# PHÂN CẢNH 31 — GIẢI THÍCH SYSTEM MESSAGE

Highlight:

```python
role="system"
```

## Voice

> System message mô tả behavior của Agent.
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

# PHÂN CẢNH 32 — GIẢI THÍCH USER MESSAGE

Highlight:

```python
role="user"
```

## Voice

> Message thứ hai là yêu cầu hiện tại.

Example:

```text
Explain recursion with a Python example.
```

> Hai message này tạo thành context nhỏ nhất mà Agent cần.

---

# PHÂN CẢNH 33 — GỌI `LLMClient`

Code:

```python
return self.llm.generate(
    messages,
    model=self.config.model,
    temperature=self.config.temperature,
)
```

## Voice

> Đây là toàn bộ hành vi của Agent v0.1.

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

# PHÂN CẢNH 34 — CHẠY TOÀN BỘ VỚI FAKE LLM

Code:

```python
config = AgentConfig(
    name="simple-agent",
    system_prompt="You are helpful.",
    model="fake-model",
)

agent = Agent(
    config=config,
    llm=FakeLLMClient(),
)

print(agent.run("Hello"))
```

Output:

```text
Hello from Fake LLM
```

## Voice

> Agent runtime đã hoạt động.
>
> Và lưu ý:
>
> đến thời điểm này chúng ta vẫn chưa cần API key.

---

# PHÂN CẢNH 35 — TEST 1: OUTPUT

Test:

```python
def test_agent_returns_llm_response():
    llm = FakeLLMClient()

    agent = Agent(
        config=AgentConfig(
            name="test-agent",
            system_prompt="You are a test agent.",
            model="test-model",
        ),
        llm=llm,
    )

    result = agent.run("hello")

    assert result == "Hello from Fake LLM"
```

## Voice

> Test đầu tiên rất đơn giản.
>
> Nếu LLM trả một response…
>
> Agent phải trả response đó.

---

# PHÂN CẢNH 36 — TEST 2: AGENT CÓ GỬI ĐÚNG MESSAGE KHÔNG?

Fake cải tiến:

```python
class FakeLLMClient:
    def __init__(self):
        self.received_messages = []

    def generate(
        self,
        messages,
        *,
        model,
        temperature,
    ):
        self.received_messages = messages
        return "fake-response"
```

Test:

```python
def test_agent_builds_expected_messages():
    ...
```

## Voice

> Nhưng output đúng chưa đủ.
>
> Chúng ta cũng muốn kiểm tra Agent có build context đúng không.

Check:

```text
Message 1 = system
Message 2 = user
```

---

# PHÂN CẢNH 37 — TEST 3: CONFIG ĐƯỢC FORWARD ĐÚNG

Fake lưu:

```python
self.model = model
self.temperature = temperature
```

## Voice

> Và chúng ta kiểm tra model cùng temperature có được truyền xuống LLM client đúng hay không.

> Đây mới thực sự là unit test của Agent.
>
> Chúng ta đang test behavior của core.
>
> Không test provider.

---

# PHÂN CẢNH 38 — CHẠY TEST

Terminal:

```bash
pytest -q
```

Output:

```text
3 passed
```

## Voice

> Ba test.
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

# PHÂN CẢNH 39 — BÂY GIỜ MỚI KẾT NỐI PROVIDER THẬT

Transition:

```text
Core ✅

Now:

Infrastructure
```

## Voice

> Core đã chạy.
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

# PHÂN CẢNH 40 — PROVIDER ADAPTER LÀM GÌ?

Pseudo-code:

```python
class ProviderLLMClient:
    def __init__(self, client):
        self.client = client

    def generate(
        self,
        messages,
        *,
        model,
        temperature,
    ) -> str:

        provider_messages = [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
        ]

        response = self.client.generate(...)

        return extract_text(response)
```

## Voice

> Adapter này có đúng hai trách nhiệm chính.

Visual:

```text
1. Translate our Message
   → provider format

2. Translate provider response
   → our text
```

> Agent không cần biết hai bước này tồn tại.

---

# PHÂN CẢNH 41 — ĐIỂM NHẤN: PROVIDER OBJECT KHÔNG ĐƯỢC RÒ RỈ VÀO CORE

Visual xấu:

```text
Agent
 ↓
ProviderResponse
 ↓
ProviderCandidate
 ↓
ProviderPart
```

X đỏ.

## Voice

> Nếu Agent bắt đầu thao tác trực tiếp với response object của provider…
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

# PHÂN CẢNH 42 — API KEY

`.env.example`:

```env
LLM_API_KEY=
LLM_MODEL=
```

`.gitignore`:

```text
.env
.venv/
__pycache__/
```

## Voice

> Và vì repository này sẽ public trên GitHub…
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

# PHÂN CẢNH 43 — PHÂN BIỆT CONFIG VÀ SECRET

Visual:

```text
AgentConfig
├── model
├── temperature
└── system_prompt

Environment
└── API_KEY
```

## Voice

> Một điểm dễ nhầm:
>
> model name và temperature là application configuration.
>
> API key là secret.
>
> Không phải mọi configuration đều nên nằm cùng một nơi.

---

# PHÂN CẢNH 44 — KHỞI TẠO PROVIDER

Pseudo-code:

```python
api_key = load_from_environment()

provider_client = ProviderSDK(
    api_key=api_key
)

llm = ProviderLLMClient(
    client=provider_client
)
```

## Voice

> Provider được khởi tạo bên ngoài Agent.
>
> Sau đó adapter được đưa vào Agent thông qua `LLMClient`.

---

# PHÂN CẢNH 45 — COMPOSITION ROOT

Visual:

```python
config = AgentConfig(...)

llm = ProviderLLMClient(...)

agent = Agent(
    config=config,
    llm=llm,
)
```

## Voice

> Đây là nơi các thành phần của application được ghép lại.
>
> Có thể gọi đây là composition root.
>
> Nhưng tên gọi không quan trọng.
>
> Quan trọng là Agent không tự tạo dependency của chính mình.

---

# PHÂN CẢNH 46 — CHẠY REQUEST THẬT ĐẦU TIÊN

Terminal:

```text
You:
Giải thích recursion bằng một ví dụ Python đơn giản.
```

Loading.

Answer xuất hiện.

## Voice

> Và lần đầu tiên…
>
> Agentic Studio đang nói chuyện với một model thật.

Pause để output chạy.

---

# PHÂN CẢNH 47 — KHÔNG ĂN MỪNG QUÁ SỚM

Camera.

## Voice

> Nhưng đừng để output này đánh lừa chúng ta.
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

# PHÂN CẢNH 48 — TRACE MỘT REQUEST TỪ ĐẦU ĐẾN CUỐI

Animation chậm.

## Voice

> Hãy trace một request.

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

# PHÂN CẢNH 49 — CÂU HỎI GÂY TRANH LUẬN: ĐÂY CÓ PHẢI AGENT KHÔNG?

Screen đen.

Text:

# IS THIS REALLY AN AGENT?

## Voice

> Và bây giờ đến câu hỏi mà tôi nghĩ chúng ta không nên né tránh.
>
> Thứ vừa build có thực sự là một AI Agent không?

---

# PHÂN CẢNH 50 — TRẢ LỜI RÕ RÀNG

Diagram Video 01:

```text
Observe
 ↓
Decide
 ↓
Act
 ↓
Observe
```

## Voice

> Nếu dùng định nghĩa rộng, chúng ta đã có một Agent abstraction nhận task và dùng model để sinh response.
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

# PHÂN CẢNH 51 — VẬY TẠI SAO LẠI GỌI NÓ LÀ AGENT?

## Voice

> Vậy tại sao chúng ta vẫn tạo class tên `Agent`?

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

# PHÂN CẢNH 52 — SO SÁNH CHAT COMPLETION VỚI AGENT CORE

Split screen.

### Bên trái

```python
client.generate(prompt)
```

### Bên phải

```text
User
 ↓
Agent
 ↓
LLM abstraction
 ↓
Provider
```

## Voice

> Output hôm nay có thể giống một chatbot.
>
> Nhưng architecture đã bắt đầu khác.
>
> Chúng ta đã tạo một runtime có boundary rõ ràng để tiếp tục mở rộng.

---

# PHÂN CẢNH 53 — NHỮNG THỨ CHÚNG TA CỐ Ý KHÔNG BUILD

Full screen từng item.

```text
Tool Calling        ❌
Tool Registry       ❌
Agent Loop          ❌
State               ❌
Session             ❌
Memory              ❌
RAG                 ❌
Planning            ❌
Multi-Agent         ❌
Orchestration       ❌
Retries             ❌
Tracing             ❌
Security            ❌
```

## Voice

> Nếu nhìn roadmap sáu tháng, danh sách thứ chúng ta chưa có dài hơn rất nhiều thứ đã có.

Pause.

> Đó không phải thiếu sót.
>
> Đó là thiết kế.

---

# PHÂN CẢNH 54 — NGUYÊN TẮC LỚN CỦA SERIES

Text full screen:

# COMPLEXITY MUST BE EARNED

## Voice

> Tôi muốn giữ một nguyên tắc xuyên suốt series:
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

# PHÂN CẢNH 55 — MINH HỌA ROADMAP BẰNG PROBLEM-DRIVEN DEVELOPMENT

Animation:

```text
Agent cannot act
        ↓
Tools

Agent needs multiple actions
        ↓
Agent Loop

Agent needs execution history
        ↓
State

Agent needs remembered knowledge
        ↓
Memory

Task too complex
        ↓
Planning

Many independent roles
        ↓
Multi-Agent

Many tasks
        ↓
Orchestration
```

## Voice

> Mỗi capability sẽ xuất hiện vì architecture hiện tại không còn giải quyết được bài toán tiếp theo.

---

# PHÂN CẢNH 56 — REVIEW BỐN ABSTRACTION

Cards xuất hiện.

## 1. Message

```text
Conversation data
```

> Representation cho message.

## 2. AgentConfig

```text
Agent configuration
```

> Tách configuration khỏi behavior.

## 3. LLMClient

```text
Model capability boundary
```

> Tách Agent khỏi provider.

## 4. Agent

```text
Runtime coordination
```

> Điều phối context tối thiểu và LLM call.

---

# PHÂN CẢNH 57 — KIẾN TRÚC V0.1

Full master diagram:

```text
                    ┌─────────────────┐
                    │   AgentConfig   │
                    │                 │
                    │ name            │
                    │ system_prompt   │
                    │ model           │
                    │ temperature     │
                    └────────┬────────┘
                             │
                             ▼
┌──────────┐          ┌──────────────┐
│   User   │─────────►│    Agent     │
└──────────┘          └──────┬───────┘
                             │
                   list[Message]
                             │
                             ▼
                    ┌────────────────┐
                    │   LLMClient    │
                    └────────┬───────┘
                             │
                             ▼
                    ┌────────────────┐
                    │Provider Adapter│
                    └────────┬───────┘
                             │
                             ▼
                    ┌────────────────┐
                    │      LLM       │
                    └────────┬───────┘
                             │
                             ▼
                          Answer
```

---

# PHÂN CẢNH 58 — REPOSITORY REVIEW

Tree:

```text
agentic-studio/
│
├── src/
│   ├── __init__.py
│   ├── agent.py
│   └── main.py
│
├── tests/
│   └── test_agent.py
│
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## Voice

> Và đây là toàn bộ repository.
>
> Không 40 directories.
>
> Không framework.
>
> Không magic.

> Mọi thứ vẫn đủ nhỏ để chúng ta hiểu từng dòng code.

---

# PHÂN CẢNH 59 — README ARCHITECTURE

Show README:

```markdown
# Agentic Studio

Current version: v0.1

Architecture:

User
 ↓
Agent
 ↓
LLM
 ↓
Answer
```

## Voice

> README cũng phải phản ánh architecture hiện tại.
>
> Không document architecture tương lai như thể nó đã tồn tại.

---

# PHÂN CẢNH 60 — VERSIONING

Terminal:

```bash
git add .
git commit -m "feat: build simple agent core"
git tag video-02
git tag v0.1
```

## Voice

> Đây là checkpoint đầu tiên của toàn bộ series.

Visual:

```text
video-02
v0.1
```

---

# PHÂN CẢNH 61 — TẠO CẢM GIÁC “HỆ THỐNG ĐANG LỚN LÊN”

Timeline:

```text
VIDEO 01
Concept

        ↓

VIDEO 02
Agent Core

        ↓

VIDEO 03
Tool Calling

        ↓

VIDEO 04
Tool-enabled Agent

        ↓

VIDEO 05
Agent Loop

        ↓

VIDEO 06
Autonomous Loop
```

## Voice

> Từ đây trở đi, chúng ta sẽ không reset repository.
>
> Mỗi video tiếp tục từ chính architecture này.

---

# PHÂN CẢNH 62 — DEMO GIỚI HẠN CỦA AGENT HIỆN TẠI

Terminal:

```text
You:
Trong thư mục project hiện tại có bao nhiêu file Python?
```

Agent trả lời kiểu:

```text
I don't have access to your filesystem...
```

## Voice

> Và bây giờ hãy cố tình làm Agent thất bại.

---

# PHÂN CẢNH 63 — THỬ MỘT TASK CẦN HÀNH ĐỘNG

User:

```text
Tạo file hello.txt chứa dòng "Hello Agentic Studio".
```

Agent:

```text
I can't directly create files...
```

## Voice

> Đây là limitation quan trọng.
>
> Agent của chúng ta có thể **mô tả hành động**.
>
> Nhưng nó chưa thể **thực hiện hành động**.

---

# PHÂN CẢNH 64 — ĐIỂM NHẤN VIDEO

Screen tối.

Text xuất hiện từng từ.

```text
LLM
CAN GENERATE
A DECISION.
```

Sau đó:

```text
BUT IT DOES NOT
EXECUTE YOUR PYTHON FUNCTION.
```

## Voice

> Và đây chính là nơi rất nhiều người mới học Agent bị nhầm.
>
> Language model không tự chui vào Python process của bạn rồi gọi function.
>
> Nó chỉ sinh output.

---

# PHÂN CẢNH 65 — ĐẶT VẤN ĐỀ CHO VIDEO 03

Diagram:

```text
User
 ↓
Agent
 ↓
LLM
 ↓
"calculator"
{
  "a": 73,
  "b": 19
}
```

Pause.

> Nếu LLM chỉ sinh tên Tool và arguments…
>
> ai thực sự gọi function?

Diagram mở rộng:

```text
LLM
 ↓
tool_name + arguments
 ↓
Application
 ↓
Tool
 ↓
Result
```

---

# PHÂN CẢNH 66 — BA CÂU HỎI CHO VIDEO SAU

Text từng dòng.

> LLM biết Tool nào đang tồn tại bằng cách nào?

> Làm sao model biết arguments phải có cấu trúc gì?

> Và điều gì xảy ra nếu model yêu cầu một Tool không tồn tại?

---

# PHÂN CẢNH 67 — TEASER CODE

Flash code rất nhanh:

```python
class Tool:
```

```python
class ToolRegistry:
```

```python
tool.execute(arguments)
```

```json
{
  "name": "calculator",
  "arguments": {
    "a": 73,
    "b": 19
  }
}
```

Không giải thích.

---

# PHÂN CẢNH 68 — TEASER ARCHITECTURE

Architecture hiện tại:

```text
TODAY

User
 ↓
Agent
 ↓
LLM
 ↓
Answer
```

Sau đó bên phải xuất hiện:

```text
NEXT

User
 ↓
Agent
 ↓
LLM
 ↓
Tool Request
 ↓
Application
 ↓
Tool
 ↓
Result
```

---

# PHÂN CẢNH 69 — KẾT LUẬN BẰNG MỘT CÂU

Camera.

## Voice

> Hôm nay chúng ta đã cho Agent một **bộ não để trả lời**.
>
> Video tiếp theo, chúng ta sẽ bắt đầu cho nó **đôi tay để hành động**.

Pause.

Title:

# NEXT

## HOW TOOL CALLING REALLY WORKS

---

# PHÂN CẢNH 70 — END CARD

```text
Agentic Studio

v0.1
Simple Agent Core

User → Agent → LLM → Answer
```

GitHub repository.

Video tiếp theo.

Fade out.

---

# 4. CODE FLOW HOÀN CHỈNH CỦA VIDEO

Toàn bộ code nên được giới thiệu theo đúng thứ tự này:

```text
1. Repository
      ↓
2. Message
      ↓
3. AgentConfig
      ↓
4. LLMClient
      ↓
5. FakeLLMClient
      ↓
6. Agent
      ↓
7. Unit Tests
      ↓
8. Provider Adapter
      ↓
9. Environment / Secrets
      ↓
10. Composition Root
      ↓
11. Real LLM Run
      ↓
12. Architecture Review
```

Không nên:

```text
Provider API
↓
Agent
↓
Refactor
↓
Tests
↓
Message
↓
Config
```

Thứ tự trên khiến câu chuyện bị rời.

---

# 5. CODE V0.1 THAM KHẢO

## `Message`

```python
from dataclasses import dataclass
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
```

---

## `AgentConfig`

```python
@dataclass(frozen=True)
class AgentConfig:
    name: str
    system_prompt: str
    model: str
    temperature: float = 0.2
```

---

## `LLMClient`

```python
from typing import Protocol


class LLMClient(Protocol):
    def generate(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float,
    ) -> str:
        ...
```

---

## `Agent`

```python
class Agent:
    def __init__(
        self,
        config: AgentConfig,
        llm: LLMClient,
    ) -> None:
        self.config = config
        self.llm = llm

    def run(self, user_input: str) -> str:
        messages = [
            Message(
                role="system",
                content=self.config.system_prompt,
            ),
            Message(
                role="user",
                content=user_input,
            ),
        ]

        return self.llm.generate(
            messages,
            model=self.config.model,
            temperature=self.config.temperature,
        )
```

---

## Fake

```python
class FakeLLMClient:
    def __init__(self) -> None:
        self.received_messages: list[Message] = []
        self.model: str | None = None
        self.temperature: float | None = None

    def generate(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float,
    ) -> str:
        self.received_messages = messages
        self.model = model
        self.temperature = temperature

        return "fake-response"
```

---

# 6. NHỮNG KHÁI NIỆM PHẢI LÀM RÕ TRONG VIDEO

Video chỉ đạt yêu cầu khi người xem hiểu được tất cả các câu hỏi này.

### AI Agent v0.1 là gì?

Là Agent Core tối giản:

```text
Input
 ↓
Context
 ↓
LLM
 ↓
Output
```

Chưa phải autonomous agent hoàn chỉnh.

---

### Tại sao không gọi thẳng provider SDK?

Vì:

```text
Agent
↓
Provider SDK
```

tạo coupling.

Ta muốn:

```text
Agent
↓
LLMClient
↓
Provider Adapter
```

---

### `Message` giải quyết gì?

Representation rõ ràng cho conversation data.

---

### `AgentConfig` giải quyết gì?

Tách:

```text
configuration
```

khỏi:

```text
runtime behavior
```

---

### `LLMClient` giải quyết gì?

Tách domain khỏi infrastructure.

---

### `FakeLLMClient` giải quyết gì?

Cho phép:

```text
fast
cheap
deterministic
offline
unit tests
```

---

### Provider Adapter giải quyết gì?

Chuyển đổi giữa:

```text
our domain
```

và:

```text
provider-specific API
```

---

### Tại sao chưa có Memory?

Chưa có problem cần Memory.

---

### Tại sao chưa có Tools?

Tools là chủ đề tiếp theo.

---

### Tại sao chưa có Agent Loop?

Chưa có Tool Observation để loop.

---

### Agent có thể đổi provider không?

Có, về mặt architecture:

```text
Agent stays unchanged.
```

---

### Agent hiện tại có thực sự autonomous không?

Không.

Nó chưa có:

```text
Action
Observation
Loop
```

---

# 7. CÁC “WOW MOMENT” CẦN GIỮ

Video dài không sao, nhưng phải có các điểm nhấn mạnh.

## Wow Moment 1

```text
Calling an LLM
≠
Building an Agent Architecture
```

---

## Wow Moment 2

```text
Agent should not know
which provider it uses.
```

---

## Wow Moment 3

```text
Unit Test
should not need
an AI model.
```

---

## Wow Moment 4

```text
Agent Core
≠
Autonomous Agent
```

---

## Wow Moment 5

```text
LLM chooses an action.
Your application executes it.
```

Đây là bridge sang Video 03.

---

# 8. CÁC CÂU NÊN NHẤN GIỌNG

> **“Code chạy được chưa có nghĩa architecture của chúng ta đúng.”**

> **“Agent không nên biết model đang nằm ở provider nào.”**

> **“Chúng ta test Agent mà không cần gọi bất kỳ AI model nào.”**

> **“Complexity phải xuất hiện vì có một problem cần giải quyết.”**

> **“Agent hôm nay biết nói, nhưng chưa biết hành động.”**

> **“LLM không trực tiếp chạy function Python của bạn.”**

---

# 9. NHỊP DỰNG ĐỀ XUẤT

Không cần khóa vào timestamp.

Dùng pattern:

```text
30–60s Concept
↓
Code
↓
Run
↓
Problem
↓
Diagram
↓
Code
↓
Run
```

Không để quá lâu chỉ có talking head.

Sau mỗi 2–3 phân cảnh code nên chuyển sang:

```text
diagram
terminal
zoom
animation
question card
```

---

# 10. B-ROLL CẦN CHUẨN BỊ

1. Repository trống.
2. Git init.
3. Architecture Video 01.
4. Future production architecture mờ.
5. Gọi API trực tiếp.
6. Provider coupling diagram.
7. Message animation.
8. AgentConfig animation.
9. LLMClient boundary.
10. Fake vs Real provider.
11. Unit tests.
12. Provider adapter.
13. Environment variable.
14. Real API run.
15. Request trace animation.
16. Current architecture.
17. Future architecture.
18. Agent failure với filesystem.
19. Tool calling teaser.
20. Version timeline.

---

# 11. DIAGRAM MASTER VIDEO 02

## Stage A

```text
User
 ↓
LLM
 ↓
Answer
```

---

## Stage B

```text
User
 ↓
Agent
 ↓
LLM
 ↓
Answer
```

---

## Stage C

```text
              AgentConfig
                   │
                   ▼
User ────────►   Agent
                   │
                   ▼
              LLMClient
                   │
                   ▼
                Answer
```

---

## Stage D

```text
              AgentConfig
                   │
                   ▼
User ────────►   Agent
                   │
             list[Message]
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

Đây là master diagram cuối cùng.

---

# 12. DEFINITION OF DONE

Không kết thúc recording nếu chưa thể chứng minh:

```text
[PASS] Repository được tạo từ đầu

[PASS] Có Message abstraction

[PASS] Message có role + content

[PASS] Có AgentConfig

[PASS] Config không hard-code trong Agent

[PASS] Có LLMClient abstraction

[PASS] Agent không import provider SDK

[PASS] Có FakeLLMClient

[PASS] Agent được test offline

[PASS] Test không gọi real API

[PASS] Provider adapter nằm ngoài Agent core

[PASS] Provider-specific response không leak vào Agent

[PASS] API key nằm ngoài source code

[PASS] .env không được commit

[PASS] Agent nhận user input

[PASS] Agent tạo system + user Message

[PASS] Agent gọi LLMClient

[PASS] Agent trả answer

[PASS] Real provider chạy end-to-end

[PASS] Người xem hiểu đây chưa phải autonomous Agent hoàn chỉnh

[PASS] Chưa thêm Tool Calling

[PASS] Chưa thêm Agent Loop

[PASS] Repository được tag video-02

[PASS] Repository được tag v0.1
```

---

# 13. TITLE ĐỀ XUẤT

## Ưu tiên 1

# Tôi Tự Build AI Agent Bằng Python — Không LangChain, Không Framework

## Ưu tiên 2

# Đừng Dùng LangChain Vội — Hãy Tự Build AI Agent Trước

## Ưu tiên 3

# Từ Repository Trống Đến AI Agent Đầu Tiên | Agentic Studio #02

## Ưu tiên 4

# AI Agent Hoạt Động Bên Trong Như Thế Nào? Tự Build Từ Đầu

---

# 14. THUMBNAIL

Không nên nhồi code.

Concept:

```text
┌────────────────────────────────────┐
│                                    │
│       CODE        →      AGENT     │
│        { }               ◉         │
│                                    │
│          NO FRAMEWORK              │
│                                    │
└────────────────────────────────────┘
```

Text chính:

# BUILD AI AGENT

Text phụ nhỏ:

```text
FROM SCRATCH
```

Hoặc:

# NO LANGCHAIN

---

# 15. OPENING 20 GIÂY CÔ ĐỌNG

Nếu cần phiên bản hook cực mạnh:

> Một AI Agent không bắt đầu bằng LangChain, CrewAI hay một framework nào cả.
>
> Nó bắt đầu bằng một câu hỏi đơn giản:
>
> **Agent của chúng ta thực sự cần biết những gì?**
>
> Trong video này, chúng ta sẽ bắt đầu từ repository gần như trống và tự build Agent Core đầu tiên bằng Python.
>
> Và đến cuối video, bạn sẽ hiểu vì sao một đoạn code gọi LLM chạy được vẫn chưa đủ để trở thành một kiến trúc Agent tốt.

---

# 16. CÂU KẾT VIDEO

> Agent v0.1 của chúng ta đã có thể nhận một task, tạo context và sử dụng một language model để đưa ra câu trả lời.
>
> Nhưng nó vẫn chỉ có thể **nói**.
>
> Nó chưa thể đọc file.
>
> Chưa thể tính toán bằng một function.
>
> Chưa thể gọi API.
>
> Và chưa thể tác động lên environment.
>
> Muốn làm được những việc đó, chúng ta phải giải quyết một câu hỏi quan trọng:
>
> **Làm thế nào một LLM yêu cầu chương trình của chúng ta thực hiện một hành động?**
>
> Đó chính là Tool Calling.
>
> Và đó là thứ chúng ta sẽ tự build trong video tiếp theo.

Title card:

# VIDEO 03

## TOOL CALLING THỰC SỰ HOẠT ĐỘNG NHƯ THẾ NÀO?

```text
LLM decides.

Application executes.
```

Fade to black.

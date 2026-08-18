# VIDEO 02 — VIẾT AI AGENT ĐẦU TIÊN BẰNG PYTHON

## Metadata

- video_id: video-02
- milestone: Agentic Studio v0.1 — Simple Agent
- target_duration: 00:16:15.000 (975 seconds)
- audio_scope: EXCLUDED
- tool_calling_scope: OUT_OF_SCOPE
- tutorial_project: agentic-studio
- required_final_architecture:

```text
User
 ↓
Agent
 ↓
LLM
 ↓
Answer
```

## Definition of Done

- WindAgent build được tutorial repo từ workspace trống.
- `Message` tồn tại.
- `AgentConfig` tồn tại.
- `LLMClient` tồn tại.
- `Agent` không phụ thuộc provider SDK.
- Fake LLM hoạt động offline.
- Unit tests pass không dùng API.
- Provider implementation thật đã được integration-test.
- Không secret nào xuất hiện trong source/video.
- `pytest` output trong video là output verified.
- Tutorial repository có commit milestone.
- Tutorial repository có `video-02`.
- Tutorial repository có `v0.1`.
- Tool Calling không xuất hiện trong runtime Video 02.
- Mọi code take sinh từ verified checkpoint.
- 19 scene đúng timeline.
- Các architecture diagram đúng script.
- Final video dài đúng 16:15.
- Final visual master không phụ thuộc audio.
- 1440p master pass ffprobe.
- 1080p delivery pass ffprobe.
- Cue sheet được tạo.
- Final artifact có SHA-256.
- Có reproducibility receipt.

## Scene Map (19 scenes)

| Scene | Timecode | Title |
|-------|----------|-------|
| S01 | 00:00–00:25 | Cold Open |
| S02 | 00:25–00:50 | Hook |
| S03 | 00:50–01:25 | Video 01 Recap |
| S04 | 01:25–02:10 | Architecture v0.1 |
| S05 | 02:10–02:45 | Create Repository |
| S06 | 02:45–03:40 | Message |
| S07 | 03:40–04:35 | AgentConfig |
| S08 | 04:35–06:00 | LLMClient |
| S09 | 06:00–06:50 | Fake LLM |
| S10 | 06:50–08:25 | Agent |
| S11 | 08:25–09:00 | Is This An Agent? |
| S12 | 09:00–10:15 | Real Provider |
| S13 | 10:15–11:05 | API Key |
| S14 | 11:05–12:00 | First Run |
| S15 | 12:00–13:20 | Tests |
| S16 | 13:20–14:10 | Not Yet |
| S17 | 14:10–15:00 | Architecture Review |
| S18 | 15:00–15:35 | Git Milestone |
| S19 | 15:35–16:15 | Video 03 Teaser |

## Visual Plan

### Required Diagrams

Diagram 1 — Final architecture:

```text
User
 ↓
Agent
 ↓
LLM
 ↓
Answer
```

Diagram 2 — Component flow:

```text
AgentConfig
     │
     ▼
   Agent
     │
     ▼
 LLMClient
     │
     ▼
 Provider
```

Diagram 3 — Today vs Next:

```text
TODAY

User → Agent → LLM → Answer
```

```text
NEXT

User
 ↓
Agent
 ↓
LLM
 ↓
Tool
```

Diagram 4 — LLMClient abstraction:

```text
Agent
 ↓
LLMClient
 ├── Provider A
 ├── Provider B
 ├── Local Model
 └── Test Fake
```

Diagram 5 — Observe/Decide/Act:

```text
Observe
Decide
Act
Observe
```

Diagram 6 — Domain/Infrastructure boundary:

```text
DOMAIN
Agent
Message
AgentConfig
LLMClient

─────────────

INFRASTRUCTURE
Provider SDK
HTTP
API Key
Response Mapping
```

### Title Cards

Title card 1:

```text
VIDEO 02
AI AGENT ĐẦU TIÊN BẰNG PYTHON
```

Title card 2:

```text
Agentic Studio
v0.1 — Simple Agent
```

Title card 3:

```text
VIDEO 03
TOOL CALLING HOẠT ĐỘNG BÊN TRONG NHƯ THẾ NÀO?
```

### Checklist Scene (S16 — Not Yet)

```text
Tool Calling       ✕
Agent Loop         ✕
Memory             ✕
RAG                ✕
Planning           ✕
Multi-Agent        ✕
Orchestration      ✕
```

## Tutorial Repository

Deterministic builder creates `agentic-studio`:

```text
agentic-studio/
├── src/
│   ├── __init__.py
│   └── agent.py
├── tests/
│   └── test_agent.py
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

### Code Structure

```text
src/agent.py
├── Message          (frozen dataclass: role, content)
├── AgentConfig      (name, system_prompt, model, temperature)
├── LLMClient        (Protocol — Agent core không import SDK provider)
├── FakeLLMClient    (deterministic, offline, no network)
├── Agent            (run: user_input → system Message → user Message → LLMClient.generate() → answer)
└── real provider adapter (infrastructure boundary, API key từ environment)
```

### Verification Targets per Checkpoint

- cp_01_message — `import works`, `Role validation works`, `Message immutable`
- cp_02_config — `name`, `system_prompt`, `model`, `temperature`
- cp_03_llm_protocol — Agent core không import SDK provider
- cp_04_fake_llm — deterministic, no network
- cp_05_agent — `user_input → system Message → user Message → LLMClient.generate() → answer`
- cp_09_v0_1 — golden final checkpoint

### Required Terminal Commands

```text
mkdir agentic-studio
cd agentic-studio
git init
pytest                 # target: "2 passed"
python -m src.agent    # cold open demo
git add .
git commit -m "feat: build simple agent core"
git tag video-02
git tag v0.1
```

## Shot-by-Shot (Passes)

### Pass 1 — Cold Open (S01)

- Run `python -m src.agent`.
- Prompt: `Giải thích recursion bằng một ví dụ đơn giản.`
- Show verified model response.
- Then `agent.run(...)`.
- Show `User → Agent → LLM → Answer`.

### Pass 2 — Repository (S05)

- Run `mkdir agentic-studio`, `cd agentic-studio`, `git init`.
- File tree appears: src, tests, .env.example, .gitignore, pyproject.toml, README.md.

### Pass 3 — Message (S06)

- Replay code.
- Highlight `@dataclass(frozen=True)`, then `role`, `content`.

### Pass 4 — AgentConfig (S07)

- Replay.
- Highlight in turn: `name`, `system_prompt`, `model`, `temperature`.

### Pass 5 — LLMClient (S08)

- Highlight `class LLMClient(Protocol):`.
- Show LLMClient abstraction diagram.

### Pass 6 — FakeLLMClient (S09)

- Replay implementation.
- Overlay: `Unit Test ≠ Real API`.

### Pass 7 — Agent (S10)

- Quay constructor, sau đó `run()`.
- Highlight: `system`, `user`, `generate()`.
- End with flow diagram: `"Hello" → Agent.run() → [system, user] → LLMClient.generate() → "Answer"`.

### Pass 8 — Is This An Agent? (S11)

- Architecture: `Observe / Decide / Act / Observe`.
- Làm mờ các phần chưa tồn tại.

### Pass 9 — Provider (S12)

- Show DOMAIN / INFRASTRUCTURE boundary.

### Pass 10 — API Key (S13)

- Show `.env.example` and `.gitignore`.
- Visual: `api_key = "sk-..."` with ✕. Data hiển thị chỉ là placeholder.

### Pass 11 — First Run (S14)

- Replay `agent = Agent(...)`, `answer = agent.run(...)`, `print(answer)`.
- Hiện golden provider output.

### Pass 12 — Testing (S15)

- Replay test file.
- Run `pytest`. Target: `2 passed`. Output verified từ Phase 3.

### Pass 13 — Not Yet (S16)

- Checklist các chức năng chưa có.

### Pass 14 — Architecture Review (S17)

- Full-screen architecture.

### Pass 15 — Git Milestone (S18)

- Replay thật: `git add .`, `git commit -m "feat: build simple agent core"`, `git tag video-02`, `git tag v0.1`.
- Sau đó: `Agentic Studio v0.1 — Simple Agent`.

### Pass 16 — Outro (S19)

- Bắt đầu: `User → Agent → LLM → ?`.
- Sau đó: `LLM ≠ Function Executor`.
- Kết thúc: `VIDEO 03 — TOOL CALLING`.

## Constraints

- Audio không thuộc scope — user tự lồng tiếng sau.
- Không fake terminal — runtime mismatch phải trả `SCRIPT_RUNTIME_MISMATCH`.
- Không điều khiển editor bằng tọa độ chuột.
- API thật chỉ dùng trong preflight; final take `NO LIVE PROVIDER DEPENDENCY`.
- Security gate trước mọi recording: git grep, secret scanner, .env check, terminal output scan. Cấm `AIza...`, `sk-...`, `gsk_...`, `nvapi-...`, `Bearer ...`.
- Không triển khai: TTS, voice cloning, voice alignment, background music, SFX, subtitle generation, Tool Calling runtime, Memory, RAG, Planning, Multi-Agent.
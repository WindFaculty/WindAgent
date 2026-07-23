# 2. Kiến trúc mục tiêu

```text
wind-agent/
├── apps/
│   ├── api/
│   ├── cli/
│   ├── web/
│   ├── worker/
│   ├── desktop/
│   └── backend/         
│
├── core/
│   ├── domain/
│   ├── contracts/
│   ├── events/
│   ├── errors/
│   ├── config/
│   └── security/
│
├── orchestration/
│   ├── task_manager/
│   ├── workflow_engine/
│   ├── state_machine/
│   ├── scheduler/
│   ├── dispatcher/
│   ├── retry/
│   └── recovery/
│
├── intelligence/
│   ├── task_classifier/
│   ├── planner/
│   ├── context_builder/
│   ├── model_router/
│   ├── summarizer/
│   ├── reviewer/
│   └── reporter/
│
├── providers/
│   ├── base/
│   ├── openai/
│   ├── anthropic/
│   ├── google/
│   ├── nvidia/
│   ├── openrouter/
│   ├── mistral/
│   ├── ollama/
│   └── local/
│
├── tools/
│   ├── registry/
│   ├── filesystem/
│   ├── shell/
│   ├── git/
│   ├── code_search/
│   ├── ast/
│   ├── lsp/
│   ├── testing/
│   ├── browser/
│   ├── database/
│   ├── github/
│   └── mcp/
│
├── workflows/
├── verification/
├── context/
├── memory/
├── execution/
├── storage/
├── observability/
├── evals/
├── plugins/
├── skills/
├── scripts/
├── tests/
├── configs/
└── docs/
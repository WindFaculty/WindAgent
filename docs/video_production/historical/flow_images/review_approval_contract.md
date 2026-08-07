# Flow Review & Approval Contract (Phase 14)

**Gate:** `VP14_FLOW_IMAGE_GENERATION_VERIFIED`
**Plan:** [04_phase_12_16_flow_browser_provider.md](../plans/04_phase_12_16_flow_browser_provider.md) §18.4
**Location:** `tools/windagent_tools/google_flow/review_approval.py`

## 1. Purpose

`ReviewGate` decides the fate of each acquired candidate. Approval fails
CLOSED (plan 04 §18.4):

- deterministic file validity is evaluated BEFORE any VLM scoring;
- a character master (`CREATE_CHARACTER_REFERENCE`) is ALWAYS human-approved
  in Release 0.1 — never auto-approved;
- a rejected candidate keeps its reason and evidence and is never auto-bound
  to the package;
- re-generation creates a new attempt/job while keeping the causal link
  (via `FlowJobRegistry.next_attempt`).

## 2. Decisions

```text
APPROVED       deterministic valid + VLM high confidence + not character master
REJECTED       deterministic file validation failed / not published
REQUIRES_HUMAN character master, OR VLM confidence below threshold
```

## 3. VLM port

```python
class VlmReviewPort(Protocol):
    async def score(*, candidate, request) -> VlmScores:
        ...  # prompt_compliance, identity (multi-dimensional, never one number)
```

The VLM is a port: tests inject a deterministic fake; a real VLM adapter
lives outside the tools boundary (no `windagent_intelligence` import).

## 4. Review record

```python
CandidateReview(
    candidate_id, decision, reason,
    deterministic_valid, character_master,
    vlm_scores, reviewed_at,
)
```

## 5. Contract

- Character master → `REQUIRES_HUMAN` even at 0.99 VLM confidence.
- VLM below `compliance_threshold`/`identity_threshold` (0.6) →
  `REQUIRES_HUMAN`, never auto-approved.
- `REJECTED` keeps the reason; the generator never binds a candidate
  automatically — binding is an explicit, later step.

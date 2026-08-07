# Verdict & Selection Contract (plan 05 §25.4-§25.5) — Phase 20

Gate: `VP20_GENERATION_REVIEW_VERIFIED`

## 1. Mục đích

`VerdictPolicy` (`.../reviewers/verdict.py`) quyết định verdict candidate;
`CandidateSelector` (`.../reviewers/selection.py`) chọn candidate trong số
không bị block. Cả hai deterministic, offline, và **truy được về policy, model
và evidence** (gate condition 4).

## 2. Verdict policy (plan §25.4)

Thứ tự kiểm tra (fail closed trước):

```text
1. bất kỳ defect REVIEW_ERROR            -> REVIEW_ERROR
2. bất kỳ blocking defect                -> REJECT     (blocking luôn thắng)
3. dimension dưới threshold              -> REJECT
4. confidence dưới floor                 -> HUMAN_REVIEW_REQUIRED
5. ngược lại                             -> APPROVE
```

Verdicts: `APPROVE`, `REJECT`, `HUMAN_REVIEW_REQUIRED`, `REVIEW_ERROR`.

**Blocking defect luôn thắng aggregate preference** — candidate có average
score cao nhưng blocking defect vẫn REJECT, không auto-select. **Low confidence
chuyển human review**, không tạo false PASS.

`review_id = rv_{candidate_id}:{policy_version}` — policy/threshold đổi tạo
**revision mới**, không sửa result cũ (plan §26).

## 3. Candidate selection (plan §25.5)

- **Rank chỉ trong số candidate APPROVE** (không block, không error).
- **Deterministic + order-independent**: input list order không ảnh hưởng kết
  quả — rank theo `(average_score DESC, candidate_id ASC)`; tie-break bằng
  candidate id.
- `SelectionRecord` mang `algorithm_version`, `policy_version`, `reason`.
- **Human override có audit** (`HumanSelectionOverride`: actor, decision,
  reason, recorded_at) và thắng mọi ranking.
- **Rejected candidate giữ evidence**; `RetryProposal` ghi defect cần sửa +
  request field cần thay.

## 4. Kiểm chứng (verifier)

- `verdict_policy_receipt.json`: REVIEW_ERROR → error; blocking defect thắng
  aggregate; below-threshold → REJECT; low confidence → human; clean → APPROVE.
- `selection_receipt.json`: rank chỉ unblocked; ordering đổi không đổi kết
  quả; không candidate khả dụng → không chọn; human override audit; retry
  proposal có field changes; trace policy/algorithm version.

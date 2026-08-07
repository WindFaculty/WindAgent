# Deterministic Gate Contract (plan 05 §25.1, §24) — Phase 20

Gate: `VP20_GENERATION_REVIEW_VERIFIED`

## 1. Mục đích

`DeterministicReviewer`
(`intelligence/windagent_intelligence/video/reviewers/deterministic.py`) là
**tier đầu tiên** của reviewer hierarchy (plan §24). Nó áp dụng các luật
media/file/safety **hoàn toàn offline + deterministic** lên `MediaProbeFacts`
được inject từ ngoài (adapter ffprobe sống ngoài layer này) — reviewer không
bao giờ chạy subprocess.

## 2. Luật (plan §25.1)

1. **Hash/file/decoder validity** — content hash phải là SHA-256 64-char;
   file phải decode được; video phải có video stream.
2. **Duration / resolution / frame rate / stream** — duration > 0; video cần
   resolution + frame rate hợp lệ.
3. **Black / truncated ending** + sample-frame decode.
4. **Required candidate metadata/provenance**.
5. **Safety file checks**.

Mỗi finding là một `BlockingDefect` với **typed reason code** + evidence
(`INVALID_CONTENT_HASH`, `MEDIA_DECODE_FAILURE`, `MISSING_VIDEO_STREAM`,
`INVALID_DURATION`, `MISSING_MEDIA_METADATA`, `BLACK_ENDING`,
`TRUNCATED_ENDING`, `MISSING_PROVENANCE`, `SAFETY_FINDING`).

## 3. Fail-closed (gate condition 1, plan §24)

Candidate không decode hoặc thiếu video stream bị **BLOCK tại gate** —
`technical_valid = False` → pipeline **KHÔNG chạy VLM**; VLM/human score
không bao giờ che được deterministic failure.

## 4. Output

`DeterministicReviewResult`: `dimension_results` (TECHNICAL_VALIDITY +
SAFETY), `blocking_defects`, `technical_valid`.

## 5. Kiểm chứng (verifier)

- `deterministic_gate_receipt.json`: candidate hợp lệ pass gate; mỗi vi phạm
  (decode, stream, hash, duration, metadata, black/truncated, provenance,
  safety) tạo typed blocking defect; decode fail → `technical_valid = False`;
  safety không làm hỏng technical_valid nhưng vẫn blocking.

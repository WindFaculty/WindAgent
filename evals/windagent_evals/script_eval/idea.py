"""Script Eval Phase 2 — idea generation benchmark + fail-closed validator.

Spec: test_kich_ban.md section 5. Gate SCRIPT_EVAL_IDEA_VALID:
  - benchmark of 12 briefs (T01-T12) x 3 durations (5/10/20 min) = 36 runs
  - every idea must carry a clear hook, kid-appropriate conflict, a premise
    that can sustain the target duration, differentiation from sibling ideas,
    a payoff, a non-preachy lesson, and visual potential.

Severity policy: structural/objective failures (missing, empty, too thin,
duplicate, banned terms) are ERRORs and fail the gate; subjective qualities
(preachy lesson, weak visual language) are WARNINGs that never fail the gate.

Stdlib-only by design (evals package declares no extra deps).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

IDEA_SCHEMA_VERSION = "1.0.0"

# deterministic thresholds (documented in verdict; tunable after first run)
MIN_HOOK_CHARS = 20
PREMISE_CHARS_PER_MINUTE = 20
MIN_VISUAL_CHARS = 30
DUPLICATE_JACCARD = 0.6
DURATIONS_MINUTES = (5, 10, 20)

# conflict terms unsuitable for young children (3-6 audience).
# Word-boundary matching; "mau" (colour) excluded — too ambiguous with
# "mau"/"mau" (blood) in diacritic-free Vietnamese.
BANNED_CONFLICT_TERMS = {
    "kill", "gun", "blood", "die", "death", "weapon", "bomb", "knife",
    "cheat", "steal", "giet", "sung", "chet", "vu khi", "bom", "dao",
    "danh nhau", "bao luc", "bat nat",
}

# absolutist/moralizing markers -> preachy lesson (WARNING, subjective)
PREACHY_MARKERS = {
    "always", "never", "must", "luon luon", "khong bao gio", "phai nho",
    "nhat dinh", "bat buoc",
}

# visual-action vocabulary (visual potential heuristic)
VISUAL_ACTION_WORDS = {
    "chase", "climb", "jump", "fly", "run", "hide", "search", "build",
    "catch", "swim", "dance", "chay", "leo", "nhay", "bay", "tron", "tim",
    "xay", "bat", "boi", "mua",
}

REQUIRED_IDEA_FIELDS = [
    "case_id", "duration_minutes", "hook", "conflict", "premise",
    "differentiation", "payoff", "lesson", "visual_potential",
]

# 12 benchmark briefs from the plan table (T01-T12)
BENCHMARK_BRIEFS: Tuple[Dict[str, str], ...] = (
    {"case_id": "T01", "type": "phieu_luu", "genre": "adventure",
     "brief": "Một chuyến phiêu lưu nhỏ trong khu vườn hoặc công viên quen thuộc."},
    {"case_id": "T02", "type": "hai", "genre": "comedy",
     "brief": "Tình huống hài hước đến từ hiểu lầm ngộ nghĩnh giữa các bạn nhỏ."},
    {"case_id": "T03", "type": "giao_duc", "genre": "educational",
     "brief": "Bài học đơn giản về một khái niệm (màu sắc, con số, hình khối)."},
    {"case_id": "T04", "type": "tinh_ban", "genre": "friendship",
     "brief": "Một người bạn mới xuất hiện và cách cả nhóm kết bạn."},
    {"case_id": "T05", "type": "gia_dinh", "genre": "family",
     "brief": "Hoạt động gia đình hàng ngày trở thành khoảnh khắc đáng nhớ."},
    {"case_id": "T06", "type": "problem_solving", "genre": "problem-solving",
     "brief": "Một vấn đề nhỏ cần giải quyết bằng cách thử và sửa sai."},
    {"case_id": "T07", "type": "khoa_hoc", "genre": "simple-science",
     "brief": "Hiện tượng khoa học đơn giản (bóng, nước, gió) được khám phá."},
    {"case_id": "T08", "type": "moi_truong", "genre": "environment",
     "brief": "Bảo vệ môi trường: nhặt rác, tưới cây, tiết kiệm nước."},
    {"case_id": "T09", "type": "bedtime", "genre": "bedtime-story",
     "brief": "Câu chuyện trước khi ngủ, nhẹ nhàng và dễ chìm vào giấc ngủ."},
    {"case_id": "T10", "type": "fantasy", "genre": "fantasy",
     "brief": "Thế giới tưởng tượng: sinh vật lạ, phép màu, vùng đất kỳ diệu."},
    {"case_id": "T11", "type": "mystery", "genre": "light-mystery",
     "brief": "Bí ẩn nhẹ nhàng: một đồ vật biến mất và hành trình tìm ra thủ phạm."},
    {"case_id": "T12", "type": "khong_loi", "genre": "wordless",
     "brief": "Gần như không lời thoại; kể chuyện bằng hành động và biểu cảm."},
)

IDEA_TYPES = {b["case_id"]: b["type"] for b in BENCHMARK_BRIEFS}


def benchmark_runs() -> List[Dict[str, Any]]:
    """Expand briefs x durations -> 36 run specs (run_id like T01_005m)."""
    runs: List[Dict[str, Any]] = []
    for brief in BENCHMARK_BRIEFS:
        for minutes in DURATIONS_MINUTES:
            runs.append({
                "run_id": f"{brief['case_id']}_{minutes:03d}m",
                "case_id": brief["case_id"],
                "type": brief["type"],
                "duration_minutes": minutes,
                "brief": brief["brief"],
            })
    return runs


@dataclass(frozen=True)
class IdeaFinding:
    check: str
    severity: str  # ERROR (fails gate) | WARNING (flagged, review)
    path: str
    message: str


@dataclass(frozen=True)
class IdeaReport:
    schema_valid: bool
    differentiation_valid: bool
    findings: Tuple[IdeaFinding, ...] = field(default_factory=tuple)
    case_id: str = ""
    duration_minutes: Optional[float] = None

    @property
    def valid(self) -> bool:
        return self.schema_valid and self.differentiation_valid

    @property
    def errors(self) -> List[IdeaFinding]:
        return [f for f in self.findings if f.severity == "ERROR"]

    @property
    def warnings(self) -> List[IdeaFinding]:
        return [f for f in self.findings if f.severity == "WARNING"]


def _f(findings: List[IdeaFinding], check: str, severity: str, path: str,
       message: str) -> None:
    findings.append(IdeaFinding(check=check, severity=severity, path=path,
                                message=message))


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _jaccard(a: str, b: str) -> float:
    """Word-set overlap in [0,1]; 1.0 = identical wording."""
    wa = set(re.findall(r"[a-z0-9]+", a.lower()))
    wb = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def validate_idea(idea: Any, siblings: Optional[List[Dict[str, Any]]] = None
                  ) -> IdeaReport:
    """Validate one generated idea against the Phase 2 criteria.

    Fail-closed: non-dict input -> invalid report, never raises. `siblings`
    are the other benchmark ideas; an idea too similar to any sibling fails
    differentiation (the plan's "khac biet so voi cac test khac").
    """
    findings: List[IdeaFinding] = []

    if not isinstance(idea, dict):
        _f(findings, "missing_field", "ERROR", "$",
           f"idea must be an object, got {type(idea).__name__}")
        return IdeaReport(schema_valid=False, differentiation_valid=False,
                          findings=tuple(findings))
    for key in REQUIRED_IDEA_FIELDS:
        if key not in idea:
            _f(findings, "missing_field", "ERROR", f"$.{key}",
               f"missing required field `{key}`")
        elif idea[key] is None:
            _f(findings, "missing_field", "ERROR", f"$.{key}",
               f"field `{key}` is null")

    case_id = idea.get("case_id")
    duration = idea.get("duration_minutes")

    # ---- structural
    if case_id is not None and case_id not in IDEA_TYPES:
        _f(findings, "invalid_type", "ERROR", "$.case_id",
           f"case_id `{case_id!r}` not in benchmark (T01-T12)")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        _f(findings, "invalid_type", "ERROR", "$.duration_minutes",
           f"must be a number of minutes, got {type(duration).__name__}")
    elif duration not in DURATIONS_MINUTES:
        _f(findings, "invalid_type", "ERROR", "$.duration_minutes",
           f"duration {duration} not in {DURATIONS_MINUTES}")

    # ---- hook: clear hook
    hook = idea.get("hook")
    if not _is_str(hook):
        _f(findings, "weak_hook", "ERROR", "$.hook",
           "hook must be a non-empty string")
    elif len(hook.strip()) < MIN_HOOK_CHARS:
        _f(findings, "weak_hook", "ERROR", "$.hook",
           f"hook too vague ({len(hook.strip())} chars, min {MIN_HOOK_CHARS})")

    # ---- conflict: kid-appropriate
    conflict = idea.get("conflict")
    if not _is_str(conflict):
        _f(findings, "inappropriate_conflict", "ERROR", "$.conflict",
           "conflict must be a non-empty string")
    else:
        low = conflict.lower()
        banned = sorted(t for t in BANNED_CONFLICT_TERMS
                        if re.search(rf"\b{re.escape(t)}\b", low))
        if banned:
            _f(findings, "inappropriate_conflict", "ERROR", "$.conflict",
               f"conflict unsuitable for young children, terms: {banned}")

    # ---- premise: enough to sustain target duration
    premise = idea.get("premise")
    if not _is_str(premise):
        _f(findings, "thin_premise", "ERROR", "$.premise",
           "premise must be a non-empty string")
    elif isinstance(duration, (int, float)) and not isinstance(duration, bool):
        needed = float(duration) * PREMISE_CHARS_PER_MINUTE
        if len(premise.strip()) < needed:
            _f(findings, "thin_premise", "ERROR", "$.premise",
               f"premise too thin for {duration} min "
               f"({len(premise.strip())} chars, need >= {needed:.0f})")

    # ---- differentiation vs sibling ideas
    diff_ok = True
    diff_field = idea.get("differentiation")
    if not _is_str(diff_field):
        _f(findings, "duplicate_idea", "ERROR", "$.differentiation",
           "differentiation must be a non-empty string")
        diff_ok = False
    for sib in siblings or []:
        if not isinstance(sib, dict):
            continue
        for field_name, mine, other in (
                ("premise", premise, sib.get("premise")),
                ("differentiation", diff_field, sib.get("differentiation"))):
            if not _is_str(mine) or not _is_str(other):
                continue
            j = _jaccard(mine, other)
            if j >= DUPLICATE_JACCARD:
                _f(findings, "duplicate_idea", "ERROR", f"$.{field_name}",
                   f"{field_name} too similar to sibling idea "
                   f"`{sib.get('case_id', '?')}` (Jaccard "
                   f"{j:.2f} >= {DUPLICATE_JACCARD})")
                diff_ok = False
                break
        if not diff_ok:
            break

    # ---- payoff
    if not _is_str(idea.get("payoff")):
        _f(findings, "missing_payoff", "ERROR", "$.payoff",
           "payoff must be a non-empty string")

    # ---- lesson: present but not preachy (subjective -> WARNING)
    lesson = idea.get("lesson")
    if not _is_str(lesson):
        _f(findings, "preachy_lesson", "WARNING", "$.lesson",
           "lesson empty (allowed, but a lesson is expected per plan)")
    else:
        low = lesson.lower()
        preachy = sorted(t for t in PREACHY_MARKERS if t in low)
        if preachy:
            _f(findings, "preachy_lesson", "WARNING", "$.lesson",
               f"lesson sounds preachy/didactic, markers: {preachy}")

    # ---- visual potential (subjective -> WARNING when weak)
    visual = idea.get("visual_potential")
    if not _is_str(visual):
        _f(findings, "not_visual", "WARNING", "$.visual_potential",
           "visual_potential empty (story may not be visualizable)")
    elif len(visual.strip()) < MIN_VISUAL_CHARS:
        _f(findings, "not_visual", "WARNING", "$.visual_potential",
           f"visual_potential thin ({len(visual.strip())} chars, "
           f"min {MIN_VISUAL_CHARS})")
    else:
        low = visual.lower()
        if not any(w in low for w in VISUAL_ACTION_WORDS):
            _f(findings, "not_visual", "WARNING", "$.visual_potential",
               "no visual-action vocabulary; may be hard to show on screen")

    schema_errors = {f.check for f in findings if f.severity == "ERROR"
                     and f.check != "duplicate_idea"}
    return IdeaReport(
        schema_valid=not schema_errors,
        differentiation_valid=diff_ok,
        findings=tuple(findings),
        case_id=str(case_id) if case_id else "",
        duration_minutes=float(duration) if isinstance(duration, (int, float))
        and not isinstance(duration, bool) else None,
    )


__all__ = [
    "IDEA_SCHEMA_VERSION", "MIN_HOOK_CHARS", "PREMISE_CHARS_PER_MINUTE",
    "MIN_VISUAL_CHARS", "DUPLICATE_JACCARD", "DURATIONS_MINUTES",
    "BANNED_CONFLICT_TERMS", "PREACHY_MARKERS", "VISUAL_ACTION_WORDS",
    "REQUIRED_IDEA_FIELDS", "BENCHMARK_BRIEFS", "IDEA_TYPES",
    "benchmark_runs", "IdeaFinding", "IdeaReport", "validate_idea",
    "_jaccard",
]

"""
Task Reviewer for WindAgent Intelligence (Phase 22).
Reviews patches, evidence, and acceptance criteria for completed tasks.
Cannot pass (ReviewVerdict.PASS) if verification result is missing.
Fail-closed: missing evidence = BLOCKED, not PASSED.
"""

from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from windagent_core.errors.exceptions import ValidationError

logger = logging.getLogger("windagent.intelligence.reviewer")


class ReviewVerdict(str, Enum):
    PASS = "pass"
    PASS_WITH_COMMENTS = "pass_with_comments"
    BLOCKED = "blocked"       # Missing evidence or failed checks
    FAIL = "fail"             # Explicit failure
    NEEDS_REVISION = "needs_revision"


@dataclass
class ReviewCheck:
    """A single check within a review."""
    check_name: str
    passed: bool
    details: str = ""
    evidence_ref: Optional[str] = None   # Reference to supporting evidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "details": self.details,
            "evidence_ref": self.evidence_ref,
        }


@dataclass
class ReviewResult:
    """Complete result of a task review."""
    review_id: str
    task_prompt_hash: str
    verdict: ReviewVerdict
    checks: List[ReviewCheck]
    summary: str
    issues: List[str]
    recommendations: List[str]
    has_verification_evidence: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def passed(self) -> bool:
        return self.verdict in (ReviewVerdict.PASS, ReviewVerdict.PASS_WITH_COMMENTS)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "task_prompt_hash": self.task_prompt_hash,
            "verdict": self.verdict.value,
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "summary": self.summary,
            "issues": self.issues,
            "recommendations": self.recommendations,
            "has_verification_evidence": self.has_verification_evidence,
            "created_at": self.created_at,
        }


class TaskReviewer:
    """Reviews task results against acceptance criteria.
    Fail-closed: cannot return PASS without verification evidence.
    """

    def __init__(self, require_verification_evidence: bool = True):
        self.require_verification_evidence = require_verification_evidence

    def review(
        self,
        task_prompt: str,
        acceptance_criteria: List[str],
        patch_summary: Optional[str] = None,
        tool_outputs: Optional[List[Dict[str, Any]]] = None,
        verification_result: Optional[Dict[str, Any]] = None,
        test_results: Optional[List[Dict[str, Any]]] = None,
    ) -> ReviewResult:
        """Performs a structured review of the task output against acceptance criteria.
        Returns a ReviewResult. Cannot PASS if verification evidence is missing.
        """
        review_id = f"review_{hashlib.sha256(task_prompt.encode()).hexdigest()[:12]}"
        task_hash = hashlib.sha256(task_prompt.encode("utf-8")).hexdigest()[:16]

        checks: List[ReviewCheck] = []
        issues: List[str] = []
        recommendations: List[str] = []

        # 1. Check acceptance criteria
        criteria_checks = self._check_acceptance_criteria(acceptance_criteria, tool_outputs)
        checks.extend(criteria_checks)

        # 2. Check patch/evidence presence
        if patch_summary:
            checks.append(ReviewCheck(
                check_name="patch_evidence",
                passed=True,
                details="Patch summary provided",
                evidence_ref=patch_summary[:100],
            ))
        else:
            checks.append(ReviewCheck(
                check_name="patch_evidence",
                passed=False,
                details="No patch summary provided",
            ))
            issues.append("Missing patch summary evidence")

        # 3. Check evidence completeness
        evidence_check = self._check_evidence_completeness(tool_outputs)
        checks.append(evidence_check)
        if not evidence_check.passed:
            issues.append(evidence_check.details)

        # 4. Verification evidence check (FAIL-CLOSED: cannot pass without this)
        has_evidence = verification_result is not None
        if self.require_verification_evidence and not has_evidence:
            checks.append(ReviewCheck(
                check_name="verification_evidence",
                passed=False,
                details="Missing verification result. Reviewer cannot pass without verification evidence.",
            ))
            issues.append("Missing verification result — reviewer is fail-closed")
            recommendations.append("Run verification before requesting review")
        else:
            checks.append(ReviewCheck(
                check_name="verification_evidence",
                passed=True,
                details="Verification evidence present",
                evidence_ref=str(verification_result),
            ))

        # 5. Test result checks
        if test_results:
            passed_tests = sum(1 for t in test_results if t.get("passed", False))
            total_tests = len(test_results)
            checks.append(ReviewCheck(
                check_name="test_results",
                passed=passed_tests == total_tests,
                details=f"{passed_tests}/{total_tests} tests passed",
            ))
            if passed_tests < total_tests:
                issues.append(f"{total_tests - passed_tests} test(s) failed")
        elif self.require_verification_evidence:
            checks.append(ReviewCheck(
                check_name="test_results",
                passed=False,
                details="No test results provided",
            ))
            issues.append("No test results provided")

        # 6. Determine verdict
        verdict = self._determine_verdict(checks, has_evidence, issues)

        # 7. Generate summary
        total_checks = len(checks)
        passed_checks = sum(1 for c in checks if c.passed)
        summary = (
            f"Review completed: {passed_checks}/{total_checks} checks passed. "
            f"Verdict: {verdict.value}. "
            f"{len(issues)} issue(s) found."
        )

        if not recommendations:
            recommendations.append("Address all issues before proceeding")

        return ReviewResult(
            review_id=review_id,
            task_prompt_hash=task_hash,
            verdict=verdict,
            checks=checks,
            summary=summary,
            issues=issues,
            recommendations=recommendations,
            has_verification_evidence=has_evidence,
        )

    def _check_acceptance_criteria(
        self,
        criteria: List[str],
        tool_outputs: Optional[List[Dict[str, Any]]],
    ) -> List[ReviewCheck]:
        """Checks each acceptance criterion against available evidence."""
        checks = []
        if not criteria:
            checks.append(ReviewCheck(
                check_name="acceptance_criteria",
                passed=False,
                details="No acceptance criteria defined",
            ))
            return checks

        all_evidence_text = ""
        if tool_outputs:
            all_evidence_text = " ".join(str(t.get("output", "")) for t in tool_outputs).lower()

        for criterion in criteria:
            # Simple keyword presence check as a heuristic
            keywords = [w.lower() for w in criterion.split() if len(w) > 3]
            matched = sum(1 for kw in keywords if kw in all_evidence_text)
            threshold = max(1, len(keywords) // 2)
            passed = matched >= threshold if keywords else False

            checks.append(ReviewCheck(
                check_name=f"criterion: {criterion[:50]}",
                passed=passed,
                details=f"Matched {matched}/{len(keywords)} keywords" if keywords else "No keywords to match",
            ))

        return checks

    def _check_evidence_completeness(self, tool_outputs: Optional[List[Dict[str, Any]]]) -> ReviewCheck:
        """Checks that tool outputs contain evidence."""
        if not tool_outputs:
            return ReviewCheck(
                check_name="evidence_completeness",
                passed=False,
                details="No tool outputs provided as evidence",
            )

        has_success = any(t.get("success", False) or t.get("exit_code", -1) == 0 for t in tool_outputs)
        if has_success:
            return ReviewCheck(
                check_name="evidence_completeness",
                passed=True,
                details=f"{len(tool_outputs)} tool output(s) with successful results",
            )
        else:
            return ReviewCheck(
                check_name="evidence_completeness",
                passed=False,
                details="Tool outputs present but no successful results",
            )

    def _determine_verdict(self, checks: List[ReviewCheck], has_evidence: bool, issues: List[str]) -> ReviewVerdict:
        """Determines the final verdict from check results.
        Fail-closed: cannot PASS without verification evidence.
        """
        if not has_evidence and self.require_verification_evidence:
            return ReviewVerdict.BLOCKED

        failed_checks = [c for c in checks if not c.passed]
        if not failed_checks:
            return ReviewVerdict.PASS

        has_blocking_issues = any("Missing" in c.details or "No " in c.details for c in failed_checks)
        if has_blocking_issues:
            return ReviewVerdict.BLOCKED

        # Non-blocking failures
        if len(failed_checks) <= 2:
            return ReviewVerdict.PASS_WITH_COMMENTS

        return ReviewVerdict.NEEDS_REVISION

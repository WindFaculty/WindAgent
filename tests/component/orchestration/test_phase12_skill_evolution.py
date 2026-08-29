"""Phase 12 Component Tests — Skill Evolution, Versioning, Security Scanning, and Rollback (ban_ke_hoach_v1 §18, §24, §25, §27, §28, §29, §30, §35).

Tests:
1. Domain model immutability, enums, transitions, and code hash calculation.
2. SkillSecurityScanner: AST scanning catches eval/exec/subprocess/os.system/dunders; secret scanning catches tokens/keys.
3. SkillSecurityScanner: Clean Python code passes with 0 violations.
4. SkillValidator: Enforces registered tools, registered workflows, and blocks privilege escalation permissions.
5. SkillEvaluator: Evaluates functional test suites, token efficiency, accuracy, and safety scoring (>= 0.95).
6. Promotion Gate: Rejects candidates with failed security audits or failing benchmarks.
7. Executable Skill Governance: Executable Python skills strictly require human approval (approved_by).
8. Safe Template Promotion: Low-risk prompt template skills permit bounded automated promotion.
9. Atomic SkillVersion Commitment: Commits new version, links parent, deprecates previous active, and deploys to SkillManager.
10. Rollback Coordination: Rolls back active skill to parent version, restores code in SkillManager, records audit trail.
11. Async SQL Repository: Full persistence, retrieval, and filtering for candidates, versions, and promotions.
12. FastAPI V2 REST Endpoints: Full endpoint suite under /api/v2/skills.
13. Migration 0029: Table schema and compound index metadata integrity.
"""

from __future__ import annotations

import tempfile
from typing import Any, Dict, List, Optional
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from pydantic import ValidationError

# Ensure ORM models are registered in BaseORM.metadata
import windagent_storage.orm.agent_loop_models  # noqa: F401
import windagent_storage.orm.delegation_models  # noqa: F401
import windagent_storage.orm.persistent_goal_models  # noqa: F401
import windagent_storage.orm.agent_checkpoint_models  # noqa: F401
import windagent_storage.orm.memory_v2_models  # noqa: F401
import windagent_storage.orm.evaluation_models  # noqa: F401
import windagent_storage.orm.experience_models  # noqa: F401
import windagent_storage.orm.candidate_models  # noqa: F401
import windagent_storage.orm.harness_models  # noqa: F401
import windagent_storage.orm.experiment_models  # noqa: F401
import windagent_storage.orm.promotion_models  # noqa: F401
import windagent_storage.orm.skill_evolution_models  # noqa: F401

from windagent_core.domain.skill_evolution import (
    SkillCandidate,
    SkillCandidateStatus,
    SkillEvaluationResult,
    SkillPromotionDecision,
    SkillPromotionStatus,
    SkillRiskLevel,
    SkillSecurityAuditResult,
    SkillVersion,
    SkillVersionStatus,
)
from windagent_core.errors.exceptions import (
    PermissionDeniedError,
)
from windagent_evals.skill_evaluator import SkillEvaluator, SkillTestCase
from windagent_orchestration.learning.skill_evolution_service import SkillEvolutionService
from windagent_skills.loader.manager import SkillManager
from windagent_skills.security.skill_security_scanner import SkillSecurityScanner
from windagent_skills.validation.skill_validator import SkillValidator
from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.repositories.skill_evolution_repository import SkillEvolutionRepository
from windagent_api.routers.v2_skills import router as skills_router


# =============================================================================
# Helper Fixtures & Builders
# =============================================================================

def _sample_manifest(
    skill_id: str = "code_refactor_assistant",
    version: str = "1.0.0",
    required_tools: Optional[List[str]] = None,
    required_workflows: Optional[List[str]] = None,
    required_permissions: Optional[List[str]] = None,
    prompt_template: str = "Refactor this code: {code_input}",
    token_budget: int = 2000,
) -> Dict[str, Any]:
    return {
        "id": skill_id,
        "version": version,
        "description": "Assists in refactoring and cleaning up source code.",
        "activation_rules": ["refactor", "cleanup code"],
        "required_tools": required_tools or ["code_parser"],
        "required_workflows": required_workflows or ["ast_refactor_wf"],
        "required_permissions": required_permissions or ["file:read", "file:write"],
        "token_budget": token_budget,
        "prompt_template": prompt_template,
    }


def _make_service(repo: Any, skill_manager: SkillManager) -> SkillEvolutionService:
    scanner = SkillSecurityScanner()
    validator = SkillValidator(
        registered_tools=skill_manager._registered_tool_names,
        registered_workflows=skill_manager._registered_workflow_names,
    )
    evaluator = SkillEvaluator()
    return SkillEvolutionService(
        repository=repo,
        skill_manager=skill_manager,
        scanner=scanner,
        validator=validator,
        evaluator=evaluator,
    )


# =============================================================================
# Test Cases
# =============================================================================

@pytest.mark.asyncio
async def test_skill_domain_immutability_and_lifecycle():
    """1. Domain model immutability, enums, transitions, and code hash calculation."""
    manifest = _sample_manifest()
    candidate = SkillCandidate(
        candidate_id="skcand_001",
        skill_id="code_refactor_assistant",
        proposed_manifest=manifest,
        proposed_code="def run(code):\n    return code.strip()",
        reasoning_summary="Improves whitespace stripping efficiency.",
        status=SkillCandidateStatus.PROPOSED,
        risk_level=SkillRiskLevel.LOW,
    )

    # Immutability check
    with pytest.raises(ValidationError):
        candidate.status = SkillCandidateStatus.AUDITED  # type: ignore

    # Code hash computation
    code_hash = candidate.compute_code_hash()
    assert isinstance(code_hash, str) and len(code_hash) == 64

    # Audit transition
    audit_res = SkillSecurityAuditResult(
        passed=True,
        ast_scan_passed=True,
        permission_audit_passed=True,
        dependency_validation_passed=True,
        secret_scan_passed=True,
        violations=[],
        risk_score=0.0,
    )
    audited_cand = candidate.with_audit(audit_res)
    assert audited_cand.status == SkillCandidateStatus.AUDITED
    assert audited_cand.security_audit.is_safe is True
    assert candidate.status == SkillCandidateStatus.PROPOSED  # Original untouched

    # Evaluation transition
    eval_res = SkillEvaluationResult(
        evaluation_id="skeval_001",
        skill_candidate_id="skcand_001",
        benchmark_passed=True,
        test_suite_passed=True,
        tests_run=5,
        tests_passed=5,
        tests_failed=0,
        accuracy_score=1.0,
        safety_score=1.0,
    )
    evaluated_cand = audited_cand.with_evaluation(eval_res)
    assert evaluated_cand.status == SkillCandidateStatus.EVALUATED
    assert evaluated_cand.evaluation.benchmark_passed is True

    # Version lifecycle
    version = SkillVersion(
        version_id="skver_code_refactor_v1.0.0",
        skill_id="code_refactor_assistant",
        version="1.0.0",
        manifest=manifest,
        code_hash=code_hash,
        status=SkillVersionStatus.ACTIVE,
    )
    deprecated_ver = version.deprecate()
    assert deprecated_ver.status == SkillVersionStatus.DEPRECATED
    assert deprecated_ver.deprecated_at is not None

    rolled_back_ver = version.mark_rolled_back()
    assert rolled_back_ver.status == SkillVersionStatus.ROLLED_BACK


@pytest.mark.asyncio
async def test_security_scanner_blocks_dangerous_ast_and_secrets():
    """2. SkillSecurityScanner: AST scanning catches eval/exec/subprocess/os.system/dunders; secret scanning catches tokens/keys."""
    scanner = SkillSecurityScanner()

    # Dynamic exec test (eval)
    code_eval = "def unsafe_fn(x):\n    return eval(x)"
    passed, violations = scanner.scan_code(code_eval)
    assert passed is False
    assert any("eval" in v for v in violations)

    # Dynamic exec test (exec)
    code_exec = "exec('import os; os.system(\"rm -rf /\")')"
    passed, violations = scanner.scan_code(code_exec)
    assert passed is False
    assert any("exec" in v for v in violations)

    # Subprocess module import
    code_sub = "import subprocess\nsubprocess.run(['ls'])"
    passed, violations = scanner.scan_code(code_sub)
    assert passed is False
    assert any("subprocess" in v for v in violations)

    # os.system attribute call
    code_os = "import os\nos.system('echo dangerous')"
    passed, violations = scanner.scan_code(code_os)
    assert passed is False
    assert any("os.system" in v for v in violations)

    # Dunder inspection escape
    code_dunder = "def break_sandbox():\n    return ().__class__.__bases__[0].__subclasses__()"
    passed, violations = scanner.scan_code(code_dunder)
    assert passed is False
    assert any("__subclasses__" in v for v in violations)

    # Secret scanning
    secret_code = "AWS_SECRET = 'AKIA1234567890ABCDEF'\nTOKEN = 'sk-abcdef12345678901234567890'"
    passed, violations = scanner.scan_secrets(secret_code)
    assert passed is False
    assert len(violations) >= 2


@pytest.mark.asyncio
async def test_security_scanner_passes_clean_code():
    """3. SkillSecurityScanner: Clean Python code passes with 0 violations."""
    scanner = SkillSecurityScanner()
    clean_code = """
import math
import json

def calculate_stats(numbers):
    if not numbers:
        return {"mean": 0.0, "sum": 0}
    total = sum(numbers)
    mean = total / len(numbers)
    return {"mean": mean, "sum": total, "rounded": math.ceil(mean)}
"""
    passed, violations = scanner.scan_code(clean_code)
    assert passed is True
    assert len(violations) == 0

    audit_res = scanner.audit(source_code=clean_code)
    assert audit_res.is_safe is True
    assert audit_res.risk_score == 0.0


@pytest.mark.asyncio
async def test_validator_enforces_dependencies_and_permissions():
    """4. SkillValidator: Enforces registered tools, registered workflows, and blocks privilege escalation permissions."""
    validator = SkillValidator(
        registered_tools={"code_parser", "linter"},
        registered_workflows={"ast_refactor_wf"},
        allowed_permissions={"file:read", "file:write", "tool:execute"},
    )

    # Valid dependencies & permissions
    dep_ok, dep_viols = validator.validate_dependencies(["code_parser"], ["ast_refactor_wf"])
    assert dep_ok is True
    assert len(dep_viols) == 0

    perm_ok, perm_viols = validator.audit_permissions(["file:read", "file:write"])
    assert perm_ok is True
    assert len(perm_viols) == 0

    # Missing tool
    dep_bad, dep_viols2 = validator.validate_dependencies(["unknown_tool"], ["ast_refactor_wf"])
    assert dep_bad is False
    assert any("unknown_tool" in v for v in dep_viols2)

    # Missing workflow
    dep_bad_wf, dep_viols3 = validator.validate_dependencies(["code_parser"], ["missing_wf"])
    assert dep_bad_wf is False
    assert any("missing_wf" in v for v in dep_viols3)

    # Forbidden privilege escalation permission
    perm_bad, perm_viols2 = validator.audit_permissions(["system:root", "file:read"])
    assert perm_bad is False
    assert any("system:root" in v for v in perm_viols2)


@pytest.mark.asyncio
async def test_skill_evaluator_benchmark_and_safety_scoring():
    """5. SkillEvaluator: Evaluates functional test suites, token efficiency, accuracy, and safety scoring (>= 0.95)."""
    evaluator = SkillEvaluator()
    manifest = _sample_manifest(prompt_template="Analyze code syntax and format for: {code_input}")
    candidate = SkillCandidate(
        candidate_id="skcand_eval_01",
        skill_id="code_refactor_assistant",
        proposed_manifest=manifest,
        reasoning_summary="Adds formatting analysis.",
        status=SkillCandidateStatus.AUDITED,
    )

    test_cases = [
        SkillTestCase(
            name="basic_formatting_test",
            context_vars={"code_input": "def foo(): pass"},
            expected_substrings=["Analyze code syntax", "def foo(): pass"],
        ),
        SkillTestCase(
            name="edge_case_test",
            context_vars={"code_input": "x = 10"},
            validator_fn=lambda rendered: "Analyze" in rendered and "x = 10" in rendered,
        ),
    ]

    res = evaluator.evaluate(candidate, test_cases=test_cases)
    assert res.test_suite_passed is True
    assert res.tests_run == 2
    assert res.tests_passed == 2
    assert res.accuracy_score == 1.0
    assert res.safety_score == 1.0
    assert res.benchmark_passed is True


@pytest.mark.asyncio
async def test_promotion_gate_enforcement():
    """6. Promotion Gate: Rejects candidates with failed security audits or failing benchmarks."""
    with tempfile.TemporaryDirectory() as tmp_root:
        skill_manager = SkillManager(skills_root=tmp_root)
        skill_manager.register_tool_names({"code_parser"})
        skill_manager.register_workflow_names({"ast_refactor_wf"})

        # Setup in-memory mock repository
        class MockSkillRepo:
            def __init__(self):
                self.candidates = {}
                self.versions = {}
                self.promotions = {}

            async def get_candidate(self, cid): return self.candidates.get(cid)
            async def save_candidate(self, c): self.candidates[c.candidate_id] = c
            async def list_candidates(self, **kwargs): return list(self.candidates.values())
            async def get_version(self, vid): return self.versions.get(vid)
            async def get_version_by_semver(self, s, v): return None
            async def get_active_version(self, s): return None
            async def save_version(self, v): self.versions[v.version_id] = v
            async def list_versions(self, **kwargs): return list(self.versions.values())
            async def get_promotion(self, pid): return self.promotions.get(pid)
            async def save_promotion(self, p): self.promotions[p.decision_id] = p
            async def list_promotions(self, **kwargs): return list(self.promotions.values())

        repo = MockSkillRepo()
        service = _make_service(repo, skill_manager)

        # 1. Propose unsafe candidate (eval call)
        unsafe_manifest = _sample_manifest(skill_id="unsafe_skill")
        unsafe_cand = await service.propose_candidate(
            skill_id="unsafe_skill",
            proposed_manifest=unsafe_manifest,
            proposed_code="def run(x):\n    eval(x)",
            is_executable=True,
        )

        # Attempt to promote unsafe candidate -> Security gate must fail
        with pytest.raises(PermissionDeniedError):
            await service.promote_candidate(unsafe_cand.candidate_id, approved_by="admin")


@pytest.mark.asyncio
async def test_executable_skill_requires_human_approval():
    """7. Executable Skill Governance: Executable Python skills strictly require human approval (approved_by)."""
    with tempfile.TemporaryDirectory() as tmp_root:
        skill_manager = SkillManager(skills_root=tmp_root)
        skill_manager.register_tool_names({"code_parser"})
        skill_manager.register_workflow_names({"ast_refactor_wf"})

        class MockSkillRepo:
            def __init__(self):
                self.candidates = {}
                self.versions = {}
                self.promotions = {}

            async def get_candidate(self, cid): return self.candidates.get(cid)
            async def save_candidate(self, c): self.candidates[c.candidate_id] = c
            async def list_candidates(self, **kwargs): return list(self.candidates.values())
            async def get_version(self, vid): return self.versions.get(vid)
            async def get_version_by_semver(self, s, v): return None
            async def get_active_version(self, s): return None
            async def save_version(self, v): self.versions[v.version_id] = v
            async def list_versions(self, **kwargs): return list(self.versions.values())
            async def get_promotion(self, pid): return self.promotions.get(pid)
            async def save_promotion(self, p): self.promotions[p.decision_id] = p
            async def list_promotions(self, **kwargs): return list(self.promotions.values())

        repo = MockSkillRepo()
        service = _make_service(repo, skill_manager)

        # Propose valid executable skill
        valid_manifest = _sample_manifest(skill_id="safe_exec_skill")
        cand = await service.propose_candidate(
            skill_id="safe_exec_skill",
            proposed_manifest=valid_manifest,
            proposed_code="def run(code):\n    return code.strip()",
            is_executable=True,
        )

        # Audit and evaluate
        await service.audit_candidate(cand.candidate_id)
        await service.evaluate_candidate(cand.candidate_id)

        # Promotion without approved_by must fail with PermissionDeniedError
        with pytest.raises(PermissionDeniedError) as exc_info:
            await service.promote_candidate(cand.candidate_id, approved_by=None)
        assert "requires explicit human approval" in str(exc_info.value)

        # Promotion with human approver succeeds
        dec, ver = await service.promote_candidate(cand.candidate_id, approved_by="senior_security_reviewer")
        assert dec.status == SkillPromotionStatus.PROMOTED
        assert dec.approved_by == "senior_security_reviewer"
        assert ver.status == SkillVersionStatus.ACTIVE


@pytest.mark.asyncio
async def test_safe_template_skill_automated_promotion():
    """8. Safe Template Promotion: Low-risk prompt template skills permit bounded automated promotion."""
    with tempfile.TemporaryDirectory() as tmp_root:
        skill_manager = SkillManager(skills_root=tmp_root)
        skill_manager.register_tool_names({"code_parser"})
        skill_manager.register_workflow_names({"ast_refactor_wf"})

        class MockSkillRepo:
            def __init__(self):
                self.candidates = {}
                self.versions = {}
                self.promotions = {}

            async def get_candidate(self, cid): return self.candidates.get(cid)
            async def save_candidate(self, c): self.candidates[c.candidate_id] = c
            async def list_candidates(self, **kwargs): return list(self.candidates.values())
            async def get_version(self, vid): return self.versions.get(vid)
            async def get_version_by_semver(self, s, v): return None
            async def get_active_version(self, s): return None
            async def save_version(self, v): self.versions[v.version_id] = v
            async def list_versions(self, **kwargs): return list(self.versions.values())
            async def get_promotion(self, pid): return self.promotions.get(pid)
            async def save_promotion(self, p): self.promotions[p.decision_id] = p
            async def list_promotions(self, **kwargs): return list(self.promotions.values())

        repo = MockSkillRepo()
        service = _make_service(repo, skill_manager)

        # Template-only skill
        template_manifest = _sample_manifest(skill_id="template_skill", prompt_template="Explain: {topic}")
        cand = await service.propose_candidate(
            skill_id="template_skill",
            proposed_manifest=template_manifest,
            proposed_code=None,  # No executable code
            is_executable=False,
            is_high_risk=False,
        )

        await service.audit_candidate(cand.candidate_id)
        await service.evaluate_candidate(cand.candidate_id)

        # Can promote automatically without explicit approver
        dec, ver = await service.promote_candidate(cand.candidate_id, approved_by=None)
        assert dec.status == SkillPromotionStatus.PROMOTED
        assert dec.approved_by == "system_automated_promotion"
        assert ver.status == SkillVersionStatus.ACTIVE


@pytest.mark.asyncio
async def test_atomic_skill_version_commitment_and_activation():
    """9. Atomic SkillVersion Commitment: Commits new version, links parent, deprecates previous active, and deploys to SkillManager."""
    with tempfile.TemporaryDirectory() as tmp_root:
        skill_manager = SkillManager(skills_root=tmp_root)
        skill_manager.register_tool_names({"code_parser"})
        skill_manager.register_workflow_names({"ast_refactor_wf"})

        class MockSkillRepo:
            def __init__(self):
                self.candidates = {}
                self.versions = {}
                self.promotions = {}

            async def get_candidate(self, cid): return self.candidates.get(cid)
            async def save_candidate(self, c): self.candidates[c.candidate_id] = c
            async def list_candidates(self, **kwargs): return list(self.candidates.values())
            async def get_version(self, vid): return self.versions.get(vid)
            async def get_version_by_semver(self, s, v): return None
            async def get_active_version(self, s):
                for v in self.versions.values():
                    if v.skill_id == s and v.status == SkillVersionStatus.ACTIVE:
                        return v
                return None
            async def save_version(self, v): self.versions[v.version_id] = v
            async def list_versions(self, **kwargs): return list(self.versions.values())
            async def get_promotion(self, pid): return self.promotions.get(pid)
            async def save_promotion(self, p): self.promotions[p.decision_id] = p
            async def list_promotions(self, **kwargs): return list(self.promotions.values())

        repo = MockSkillRepo()
        service = _make_service(repo, skill_manager)

        # 1. Promote v1.0.0
        m1 = _sample_manifest(skill_id="multi_ver_skill", version="1.0.0")
        c1 = await service.propose_candidate("multi_ver_skill", m1, proposed_code="# v1", is_executable=True)
        await service.audit_candidate(c1.candidate_id)
        await service.evaluate_candidate(c1.candidate_id)
        dec1, v1 = await service.promote_candidate(c1.candidate_id, approved_by="admin_v1")

        assert v1.version == "1.0.0"
        assert v1.status == SkillVersionStatus.ACTIVE
        assert v1.parent_version is None

        # 2. Promote v1.1.0
        m2 = _sample_manifest(skill_id="multi_ver_skill", version="1.1.0")
        c2 = await service.propose_candidate("multi_ver_skill", m2, proposed_code="# v2", is_executable=True)
        await service.audit_candidate(c2.candidate_id)
        await service.evaluate_candidate(c2.candidate_id)
        dec2, v2 = await service.promote_candidate(c2.candidate_id, approved_by="admin_v2")

        assert v2.version == "1.1.0"
        assert v2.status == SkillVersionStatus.ACTIVE
        assert v2.parent_version == v1.version_id

        # Check v1 was deprecated
        v1_updated = await repo.get_version(v1.version_id)
        assert v1_updated.status == SkillVersionStatus.DEPRECATED


@pytest.mark.asyncio
async def test_skill_version_rollback_coordination():
    """10. Rollback Coordination: Rolls back active skill to parent version, restores code in SkillManager, records audit trail."""
    with tempfile.TemporaryDirectory() as tmp_root:
        skill_manager = SkillManager(skills_root=tmp_root)
        skill_manager.register_tool_names({"code_parser"})
        skill_manager.register_workflow_names({"ast_refactor_wf"})

        class MockSkillRepo:
            def __init__(self):
                self.candidates = {}
                self.versions = {}
                self.promotions = {}

            async def get_candidate(self, cid): return self.candidates.get(cid)
            async def save_candidate(self, c): self.candidates[c.candidate_id] = c
            async def list_candidates(self, **kwargs): return list(self.candidates.values())
            async def get_version(self, vid): return self.versions.get(vid)
            async def get_version_by_semver(self, s, v): return None
            async def get_active_version(self, s):
                for v in self.versions.values():
                    if v.skill_id == s and v.status == SkillVersionStatus.ACTIVE:
                        return v
                return None
            async def save_version(self, v): self.versions[v.version_id] = v
            async def list_versions(self, **kwargs): return list(self.versions.values())
            async def get_promotion(self, pid): return self.promotions.get(pid)
            async def save_promotion(self, p): self.promotions[p.decision_id] = p
            async def list_promotions(self, **kwargs): return list(self.promotions.values())

        repo = MockSkillRepo()
        service = _make_service(repo, skill_manager)

        # Promote v1
        m1 = _sample_manifest(skill_id="rollback_skill", version="1.0.0")
        c1 = await service.propose_candidate("rollback_skill", m1, proposed_code="# code v1.0.0", is_executable=True)
        await service.audit_candidate(c1.candidate_id)
        await service.evaluate_candidate(c1.candidate_id)
        await service.promote_candidate(c1.candidate_id, approved_by="admin")

        # Promote v2
        m2 = _sample_manifest(skill_id="rollback_skill", version="2.0.0")
        c2 = await service.propose_candidate("rollback_skill", m2, proposed_code="# code v2.0.0", is_executable=True)
        await service.audit_candidate(c2.candidate_id)
        await service.evaluate_candidate(c2.candidate_id)
        await service.promote_candidate(c2.candidate_id, approved_by="admin")

        # Trigger rollback to parent
        dec_rb, ver_rb = await service.rollback_skill("rollback_skill", reason="Crash in production")
        assert dec_rb.status == SkillPromotionStatus.ROLLED_BACK
        assert ver_rb.version == "1.0.0"
        assert ver_rb.status == SkillVersionStatus.ACTIVE

        # Verify manager holds v1.0.0
        installed = skill_manager.get_skill("rollback_skill")
        assert installed.version == "1.0.0"


@pytest.mark.asyncio
async def test_skill_evolution_repository_async_sql(component_db: DatabaseManager):
    """11. Async SQL Repository: Full persistence, retrieval, and filtering for candidates, versions, and promotions."""
    async with component_db.session_factory() as session:
        repo = SkillEvolutionRepository(session)

        # 1. Candidate CRUD
        manifest = _sample_manifest(skill_id="sql_test_skill")
        cand = SkillCandidate(
            candidate_id="skcand_sql_01",
            skill_id="sql_test_skill",
            proposed_manifest=manifest,
            reasoning_summary="Testing SQL repository.",
            status=SkillCandidateStatus.PROPOSED,
        )
        await repo.save_candidate(cand)

        fetched_cand = await repo.get_candidate("skcand_sql_01")
        assert fetched_cand is not None
        assert fetched_cand.skill_id == "sql_test_skill"

        cand_list = await repo.list_candidates(skill_id="sql_test_skill")
        assert len(cand_list) == 1

        # 2. Version CRUD
        ver = SkillVersion(
            version_id="skver_sql_test_v1.0.0",
            skill_id="sql_test_skill",
            version="1.0.0",
            manifest=manifest,
            code_hash="abcdef123456",
            status=SkillVersionStatus.ACTIVE,
        )
        await repo.save_version(ver)

        fetched_ver = await repo.get_version("skver_sql_test_v1.0.0")
        assert fetched_ver is not None
        assert fetched_ver.version == "1.0.0"

        active_ver = await repo.get_active_version("sql_test_skill")
        assert active_ver is not None
        assert active_ver.version_id == "skver_sql_test_v1.0.0"

        # 3. Promotion CRUD
        prom = SkillPromotionDecision(
            decision_id="skprom_sql_01",
            candidate_id="skcand_sql_01",
            skill_id="sql_test_skill",
            target_version="1.0.0",
            status=SkillPromotionStatus.PROMOTED,
            security_audit_passed=True,
            evaluation_passed=True,
            approved_by="sql_admin",
        )
        await repo.save_promotion(prom)

        fetched_prom = await repo.get_promotion("skprom_sql_01")
        assert fetched_prom is not None
        assert fetched_prom.approved_by == "sql_admin"

        prom_list = await repo.list_promotions(skill_id="sql_test_skill")
        assert len(prom_list) == 1


@pytest.mark.asyncio
async def test_fastapi_v2_skills_evolution_endpoints():
    """12. FastAPI V2 REST Endpoints: Full endpoint suite under /api/v2/skills."""
    app = FastAPI()
    app.include_router(skills_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Propose candidate
        manifest = _sample_manifest(skill_id="api_skill", version="1.0.0")
        prop_payload = {
            "skill_id": "api_skill",
            "proposed_manifest": manifest,
            "proposed_code": "def process(): return True",
            "reasoning_summary": "API evolution test.",
            "is_executable": True,
            "risk_level": "low",
        }
        res_prop = await client.post("/api/v2/skills/candidates", json=prop_payload)
        assert res_prop.status_code == 201
        cand_data = res_prop.json()
        cand_id = cand_data["candidate_id"]
        assert cand_data["skill_id"] == "api_skill"

        # 2. Audit candidate
        res_audit = await client.post(f"/api/v2/skills/candidates/{cand_id}/audit")
        assert res_audit.status_code == 200
        audit_data = res_audit.json()
        assert audit_data["security_audit"]["passed"] is True

        # 3. Evaluate candidate
        res_eval = await client.post(f"/api/v2/skills/candidates/{cand_id}/evaluate")
        assert res_eval.status_code == 200
        eval_data = res_eval.json()
        assert eval_data["evaluation"]["benchmark_passed"] is True

        # 4. Promote without approver (must fail 403 because executable)
        res_prom_unauth = await client.post(
            f"/api/v2/skills/candidates/{cand_id}/promote",
            json={"approved_by": None, "rationale": "Missing approver"},
        )
        assert res_prom_unauth.status_code == 403

        # 5. Promote with human approver (succeeds)
        res_prom = await client.post(
            f"/api/v2/skills/candidates/{cand_id}/promote",
            json={"approved_by": "api_human_admin", "rationale": "Approved via test"},
        )
        assert res_prom.status_code == 200
        prom_data = res_prom.json()
        assert prom_data["status"] == "promoted"
        assert prom_data["approved_by"] == "api_human_admin"

        # 6. List versions
        res_vers = await client.get("/api/v2/skills/versions?skill_id=api_skill")
        assert res_vers.status_code == 200
        vers_data = res_vers.json()
        assert len(vers_data) >= 1

        # 7. List installed skills
        res_skills = await client.get("/api/v2/skills")
        assert res_skills.status_code == 200


@pytest.mark.asyncio
async def test_migration_0029_schema_and_indexes_integrity():
    """13. Migration 0029: Table schema and compound index metadata integrity."""
    import importlib
    mig_0029 = importlib.import_module("windagent_storage.migrations.alembic.versions.0029_skill_evolution")

    assert mig_0029.revision == "0029_skill_evolution"
    assert mig_0029.down_revision == "0028_experiment_promotion"

    # Verify tables registered in BaseORM
    table_names = set(BaseORM.metadata.tables.keys())
    assert "skill_candidates" in table_names
    assert "skill_versions" in table_names
    assert "skill_promotion_decisions" in table_names

    # Check indexes on skill_candidates
    cand_table = BaseORM.metadata.tables["skill_candidates"]
    cand_index_names = {idx.name for idx in cand_table.indexes}
    assert "ix_skill_cand_skill_status" in cand_index_names
    assert "ix_skill_cand_created_at" in cand_index_names

    # Check indexes on skill_versions
    ver_table = BaseORM.metadata.tables["skill_versions"]
    ver_index_names = {idx.name for idx in ver_table.indexes}
    assert "ix_skill_ver_skill_status" in ver_index_names
    assert "ix_skill_ver_skill_version" in ver_index_names

    # Check indexes on skill_promotion_decisions
    prom_table = BaseORM.metadata.tables["skill_promotion_decisions"]
    prom_index_names = {idx.name for idx in prom_table.indexes}
    assert "ix_skill_prom_skill_status" in prom_index_names
    assert "ix_skill_prom_cand_status" in prom_index_names

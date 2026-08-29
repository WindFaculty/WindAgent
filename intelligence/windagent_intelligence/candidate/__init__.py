"""Candidate Learning Package (Phase 9 — ban_ke_hoach_v1 §14, §23, §24).

Exports CandidateGenerator, EligibilityGate, and CandidateService.
"""

from windagent_intelligence.candidate.candidate_generator import CandidateGenerator, generate_candidate_id
from windagent_intelligence.candidate.eligibility_gate import EligibilityGate
from windagent_intelligence.candidate.service import CandidateService

__all__ = [
    "CandidateGenerator",
    "generate_candidate_id",
    "EligibilityGate",
    "CandidateService",
]


"""
Unit tests for WindAgent Phase 14 Legacy Cutover, Feature Flags, and Shadow Execution.
apps/backend/compatibility_shim has been retired as of Phase 6 completion.
"""

import pytest
from windagent_api.bootstrap.feature_flags import FeatureFlagsManager
from windagent_verification.shadow import ShadowExecutionEngine


def test_feature_flags_manager():
    mgr = FeatureFlagsManager()
    assert mgr.is_v2_enabled() is True
    assert mgr.get_flag("WINDAGENT_V2_TASKS") is True

    mgr.set_flag("WINDAGENT_V2_TASKS", False)
    assert mgr.get_flag("WINDAGENT_V2_TASKS") is False


def test_shadow_execution_comparator():
    engine = ShadowExecutionEngine()

    def v1_calc(a, b):
        return a + b

    def v2_calc(a, b):
        return a + b

    # Parity match
    res_match = engine.compare_read_only("sum", v1_calc, v2_calc, 10, 20)
    assert res_match.parity_matched is True
    assert res_match.diff_details is None

    # Parity mismatch
    def v2_buggy(a, b):
        return a * b

    res_mismatch = engine.compare_read_only("sum_mismatch", v1_calc, v2_buggy, 10, 20)
    assert res_mismatch.parity_matched is False
    assert res_mismatch.diff_details is not None

    # Destructive operation skip
    res_dest = engine.compare_read_only("delete_task", v1_calc, v2_calc, is_destructive=True)
    assert res_dest.diff_details == "Skipped destructive operation"

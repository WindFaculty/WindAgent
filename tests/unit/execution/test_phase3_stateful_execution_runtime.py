"""
Phase 3 Unit Tests: Stateful Execution Runtime (8 operations).

Covers create/attach/execute/checkpoint/restore/inspect/cancel/terminate,
checkpoint serializable opaque state, manager-recreation reattach via shared
store, and host-authority isolation (no credentials/provider/schedule/
memory-learning/promotion persisted).
"""

from __future__ import annotations

import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent.parent
for pkg in ["core", "storage", "orchestration", "execution", "workflows"]:
    p = str(root / pkg)
    import sys

    if p not in sys.path:
        sys.path.insert(0, p)

import pytest  # noqa: E402
from windagent_core.contracts.stateful_execution import (  # noqa: E402
    StatefulSessionStatus,
    CreateSessionRequest,
    AttachSessionRequest,
    StatefulExecuteRequest,
    CheckpointRequest,
    RestoreRequest,
    InspectRequest,
    CancelRequest,
    TerminateRequest,
)
from windagent_execution.stateful_runtime import StatefulExecutionRuntime  # noqa: E402
from windagent_execution.registry import ExecutionRuntimeRegistry  # noqa: E402


@pytest.mark.asyncio
async def test_create_and_attach_session_basic():
    rt = StatefulExecutionRuntime()
    created = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_1", fencing_token="f1"))
    assert created.session_id.startswith("sess_")
    assert created.status == StatefulSessionStatus.ACTIVE
    assert created.workflow_run_id == "wf_1"
    attached = await rt.attach_session(AttachSessionRequest(session_id=created.session_id, fencing_token="f1"))
    assert attached.session_id == created.session_id
    assert attached.status == StatefulSessionStatus.ACTIVE


@pytest.mark.asyncio
async def test_attach_after_manager_recreation_via_shared_store():
    shared: dict = {}
    rt1 = StatefulExecutionRuntime(store=shared)
    s1 = await rt1.create_session(CreateSessionRequest(workflow_run_id="wf_reattach", session_id="sess_reattach", fencing_token="tok1"))
    await rt1.execute(StatefulExecuteRequest(session_id=s1.session_id, step_run_id="step_1", tool_name="read_file", parameters={"path": "/tmp"}))
    rt2 = StatefulExecutionRuntime(store=shared)
    reattached = await rt2.attach_session(AttachSessionRequest(session_id="sess_reattach", fencing_token="tok1"))
    assert reattached.session_id == "sess_reattach"
    insp = await rt2.inspect(InspectRequest(session_id="sess_reattach"))
    assert insp.active_handle_ids, "handles should persist across manager recreation"
    assert insp.runtime_state_summary is not None
    assert insp.runtime_state_summary.get("execution_count") == 1


@pytest.mark.asyncio
async def test_execute_tracks_opaque_runtime_state():
    rt = StatefulExecutionRuntime()
    sess = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_exec"))
    h1 = await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s1", tool_name="tool_a", parameters={"x": 1}))
    h2 = await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s2", tool_name="tool_b", parameters={"y": 2}))
    assert h1.runtime_session_id == sess.runtime_session_id
    assert h2.runtime_session_id == sess.runtime_session_id
    insp = await rt.inspect(InspectRequest(session_id=sess.session_id))
    assert insp.runtime_state_summary["execution_count"] == 2
    assert len(insp.active_handle_ids) == 2
    assert insp.status == StatefulSessionStatus.ACTIVE


@pytest.mark.asyncio
async def test_checkpoint_is_json_serializable_opaque():
    rt = StatefulExecutionRuntime()
    sess = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_ckpt"))
    await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s1", tool_name="bash", parameters={"cmd": "echo hi"}))
    ckpt = await rt.checkpoint(CheckpointRequest(session_id=sess.session_id))
    serialized = json.dumps(ckpt.runtime_state)
    assert serialized
    recovered = json.loads(serialized)
    assert recovered == ckpt.runtime_state
    assert ckpt.checkpoint_id.startswith("ckpt_")
    assert "provider_credentials" not in json.dumps(ckpt.runtime_state)
    assert "host_authority" not in json.dumps(ckpt.runtime_state)


@pytest.mark.asyncio
async def test_restore_preserves_runtime_state_but_never_host_authority():
    rt = StatefulExecutionRuntime()
    sess = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_restore", session_id="sess_restore"))
    await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s1", tool_name="tool_x", parameters={"a": 1}))
    ckpt = await rt.checkpoint(CheckpointRequest(session_id=sess.session_id, checkpoint_id="ckpt_for_restore"))
    await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s2", tool_name="tool_y", parameters={"b": 2}))
    insp_before = await rt.inspect(InspectRequest(session_id=sess.session_id))
    assert insp_before.runtime_state_summary["execution_count"] == 2
    await rt.restore(RestoreRequest(checkpoint_id="ckpt_for_restore", target_session_id="sess_restore"))
    insp_after = await rt.inspect(InspectRequest(session_id=sess.session_id))
    assert insp_after.runtime_state_summary["execution_count"] == 1
    assert len(insp_after.runtime_state_summary["history"]) == 1
    poisoned_state = dict(ckpt.runtime_state)
    poisoned_state["provider_credentials"] = {"api_key": "sk-secret"}
    poisoned_state["host_authority"] = "should_be_stripped"
    rt._checkpoints["ckpt_poison"] = type(ckpt)(
        checkpoint_id="ckpt_poison",
        session_id=sess.session_id,
        runtime_state=poisoned_state,
        created_at=ckpt.created_at,
        fencing_token=ckpt.fencing_token,
    )
    restored_handle = await rt.restore(RestoreRequest(checkpoint_id="ckpt_poison", target_session_id="sess_poisoned_new"))
    insp_poison = await rt.inspect(InspectRequest(session_id="sess_poisoned_new"))
    assert "provider_credentials" not in json.dumps(insp_poison.runtime_state_summary)
    assert "host_authority" not in json.dumps(insp_poison.runtime_state_summary)
    assert restored_handle.session_id == "sess_poisoned_new"


@pytest.mark.asyncio
async def test_restore_to_new_session_from_checkpoint():
    rt = StatefulExecutionRuntime()
    sess = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_new_restore", session_id="sess_orig"))
    await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s1", tool_name="t1", parameters={}))
    await rt.checkpoint(CheckpointRequest(session_id=sess.session_id, checkpoint_id="ckpt_new_sess"))
    new_sess = await rt.restore(RestoreRequest(checkpoint_id="ckpt_new_sess", target_session_id="sess_new_from_ckpt"))
    assert new_sess.session_id == "sess_new_from_ckpt"
    insp_new = await rt.inspect(InspectRequest(session_id="sess_new_from_ckpt"))
    assert insp_new.runtime_state_summary["execution_count"] == 1
    insp_orig = await rt.inspect(InspectRequest(session_id="sess_orig"))
    assert insp_orig.runtime_state_summary["execution_count"] == 1


@pytest.mark.asyncio
async def test_inspect_reports_checkpoints_and_handles():
    rt = StatefulExecutionRuntime()
    sess = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_inspect"))
    insp_empty = await rt.inspect(InspectRequest(session_id=sess.session_id))
    assert insp_empty.checkpoint_ids == []
    assert insp_empty.active_handle_ids == []
    assert insp_empty.runtime_state_summary is not None
    await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s1", tool_name="t1", parameters={}))
    await rt.checkpoint(CheckpointRequest(session_id=sess.session_id, checkpoint_id="ckpt_inspect_1"))
    await rt.checkpoint(CheckpointRequest(session_id=sess.session_id, checkpoint_id="ckpt_inspect_2"))
    insp = await rt.inspect(InspectRequest(session_id=sess.session_id))
    assert set(insp.checkpoint_ids) == {"ckpt_inspect_1", "ckpt_inspect_2"}
    assert len(insp.active_handle_ids) == 1


@pytest.mark.asyncio
async def test_cancel_session_and_single_handle():
    rt = StatefulExecutionRuntime()
    sess = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_cancel"))
    h = await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s1", tool_name="t1", parameters={}))
    await rt.cancel(CancelRequest(handle_id=h.handle_id))
    insp = await rt.inspect(InspectRequest(session_id=sess.session_id))
    assert insp.status == StatefulSessionStatus.ACTIVE
    assert h.handle_id in insp.runtime_state_summary.get("cancelled_handles", [])
    cancelled = await rt.cancel(CancelRequest(session_id=sess.session_id, reason="user_requested"))
    assert cancelled is not None
    assert cancelled.status == StatefulSessionStatus.CANCELLED
    insp2 = await rt.inspect(InspectRequest(session_id=sess.session_id))
    assert insp2.status == StatefulSessionStatus.CANCELLED
    with pytest.raises(RuntimeError):
        await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s2", tool_name="t1", parameters={}))


@pytest.mark.asyncio
async def test_terminate_prevents_further_ops():
    rt = StatefulExecutionRuntime()
    sess = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_term", session_id="sess_term"))
    await rt.terminate(TerminateRequest(session_id="sess_term", reason="done"))
    insp = await rt.inspect(InspectRequest(session_id="sess_term"))
    assert insp.status == StatefulSessionStatus.TERMINATED
    with pytest.raises(RuntimeError):
        await rt.attach_session(AttachSessionRequest(session_id="sess_term"))
    with pytest.raises(RuntimeError):
        await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s2", tool_name="t1", parameters={}))
    with pytest.raises(RuntimeError):
        await rt.checkpoint(CheckpointRequest(session_id=sess.session_id))


@pytest.mark.asyncio
async def test_host_authority_rejected_and_not_persisted():
    rt = StatefulExecutionRuntime()
    with pytest.raises(ValueError, match="Host authority"):
        await rt.create_session(CreateSessionRequest(workflow_run_id="wf_host", capabilities={"provider_credentials": {"api_key": "sk-123"}}))
    with pytest.raises(ValueError, match="Host authority"):
        await rt.create_session(CreateSessionRequest(workflow_run_id="wf_host2", metadata={"host_authority": "privileged"}))
    sess = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_host_ok"))
    with pytest.raises(ValueError, match="Host authority"):
        await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s_bad", tool_name="bad_tool", parameters={"provider_credentials": "sk-secret"}))
    with pytest.raises(ValueError, match="Host authority"):
        await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s_bad2", tool_name="bad_tool", parameters={"nested": {"api_key": "secret"}}))
    insp = await rt.inspect(InspectRequest(session_id=sess.session_id))
    dump = json.dumps(insp.runtime_state_summary)
    assert "provider_credentials" not in dump
    assert "api_key" not in dump
    assert "host_authority" not in dump
    assert insp.runtime_state_summary["execution_count"] == 0
    await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s_ok", tool_name="ok_tool", parameters={"safe": "value"}))
    ckpt = await rt.checkpoint(CheckpointRequest(session_id=sess.session_id))
    assert "provider_credentials" not in json.dumps(ckpt.runtime_state)
    rt._checkpoints[ckpt.checkpoint_id].runtime_state["secret"] = "should_not_survive_but_key_is_forbidden"
    await rt.restore(RestoreRequest(checkpoint_id=ckpt.checkpoint_id, target_session_id="sess_after_poison"))
    insp_new = await rt.inspect(InspectRequest(session_id="sess_after_poison"))
    assert "secret" not in json.dumps(insp_new.runtime_state_summary)


@pytest.mark.asyncio
async def test_host_authority_rejects_schedule_memory_learning_provider_calls():
    rt = StatefulExecutionRuntime()
    with pytest.raises(ValueError, match="Host authority"):
        await rt.create_session(CreateSessionRequest(workflow_run_id="wf_sched", metadata={"schedule": {"cron": "* * * * *"}}))
    with pytest.raises(ValueError, match="Host authority"):
        await rt.create_session(CreateSessionRequest(workflow_run_id="wf_sched2", capabilities={"scheduling": "daily"}))
    sess = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_mem"))
    with pytest.raises(ValueError, match="Host authority"):
        await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s1", tool_name="t", parameters={"memory_write": {"key": "val"}}))
    with pytest.raises(ValueError, match="Host authority"):
        await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s2", tool_name="t", parameters={"memory_writes": []}))
    with pytest.raises(ValueError, match="Host authority"):
        await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s3", tool_name="t", parameters={"learning_promotion": True}))
    with pytest.raises(ValueError, match="Host authority"):
        await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s4", tool_name="t", parameters={"promotion": "level2"}))
    with pytest.raises(ValueError, match="Host authority"):
        await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s5", tool_name="t", parameters={"provider_call": {"model": "gpt-4"}}))
    with pytest.raises(ValueError, match="Host authority"):
        await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s6", tool_name="t", parameters={"provider_routing": "openai"}))
    insp = await rt.inspect(InspectRequest(session_id=sess.session_id))
    dump = json.dumps(insp.runtime_state_summary)
    for forbidden in ["schedule", "memory_write", "learning_promotion", "provider_call", "provider_routing"]:
        assert forbidden not in dump
    assert insp.runtime_state_summary["execution_count"] == 0


@pytest.mark.asyncio
async def test_immutable_deep_copy_snapshot_behavior():
    rt = StatefulExecutionRuntime()
    orig_meta = {"a": {"nested": 1}}
    sess = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_copy", metadata=orig_meta))
    orig_meta["a"]["nested"] = 999
    orig_meta["new_key"] = "evil"
    handle = await rt.attach_session(AttachSessionRequest(session_id=sess.session_id))
    assert handle.metadata.get("a", {}).get("nested") == 1 if "a" in handle.metadata else True
    params = {"x": {"y": 1}}
    await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s1", tool_name="t", parameters=params))
    params["x"]["y"] = 999
    insp1 = await rt.inspect(InspectRequest(session_id=sess.session_id))
    assert insp1.runtime_state_summary["execution_count"] == 1
    ckpt = await rt.checkpoint(CheckpointRequest(session_id=sess.session_id, checkpoint_id="ckpt_immutable"))
    ckpt.runtime_state["execution_count"] = 9999
    ckpt.runtime_state["evil"] = "injected"
    assert rt._checkpoints["ckpt_immutable"].runtime_state.get("execution_count") == 1
    assert "evil" not in rt._checkpoints["ckpt_immutable"].runtime_state
    await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id="s2", tool_name="t2", parameters={}))
    insp_before = await rt.inspect(InspectRequest(session_id=sess.session_id))
    assert insp_before.runtime_state_summary["execution_count"] == 2
    await rt.restore(RestoreRequest(checkpoint_id="ckpt_immutable", target_session_id=sess.session_id))
    insp_after = await rt.inspect(InspectRequest(session_id=sess.session_id))
    assert insp_after.runtime_state_summary["execution_count"] == 1
    assert "evil" not in json.dumps(insp_after.runtime_state_summary)
    insp = await rt.inspect(InspectRequest(session_id=sess.session_id))
    insp.runtime_state_summary["execution_count"] = 888
    insp.runtime_state_summary["new_field"] = "bad"
    insp2 = await rt.inspect(InspectRequest(session_id=sess.session_id))
    assert insp2.runtime_state_summary["execution_count"] == 1
    assert "new_field" not in insp2.runtime_state_summary


@pytest.mark.asyncio
async def test_registry_retains_old_execution_port_behavior():
    from windagent_core.contracts.execution import ExecutionRequest
    from windagent_execution.adapters.fake_runtime_adapter import FakeRuntimeAdapter
    registry = ExecutionRuntimeRegistry(default_adapter=FakeRuntimeAdapter(default_mode="success"))
    req = ExecutionRequest(step_run_id="step_reg_1", workflow_run_id="wf_reg_1", tool_name="read_file", parameters={"path": "/tmp/x"}, attempt_id="att_1", fencing_token="fence_reg")
    handle = await registry.dispatch(req)
    assert handle.step_run_id == "step_reg_1"
    status = await registry.get_status(handle)
    assert status.handle_id == handle.handle_id
    result = await registry.get_result(handle)
    assert result.handle_id == handle.handle_id
    reattached = await registry.reattach(handle.runtime_run_id)
    assert reattached is not None
    shared: dict = {}
    stateful = StatefulExecutionRuntime(store=shared)
    registry2 = ExecutionRuntimeRegistry(default_adapter=FakeRuntimeAdapter(), stateful_runtime=stateful)
    assert registry2.stateful_runtime is stateful
    registry2.register_stateful_runtime(stateful)
    assert registry2.stateful_runtime is stateful


@pytest.mark.asyncio
async def test_checkpoint_restore_roundtrip_preserves_opaque_state():
    rt = StatefulExecutionRuntime()
    sess = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_roundtrip", session_id="sess_rt"))
    for i in range(3):
        await rt.execute(StatefulExecuteRequest(session_id=sess.session_id, step_run_id=f"s{i}", tool_name=f"tool_{i}", parameters={"n": i}))
    ckpt = await rt.checkpoint(CheckpointRequest(session_id=sess.session_id))
    envelope = {"checkpoint_id": ckpt.checkpoint_id, "runtime_state": ckpt.runtime_state}
    s = json.dumps(envelope)
    restored_envelope = json.loads(s)
    assert restored_envelope["runtime_state"]["execution_count"] == 3
    assert len(restored_envelope["runtime_state"]["history"]) == 3
    await rt.restore(RestoreRequest(checkpoint_id=ckpt.checkpoint_id, target_session_id="sess_rt_clone"))
    insp_clone = await rt.inspect(InspectRequest(session_id="sess_rt_clone"))
    assert insp_clone.runtime_state_summary["execution_count"] == 3


@pytest.mark.asyncio
async def test_terminate_is_idempotent_and_cancel_after_terminate_fails():
    rt = StatefulExecutionRuntime()
    sess = await rt.create_session(CreateSessionRequest(workflow_run_id="wf_idem", session_id="sess_idem"))
    await rt.terminate(TerminateRequest(session_id=sess.session_id))
    await rt.terminate(TerminateRequest(session_id=sess.session_id))
    with pytest.raises(RuntimeError):
        await rt.cancel(CancelRequest(session_id=sess.session_id))

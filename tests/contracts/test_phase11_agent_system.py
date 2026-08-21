"""
Phase 11 — Agent System Convergence Contract Tests.
Verifies:
- AgentDefinition ≠ AgentInstance semantic separation
- AgentDefinition CRUD & optimistic locking
- AgentInstance runtime lifecycle (start, stop, restart)
- Canonical Conversation projections (agents, tasks, events)
- Canonical Task state machine (PENDING, READY, RUNNING, BLOCKED, SUCCEEDED, FAILED, CANCELLED)
- Workflow Catalog, execution runs, derived progress percentages, pause/resume/cancel/retry
- Full cross-domain agent and workflow integration flow
"""
from __future__ import annotations



# ─────────────────────────────────────────────────────────────────────────────
# Phase 11.1 & 11.2 — Agent Definitions & Instances
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentDefinitions:
    def test_list_definitions(self, client):
        r = client.get("/api/v3/agent-definitions")
        assert r.status_code == 200
        defs = r.json()
        assert isinstance(defs, list)
        assert len(defs) >= 4
        roles = {d["role"] for d in defs}
        assert "orchestrator" in roles
        assert "coder" in roles

    def test_create_definition(self, client):
        payload = {
            "name": "Custom Security Agent",
            "slug": "custom-sec",
            "role": "reviewer",
            "description": "Scans AST for security vulnerabilities",
            "model_policy": {"family": "claude"},
        }
        r = client.post("/api/v3/agent-definitions", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert data["id"].startswith("def-")
        assert data["name"] == "Custom Security Agent"
        assert data["slug"] == "custom-sec"
        assert data["version"] == 1

    def test_get_definition_detail(self, client):
        r = client.get("/api/v3/agent-definitions/def-orchestrator-01")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "def-orchestrator-01"
        assert data["role"] == "orchestrator"

    def test_update_definition_optimistic_locking(self, client):
        r = client.get("/api/v3/agent-definitions/def-coder-01")
        assert r.status_code == 200
        cur = r.json()
        cur_version = cur["version"]

        # Conflict check with stale version
        conflict_payload = {
            "name": "Stale Coder",
            "expected_version": cur_version + 99,
        }
        r_conf = client.patch("/api/v3/agent-definitions/def-coder-01", json=conflict_payload)
        assert r_conf.status_code == 409

        # Successful update
        ok_payload = {
            "description": "Updated coder description for Phase 11",
            "expected_version": cur_version,
        }
        r_ok = client.patch("/api/v3/agent-definitions/def-coder-01", json=ok_payload)
        assert r_ok.status_code == 200
        assert r_ok.json()["version"] == cur_version + 1

    def test_get_activity_and_metrics(self, client):
        r_act = client.get("/api/v3/agent-definitions/def-orchestrator-01/activity")
        assert r_act.status_code == 200
        assert isinstance(r_act.json(), list)

        r_metrics = client.get("/api/v3/agents/metrics")
        assert r_metrics.status_code == 200
        metrics = r_metrics.json()
        assert "total" in metrics
        assert "running" in metrics
        assert "idle" in metrics
        assert "tasks_running" in metrics


class TestAgentInstances:
    def test_list_instances(self, client):
        r = client.get("/api/v3/agent-instances")
        assert r.status_code == 200
        instances = r.json()
        assert isinstance(instances, list)
        assert len(instances) >= 1

    def test_launch_instance(self, client):
        payload = {
            "definition_id": "def-coder-01",
            "conversation_id": "conv-default-01",
            "canonical_model_id": "claude-3-5-sonnet",
        }
        r = client.post("/api/v3/agent-instances", json=payload)
        assert r.status_code == 201
        inst = r.json()
        assert inst["id"].startswith("inst-")
        assert inst["status"] == "RUNNING"

    def test_start_stop_restart_lifecycle(self, client):
        r = client.get("/api/v3/agent-instances/inst-orch-01")
        assert r.status_code == 200

        # Stop
        r_stop = client.post("/api/v3/agent-instances/inst-orch-01/stop")
        assert r_stop.status_code == 200
        assert r_stop.json()["status"] == "TERMINATED"

        # Start
        r_start = client.post("/api/v3/agent-instances/inst-orch-01/start")
        assert r_start.status_code == 200
        assert r_start.json()["status"] == "RUNNING"

        # Restart
        r_restart = client.post("/api/v3/agent-instances/inst-orch-01/restart")
        assert r_restart.status_code == 200
        assert r_restart.json()["status"] == "RUNNING"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 11.3 — Conversations & Projections
# ─────────────────────────────────────────────────────────────────────────────

class TestConversations:
    def test_list_conversations(self, client):
        r = client.get("/api/v3/conversations")
        assert r.status_code == 200
        convs = r.json()
        assert isinstance(convs, list)
        assert len(convs) >= 1

    def test_create_conversation(self, client):
        payload = {
            "title": "Feature Spec Implementation",
            "objective": "Build and verify Phase 11 architecture",
        }
        r = client.post("/api/v3/conversations", json=payload)
        assert r.status_code == 201
        conv = r.json()
        assert conv["id"].startswith("conv-")
        assert conv["status"] == "ACTIVE"
        assert conv["orchestrator_instance_id"] is not None

    def test_get_conversation_projections(self, client):
        r = client.get("/api/v3/conversations/conv-default-01")
        assert r.status_code == 200
        detail = r.json()
        assert "conversation" in detail
        assert "agents" in detail
        assert "tasks" in detail
        assert "events" in detail

    def test_get_conversation_subresources(self, client):
        r_agents = client.get("/api/v3/conversations/conv-default-01/agents")
        assert r_agents.status_code == 200
        assert isinstance(r_agents.json(), list)

        r_tasks = client.get("/api/v3/conversations/conv-default-01/tasks")
        assert r_tasks.status_code == 200
        assert isinstance(r_tasks.json(), list)

        r_events = client.get("/api/v3/conversations/conv-default-01/events")
        assert r_events.status_code == 200
        assert isinstance(r_events.json(), list)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 11.4 — Tasks & State Machine
# ─────────────────────────────────────────────────────────────────────────────

class TestTasks:
    def test_list_tasks(self, client):
        r = client.get("/api/v3/tasks?conversation_id=conv-default-01")
        assert r.status_code == 200
        tasks = r.json()
        assert isinstance(tasks, list)
        assert len(tasks) >= 3

    def test_create_task(self, client):
        payload = {
            "conversation_id": "conv-default-01",
            "objective": "Deploy build artifacts to test cluster",
            "dependencies": ["task-01"],
            "concurrency_group": "deploy",
        }
        r = client.post("/api/v3/tasks", json=payload)
        assert r.status_code == 201
        task = r.json()
        assert task["id"].startswith("task-")
        assert task["state"] == "PENDING"
        assert "task-01" in task["dependencies"]

    def test_update_task_optimistic_locking(self, client):
        r = client.get("/api/v3/tasks/task-02")
        assert r.status_code == 200
        cur = r.json()
        cur_version = cur["version"]

        # Conflict check
        r_conf = client.patch("/api/v3/tasks/task-02", json={"state": "SUCCEEDED", "expected_version": cur_version + 50})
        assert r_conf.status_code == 409

        # Success update
        r_ok = client.patch("/api/v3/tasks/task-02", json={"state": "SUCCEEDED", "expected_version": cur_version})
        assert r_ok.status_code == 200
        assert r_ok.json()["state"] == "SUCCEEDED"

    def test_invalid_task_state_rejected(self, client):
        r = client.get("/api/v3/tasks/task-03")
        cur_version = r.json()["version"]
        r_inv = client.patch("/api/v3/tasks/task-03", json={"state": "INVALID_STATE_FOO", "expected_version": cur_version})
        assert r_inv.status_code in (422, 400)

    def test_cancel_and_retry_task(self, client):
        r_cancel = client.post("/api/v3/tasks/task-03/cancel")
        assert r_cancel.status_code == 200
        assert r_cancel.json()["state"] == "CANCELLED"

        r_retry = client.post("/api/v3/tasks/task-03/retry")
        assert r_retry.status_code == 200
        assert r_retry.json()["state"] == "READY"
        assert r_retry.json()["attempts"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Phase 11.8 & 11.9 — Workflows & Progress Derivation
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkflows:
    def test_list_workflows(self, client):
        r = client.get("/api/v3/workflows")
        assert r.status_code == 200
        wfs = r.json()
        assert isinstance(wfs, list)
        assert len(wfs) >= 2

    def test_create_workflow(self, client):
        payload = {
            "name": "Benchmark Evaluation Pipeline",
            "type": "Eval",
            "trigger": "Manual",
            "steps": [
                {"id": "s1", "name": "Load Dataset"},
                {"id": "s2", "name": "Evaluate Metrics"},
            ],
            "acceptance_criteria": ["All metrics above 90%"],
        }
        r = client.post("/api/v3/workflows", json=payload)
        assert r.status_code == 201
        wf = r.json()
        assert wf["id"].startswith("wf-")
        assert len(wf["steps"]) == 2

    def test_trigger_run_and_progress_derivation(self, client):
        r_trigger = client.post("/api/v3/workflow-runs", json={"workflow_id": "wf-kronos-01"})
        assert r_trigger.status_code == 201
        run = r_trigger.json()
        assert run["id"].startswith("run-")
        assert run["status"] == "RUNNING"
        assert len(run["steps"]) == 4

        # Verify progress calculation on get
        r_get = client.get(f"/api/v3/workflow-runs/{run['id']}")
        assert r_get.status_code == 200
        run_data = r_get.json()
        assert "progress_percent" in run_data

    def test_workflow_lifecycle_controls(self, client):
        # Pause
        r_pause = client.post("/api/v3/workflow-runs/run-kronos-01/pause")
        assert r_pause.status_code == 200
        assert r_pause.json()["status"] == "PAUSED"

        # Resume
        r_resume = client.post("/api/v3/workflow-runs/run-kronos-01/resume")
        assert r_resume.status_code == 200
        assert r_resume.json()["status"] == "RUNNING"

        # Cancel
        r_cancel = client.post("/api/v3/workflow-runs/run-kronos-01/cancel")
        assert r_cancel.status_code == 200
        assert r_cancel.json()["status"] == "CANCELLED"

        # Retry
        r_retry = client.post("/api/v3/workflow-runs/run-kronos-01/retry")
        assert r_retry.status_code == 200
        assert r_retry.json()["status"] == "RUNNING"


# ─────────────────────────────────────────────────────────────────────────────
# Phase 11.10 — Cross-Domain Integration Test
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossDomainIntegration:
    def test_full_agent_workflow_e2e_lifecycle(self, client):
        # 1. Create Agent Definition
        r_def = client.post("/api/v3/agent-definitions", json={
            "name": "E2E Automated Agent",
            "role": "coder",
            "description": "Autonomous integration test worker",
        })
        assert r_def.status_code == 201
        def_id = r_def.json()["id"]

        # 2. Create Conversation Context
        r_conv = client.post("/api/v3/conversations", json={
            "title": "E2E Convergence Session",
            "objective": "Verify cross-domain execution",
        })
        assert r_conv.status_code == 201
        conv_id = r_conv.json()["id"]

        # 3. Launch Agent Instance
        r_inst = client.post("/api/v3/agent-instances", json={
            "definition_id": def_id,
            "conversation_id": conv_id,
            "canonical_model_id": "claude-3-5-sonnet",
        })
        assert r_inst.status_code == 201
        inst_id = r_inst.json()["id"]

        # 4. Create and assign Task
        r_task = client.post("/api/v3/tasks", json={
            "conversation_id": conv_id,
            "objective": "Run automated integration pass",
            "assigned_agent_instance_id": inst_id,
        })
        assert r_task.status_code == 201
        task_id = r_task.json()["id"]

        # 5. Transition Task to RUNNING then SUCCEEDED
        task_ver = r_task.json()["version"]
        r_run = client.patch(f"/api/v3/tasks/{task_id}", json={"state": "RUNNING", "expected_version": task_ver})
        assert r_run.status_code == 200

        r_done = client.patch(f"/api/v3/tasks/{task_id}", json={
            "state": "SUCCEEDED",
            "result": {"verified": True},
            "expected_version": r_run.json()["version"],
        })
        assert r_done.status_code == 200

        # 6. Verify Conversation Projection includes instance and task
        r_proj = client.get(f"/api/v3/conversations/{conv_id}")
        assert r_proj.status_code == 200
        proj = r_proj.json()
        assert any(a["id"] == inst_id for a in proj["agents"])
        assert any(t["id"] == task_id and t["state"] == "SUCCEEDED" for t in proj["tasks"])

"""Unit tests for Phase 6: Canonical CLI Subcommand, Schema Version & Manifest Verification."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from windagent_cli.composition import SocialReportCommandComposer
from windagent_cli.main import main, run_social_report
from windagent_workflows.social_research import (
    REPORT_SCHEMA_VERSION,
    ModelCallReceipt,
    ModelRoute,
    SocialResearchConfig,
    SocialResearchResult,
    SocialResearchWorkflow,
    SocialSourceSpec,
    generate_report_manifest,
    verify_report_integrity,
)


class FakeModelGateway:
    async def discover_models(self, provider: str):
        mock_model = MagicMock()
        mock_model.raw_model_id = "mock-model"
        return [mock_model]

    async def generate(self, **kwargs):
        sys_inst = kwargs.get("system_instruction", "").lower()
        model = kwargs.get("model", "").lower()
        if "extract" in sys_inst or "json" in sys_inst or "qwen" in model or "local" in sys_inst:
            return json.dumps({
                "author": "Test Author",
                "post_type": "post",
                "title": "Test Title",
                "text": "Rendered test content for social media post.",
                "metrics": {"views": 100},
                "topics": ["test"],
                "claims": ["claim 1"],
            })
        return f"Synthesized summary for {kwargs.get('provider')} using {kwargs.get('model')}"


class FakeBrowserTool:
    async def execute(self, invocation, context):
        res = MagicMock()
        res.success = True
        res.error = None
        res.data = {
            "content": "Rendered test content for social media post.",
            "final_url": invocation.params["url"],
            "title": "Test Title",
            "content_sha256": "abc123hash",
            "content_chars": 42,
            "browser_backend": "agent-browser",
            "screenshot_path": None,
        }
        return res


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.mark.asyncio
async def test_social_research_workflow_generates_manifest_and_schema_v2(tmp_workspace: Path):
    """Verify workflow generates report.json with schema v2.0.0 and manifest.json."""
    config = SocialResearchConfig(
        output_dir="artifacts/social_reports",
        skip_model_preflight=True,
        save_screenshots=False,
    )
    workflow = SocialResearchWorkflow(
        model_gateway=FakeModelGateway(),
        browser_tool=FakeBrowserTool(),
        config=config,
    )
    sources = [SocialSourceSpec(url="https://youtube.com/watch?v=dQw4w9WgXcQ")]

    result = await workflow.run(
        query="Test query",
        sources=sources,
        workspace_root=str(tmp_workspace),
        task_id="task_123",
        session_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    )

    assert result.status == "COMPLETE"
    report_dir = Path(result.json_path).parent

    # Check report.json schema
    payload = json.loads(Path(result.json_path).read_text(encoding="utf-8"))
    assert payload.get("schema_version") == REPORT_SCHEMA_VERSION
    assert payload.get("task_id") == "task_123"
    assert payload.get("session_id") == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    # Check manifest.json
    manifest_path = report_dir / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("schema_version") == REPORT_SCHEMA_VERSION
    assert manifest.get("task_id") == "task_123"
    assert "report.json" in manifest.get("files", {})
    assert "report.md" in manifest.get("files", {})

    # Verify integrity
    is_valid, errors = verify_report_integrity(report_dir)
    assert is_valid is True
    assert errors == []


@pytest.mark.asyncio
async def test_verify_report_integrity_detects_tampering(tmp_workspace: Path):
    """Verify report integrity detection fails when a report file is modified."""
    report_dir = tmp_workspace / "report_tamper_test"
    report_dir.mkdir(parents=True)
    report_file = report_dir / "report.md"
    report_file.write_text("Original content", encoding="utf-8")

    generate_report_manifest(report_dir=report_dir, report_id="report_tamper_1")

    is_valid, errors = verify_report_integrity(report_dir)
    assert is_valid is True

    # Tamper with file content
    report_file.write_text("Tampered content", encoding="utf-8")
    is_valid_after, errors_after = verify_report_integrity(report_dir)
    assert is_valid_after is False
    assert len(errors_after) > 0
    assert any("Hash mismatch" in err for err in errors_after)


@pytest.mark.asyncio
async def test_social_report_cli_run_and_verify(tmp_workspace: Path, capsys):
    """Test CLI subcommand social-report execution and verification."""
    mock_result = SocialResearchResult(
        report_id="test_rep_1",
        status="COMPLETE",
        markdown_path=str(tmp_workspace / "report.md"),
        json_path=str(tmp_workspace / "report.json"),
        source_count=1,
        successful_source_count=1,
        models=(),
    )

    with patch("windagent_cli.composition.SocialReportCommandComposer.run_report", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_result
        exit_code = await run_social_report(
            query="Testing social cli",
            urls=["https://youtube.com/watch?v=12345678901"],
            json_mode=True,
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data.get("report_id") == "test_rep_1"
        assert data.get("schema_version") == "2.0.0"


def test_social_report_cli_missing_args(capsys):
    """Test CLI subcommand returns usage exit code 3 when missing query/urls."""
    exit_code = main(["social-report"])
    assert exit_code == 3

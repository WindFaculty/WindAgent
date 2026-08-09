"""
Stage C — Screenplay Workspace Comprehensive Unit Test Suite.

Tests UI8 to UI18 backend capabilities:
- UI8 Read Model Query Projector
- UI10 Structured Command Handlers
- UI11 & UI12 Fountain Parser, Serializer, and Round-trip Semantic Equivalence
- UI14 Immutable Locked Revision Invariant & Draft Creation
- UI15 Semantic Revision Diff Engine
- UI16 Production Impact Analyzer
- UI17 Human-in-the-loop AI Proposals
- UI18 Screenplay Validation Gate & Blocking Lock
"""

import pytest
import asyncio
import tempfile
from pathlib import Path

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.unit_of_work.video_production_uow import VideoProductionUnitOfWork
from windagent_core.domain.video_production.screenplay_query_service import ScreenplayQueryService
from windagent_core.domain.video_production.screenplay_command_handlers import ScreenplayCommandHandler
from windagent_core.domain.video_production.screenplay_parser import ScreenplayParser, ScreenplaySerializer
from windagent_core.domain.video_production.screenplay_diff import ScreenplayDiffEngine
from windagent_core.domain.video_production.screenplay_impact import ProductionImpactAnalyzer
from windagent_core.domain.video_production.screenplay_proposal import AIScreenplayProposalService
from windagent_core.domain.video_production.screenplay_validation import ScreenplayValidationGate


@pytest.fixture
async def uow_factory():
    tmp = Path(tempfile.mkdtemp()) / "test_sp.db"
    db_url = f"sqlite+aiosqlite:///{tmp}"
    db = DatabaseManager(db_url)
    await db.upgrade_to_head(BaseORM.metadata)
    yield db.session_factory
    await db.engine.dispose()


@pytest.mark.asyncio
async def test_ui8_read_model_projection(uow_factory):
    uow = VideoProductionUnitOfWork(uow_factory)
    async with uow:
        await uow.projects.save_project("proj_test_c", "Test Project", "ACTIVE", "rev_001")
        await uow.projects.save_revision("rev_001", "proj_test_c", None, "DRAFT", "hash_1", 1)
        await uow.commit()

    async with uow:
        query_svc = ScreenplayQueryService(uow)
        read_model = await query_svc.get_screenplay_read_model("proj_test_c", "rev_001")

        assert read_model["project_id"] == "proj_test_c"
        assert read_model["revision_id"] == "rev_001"
        assert read_model["status"] == "DRAFT"
        assert len(read_model["scenes"]) >= 1
        assert read_model["scenes"][0]["order"] == 1


@pytest.mark.asyncio
async def test_ui11_ui12_fountain_parser_and_serializer_roundtrip():
    fountain_text = (
        "Title: MISSION PHENIX\n"
        "Logline: An agent embarks on a dangerous covert mission.\n"
        "\n"
        "===\n"
        "\n"
        "INT. CONTROL ROOM - DAY /* id: scene_01 */\n"
        "The room is filled with glowing holographic monitors.\n"
        "\n"
        "HERO /* id: dlg_01 */\n"
        "(whispering)\n"
        "Are we live?\n"
    )

    parse_result = ScreenplayParser.parse(fountain_text, "sp_test")
    assert parse_result.success is True
    candidate = parse_result.candidate_screenplay

    assert candidate["title"] == "MISSION PHENIX"
    assert len(candidate["scenes"]) == 1
    sc = candidate["scenes"][0]
    assert sc["scene_id"] == "scene_01"
    assert len(sc["dialogue_lines"]) == 1

    # Roundtrip serialization
    reserialized = ScreenplaySerializer.serialize(candidate)
    assert "INT. CONTROL ROOM - DAY" in reserialized
    assert "HERO" in reserialized
    assert "Are we live?" in reserialized


@pytest.mark.asyncio
async def test_ui14_locked_revision_invariant(uow_factory):
    uow = VideoProductionUnitOfWork(uow_factory)
    async with uow:
        await uow.projects.save_project("proj_locked", "Locked Project", "ACTIVE", "rev_locked")
        await uow.projects.save_revision("rev_locked", "proj_locked", None, "LOCKED", "hash_locked", 1)
        await uow.commit()

    async with uow:
        cmd_handler = ScreenplayCommandHandler(uow)
        res = await cmd_handler.handle_command(
            command_type="UPDATE_SCENE",
            project_id="proj_locked",
            target_revision_id="rev_locked",
            payload={"scene_id": "sc_1", "title": "EXT. NEW - DAY"},
            idempotency_key="key_1",
        )

        # Direct mutation on LOCKED revision must be rejected
        assert res["status"] == "REJECTED_LOCKED"

        # Create draft command derived from locked revision must succeed
        create_res = await cmd_handler.handle_command(
            command_type="CREATE_REVISION",
            project_id="proj_locked",
            target_revision_id="rev_locked",
            payload={"reason": "Branching new draft"},
            idempotency_key="key_create",
        )
        assert create_res["status"] == "COMPLETED"
        new_rev = create_res["updated_revision_id"]
        assert new_rev != "rev_locked"


@pytest.mark.asyncio
async def test_ui15_ui16_semantic_diff_and_impact():
    base_model = {
        "screenplay_id": "sp_base",
        "revision_id": "rev_01",
        "title": "Agent Story",
        "logline": "Original logline",
        "scenes": [
            {
                "scene_id": "sc_01",
                "order": 1,
                "title": "INT. BASE - DAY",
                "action_description": "Initial action",
                "dialogue_lines": [{"dialogue_id": "dlg_01", "character_name": "HERO", "text": "Hello"}],
            }
        ],
    }

    target_model = {
        "screenplay_id": "sp_base",
        "revision_id": "rev_02",
        "title": "Agent Story",
        "logline": "Updated logline",
        "scenes": [
            {
                "scene_id": "sc_01",
                "order": 1,
                "title": "INT. BASE - NIGHT",
                "action_description": "Updated action description",
                "dialogue_lines": [{"dialogue_id": "dlg_01", "character_name": "HERO", "text": "Hello world!"}],
            }
        ],
    }

    diff_res = ScreenplayDiffEngine.compare(base_model, target_model)
    assert diff_res.has_changes is True
    assert diff_res.total_modified >= 1

    impact = ProductionImpactAnalyzer.analyze_impact("proj_test", diff_res)
    assert impact.base_revision_id == "rev_01"
    assert impact.target_revision_id == "rev_02"
    assert len(impact.changed_scenes) == 1
    assert "shot_sc_01_01" in impact.affected_shots


@pytest.mark.asyncio
async def test_ui17_ai_proposal_non_mutation():
    base_model = {
        "screenplay_id": "sp_base",
        "revision_id": "rev_01",
        "scenes": [
            {
                "scene_id": "sc_01",
                "order": 1,
                "title": "INT. BASE - DAY",
                "action_description": "The Hero stands by the window.",
                "dialogue_lines": [],
            }
        ],
    }

    proposal = AIScreenplayProposalService.create_proposal(
        project_id="proj_ai",
        base_model=base_model,
        action_type="REWRITE",
        instruction="Make it action-packed",
    )

    assert proposal.status == "PENDING"
    assert proposal.diff_result.has_changes is True
    # Verify base model was not mutated directly in-place
    assert base_model["scenes"][0]["action_description"] == "The Hero stands by the window."


@pytest.mark.asyncio
async def test_ui18_validation_gate():
    screenplay_invalid = {
        "screenplay_id": "sp_inv",
        "revision_id": "rev_inv",
        "scenes": [],
    }

    report = ScreenplayValidationGate.validate_screenplay("proj_val", screenplay_invalid)
    assert report.is_lockable is False
    assert report.blocking_count >= 1
    assert report.issues[0].severity == "BLOCKING"

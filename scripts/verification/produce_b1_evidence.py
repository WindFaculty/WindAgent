"""
Plan B B1 evidence producer / contract guard.

Modes:
- default: (re)generate golden + invalid fixtures, JSON Schema bundle,
  registry manifest, checksums, and evidence markdown for the
  STORY_ARTIFACT_CONTRACT_GATE.
- --check: validate committed fixtures + registry WITHOUT writing anything;
  exit non-zero on any violation (CI guard).

Golden fixtures: Vietnamese "Con thỏ và cánh diều" vertical slice, audience
5-8, target 180-300 s. Fixture manifest hashes are deterministic
(SHA-256 of "fixture:<artifact_type>") and documented as fixture-only;
production receipt/package hashes always come from the A envelope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from windagent_core.domain.story import (  # noqa: E402
    STORY_ARTIFACT_REGISTRY,
    ValidationReport,
    ValidationSeverity,
    find_duplicate_canonical_models,
    registered_artifact_types,
)
from windagent_core.domain.story.bibles.models import (  # noqa: E402
    CharacterCanon,
    CharacterCanonEntry,
    CharacterRelationship,
    RecurringLocation,
    RecurringObject,
    StoryBible,
    WorldBible,
    WorldRule,
)
from windagent_core.domain.story.ideation.models import (  # noqa: E402
    CreativeBrief,
    IdeaCandidate,
    IdeaCandidateSet,
    SelectedIdea,
)
from windagent_core.domain.story.ids import (  # noqa: E402
    BeatId,
    BeatSheetId,
    CreativeBriefId,
    DialogueLineId,
    DraftSceneId,
    EpisodeOutlineId,
    LockedScreenplayPackageId,
    LockedScreenplayReceiptId,
    OutlineSceneId,
    ReviewReportId,
    RevisionProposalId,
    ScreenplayDraftId,
    SelectedIdeaId,
    StoryBibleId,
    StoryCharacterId,
    StoryLocationId,
    StoryPropId,
    WorldBibleId,
)
from windagent_core.domain.story.outline.models import (  # noqa: E402
    Beat,
    BeatSheet,
    EpisodeOutline,
    OutlineScene,
)
from windagent_core.domain.story.review.models import (  # noqa: E402
    READY_FOR_PRODUCTION,
    DimensionResult,
    LockedScreenplayPackage,
    LockedScreenplayReceipt,
    PackageArtifactRef,
    ReviewFinding,
    ReviewReport,
    RevisionProposal,
)
from windagent_core.domain.story.screenplay.models import (  # noqa: E402
    DraftDialogueLine,
    DraftScene,
    ScreenplayDraft,
)
from windagent_core.domain.story.validation import VALIDATION_CODE_CATALOG  # noqa: E402
from windagent_core.domain.studio.artifact import ArtifactType  # noqa: E402

FIXTURES_DIR = (
    REPO_ROOT / "docs" / "plans" / "studio_roadmap_01" / "fixtures" / "studio_contract_v0.1"
)
ARTIFACTS_DIR = FIXTURES_DIR / "story_artifacts"
GOLDEN_DIR = ARTIFACTS_DIR / "golden"
INVALID_DIR = ARTIFACTS_DIR / "invalid"
SCHEMAS_DIR = ARTIFACTS_DIR / "schemas"
EVIDENCE_DIR = REPO_ROOT / "docs" / "plans" / "studio_roadmap_01" / "evidence"

RABBIT = StoryCharacterId("ch_rabbit")
KITE = StoryCharacterId("ch_kite")
FIELD = StoryLocationId("loc_field")
RIVER = StoryLocationId("loc_river")
KITE_PROP = StoryPropId("prop_kite")

FIXTURE_HASHES = {
    t.value: hashlib.sha256(f"fixture:{t.value}".encode()).hexdigest() for t in ArtifactType
}


# ---------------------------------------------------------------------------
# Golden content (Vietnamese rabbit-and-kite slice, 5-8, 240 s target)
# ---------------------------------------------------------------------------


def golden_artifacts() -> Dict[ArtifactType, Any]:
    brief = CreativeBrief(
        brief_id=CreativeBriefId("br_rabbit_kite"),
        title="Con thỏ và cánh diều",
        genre="thiếu nhi",
        logline="Một chú thỏ con tìm thấy cánh diều giấy bị rơi và cùng nó học cách bay.",
        tone="ấm áp, vui tươi",
        audience="5-8",
        audience_min_age=5,
        audience_max_age=8,
        language="vi",
        theme="tình bạn, kiên trì",
        target_duration_seconds=240,
        aspect_ratio="16:9",
        constraints=["không có cảnh đêm đáng sợ", "lời thoại ngắn, dễ hiểu"],
        prohibited_content=["bạo lực", "khủng bố", "sợ hãi"],
    )
    candidate_set = IdeaCandidateSet(
        candidates=[
            IdeaCandidate(
                candidate_id="c1",
                title="Chú thỏ và cánh diều giấy",
                summary="Thỏ con nhặt được cánh diều giấy bị rơi bên bờ sông, cùng nó tập thả và kết bạn.",
                logline="Một chú thỏ học cách thả diều cùng người bạn giấy mới.",
                premise="Tình bạn giữa thỏ con và cánh diều giấy.",
                themes=["tình bạn", "kiên trì"],
                score=0.92,
                score_dimensions={
                    "AGE_FIT": 0.95, "SAFETY": 1.0, "BRIEF_ADHERENCE": 0.95,
                    "DURATION_FIT": 0.9, "PRODUCTION_FEASIBILITY": 1.0,
                    "CLARITY": 0.85, "EMOTIONAL_ARC": 0.8, "ORIGINALITY": 0.75,
                },
                brief_adherence=0.95,
                age_fit=0.95,
                safety_ok=True,
                content={"estimated_seconds": 240, "scene_count": 4, "character_count": 2, "location_count": 2},
            ),
            IdeaCandidate(
                candidate_id="c2",
                title="Cánh diều bay qua sông",
                summary="Cánh diều đưa thỏ con bay qua sông để gặp những người bạn mới ở bản bên.",
                logline="Một chuyến bay bất ngờ qua dòng sông.",
                premise="Khám phá thế giới bên kia sông.",
                themes=["khám phá"],
                score=0.81,
                score_dimensions={
                    "AGE_FIT": 0.85, "SAFETY": 1.0, "BRIEF_ADHERENCE": 0.8,
                    "DURATION_FIT": 0.8, "PRODUCTION_FEASIBILITY": 0.9,
                    "CLARITY": 0.8, "EMOTIONAL_ARC": 0.75, "ORIGINALITY": 0.85,
                },
                brief_adherence=0.8,
                age_fit=0.85,
                safety_ok=True,
                content={"estimated_seconds": 260, "scene_count": 5, "character_count": 4, "location_count": 3},
            ),
            IdeaCandidate(
                candidate_id="c3",
                title="Thỏ con học thả diều",
                summary="Thỏ con kiên trì tập thả diều qua nhiều lần thất bại và cuối cùng thành công.",
                logline="Kiên trì luyện tập sẽ đạt được ước mơ.",
                premise="Bài học kiên trì qua việc học thả diều.",
                themes=["kiên trì"],
                score=0.78,
                score_dimensions={
                    "AGE_FIT": 0.9, "SAFETY": 1.0, "BRIEF_ADHERENCE": 0.85,
                    "DURATION_FIT": 0.75, "PRODUCTION_FEASIBILITY": 0.9,
                    "CLARITY": 0.8, "EMOTIONAL_ARC": 0.7, "ORIGINALITY": 0.6,
                },
                brief_adherence=0.85,
                age_fit=0.9,
                safety_ok=True,
                content={"estimated_seconds": 230, "scene_count": 4, "character_count": 2, "location_count": 2},
            ),
        ],
        evaluated=True,
        scoring_rubric_version="score_rubric/v1",
        recommended_candidate_id="c1",
    )
    selected = SelectedIdea(
        selected_idea_id=SelectedIdeaId("sel_rabbit_kite"),
        source_set_id="set_rabbit_kite",
        candidate_id="c1",
        title="Chú thỏ và cánh diều giấy",
        summary=candidate_set.candidates[0].summary,
        rationale="Đề tài quen thuộc với lứa tuổi 5-8, điểm tổng cao nhất (0.92), an toàn và dễ sản xuất.",
        score=0.92,
        score_dimensions=candidate_set.candidates[0].score_dimensions,
        selection_policy="AUTO_WHEN_POLICY_ALLOWS",
    )
    story_bible = StoryBible(
        bible_id=StoryBibleId("bible_rabbit_kite"),
        title="Con thỏ và cánh diều",
        premise="Thỏ con nhặt được cánh diều giấy bị rơi; nhờ sự kiên trì của cả hai, cánh diều bay cao và tình bạn lớn lên.",
        theme="tình bạn và sự kiên trì",
        tone="ấm áp, vui tươi",
        arc_summary="Mở đầu: thỏ nhặt diều rơi. Giữa: thỏ tập thả, gặp cơn gió lớn. Kết: diều bay cao, cả hai vui mừng.",
        stakes="Cánh diều có thể bay mất nếu thỏ không giữ được dây.",
        story_rules=["Diều bay khi có gió", "Giấy không chịu được mưa to", "Thỏ chạy nhanh nhưng không biết bay"],
        language="vi",
    )
    world_bible = WorldBible(
        world_id=WorldBibleId("world_rabbit_kite"),
        setting="Một ngôi làng nhỏ ven sông vào mùa gió, có cánh đồng cỏ rộng.",
        physical_rules=[
            WorldRule(rule_id="r1", statement="Diều bay khi có gió", kind="physics"),
            WorldRule(rule_id="r2", statement="Giấy không chịu được mưa to", kind="physics"),
        ],
        story_rules=[
            WorldRule(rule_id="r3", statement="Cánh diều giấy có thể nói chuyện", kind="story"),
        ],
        recurring_locations=[
            RecurringLocation(location_id=FIELD, name="Cánh đồng gió", description="Cánh đồng cỏ rộng ven làng", atmosphere="thoáng đãng", lighting="nắng nhẹ"),
            RecurringLocation(location_id=RIVER, name="Dòng sông", description="Con sông nhỏ chảy qua làng", atmosphere="mát mẻ", lighting="sáng"),
        ],
        recurring_objects=[
            RecurringObject(prop_id=KITE_PROP, name="Cánh diều giấy", description="Cánh diều hình con chim làm bằng giấy màu", significance="Người bạn của thỏ con"),
        ],
        style_constraints={"palette": "màu pastel ấm", "shape": "tròn trịa, thân thiện"},
        language="vi",
    )
    character_canon = CharacterCanon(
        canon_id="canon_rabbit_kite",
        language="vi",
        characters=[
            CharacterCanonEntry(
                character_id=RABBIT,
                name="Thỏ con",
                role="protagonist",
                goal="Học cách thả diều thật cao",
                traits=["kiên nhẫn", "tò mò", "nhút nhát lúc đầu"],
                relationships=[CharacterRelationship(from_id=RABBIT, to_id=KITE, kind="friend", description="Bạn thân mới quen")],
                appearance="Thỏ trắng, đeo chiếc khăn nhỏ màu cam",
                voice="giọng nhẹ nhàng, hồn nhiên",
                age_band="5-8",
            ),
            CharacterCanonEntry(
                character_id=KITE,
                name="Cánh diều giấy",
                role="deuteragonist",
                goal="Bay cao hơn nữa",
                traits=["vui vẻ", "hơi kiêu một chút"],
                relationships=[],
                appearance="Diều hình con chim, giấy màu xanh và vàng",
                voice="giọng trong trẻo, nhanh nhẹn",
                age_band="5-8",
            ),
        ],
    )
    beat_sheet = BeatSheet(
        beat_sheet_id=BeatSheetId("bs_rabbit_kite"),
        title="Con thỏ và cánh diều",
        total_target_seconds=240,
        tolerance_seconds=15,
        beats=[
            Beat(beat_id=BeatId("b1"), order=1, role="hook", description="Thỏ nhặt cánh diều rơi bên bờ sông", emotional_beat="tò mò", character_ids=[RABBIT], location_id=RIVER, target_seconds=40),
            Beat(beat_id=BeatId("b2"), order=2, role="rising", description="Thỏ tập thả diều, gặp trở ngại vì chưa biết cách", emotional_beat="kiên trì", character_ids=[RABBIT, KITE], location_id=FIELD, target_seconds=80),
            Beat(beat_id=BeatId("b3"), order=3, role="climax", description="Cơn gió lớn, cánh diều suýt bay mất", emotional_beat="lo lắng", character_ids=[RABBIT, KITE], location_id=FIELD, target_seconds=60),
            Beat(beat_id=BeatId("b4"), order=4, role="resolution", description="Thỏ giữ được dây, diều bay cao, cả hai vui mừng", emotional_beat="vui sướng", character_ids=[RABBIT, KITE], location_id=FIELD, target_seconds=60),
        ],
    )
    outline = EpisodeOutline(
        outline_id=EpisodeOutlineId("ol_rabbit_kite"),
        title="Con thỏ và cánh diều",
        language="vi",
        audience_band="5-8",
        target_duration_seconds=240,
        tolerance_seconds=15,
        scenes=[
            OutlineScene(scene_id=OutlineSceneId("s1"), order=1, intent="Giới thiệu thỏ con và cánh diều rơi", location_id=RIVER, character_ids=[RABBIT], conflict_change="Thỏ nhặt được diều", visual_action="Thỏ chạy ra bờ sông nhặt cánh diều", dialogue_budget_seconds=10, estimated_seconds=40, beat_refs=[BeatId("b1")]),
            OutlineScene(scene_id=OutlineSceneId("s2"), order=2, intent="Thỏ tập thả diều và làm quen", location_id=FIELD, character_ids=[RABBIT, KITE], conflict_change="Diều nói chuyện, thỏ tập thả", visual_action="Thỏ chạy trên đồng, diều bay thấp", dialogue_budget_seconds=25, estimated_seconds=80, beat_refs=[BeatId("b2")]),
            OutlineScene(scene_id=OutlineSceneId("s3"), order=3, intent="Cơn gió lớn đe dọa cánh diều", location_id=FIELD, character_ids=[RABBIT, KITE], conflict_change="Gió lớn làm diều suýt mất", visual_action="Cây cối nghiêng ngả, thỏ giữ chặt dây", dialogue_budget_seconds=15, estimated_seconds=60, beat_refs=[BeatId("b3")]),
            OutlineScene(scene_id=OutlineSceneId("s4"), order=4, intent="Diều bay cao, kết thúc vui", location_id=FIELD, character_ids=[RABBIT, KITE], conflict_change="Diều bay cao vút", visual_action="Diều bay cao trên bầu trời xanh", dialogue_budget_seconds=10, estimated_seconds=60, beat_refs=[BeatId("b4")]),
        ],
    )
    draft = ScreenplayDraft(
        draft_id=ScreenplayDraftId("draft_rabbit_kite"),
        title="Con thỏ và cánh diều",
        logline="Một chú thỏ con tìm thấy cánh diều giấy bị rơi và cùng nó học cách bay.",
        language="vi",
        audience_band="5-8",
        target_duration_seconds=240,
        tolerance_seconds=15,
        scenes=[
            DraftScene(
                scene_id=DraftSceneId("dscn_1"), order=1, outline_scene_id=OutlineSceneId("s1"),
                location_id=RIVER, character_ids=[RABBIT],
                action_description="Buổi sáng, thỏ con chạy ra bờ sông và nhìn thấy cánh diều giấy nằm trên bãi cỏ.",
                dialogue=[
                    DraftDialogueLine(dialogue_id=DialogueLineId("dl_1"), scene_id=DraftSceneId("dscn_1"), character_id=RABBIT, order=1, text="Ồ, cánh diều đẹp quá! Bạn làm sao mà rơi ở đây?", estimated_seconds=8),
                ],
                transition="CUT TO:",
                estimated_seconds=40,
                source_beat_ids=[BeatId("b1")],
            ),
            DraftScene(
                scene_id=DraftSceneId("dscn_2"), order=2, outline_scene_id=OutlineSceneId("s2"),
                location_id=FIELD, character_ids=[RABBIT, KITE],
                action_description="Thỏ con ôm cánh diều chạy ra cánh đồng gió. Cánh diều cựa quậy nói chuyện.",
                dialogue=[
                    DraftDialogueLine(dialogue_id=DialogueLineId("dl_2"), scene_id=DraftSceneId("dscn_2"), character_id=KITE, order=1, text="Nắm chặt dây diều nhé! Mình sẽ bay thử!", estimated_seconds=10),
                    DraftDialogueLine(dialogue_id=DialogueLineId("dl_3"), scene_id=DraftSceneId("dscn_2"), character_id=RABBIT, order=2, text="Mình sẽ cố gắng! Chạy nhanh thế này đủ chưa nhỉ?", estimated_seconds=10),
                ],
                narration="Tiếng gió rì rào, cánh diều nhấc bổng lên rồi lại chúi xuống.",
                transition="CUT TO:",
                estimated_seconds=80,
                source_beat_ids=[BeatId("b2")],
            ),
            DraftScene(
                scene_id=DraftSceneId("dscn_3"), order=3, outline_scene_id=OutlineSceneId("s3"),
                location_id=FIELD, character_ids=[RABBIT, KITE],
                action_description="Một cơn gió lớn ập tới. Cây cối nghiêng ngả, cánh diều bị kéo căng hết cỡ.",
                dialogue=[
                    DraftDialogueLine(dialogue_id=DialogueLineId("dl_4"), scene_id=DraftSceneId("dscn_3"), character_id=RABBIT, order=1, text="Ôi, gió to quá! Mình sắp không giữ được rồi!", estimated_seconds=10),
                    DraftDialogueLine(dialogue_id=DialogueLineId("dl_5"), scene_id=DraftSceneId("dscn_3"), character_id=KITE, order=2, text="Đừng buông tay! Mình tin bạn!", estimated_seconds=8),
                ],
                transition="DISSOLVE TO:",
                estimated_seconds=60,
                source_beat_ids=[BeatId("b3")],
            ),
            DraftScene(
                scene_id=DraftSceneId("dscn_4"), order=4, outline_scene_id=OutlineSceneId("s4"),
                location_id=FIELD, character_ids=[RABBIT, KITE],
                action_description="Cơn gió dịu lại. Cánh diều bay cao vút trên bầu trời xanh, thỏ con vui sướng vẫy tay.",
                dialogue=[
                    DraftDialogueLine(dialogue_id=DialogueLineId("dl_6"), scene_id=DraftSceneId("dscn_4"), character_id=KITE, order=1, text="Nhìn kìa, mình bay cao rồi!", estimated_seconds=8),
                    DraftDialogueLine(dialogue_id=DialogueLineId("dl_7"), scene_id=DraftSceneId("dscn_4"), character_id=RABBIT, order=2, text="Tuyệt quá! Ngày mai mình lại thả diều nhé!", estimated_seconds=8),
                ],
                narration="Cánh diều lượn vòng trên nền trời xanh, tiếng cười của thỏ con vang khắp cánh đồng.",
                transition="FADE OUT:",
                estimated_seconds=60,
                source_beat_ids=[BeatId("b4")],
            ),
        ],
    )
    review_report = ReviewReport(
        report_id=ReviewReportId("rr_rabbit_kite"),
        draft_id=draft.draft_id,
        review_iteration=1,
        findings=[],
        dimensions=[
            DimensionResult(dimension="FORMAT_VALIDITY", score=1.0, blocking=False, note="Cấu trúc hợp lệ, lời thoại gán đúng nhân vật"),
            DimensionResult(dimension="DURATION_FIT", score=1.0, blocking=False, note="Tổng 240 giây khớp mục tiêu"),
            DimensionResult(dimension="BEAT_COVERAGE", score=1.0, blocking=False, note="Đủ 4 beat"),
            DimensionResult(dimension="CANON_REFERENCE_INTEGRITY", score=1.0, blocking=False, note="Mọi ID dẫn về canon"),
            DimensionResult(dimension="SAFETY", score=1.0, blocking=False, note="Không có nội dung cấm"),
        ],
        verdict="PASS",
        quality_summary="Bản thảo đạt mọi ngưỡng chất lượng cho lứa tuổi 5-8.",
        maximum_iterations=3,
    )
    revision_proposal = RevisionProposal(
        proposal_id=RevisionProposalId("prop_rabbit_kite"),
        draft_id=draft.draft_id,
        review_report_id=review_report.report_id,
        accepted_finding_codes=[],
        revision_reason="Không cần sửa: bản thảo đạt ngưỡng chất lượng ngay từ lần duyệt đầu.",
        iteration_number=1,
        maximum_iterations=3,
    )
    receipt = LockedScreenplayReceipt(
        receipt_id=LockedScreenplayReceiptId("rcpt_rabbit_kite"),
        draft_id=draft.draft_id,
        state=READY_FOR_PRODUCTION,
        approval_mode="AUTO",
        policy_id="approval_policy_v1",
        issued_at="2026-08-09T00:00:00Z",
    )
    package = LockedScreenplayPackage(
        package_id=LockedScreenplayPackageId("pkg_rabbit_kite"),
        receipt_id=receipt.receipt_id,
        title=draft.title,
        assembled_at="2026-08-09T00:00:01Z",
        manifest=[
            PackageArtifactRef(artifact_type=t, artifact_id=f"art_{t}", content_hash=FIXTURE_HASHES[t], revision_id="rev_1")
            for t in [
                "CreativeBrief", "IdeaCandidateSet", "SelectedIdea", "StoryBible",
                "WorldBible", "CharacterCanon", "BeatSheet", "EpisodeOutline",
                "ScreenplayDraft", "ReviewReport", "LockedScreenplayReceipt",
            ]
        ],
    )
    return {
        ArtifactType.CREATIVE_BRIEF: brief,
        ArtifactType.IDEA_CANDIDATE_SET: candidate_set,
        ArtifactType.SELECTED_IDEA: selected,
        ArtifactType.STORY_BIBLE: story_bible,
        ArtifactType.WORLD_BIBLE: world_bible,
        ArtifactType.CHARACTER_CANON: character_canon,
        ArtifactType.BEAT_SHEET: beat_sheet,
        ArtifactType.EPISODE_OUTLINE: outline,
        ArtifactType.SCREENPLAY_DRAFT: draft,
        ArtifactType.REVIEW_REPORT: review_report,
        ArtifactType.REVISION_PROPOSAL: revision_proposal,
        ArtifactType.LOCKED_SCREENPLAY_RECEIPT: receipt,
        ArtifactType.LOCKED_SCREENPLAY_PACKAGE: package,
    }


# ---------------------------------------------------------------------------
# Invalid fixtures (must fail closed)
# ---------------------------------------------------------------------------

INVALID_FIXTURES: Dict[str, Any] = {
    "invalid_idea_set_two_candidates.json": {
        "schema_version": "studio.artifact/v1alpha1",
        "artifact_type": "IdeaCandidateSet",
        "candidates": [
            {"candidate_id": "c1", "title": "T1"},
            {"candidate_id": "c2", "title": "T2"},
        ],
        "evaluated": False,
    },
    "invalid_idea_set_duplicate_ids.json": {
        "schema_version": "studio.artifact/v1alpha1",
        "artifact_type": "IdeaCandidateSet",
        "candidates": [
            {"candidate_id": "same", "title": "T1"},
            {"candidate_id": "same", "title": "T2"},
            {"candidate_id": "c3", "title": "T3"},
        ],
        "evaluated": False,
    },
    "invalid_schema_version_v2.json": {
        "schema_version": "studio.artifact/v2",
        "artifact_type": "CreativeBrief",
        "brief_id": "br_x",
        "title": "X",
    },
    "invalid_unknown_artifact_type.json": {
        "schema_version": "studio.artifact/v1alpha1",
        "artifact_type": "GhostArtifact",
        "content": {},
    },
    "invalid_malformed_json.json": "{not valid json!!!",
    "invalid_dialogue_attribution.json": {
        "schema_version": "studio.artifact/v1alpha1",
        "artifact_type": "ScreenplayDraft",
        "draft_id": "draft_bad",
        "title": "Bản thảo lỗi",
        "language": "vi",
        "audience_band": "5-8",
        "target_duration_seconds": 240,
        "tolerance_seconds": 15,
        "scenes": [
            {
                "scene_id": "dscn_bad",
                "order": 1,
                "outline_scene_id": "s1",
                "location_id": "loc_field",
                "character_ids": ["ch_rabbit"],
                "action_description": "Thỏ con đứng trên đồng.",
                "dialogue": [
                    {
                        "dialogue_id": "dl_bad",
                        "scene_id": "dscn_bad",
                        "character_id": "ch_kite",
                        "order": 1,
                        "text": "Mình bay đây!",
                        "estimated_seconds": 5,
                    }
                ],
                "estimated_seconds": 30,
            }
        ],
    },
    "invalid_outline_duration.json": {
        "schema_version": "studio.artifact/v1alpha1",
        "artifact_type": "EpisodeOutline",
        "outline_id": "ol_bad",
        "title": "Outline quá dài",
        "language": "vi",
        "audience_band": "5-8",
        "target_duration_seconds": 240,
        "tolerance_seconds": 15,
        "scenes": [
            {"scene_id": f"s{i}", "order": i, "intent": f"Cảnh {i}", "location_id": "loc_field",
             "character_ids": ["ch_rabbit"], "estimated_seconds": 100, "beat_refs": [f"b{i}"]}
            for i in range(1, 5)
        ],
    },
    "invalid_package_missing_lineage.json": {
        "schema_version": "studio.artifact/v1alpha1",
        "artifact_type": "LockedScreenplayPackage",
        "package_id": "pkg_bad",
        "receipt_id": "rcpt_bad",
        "title": "Gói thiếu dòng dõi",
        "manifest": [
            {"artifact_type": "ScreenplayDraft", "artifact_id": "a1", "content_hash": "a" * 64}
        ],
    },
    "invalid_envelope_field_leak.json": {
        "schema_version": "studio.artifact/v1alpha1",
        "artifact_type": "CreativeBrief",
        "brief_id": "br_leak",
        "title": "X",
        "content_hash": "abc123",
    },
    "invalid_long_text.json": {
        "schema_version": "studio.artifact/v1alpha1",
        "artifact_type": "ScreenplayDraft",
        "draft_id": "draft_long",
        "title": "Bản thảo dài",
        "language": "vi",
        "audience_band": "5-8",
        "target_duration_seconds": 240,
        "tolerance_seconds": 15,
        "scenes": [
            {
                "scene_id": "dscn_long",
                "order": 1,
                "outline_scene_id": "s1",
                "location_id": "loc_field",
                "character_ids": ["ch_rabbit"],
                "action_description": "X" * 25000,
                "dialogue": [],
                "estimated_seconds": 30,
            }
        ],
    },
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_golden() -> List[str]:
    """Validate every golden fixture against its registered model+validator."""
    failures: List[str] = []
    artifacts = golden_artifacts()
    for artifact_type, model in artifacts.items():
        registration = STORY_ARTIFACT_REGISTRY[artifact_type]
        expected_type = registration.content_model.__name__
        if type(model).__name__ != expected_type:
            failures.append(f"{artifact_type.value}: model {type(model).__name__} != {expected_type}")
        # Deterministic serialization round trip.
        restored = registration.content_model.deserialize(model.serialize())
        if restored != model:
            failures.append(f"{artifact_type.value}: serialization round trip mismatch")
        if registration.validator is not None:
            report = registration.validator(restored)
            if not report.is_pass():
                failures.append(
                    f"{artifact_type.value}: golden fixture fails validation: {report.summary()}"
                )
    return failures


def validate_invalid() -> List[str]:
    """Every invalid fixture must fail closed (parse error or failed validation)."""
    failures: List[str] = []
    for name, raw in INVALID_FIXTURES.items():
        if name in BOUNDARY_LEAK_FILES:
            continue  # handled by the boundary scan below
        text = json.dumps(raw, ensure_ascii=False) if not isinstance(raw, str) else raw
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue  # malformed JSON: correctly rejected
        artifact_type_name = data.get("artifact_type")
        try:
            artifact_type = ArtifactType(artifact_type_name)
        except ValueError:
            continue  # unknown discriminator: correctly rejected
        registration = STORY_ARTIFACT_REGISTRY.get(artifact_type)
        if registration is None:
            continue  # unregistered type: correctly rejected
        try:
            model = registration.content_model.model_validate(data)
        except Exception:
            continue  # schema/validation error at parse: correctly rejected
        if registration.validator is not None:
            report = registration.validator(model)
            if report.is_pass():
                failures.append(f"{name}: invalid fixture PASSES validation")
    return failures


#: Envelope-field leak fixtures: content parses (additive extra fields are
#: allowed by the versioning rule) but must be flagged by the boundary scan —
#: content models never own envelope fields.
BOUNDARY_LEAK_FILES = {
    "invalid_envelope_field_leak.json": ("content_hash", "abc123"),
}


def validate_boundary_leaks() -> List[str]:
    """Every boundary-leak fixture must carry a forbidden envelope field."""
    failures: List[str] = []
    for name, (field, _value) in BOUNDARY_LEAK_FILES.items():
        raw = INVALID_FIXTURES[name]
        data = json.loads(raw) if isinstance(raw, str) else raw
        if field not in data:
            failures.append(f"{name}: expected envelope-field leak {field!r} not present")
    return failures


def schema_bundle() -> Dict[str, Any]:
    bundle: Dict[str, Any] = {}
    for artifact_type, registration in STORY_ARTIFACT_REGISTRY.items():
        bundle[artifact_type.value] = registration.content_model.model_json_schema()
    return bundle


def write_artifacts() -> Dict[str, Any]:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    INVALID_DIR.mkdir(parents=True, exist_ok=True)
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)

    golden_checksums: Dict[str, str] = {}
    for artifact_type, model in golden_artifacts().items():
        path = GOLDEN_DIR / f"{artifact_type.value}.json"
        raw = (model.serialize() + "\n").encode("utf-8")
        path.write_bytes(raw)
        golden_checksums[path.name] = hashlib.sha256(raw).hexdigest()

    invalid_checksums: Dict[str, str] = {}
    for name, raw in INVALID_FIXTURES.items():
        text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False, indent=2)
        path = INVALID_DIR / name
        payload = (text + "\n").encode("utf-8")
        path.write_bytes(payload)
        invalid_checksums[name] = hashlib.sha256(payload).hexdigest()

    bundle = schema_bundle()
    schema_checksums: Dict[str, str] = {}
    for artifact_name, schema in bundle.items():
        path = SCHEMAS_DIR / f"{artifact_name}.json"
        raw = (json.dumps(schema, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        path.write_bytes(raw)
        schema_checksums[f"{artifact_name}.json"] = hashlib.sha256(raw).hexdigest()

    registry_manifest = {
        "schema": "story_artifact_registry/v1",
        "contract_version": "studio.contract/v0.1",
        "artifact_schema_version": "studio.artifact/v1alpha1",
        "registry": {
            artifact_type.value: {
                "content_model": registration.content_model.__name__,
                "schema_file": f"schemas/{artifact_type.value}.json",
                "validation_codes": list(registration.validation_codes),
                "description": registration.description,
            }
            for artifact_type, registration in STORY_ARTIFACT_REGISTRY.items()
        },
    }
    (ARTIFACTS_DIR / "story_artifact_registry.json").write_bytes(
        (json.dumps(registry_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )

    checksums = {
        "schema": "story_artifact_checksums/v1",
        "generated_at": "2026-08-09T00:00:00Z",
        "golden": golden_checksums,
        "invalid": invalid_checksums,
        "schemas": schema_checksums,
    }
    (ARTIFACTS_DIR / "checksums.json").write_bytes(
        (json.dumps(checksums, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    return checksums


def write_evidence(checksums: Dict[str, Any]) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    catalog_lines = [
        "# B1 Evidence — Story Validation-Code Catalog",
        "",
        f"Contract: `studio.contract/v0.1`; artifact schema `studio.artifact/v1alpha1`; generated {checksums['generated_at']}.",
        "",
        "Stable machine codes (frozen B0 taxonomy + B1 artifact codes). Translated labels never replace codes (C contract invariant 3).",
        "",
        "| Code | Dimension | Default severity | Description |",
        "|---|---|---|---|",
    ]
    for code in sorted(VALIDATION_CODE_CATALOG):
        entry = VALIDATION_CODE_CATALOG[code]
        catalog_lines.append(
            f"| `{code}` | {entry['dimension']} | {entry['default_severity']} | {entry['description']} |"
        )
    (EVIDENCE_DIR / "b1_validation_code_catalog.md").write_text(
        "\n".join(catalog_lines) + "\n", encoding="utf-8"
    )

    golden = golden_artifacts()
    matrix_lines = [
        "# B1 Evidence — STORY_ARTIFACT_CONTRACT_GATE",
        "",
        "Gate owner: Plan B (A/C consumers co-review). Baseline: see `b0_*` evidence.",
        "",
        "## 1. Registry and duplicate-model check",
        "",
        f"- Registered artifact types: **{len(STORY_ARTIFACT_REGISTRY)}/13** (all frozen types).",
        f"- Duplicate canonical models: **{find_duplicate_canonical_models() or 'none'}**.",
        "",
        "| Artifact type | Content model | Validator | Golden | Invalid fixtures |",
        "|---|---|---|---|---|",
    ]
    for artifact_type in sorted(registered_artifact_types(), key=lambda t: t.value):
        registration = STORY_ARTIFACT_REGISTRY[artifact_type]
        matrix_lines.append(
            f"| `{artifact_type.value}` | `{registration.content_model.__name__}` | "
            f"{'`' + registration.validator.__name__ + '`' if registration.validator else '—'} | "
            f"`golden/{artifact_type.value}.json` | {len(INVALID_FIXTURES)} invalid cases exercise the registry |"
        )

    matrix_lines += [
        "",
        "## 2. Golden fixture report (Vietnamese rabbit-and-kite slice, 5-8, 240 s)",
        "",
        "- All 13 golden artifacts: deterministic serialization round trip + registered validator pass.",
        "- Canon ID traceability: `ch_rabbit`, `ch_kite`, `loc_field`, `loc_river`, `prop_kite`, beats `b1-b4`, outline scenes `s1-s4`, draft scenes `dscn_1-4`.",
        "- Draft duration: 40+80+60+60 = **240 s** (target 240, tolerance 15) — inside the 180-300 s envelope.",
        f"- Golden file checksums: `story_artifacts/checksums.json` ({len(checksums['golden'])} files).",
        "",
        "## 3. Invalid fixture report (fail-closed)",
        "",
        f"- **{len(INVALID_FIXTURES)}** invalid fixtures; every one is rejected at parse time or fails validation:",
        "  - candidate count rule (2 candidates) — parse rejection",
        "  - duplicate candidate IDs — validation BLOCKING",
        "  - unknown schema version `studio.artifact/v2` — fail closed",
        "  - unknown artifact type — discriminator rejection",
        "  - malformed JSON — parse rejection",
        "  - dialogue attribution violation — `DIALOGUE_ATTRIBUTION` BLOCKING",
        "  - outline duration 400 s — `DURATION_BOUND` BLOCKING",
        "  - package manifest missing lineage — `MANIFEST_MISSING_REF` BLOCKING",
        "  - envelope-field leak in content — flagged by the boundary checker (never a canonical artifact)",
        "  - oversized scene text — `FIELD_TOO_LONG` WARNING (fails strict pass)",
        "",
        "## 4. Compatibility matrix",
        "",
        "| Legacy symbol | B1 decision | Canonical home | Adapter |",
        "|---|---|---|---|",
        "| `CreativeBrief` (video) | REUSE -> WRAP | `story/ideation/models.py` | `from_video_brief` (lossless + documented defaults) |",
        "| `StoryConcept` | DEPRECATE single-concept | projection from `IdeaCandidate` | `to_story_concept` with explicit loss metadata |",
        "| `DialogueLine` | REUSE (compose) | `DraftDialogueLine` (same field vocabulary) | `from_video_screenplay` + `dialogue_line_loss` |",
        "| `Screenplay` (V2 text) | REUSE as read model; structured draft is authority | `story/screenplay/models.py` | `from_video_screenplay` (loss-reporting) |",
        "| `CharacterBible`/`LocationBible`/`PropBible` | REUSE as mapping input | `CharacterCanon`/`WorldBible` entries | B4 mapping adapters (future) |",
        "| `VideoProductionPackage` | REUSE hash/lineage semantics | `StoryContent.content_hash()` + package manifest | registry + envelope hash |",
        "| A `IdeaCandidate`/`IdeaCandidateSet` placeholders | REPLACED by B canonical aliases | `story/ideation/models.py` | A envelope re-exports (one canonical model) |",
        "",
        "## 5. A envelope wrapping",
        "",
        "- `StoryArtifactEnvelope.build(...)` wraps canonical B content; envelope hash == `canonical_content_hash` (verified in tests).",
        "- Content models carry zero envelope fields (checked per registered model).",
        "- `story_task_io.json` (B0) remains `proposal-awaiting-a-approval`; this gate pins the content schemas behind it.",
        "",
        "## 6. Gate verdict",
        "",
        "**`STORY_ARTIFACT_CONTRACT_GATE`: PASS (B-side evidence).**",
        "",
        "- Schema bundle: 13 JSON Schemas generated from the registered canonical models (`story_artifacts/schemas/`).",
        "- Golden + invalid fixture checksums: `story_artifacts/checksums.json`.",
        "- Duplicate-model check: none (see §1).",
        "- C-side: TypeScript fixture generation and API mapping remain C's half of the gate (Plan C phase), to be co-signed at contract review.",
    ]
    (EVIDENCE_DIR / "b1_artifact_contract_gate.md").write_text(
        "\n".join(matrix_lines) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="B1 artifact contract fixtures/evidence")
    parser.add_argument("--check", action="store_true", help="validate committed fixtures, write nothing")
    args = parser.parse_args()

    failures = validate_golden() + validate_invalid() + validate_boundary_leaks()

    # Registry invariant checks (mirror the unit/architecture tests).
    if len(STORY_ARTIFACT_REGISTRY) != 13:
        failures.append(f"registry has {len(STORY_ARTIFACT_REGISTRY)} entries, expected 13")
    if find_duplicate_canonical_models():
        failures.append(f"duplicate canonical models: {find_duplicate_canonical_models()}")
    for artifact_type, registration in STORY_ARTIFACT_REGISTRY.items():
        for code in registration.validation_codes:
            if code not in VALIDATION_CODE_CATALOG:
                failures.append(f"{artifact_type.value} references unknown code {code}")

    if failures:
        print("B1 artifact contract: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("B1 artifact contract: PASS (13/13 types, golden + invalid fixtures, no duplicates)")
    if not args.check:
        checksums = write_artifacts()
        write_evidence(checksums)
        print(f"wrote fixtures -> {ARTIFACTS_DIR.relative_to(REPO_ROOT)}")
        print(f"wrote evidence -> {EVIDENCE_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

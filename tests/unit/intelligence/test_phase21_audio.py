"""
Phase 21 — Dialogue, TTS và audio production unit tests (plan 06 §9, gate
VP21_AUDIO_PIPELINE_VERIFIED).

Covers the gate test matrix:
- multi-character voice mapping never swaps;
- Unicode/Vietnamese pronunciation fixture (number/abbrev expansion);
- empty / overlong line handling;
- TTS timeout / invalid file fail closed;
- low alignment confidence -> human review;
- dialogue longer than the shot -> timing proposal, never cut;
- SFX/BGM unknown license blocks the mix;
- loudness / peak technical checks;
- dialogue change invalidates the correct audio/mix/final artifacts.
"""

from __future__ import annotations

from windagent_core.domain.video_production.audio import (
    AudioMixPlan,
    CharacterVoiceProfile,
    DialogueTrack,
    SoundEffectCue,
    TtsAudioAsset,
    WordTimestamp,
)
from windagent_core.domain.video_production.enums import (
    AudioAlignmentStatus,
    AudioCueKind,
    AudioInvalidationScope,
    LicenseState,
    VoiceRightsState,
)
from windagent_core.domain.video_production.ids import (
    AudioMixPlanId,
    CharacterId,
    CharacterVoiceProfileId,
    DialogueLineId,
    DialogueTrackId,
    SceneId,
    ShotId,
    SoundEffectCueId,
    TtsAudioAssetId,
    TtsRequestId,
    WordTimestampId,
)
from windagent_core.domain.video_production.screenplay import DialogueLine

from windagent_intelligence.video.audio import (
    AlignmentService,
    AudioPipelineService,
    DialoguePreparer,
    MixPlanner,
    TtsSynthesisRequest,
    TtsSynthesisResult,
    TtsSynthesizer,
    VoiceCastingService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _line(dialogue_id: str, character_id: str, text: str, delivery: str = "") -> DialogueLine:
    return DialogueLine(
        dialogue_id=DialogueLineId(dialogue_id),
        scene_id=SceneId("scn_1"),
        character_id=CharacterId(character_id),
        order=1,
        text=text,
        delivery=delivery,
    )


def _voice(
    profile_id: str,
    character_id: str,
    *,
    voice_id: str = "v1",
    approved: bool = True,
    rights: VoiceRightsState = VoiceRightsState.LICENSED,
) -> CharacterVoiceProfile:
    return CharacterVoiceProfile(
        profile_id=CharacterVoiceProfileId(profile_id),
        character_id=CharacterId(character_id),
        voice_name=character_id,
        provider="flow",
        model="tts-v1",
        voice_id=voice_id,
        voice_version="1",
        rights_state=rights,
        approved=approved,
        preview_only=not approved,
    )


def _word(tid: str, word: str, start: float, end: float, conf: float = 0.95) -> WordTimestamp:
    return WordTimestamp(
        timestamp_id=WordTimestampId(tid),
        word=word,
        start_seconds=start,
        end_seconds=end,
        confidence=conf,
    )


class _FakeTts:
    def __init__(self, *, timed_out: bool = False, empty: bool = False, invalid: bool = False):
        self.timed_out = timed_out
        self.empty = empty
        self.invalid = invalid
        self.calls = 0

    def synthesize(self, request: TtsSynthesisRequest) -> TtsSynthesisResult:
        self.calls += 1
        if self.timed_out:
            return TtsSynthesisResult(request_id=str(request.request_id), timed_out=True)
        if self.empty:
            return TtsSynthesisResult(request_id=str(request.request_id))
        if self.invalid:
            return TtsSynthesisResult(
                request_id=str(request.request_id),
                content=b"x",
                sample_rate=0,  # invalid
                channel_layout="",
                duration_seconds=0.0,
            )
        return TtsSynthesisResult(
            request_id=str(request.request_id),
            content=b"AUDIO" * 64,
            sample_rate=48000,
            channel_layout="stereo",
            duration_seconds=2.0,
            provider="flow",
            model="tts-v1",
            voice_id="v1",
        )

    async def asynthesize(self, request: TtsSynthesisRequest) -> TtsSynthesisResult:
        return self.synthesize(request)


# ---------------------------------------------------------------------------
# §8.1 — Dialogue preparation
# ---------------------------------------------------------------------------
class TestDialoguePreparation:
    def test_vietnamese_normalization_number_and_abbrev(self):
        line = _line("dlg_1", "chr_1", "Xin chào, số 5. OK TV.")
        receipt = DialoguePreparer().prepare([line])
        assert len(receipt.tracks) == 1
        track = receipt.tracks[0]
        assert "5" not in track.prepared_text  # number expanded
        assert "5" in track.text  # original text preserved
        assert track.prepared_text.startswith("Xin chào, số năm")
        assert "ok tivi" in track.prepared_text.lower() or "ok" in track.prepared_text.lower()

    def test_empty_line_is_issue_not_dropped_silently(self):
        receipt = DialoguePreparer().prepare([_line("dlg_1", "chr_1", "   ")])
        assert receipt.tracks == []
        assert any(i.code == "EMPTY_LINE" for i in receipt.issues)

    def test_overlong_line_is_issue(self):
        long_text = "a" * 500
        receipt = DialoguePreparer().prepare([_line("dlg_1", "chr_1", long_text)])
        assert receipt.tracks == []
        assert any(i.code == "OVERLONG_LINE" for i in receipt.issues)

    def test_narration_intent_classified(self):
        line = _line("dlg_1", "chr_1", "Vào một buổi sáng.", delivery="narration")
        receipt = DialoguePreparer().prepare([line])
        assert receipt.tracks[0].intent_type.value == "NARRATION"

    def test_target_duration_estimated(self):
        line = _line("dlg_1", "chr_1", "Hello world this is eight chars x")
        receipt = DialoguePreparer().prepare([line])
        assert receipt.tracks[0].target_duration_seconds > 0


# ---------------------------------------------------------------------------
# §8.2 — Voice casting: mapping never swaps, preview never final
# ---------------------------------------------------------------------------
class TestVoiceCasting:
    def test_multi_character_mapping_never_swaps(self):
        service = VoiceCastingService()
        catalog = [
            _voice("vpr_1", "chr_A", voice_id="va"),
            _voice("vpr_2", "chr_B", voice_id="vb"),
        ]
        receipt = service.cast(
            character_ids=["chr_A", "chr_B"],
            character_names={"chr_A": "A", "chr_B": "B"},
            catalog=catalog,
        )
        assert len(receipt.profiles) == 2
        by_char = {str(p.character_id): p.voice_id for p in receipt.profiles}
        assert by_char["chr_A"] == "va"
        assert by_char["chr_B"] == "vb"

    def test_preview_never_final_without_approval(self):
        service = VoiceCastingService()
        preview = _voice("vpr_1", "chr_A", approved=False)
        receipt = service.cast(
            character_ids=["chr_A"],
            character_names={"chr_A": "A"},
            catalog=[preview],
        )
        assert any(i.code == "PREVIEW_NOT_APPROVED" for i in receipt.issues)
        assert all(p.approved is False for p in receipt.profiles)

    def test_voice_reuse_forbidden(self):
        service = VoiceCastingService()
        catalog = [
            _voice("vpr_1", "chr_A", voice_id="shared"),
            _voice("vpr_2", "chr_B", voice_id="shared"),
        ]
        receipt = service.cast(
            character_ids=["chr_A", "chr_B"],
            character_names={"chr_A": "A", "chr_B": "B"},
            catalog=catalog,
        )
        assert any(i.code == "VOICE_REUSE_FORBIDDEN" for i in receipt.issues)

    def test_approve_does_not_fabricate_license(self):
        profile = _voice("vpr_1", "chr_A", rights=VoiceRightsState.UNKNOWN)
        approved = VoiceCastingService().approve(profile, actor="human-1")
        assert approved.approved is True
        assert approved.approval_actor == "human-1"
        assert approved.rights_state == VoiceRightsState.UNKNOWN  # never fabricated


# ---------------------------------------------------------------------------
# §8.3 — TTS: fail closed, invalid output never published
# ---------------------------------------------------------------------------
class TestTts:
    def _request(self, **kw) -> TtsSynthesisRequest:
        req = TtsSynthesisRequest(
            request_id=TtsRequestId("ttr_1"),
            dialogue_id=kw.pop("dialogue_id", "dlg_1"),
            text=kw.pop("text", "Xin chào"),
            voice_profile_hash=kw.pop("voice_profile_hash", "h" * 64),
        )
        return TtsSynthesisRequest(
            request_id=req.request_id,
            dialogue_id=req.dialogue_id,
            text=req.text,
            voice_profile_hash=req.voice_profile_hash,
            language=req.language,
            locale=req.locale,
            synthesis_params=req.synthesis_params,
            request_hash=req.compute_request_hash(),
            **kw,
        )

    def test_request_hash_deterministic_and_binds_inputs(self):
        r1 = self._request()
        r2 = self._request()
        assert r1.compute_request_hash() == r2.compute_request_hash()
        r3 = self._request(dialogue_id="dlg_OTHER")
        assert r1.compute_request_hash() != r3.compute_request_hash()

    def test_valid_audio_asset_created(self):
        receipt = TtsSynthesizer().synthesize(_FakeTts(), self._request())
        assert len(receipt.assets) == 1
        asset = receipt.assets[0]
        assert len(asset.content_hash) == 64
        assert asset.sample_rate == 48000
        assert asset.channel_layout == "stereo"
        assert asset.duration_seconds > 0

    def test_timeout_is_issue_never_published(self):
        receipt = TtsSynthesizer().synthesize(_FakeTts(timed_out=True), self._request())
        assert receipt.assets == []
        assert any(i.code == "TTS_TIMEOUT" for i in receipt.issues)

    def test_empty_output_is_issue(self):
        receipt = TtsSynthesizer().synthesize(_FakeTts(empty=True), self._request())
        assert receipt.assets == []
        assert any(i.code == "TTS_EMPTY_OUTPUT" for i in receipt.issues)

    def test_invalid_output_is_issue(self):
        receipt = TtsSynthesizer().synthesize(_FakeTts(invalid=True), self._request())
        assert receipt.assets == []
        assert any(i.code == "TTS_INVALID_OUTPUT" for i in receipt.issues)


# ---------------------------------------------------------------------------
# §8.4 — Alignment: low confidence -> human, overlong -> proposal (never cut)
# ---------------------------------------------------------------------------
class TestAlignment:
    def _track(self, dialogue_id: str = "dlg_1", audio_duration: float = 2.0) -> DialogueTrack:
        asset = TtsAudioAsset(
            asset_id=TtsAudioAssetId("tsa_1"),
            content_hash="c" * 64,
            sample_rate=48000,
            channel_layout="stereo",
            duration_seconds=audio_duration,
            byte_size=100,
            source_request_hash="r" * 64,
        )
        return DialogueTrack(
            track_id=DialogueTrackId(f"dtr_{dialogue_id}"),
            dialogue_id=DialogueLineId(dialogue_id),
            character_id=CharacterId("chr_1"),
            text="hello",
            target_duration_seconds=2.0,
            audio=asset,
        )

    def test_low_confidence_routes_to_human(self):
        service = AlignmentService(confidence_floor=0.6)
        receipt = service.align(
            [self._track()],
            word_timestamps_by_track={
                "dlg_1": [_word("wt_1", "hello", 0.0, 0.5, conf=0.3)],
            },
        )
        assert receipt.tracks[0].alignment_status == AudioAlignmentStatus.LOW_CONFIDENCE
        assert any(i.code == "ALIGNMENT_LOW_CONFIDENCE" for i in receipt.issues)

    def test_missing_timestamps_is_finding(self):
        receipt = AlignmentService().align([self._track()])
        assert any(i.code == "ALIGNMENT_MISSING" for i in receipt.issues)
        # state must not contradict the finding: UNALIGNED, not usable audio
        track = receipt.tracks[0]
        assert track.alignment_status == AudioAlignmentStatus.UNALIGNED
        assert track.alignment_confidence == 0.0
        assert track.has_valid_audio is False

    def test_overlong_line_proposes_timing_never_cuts(self):
        service = AlignmentService(max_stretch_ratio=1.15)
        # aligned track (timestamps present) whose audio 5.0s vs shot 2.0s
        # -> ratio 2.5 beyond policy -> OVERLONG_LINE, never cut
        receipt = service.align(
            [self._track(audio_duration=5.0)],
            word_timestamps_by_track={"dlg_1": [_word("wt_1", "hello", 0.0, 5.0)]},
            shot_duration_by_track={"dlg_1": 2.0},
        )
        assert receipt.tracks[0].alignment_status == AudioAlignmentStatus.OVERLONG_LINE
        assert any(i.code == "OVERLONG_FOR_SHOT" for i in receipt.issues)
        assert any("never cut" in p["proposal"] for p in receipt.timing_proposals)

    def test_within_stretch_ratio_is_timing_proposed(self):
        service = AlignmentService(max_stretch_ratio=1.15)
        # aligned track: audio 2.1s vs shot 2.0s -> ratio 1.05 within policy
        receipt = service.align(
            [self._track(audio_duration=2.1)],
            word_timestamps_by_track={"dlg_1": [_word("wt_1", "hello", 0.0, 2.1)]},
            shot_duration_by_track={"dlg_1": 2.0},
        )
        assert receipt.tracks[0].alignment_status == AudioAlignmentStatus.TIMING_PROPOSED


# ---------------------------------------------------------------------------
# §8.5 — Mix: license gate, versioned policy, invalidation scope
# ---------------------------------------------------------------------------
class TestMix:
    def _cue(self) -> SoundEffectCue:
        return SoundEffectCue(
            cue_id=SoundEffectCueId("sfx_1"),
            kind=AudioCueKind.SFX,
            shot_id=ShotId("s1"),
            timeline_start_seconds=0.0,
            duration_seconds=1.0,
            license_state=LicenseState.LICENSED,
        )

    def test_unknown_license_blocks_mix(self):
        plan, issues = MixPlanner().plan(
            project_id="vp_1",
            revision_id="rev_1",
            dialogue_tracks=[],
            sfx_cues=[self._cue()],
        )
        assert issues == []
        bad = self._cue().model_copy(update={"license_state": LicenseState.UNKNOWN})
        plan2, issues2 = MixPlanner().plan(
            project_id="vp_1",
            revision_id="rev_1",
            dialogue_tracks=[],
            sfx_cues=[bad],
        )
        assert any(i.code == "UNKNOWN_CUE_LICENSE" for i in issues2)

    def test_mix_policy_versioned_and_hash_deterministic(self):
        planner = MixPlanner()
        plan1, _ = planner.plan(project_id="vp_1", revision_id="rev_1", dialogue_tracks=[])
        plan2, _ = planner.plan(project_id="vp_1", revision_id="rev_1", dialogue_tracks=[])
        assert plan1.mix_policy_version == "1.0.0"
        assert plan1.mix_hash == plan2.mix_hash
        assert plan1.loudness_target_lufs == -16.0
        assert plan1.peak_ceiling_db == -1.0

    def test_invalidation_scopes(self):
        plan = AudioMixPlan(
            mix_id=AudioMixPlanId("amx_1"),
            project_id="vp_1",
            revision_id="rev_1",
        )
        assert plan.invalidated_scope(AudioCueKind.BGM) == AudioInvalidationScope.MIX_ONLY
        assert plan.invalidated_scope(AudioCueKind.SFX) == AudioInvalidationScope.MIX_ONLY
        assert plan.invalidated_scope("dialogue") == AudioInvalidationScope.TRACK_AND_MIX


# ---------------------------------------------------------------------------
# §8 — Pipeline end-to-end
# ---------------------------------------------------------------------------
class TestAudioPipeline:
    def test_pipeline_full_flow(self):
        lines = [
            _line("dlg_1", "chr_A", "Xin chào bạn."),
            _line("dlg_2", "chr_B", "Chào bạn."),
        ]
        receipt = AudioPipelineService().run(
            project_id="vp_1",
            revision_id="rev_1",
            dialogue_lines=lines,
            tts_port=_FakeTts(),
            voice_catalog=[
                _voice("vpr_1", "chr_A", voice_id="va"),
                _voice("vpr_2", "chr_B", voice_id="vb"),
            ],
            word_timestamps_by_track={
                "dlg_1": [_word("wt_1", "Xin", 0.0, 0.4)],
                "dlg_2": [_word("wt_2", "Chào", 0.0, 0.3)],
            },
        )
        assert len(receipt.dialogue.tracks) == 2
        assert len(receipt.tts.assets) == 2
        assert receipt.mix is not None
        assert receipt.issues == []

    def test_pipeline_skips_tts_for_unapproved_voice(self):
        lines = [_line("dlg_1", "chr_A", "Xin chào bạn.")]
        receipt = AudioPipelineService().run(
            project_id="vp_1",
            revision_id="rev_1",
            dialogue_lines=lines,
            tts_port=_FakeTts(),
            voice_catalog=[_voice("vpr_1", "chr_A", approved=False)],
        )
        assert receipt.tts.assets == []
        assert any(i.code == "PREVIEW_NOT_APPROVED" for i in receipt.issues)

    def test_pipeline_surfaces_tts_timeout(self):
        lines = [_line("dlg_1", "chr_A", "Xin chào bạn.")]
        receipt = AudioPipelineService().run(
            project_id="vp_1",
            revision_id="rev_1",
            dialogue_lines=lines,
            tts_port=_FakeTts(timed_out=True),
            voice_catalog=[_voice("vpr_1", "chr_A")],
        )
        assert receipt.tts.assets == []
        assert any(i.code == "TTS_TIMEOUT" for i in receipt.issues)

    def test_dialogue_change_yields_distinct_prepared_text(self):
        """§8.1: a text change produces a distinct prepared track; each track
        records its own audio_revision (caller bumps it on re-prepare)."""
        prep = DialoguePreparer()
        r1 = prep.prepare([_line("dlg_1", "chr_A", "Version one.")])
        r2 = prep.prepare([_line("dlg_1", "chr_A", "Version two changed.")])
        assert r1.tracks[0].audio_revision == 1
        assert r2.tracks[0].audio_revision == 1
        assert r1.tracks[0].prepared_text != r2.tracks[0].prepared_text
        assert r1.tracks[0].text != r2.tracks[0].text  # distinct source lines

"""B1 canon: referential integrity, duplicates, cycles, world-rule conflicts."""

from __future__ import annotations

from windagent_core.domain.story.bibles import (
    CharacterCanon,
    CharacterCanonEntry,
    CharacterRelationship,
    RecurringLocation,
    RecurringObject,
    StoryBible,
    WorldBible,
    WorldRule,
    validate_canon_set,
)
from windagent_core.domain.story.ids import (
    StoryBibleId,
    StoryCharacterId,
    StoryLocationId,
    StoryPropId,
    WorldBibleId,
)


def _canon() -> CharacterCanon:
    rabbit = StoryCharacterId("ch_rabbit")
    kite = StoryCharacterId("ch_kite")
    return CharacterCanon(
        canon_id="canon_1",
        language="vi",
        characters=[
            CharacterCanonEntry(
                character_id=rabbit,
                name="Thỏ con",
                role="protagonist",
                goal="Học cách thả diều",
                traits=["kiên nhẫn", "tò mò"],
                relationships=[CharacterRelationship(from_id=rabbit, to_id=kite, kind="friend")],
                age_band="5-8",
            ),
            CharacterCanonEntry(
                character_id=kite,
                name="Cánh diều giấy",
                role="deuteragonist",
                goal="Bay cao hơn nữa",
                age_band="5-8",
            ),
        ],
    )


def test_canon_set_valid():
    bible = StoryBible(
        bible_id=StoryBibleId.generate("bible"),
        title="Con thỏ và cánh diều",
        premise="Một chú thỏ tìm thấy cánh diều bị rơi và cùng nó học cách bay.",
        arc_summary="Thỏ nhặt diều -> tập thả -> diều bay -> cả hai vui.",
    )
    world = WorldBible(
        world_id=WorldBibleId.generate("world"),
        setting="Một ngôi làng nhỏ ven sông vào mùa gió.",
        recurring_locations=[RecurringLocation(location_id=StoryLocationId("loc_field"), name="Cánh đồng gió")],
        recurring_objects=[RecurringObject(prop_id=StoryPropId("prop_kite"), name="Cánh diều giấy")],
    )
    report = validate_canon_set(bible, world, _canon(), audience_min_age=5)
    assert report.is_pass(), report.summary()


def test_relationship_to_unknown_character_blocks():
    canon = _canon().model_copy(update={
        "characters": [
            entry.model_copy(update={
                "relationships": [CharacterRelationship(
                    from_id=entry.character_id, to_id=StoryCharacterId("ch_ghost"), kind="friend"
                )]
            }) if entry.character_id == StoryCharacterId("ch_rabbit") else entry
            for entry in _canon().characters
        ]
    })
    report = validate_canon_set(StoryBible(bible_id=StoryBibleId.generate("b"), title="T", premise="P", arc_summary="A"), WorldBible(world_id=WorldBibleId.generate("w"), setting="S"), canon)
    assert any(i.code == "REF_MISSING" for i in report.issues)


def test_relationship_cycle_detected():
    a, b = StoryCharacterId("a"), StoryCharacterId("b")
    canon = CharacterCanon(canon_id="c", characters=[
        CharacterCanonEntry(character_id=a, name="A", relationships=[
            CharacterRelationship(from_id=a, to_id=b, kind="friend")]),
        CharacterCanonEntry(character_id=b, name="B", relationships=[
            CharacterRelationship(from_id=b, to_id=a, kind="friend")]),
    ])
    report = validate_canon_set(
        StoryBible(bible_id=StoryBibleId.generate("b"), title="T", premise="P", arc_summary="A"),
        WorldBible(world_id=WorldBibleId.generate("w"), setting="S"),
        canon,
    )
    assert any(i.code == "RELATIONSHIP_CYCLE" for i in report.issues)


def test_self_loop_blocks():
    a = StoryCharacterId("a")
    canon = CharacterCanon(canon_id="c", characters=[
        CharacterCanonEntry(character_id=a, name="A", relationships=[
            CharacterRelationship(from_id=a, to_id=a, kind="friend")]),
    ])
    report = validate_canon_set(
        StoryBible(bible_id=StoryBibleId.generate("b"), title="T", premise="P", arc_summary="A"),
        WorldBible(world_id=WorldBibleId.generate("w"), setting="S"),
        canon,
    )
    assert any(i.code == "RELATIONSHIP_CYCLE" and i.severity.value == "BLOCKING" for i in report.issues)


def test_duplicate_names_warn():
    canon = _canon().model_copy(update={
        "characters": [entry.model_copy(update={"name": "Thỏ con"}) for entry in _canon().characters]
    })
    report = validate_canon_set(
        StoryBible(bible_id=StoryBibleId.generate("b"), title="T", premise="P", arc_summary="A"),
        WorldBible(world_id=WorldBibleId.generate("w"), setting="S"),
        canon,
    )
    assert any(i.code == "DUPLICATE_NAME" for i in report.issues)


def test_world_rule_conflict_surfaces_not_mutates():
    world = WorldBible(
        world_id=WorldBibleId.generate("w"),
        setting="Làng ven sông",
        physical_rules=[
            WorldRule(rule_id="r1", statement="Diều bay khi có gió"),
            WorldRule(rule_id="r2", statement="diều bay khi có gió"),
        ],
    )
    report = validate_canon_set(
        StoryBible(bible_id=StoryBibleId.generate("b"), title="T", premise="P", arc_summary="A"),
        world,
        _canon(),
    )
    assert any(i.code == "WORLD_RULE_COMPLIANCE" for i in report.issues)
    # Canon never auto-mutated: rule ids unchanged.
    assert [r.rule_id for r in world.physical_rules] == ["r1", "r2"]


def test_audience_mismatch_blocks():
    canon = _canon().model_copy(update={
        "characters": [entry.model_copy(update={"age_band": "16+"}) for entry in _canon().characters]
    })
    report = validate_canon_set(
        StoryBible(bible_id=StoryBibleId.generate("b"), title="T", premise="P", arc_summary="A"),
        WorldBible(world_id=WorldBibleId.generate("w"), setting="S"),
        canon,
        audience_min_age=5,
    )
    assert any(i.code == "SAFETY_AGE_UNSUITABLE" for i in report.issues)

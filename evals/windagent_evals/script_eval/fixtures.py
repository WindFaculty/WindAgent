"""Shared Phase 1 fixtures: one valid production script + one broken copy.

Single source for the contract validator's smoke fixtures — tests and the
evidence producer must never drift apart.
"""

from __future__ import annotations

import copy
from typing import Callable


def valid_production_script() -> dict:
    return {
        "project": {
            "title": "Miko va qua bong", "episode": 1,
            "target_audience": "3-6", "target_duration_minutes": 5,
            "genre": "adventure", "theme": "friendship",
            "educational_goal": "chia se va giup do",
        },
        "world_bible": {"locations": [
            {"id": "house", "name": "Nha cua Miko"},
            {"id": "park", "name": "Cong vien"},
        ]},
        "characters": [
            {"id": "miko", "name": "Miko", "age_type": "child 5",
             "appearance": "yellow shirt, blue shorts",
             "personality": "curious, kind", "motivation": "tim bong",
             "voice_profile": "high, bright",
             "relationships": [{"character_id": "luna", "kind": "sister"}]},
            {"id": "luna", "name": "Luna", "age_type": "child 3",
             "appearance": "pink dress", "personality": "shy",
             "motivation": "di cung chi", "voice_profile": "soft",
             "relationships": []},
        ],
        "story": {
            "logline": "Miko tim qua bong bi mat.",
            "synopsis": "Miko danh mat bong, di tim va tim thay.",
            "acts": [{"title": "Act 1"}, {"title": "Act 2"}],
            "beats": [{"description": "Mat bong", "scene_id": "SCENE_001"}],
        },
        "scenes": [
            {"scene_id": "SCENE_001", "location": "house", "time": "morning",
             "characters": ["miko"], "objective": "tim bong",
             "conflict": "bong khong o cho cu", "action": "Miko tim khap nha",
             "dialogue": "Bong cua minh dau roi?", "emotional_state": "sad",
             "continuity_state": {"bong": "lost"}, "estimated_duration_seconds": 90},
            {"scene_id": "SCENE_002", "location": "park", "time": "morning",
             "characters": ["miko", "luna"], "objective": "hoi luna",
             "conflict": "luna khong biet", "action": "Miko hoi luna",
             "dialogue": "Luna co thay bong khong?", "emotional_state": "worried",
             "continuity_state": {"bong": "lost"}, "estimated_duration_seconds": 120},
            {"scene_id": "SCENE_003", "location": "park", "time": "afternoon",
             "characters": ["miko"], "objective": "nhat bong",
             "conflict": "bong mac tren cay", "action": "Miko nhat bong",
             "dialogue": "Tim thay roi!", "emotional_state": "happy",
             "continuity_state": {"bong": "found"}, "estimated_duration_seconds": 90},
        ],
        "ending": {"summary": "Miko tim thay bong, cam on luna."},
        "moral": "Chia se va kien nhan se duoc den dap.",
        "continuity_summary": "Bong lost -> found; vi tri nha -> park.",
        "production_notes": "3 scenes, 2 characters, 2 locations.",
    }


def broken_production_script() -> dict:
    """Valid script with one fault injected per contract check (all at once)."""
    doc = valid_production_script()
    doc["project"].pop("theme")                      # missing_field
    doc["scenes"][2]["characters"] = "miko"          # invalid_type
    doc["scenes"].append(copy.deepcopy(doc["scenes"][0]))   # duplicate_id
    doc["scenes"][1]["characters"].append("ghost")   # unknown_character
    doc["scenes"][2]["location"] = "forest"          # unknown_location
    doc["scenes"][1]["estimated_duration_seconds"] = -5  # negative_duration
    doc["scenes"][2]["estimated_duration_seconds"] = 0    # zero_duration
    doc["scenes"][0]["scene_id"] = "SCENE_003"       # scene_ordering
    doc["characters"][0]["relationships"] = [{"character_id": "ghost"}]  # broken_references
    doc["story"]["beats"][0]["scene_id"] = "SCENE_099"   # broken_references
    doc["scenes"][1]["time"] = "midnight-ish"        # invalid_enum
    doc["scenes"][1]["dialogue"] = ""                # empty_dialogue (WARNING)
    doc["scenes"][1]["objective"] = ""               # empty_scene_objective (WARNING)
    doc["scenes"][0]["estimated_duration_seconds"] = 9000  # duration_mismatch (WARNING)
    return doc


# check -> {"mutator": fn(doc), "severity": "ERROR" | "WARNING"}
FAULT_INJECTIONS: dict = {
    "missing_field": {"severity": "ERROR", "mutator": lambda d: d["project"].pop("theme")},
    "invalid_type": {"severity": "ERROR", "mutator": lambda d: d["scenes"][0].__setitem__(
        "estimated_duration_seconds", True)},
    "duplicate_id": {"severity": "ERROR", "mutator": lambda d: d["scenes"].append(
        copy.deepcopy(d["scenes"][0]))},
    "unknown_character": {"severity": "ERROR", "mutator": lambda d: d["scenes"][1].__setitem__(
        "characters", ["ghost"])},
    "unknown_location": {"severity": "ERROR", "mutator": lambda d: d["scenes"][2].__setitem__(
        "location", "forest")},
    "negative_duration": {"severity": "ERROR", "mutator": lambda d: d["scenes"][1].__setitem__(
        "estimated_duration_seconds", -5)},
    "zero_duration": {"severity": "ERROR", "mutator": lambda d: d["scenes"][1].__setitem__(
        "estimated_duration_seconds", 0)},
    "scene_ordering": {"severity": "ERROR", "mutator": lambda d: d["scenes"][0].__setitem__(
        "scene_id", "SCENE_003")},
    "broken_references": {"severity": "ERROR", "mutator": lambda d: d["characters"][0].__setitem__(
        "relationships", [{"character_id": "ghost"}])},
    "invalid_enum": {"severity": "ERROR", "mutator": lambda d: d["scenes"][0].__setitem__(
        "time", "midnight-ish")},
    "empty_dialogue": {"severity": "WARNING", "mutator": lambda d: d["scenes"][1].__setitem__(
        "dialogue", "   ")},
    "empty_scene_objective": {"severity": "WARNING", "mutator": lambda d: d["scenes"][1].__setitem__(
        "objective", "")},
    "duration_mismatch": {"severity": "WARNING", "mutator": lambda d: d["scenes"][0].__setitem__(
        "estimated_duration_seconds", 9000)},
}


def mutate(mutator: Callable[[dict], None]) -> dict:
    doc = valid_production_script()
    mutator(doc)
    return doc


# ---------------------------------------------------------------------------
# Phase 2 — idea generation fixtures (test_kich_ban.md section 5)
# ---------------------------------------------------------------------------

SIBLING_DIFFERENTIATION = (
    "Khac cac idea khac: xoay quanh buoi di choi cong vien cung gia dinh, "
    "nhan manh su gan ket gia dinh hon la kham pha."
)


def valid_idea() -> dict:
    """A Phase-2 idea that passes every check clean (T01, 5 minutes)."""
    return {
        "case_id": "T01",
        "duration_minutes": 5,
        "hook": "Qua bong phat sang cua Miko lan xuong hang tho ky bi, "
                "mo ra con duong dan toi khu vuon bi bo quen.",
        "conflict": "Miko va Luna tranh nhau ai duoc cam den, nhung den "
                    "gap phai gio lon thoi tat.",
        "premise": "Miko danh roi qua bong phat sang xuong hang tho. Cung "
                   "Luna, Miko xuong tim, gap ong cuoi duong chi duong, vuot "
                   "qua cau tre lung lay va tim thay khu vuon ky dieu noi "
                   "bong phat sang roi. Hai chi em hoc cach thay phien nhau "
                   "cam den de ca hai cung di duoc.",
        "differentiation": "Khac cac idea khac: xoay quanh vat phat sang ky "
                           "bi va hang tho, nhan manh su hop tac giua hai chi em.",
        "payoff": "Miko va Luna tim thay bong, thap sang lai khu vuon va "
                  "ca hai cung choi den khi troi toi.",
        "lesson": "Thay phien nhau giup ca hai cung dat duoc dieu mong muon.",
        "visual_potential": "Bong phat sang chay xuong hang, den lung lay "
                            "trong gio, Miko chay duoi theo qua cau tre, "
                            "khu vuon bung sang mau sac khi bong duoc nhat len.",
    }


def sibling_idea() -> dict:
    """A second, distinct valid idea (T02, used as the differentiation twin)."""
    return {
        "case_id": "T02",
        "duration_minutes": 5,
        "hook": "Bo me dan hai chi em di choi cong vien, nhung tro choi "
                "quen thuoc bat ngo tro thanh cuoc phieu luu nho.",
        "conflict": "Luna muon choi xich du nhung xich du da hu tu hom qua.",
        "premise": "Gia dinh Miko di choi cong vien cuoi tuan. Luna phat "
                   "hien xich du bi hu nen buon. Ca nha cung nhau tim cach "
                   "sua xich du bang day thung va que go, vua lam vua "
                   "cuoi, va xich du chay lai duoc truoc khi troi toi.",
        "differentiation": SIBLING_DIFFERENTIATION,
        "payoff": "Xich du duoc sua, Luna choi thoa thich va ca nha tu hao "
                  "ve viec lam chung.",
        "lesson": "Cung nhau lam viec se nhanh hon va vui hon lam mot minh.",
        "visual_potential": "Ca nha ngoi quanh xich du, bo dua day thung, "
                            "me buoc que go, Luna nhay len thu xich du lan "
                            "dau, ai cung cuoi vang.",
    }


def broken_idea() -> dict:
    """Valid idea with one fault injected per Phase 2 check (all at once)."""
    doc = valid_idea()
    doc.pop("case_id")                              # missing_field
    doc["duration_minutes"] = "5"                   # invalid_type
    doc["hook"] = "ok"                              # weak_hook
    doc["conflict"] = "Mot ban lon bat nat Miko o truong."  # inappropriate_conflict
    doc["premise"] = ""                             # thin_premise
    doc["differentiation"] = SIBLING_DIFFERENTIATION  # duplicate_idea
    doc["payoff"] = ""                              # missing_payoff
    doc["lesson"] = "Con phai luon luon nghe loi nguoi lon."  # preachy_lesson
    doc["visual_potential"] = ""                    # not_visual
    return doc


IDEA_FAULT_INJECTIONS: dict = {
    "missing_field": {"severity": "ERROR",
                      "mutator": lambda d: d.pop("case_id")},
    "invalid_type": {"severity": "ERROR",
                     "mutator": lambda d: d.__setitem__("duration_minutes", "5")},
    "weak_hook": {"severity": "ERROR",
                  "mutator": lambda d: d.__setitem__("hook", "ok")},
    "inappropriate_conflict": {"severity": "ERROR",
                               "mutator": lambda d: d.__setitem__(
                                   "conflict", "Mot ban lon bat nat Miko.")},
    "thin_premise": {"severity": "ERROR",
                     "mutator": lambda d: d.__setitem__("premise", "")},
    "duplicate_idea": {"severity": "ERROR",
                       "mutator": lambda d: d.__setitem__(
                           "differentiation", SIBLING_DIFFERENTIATION)},
    "missing_payoff": {"severity": "ERROR",
                       "mutator": lambda d: d.__setitem__("payoff", "")},
    "preachy_lesson": {"severity": "WARNING",
                       "mutator": lambda d: d.__setitem__(
                           "lesson", "Con phai luon luon nghe loi nguoi lon.")},
    "not_visual": {"severity": "WARNING",
                   "mutator": lambda d: d.__setitem__("visual_potential", "")},
}

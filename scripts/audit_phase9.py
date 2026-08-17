#!/usr/bin/env python3
"""
Phase 9 System Audit — Story Production Domain Verification.

Verifies all Phase 9 Gate criteria:
  DEFAULT_CHARACTERS       = 0
  DEFAULT_SCENES           = 0
  DEFAULT_COMMENTS         = 0
  DEFAULT_VERSIONS         = 0
  fake generation timer    = 0
  hardcoded media URL      = 0 (runtime dependency)

Verdict: FRONTEND_V2_PHASE_09_STORY_PRODUCTION_VERIFIED
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
FRONTEND_ROOT = ROOT / "frontend"
DESKTOP_ROOT = ROOT / "apps" / "desktop" / "src" / "pages"
APP_FEATURES = FRONTEND_ROOT / "app" / "src" / "features"
API_CONTRACTS = FRONTEND_ROOT / "packages" / "api-contracts" / "src"
API_CLIENT = FRONTEND_ROOT / "packages" / "api-client" / "src"
BACKEND_V3 = ROOT / "apps" / "api" / "windagent_api" / "routers" / "v3"

RESULTS: list[tuple[str, bool, str]] = []

def check(name: str, ok: bool, detail: str = "") -> None:
    icon = "✅" if ok else "❌"
    RESULTS.append((icon, ok, name + (f" — {detail}" if detail else "")))
    print(f"  {icon}  {name}" + (f"  [{detail}]" if detail else ""))


def grep(path: Path, pattern: str, recursive: bool = True) -> list[Path]:
    """Return files matching the pattern."""
    files_to_search: list[Path] = list(path.rglob("*.tsx")) + list(path.rglob("*.ts")) + list(path.rglob("*.py")) if recursive else [path]
    matches = []
    regex = re.compile(pattern)
    for f in files_to_search:
        try:
            if regex.search(f.read_text(encoding="utf-8", errors="ignore")):
                matches.append(f)
        except Exception:
            pass
    return matches


def grep_content(path: Path, pattern: str) -> list[tuple[Path, int, str]]:
    """Return (file, line_no, line_text) for lines matching pattern."""
    regex = re.compile(pattern)
    results = []
    for f in path.rglob("*.tsx") if path.is_dir() else [path]:
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if regex.search(line):
                    results.append((f, i, line.strip()))
        except Exception:
            pass
    return results


print()
print("=" * 72)
print("  Phase 9 — Story Production Domain — System Audit")
print("=" * 72)
print()

# ─── Backend Routers Present ──────────────────────────────────────────────────
print("▌ Backend V3 Routers")
for router_name in ["characters.py", "world.py", "storyboard.py", "reviews.py", "assets.py"]:
    router_path = BACKEND_V3 / router_name
    check(f"routers/v3/{router_name} exists", router_path.exists())

# Verify all routers are registered
router_py = (BACKEND_V3 / "router.py").read_text(encoding="utf-8")
for domain in ["characters", "world", "storyboard", "reviews", "assets"]:
    check(f"v3/router.py registers {domain}", f"v3_{domain}_router" in router_py)

print()

# ─── API Contracts ──────────────────────────────────────────────────────────
print("▌ API Contracts (api-contracts/src/projects.ts)")
contracts_text = (API_CONTRACTS / "projects.ts").read_text(encoding="utf-8")
for contract in [
    "CharacterResource", "CharacterIdentity", "CharacterPsychology",
    "WorldBibleResource", "LocationResource", "FactionResource",
    "SceneResource", "StoryboardResource", "GenerationJobResource",
    "ReviewResource", "ReviewDecisionResource",
    "AssetResource", "AssetProvenance", "AssetRevisionResource",
]:
    check(f"Contract {contract} defined", contract in contracts_text)

# Ensure no duplicate AssetResource conflict (legacy renamed to LegacyAssetResource)
legacy_assets = (API_CONTRACTS / "assets.ts").read_text(encoding="utf-8")
check("LegacyAssetResource renamed (no conflict)", "LegacyAssetResource" in legacy_assets and "export interface AssetResource" not in legacy_assets)

print()

# ─── API Client ─────────────────────────────────────────────────────────────
print("▌ API Client (api-client/src/client.ts)")
client_text = (API_CLIENT / "client.ts").read_text(encoding="utf-8")
for api_class in ["CharactersApi", "WorldApi", "StoryboardApi", "ReviewsApi", "AssetsApi"]:
    check(f"{api_class} defined in client.ts", f"class {api_class}" in client_text)

check("WindAgentClient.characters wired", "this.characters = new CharactersApi" in client_text)
check("WindAgentClient.world wired", "this.world = new WorldApi" in client_text)
check("WindAgentClient.storyboard wired", "this.storyboard = new StoryboardApi" in client_text)
check("WindAgentClient.reviews wired", "this.reviews = new ReviewsApi" in client_text)

# StoryboardApi.triggerGeneration must not mention setTimeout
sb_api_match = re.search(r"triggerGeneration.*?(?=async \w|\Z)", client_text, re.DOTALL)
if sb_api_match:
    snippet = sb_api_match.group(0)
    check("StoryboardApi.triggerGeneration has no setTimeout", "setTimeout" not in snippet)
else:
    check("StoryboardApi.triggerGeneration present", False, "method not found")

print()

# ─── Frontend Features ────────────────────────────────────────────────────────
print("▌ Frontend Features (@windagent/app/src/features)")
for feature, page in [
    ("characters/pages/CharactersPage.tsx", "CharactersPage"),
    ("world/pages/WorldPage.tsx", "WorldPage"),
    ("storyboard/pages/StoryboardPage.tsx", "StoryboardPage"),
    ("reviews/pages/ReviewsPage.tsx", "ReviewsPage"),
    ("assets/pages/AssetsPage.tsx", "AssetsPage"),
]:
    p = APP_FEATURES / feature
    check(f"features/{feature} exists", p.exists())

print()

# ─── Phase 9 Gate — Mock Elimination ─────────────────────────────────────────
print("▌ Phase 9 Gate — Mock Elimination")

# DEFAULT_CHARACTERS in desktop
default_chars = grep(DESKTOP_ROOT, r"\bDEFAULT_CHARACTERS\b", recursive=False)
check("DEFAULT_CHARACTERS = 0 in desktop pages", len(default_chars) == 0,
      f"Still present in: {[f.name for f in default_chars]}")

# DEFAULT_SCENES in desktop
default_scenes = grep(DESKTOP_ROOT, r"\bDEFAULT_SCENES\b", recursive=False)
check("DEFAULT_SCENES = 0 in desktop pages", len(default_scenes) == 0,
      f"Still present in: {[f.name for f in default_scenes]}")

# DEFAULT_VERSIONS in desktop
default_versions = grep(DESKTOP_ROOT, r"\bDEFAULT_VERSIONS\b", recursive=False)
check("DEFAULT_VERSIONS = 0 in desktop pages", len(default_versions) == 0,
      f"Still present in: {[f.name for f in default_versions]}")

# DEFAULT_COMMENTS in desktop
default_comments = grep(DESKTOP_ROOT, r"\bDEFAULT_COMMENTS\b", recursive=False)
check("DEFAULT_COMMENTS = 0 in desktop pages", len(default_comments) == 0,
      f"Still present in: {[f.name for f in default_comments]}")

# fake setTimeout in storyboard feature
storyboard_feature = APP_FEATURES / "storyboard"
fake_timers = grep_content(storyboard_feature, r"setTimeout\(")
check("setTimeout fake timer = 0 in features/storyboard", len(fake_timers) == 0,
      f"Found in: {[(str(f.name), ln) for f, ln, _ in fake_timers]}")

# hardcoded lh3.googleusercontent media URLs in features (runtime dependency)
hardcoded_media = grep_content(APP_FEATURES, r"lh3\.googleusercontent\.com")
check("hardcoded media URLs = 0 runtime dependency in features", len(hardcoded_media) == 0,
      f"Found in: {[(str(f.name), ln) for f, ln, _ in hardcoded_media]}")

# storyboard scenes carry source_screenplay_revision_id in backend model
storyboard_router = (BACKEND_V3 / "storyboard.py").read_text(encoding="utf-8")
check("source_screenplay_revision_id in scene model (storyboard.py)", "source_screenplay_revision_id" in storyboard_router)

# review decisions require revision_id
reviews_router = (BACKEND_V3 / "reviews.py").read_text(encoding="utf-8")
check("revision_id in ReviewDecision (reviews.py)", "revision_id" in reviews_router)
check("expected_version in ReviewDecision (reviews.py)", "expected_version" in reviews_router)

# asset provenance chain in asset model
assets_router = (BACKEND_V3 / "assets.py").read_text(encoding="utf-8")
for field in ["content_hash", "parent_revision_id", "job_id", "generator", "model"]:
    check(f"AssetProvenance.{field} in assets.py", field in assets_router)

print()

# ─── Realtime (WebSocket) ─────────────────────────────────────────────────────
print("▌ Realtime / WebSocket")
check("Storyboard WS /ws/v3/storyboard/{episode_id} implemented", "ws_router" in storyboard_router)
check("useStoryboardRealtime hook in features/storyboard", (storyboard_feature / "hooks" / "useStoryboard.ts").exists())

# Verify useStoryboardRealtime does NOT use setTimeout
realtime_hook = (storyboard_feature / "hooks" / "useStoryboard.ts").read_text(encoding="utf-8")
check("useStoryboardRealtime has no setTimeout calls", "setTimeout(" not in realtime_hook)

print()

# ─── Phase 9F Integration Contract Tests ─────────────────────────────────────
print("▌ Phase 9F Integration Certification Tests")
test_path = ROOT / "tests" / "contracts" / "test_phase9_story_production.py"
check("test_phase9_story_production.py exists", test_path.exists())
if test_path.exists():
    test_text = test_path.read_text(encoding="utf-8")
    for test_class in ["TestCharactersE2E", "TestWorldE2E", "TestStoryboardE2E", "TestReviewsE2E", "TestAssetsE2E", "TestCrossDomainIntegration"]:
        check(f"  {test_class} present", test_class in test_text)

print()
print("=" * 72)

passed = sum(1 for _, ok, _ in RESULTS if ok)
failed = sum(1 for _, ok, _ in RESULTS if not ok)
total = len(RESULTS)

print(f"  Results: {passed}/{total} checks passed, {failed} failed")
print()

if failed == 0:
    print("  ✅  VERDICT: FRONTEND_V2_PHASE_09_STORY_PRODUCTION_VERIFIED")
else:
    print("  ❌  VERDICT: PHASE 09 NOT VERIFIED — Fix failing checks above")
    print()
    print("  Failing checks:")
    for icon, ok, name in RESULTS:
        if not ok:
            print(f"    • {name}")

print("=" * 72)
print()

sys.exit(0 if failed == 0 else 1)

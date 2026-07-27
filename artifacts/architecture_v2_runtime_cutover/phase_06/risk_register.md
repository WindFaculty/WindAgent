# Phase 6 risk register

| Risk | Level | Current control | Follow-up |
|---|---|---|---|
| An external launcher outside this repository still imports the removed package | Medium | Repository consumers are zero; exact deletion manifest and a minimal-delegation rollback design are available | Add a time-boxed compatibility package only when a concrete consumer is identified |
| A developer recreates Python code under `apps/backend` | Low | Architecture policy has an empty allowlist and directly scans the retired tree | Keep the architecture check required in CI |
| Desktop actions without a canonical V2 mutation contract lose behavior | Medium | Those actions fail locally and do not silently call the V1 tombstone; provider/model views are read-only V2 views | Add explicit V2 commands before re-enabling each mutation |
| Ignored local cache or virtual-environment content remains below the deleted directory | Low | No tracked runtime file or Python source exists there; clean installs do not include local ignored content | Remove local caches manually when they are no longer needed |
| Automated build smoke does not exercise every OS GUI integration | Low | Desktop/web tests, typechecks, and production builds pass | Run the release-candidate GUI/browser checklist on supported operating systems |
| Worker module version constant differs from its project metadata | Low | It does not affect independent installation or legacy removal | Align version metadata in the release/versioning workflow |

# Upstream Retirement — Video Pre-production Kernel (Phase 6)

Source: plan 02 `§16.5`, `§4` (scope), `§8.3` (quarantine boundary).

## 1. Goal

After Phase 6, the canonical pre-production runtime has **zero** import or
launch of `third_party/videoclaw/upstream/`. The upstream snapshot remains in
the repository only as an auditable vendor artifact for characterization; it
is never a runtime or build dependency.

## 2. Where upstream may live

| Zone | Allowed? | Purpose |
|---|---|---|
| `third_party/videoclaw/upstream/` | yes (quarantined) | vendored snapshot, audit only |
| `scripts/verification/phase5_upstream_probe.py` | yes (only launcher) | characterization harness subprocess |
| `scripts/verification/verify_phase5_characterization.py` | yes | reads probe output, checks quarantine |
| `tests/` | yes (negative fixtures) | proves canonical code never imports it |
| `scripts/check_architecture_imports.py` | yes | enforcement rule |
| `intelligence/windagent_intelligence/video/**` | **no** | canonical kernel — must not reference upstream |
| `core`, `providers`, `tools`, `workflows`, `apps`, `storage`, `orchestration` | **no** | canonical packages |

## 3. Enforcement

1. **Static architecture check** — `check_videoclaw_quarantine` rule in
   `scripts/check_architecture_imports.py` (5 negative rules) plus
   `verify_phase4_intake.py`. Architecture check reports 0 violations.
2. **Harness isolation test** — `tests/architecture/test_phase05_
   characterization_harness.py` proves the only launch/import mechanism is
   the probe subprocess and that it is confined to `scripts/verification/`.
3. **Phase 6 verifier** — `verify_phase6_kernel.py` scans the canonical
   kernel package for any `third_party` / `videoclaw` import statement or
   `sys.path` mutation and records `no_upstream_import_report.json`.
4. **Runtime substitution test** — the verifier's integration receipt runs
   the full idea→package path with the upstream directory temporarily made
   unavailable (renamed out of the way on a temp copy) and proves the kernel
   still assembles a valid package.

## 4. Retirement evidence

`artifacts/video_production/phase_06/no_upstream_import_report.json`:

```text
kernel_package:        intelligence/windagent_intelligence/video/
scanned_files:         <count>
upstream_imports_found: []
sys_path_mutations:     []
launch_statements:      []
verdict:                PASS
```

## 5. Rules of engagement

- The kernel declares its own canonical screenplay format and parsing rules;
  it does not copy upstream template text. Behavior parity comes from
  `equivalence_policy.md` semantic fields.
- Removing/renaming the upstream snapshot from a test environment must not
  change build or runtime behavior of the canonical packages.
- Any future patch to the vendored snapshot must go through
  `third_party/videoclaw/PATCHES.md` and re-run Phase 4/5 verification.

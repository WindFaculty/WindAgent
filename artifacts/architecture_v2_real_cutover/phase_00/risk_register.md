# Phase 0 risk register

- HIGH: Baseline full test suite fails: 9 failed, 473 passed, 1 skipped.
- HIGH: Legacy backend suite fails heavily: 107 failed, 290 passed, 51 errors.
- HIGH: Existing `ban_ke_hoach.md` worktree edit predates Phase 0. Preserved in `tracked_worktree_before.patch`; not modified by execution.
- MEDIUM: Architecture checker reports PASS while baseline test detects forbidden Intelligence-to-Orchestration imports. Checker may under-enforce policy.
- MEDIUM: Secret-pattern scan found 465 textual matches across tracked files. Values omitted; manual classification required. No secret value copied into evidence.
- LOW: Desktop build emits chunk-size warning; build succeeds.

No stash existed. No stash popped/deleted. No user database touched. No schema reset performed.

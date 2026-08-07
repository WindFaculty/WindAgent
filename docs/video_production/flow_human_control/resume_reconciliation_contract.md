# Safe Resume Protocol & Job Reconciliation Contract — Phase 16

## 1. Overview

Resuming an automated workflow after human intervention must be deterministic, safe, and prevent duplicate generation submit calls.

## 2. Six-Step Safe Resume Protocol

When a human user resolves a challenge and requests session resume, the system executes the 6-step protocol:

```text
Human User Resolves Challenge
          ↓
1. Health Check (Browser & UI reachable)
          ↓
2. Challenge Clearance Check (No active challenge)
          ↓
3. Account & Project Validation (Project ID & Account match)
          ↓
4. Active Job Reconciliation (SUBMITTING → UNKNOWN_REQUIRES_RECONCILIATION)
          ↓
5. Safe Resume State Transition (Unpause session)
          ↓
6. Audit Logging (Record resolution receipt)
```

## 3. Zero Duplicate Submit Invariant

- If human intervention occurred while a generation job was in `SUBMITTING` status, resuming will **never** re-trigger submit.
- The job status is transitioned to `UNKNOWN_REQUIRES_RECONCILIATION`, forcing a browser inspection of existing project artifacts to reconcile whether the submit succeeded upstream.

## 4. Resume Preconditions and Durability

- Resume rejects an empty or explicit Flow error observation, then rejects any
  remaining human challenge before unpausing a session.
- The requested project ID must match the durable action record. A composition
  root may supply a project-verifier callback to validate the current browser
  project with its existing two-signal mapping.
- Resolution (`resolved_by`, timestamp, status) is persisted before the
  session becomes eligible for new automated actions.

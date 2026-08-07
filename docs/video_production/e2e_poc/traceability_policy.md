# Full-Chain Traceability Policy

## 1. Overview

Full-chain traceability guarantees that every frame, audio segment, and prompt in the final video deliverable can be traced deterministically back to its originating screenplay revision, prompt block, and reference hash.

## 2. Traceability Directed Acyclic Graph (DAG) Structure

The traceability DAG links artifacts from top-level deliverable down to base inputs:

```text
Final Deliverable (SHA-256)
  └── Edit Decision List (EDL Hash)
        ├── Approved Shot Clips (Content Hashes)
        │     └── Flow Video Request & Candidate (Request Hash)
        │           ├── Compiled Prompt (Prompt Hash)
        │           └── Reference Bindings (Asset Hashes)
        │                 └── Character & Location Bibles
        ├── Approved Audio Track (Audio Hash)
        │     └── TTS Synthesis Requests & Alignment Cues
        └── Subtitle Track (Subtitle Hash)
              └── Screenplay Dialogue Lines (Revision ID)
                    └── Production Package Revision (Package SHA-256)
```

## 3. Audit Criteria

A run passes traceability audit if and only if:
1. Every node in the DAG possesses a valid SHA-256 content hash.
2. No dangling or unlinked intermediate media assets exist in the graph.
3. Every shot binding resolves to an approved character/location bible revision.

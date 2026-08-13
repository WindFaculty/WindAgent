# Story Frontend Gap Matrix (Roadmap 1 S12)

Evidence: StudioPage.tsx, components/studio/ArtifactViews.tsx, RunProgress.tsx, ApprovalBar.tsx, @windagent/studio-* packages, roadmap docs/plans/studio_roadmap_01.

## Surface matrix

| Required surface | Existing? | Implementation | Reusable | Missing work |
|---|---|---|---|---|
| Studio Home (series list) | YES | StudioPage route list view (#/studio) + store.loadSeriesList | HIGH | polish into cards/stat cards; move into studio-shell layout |
| Series | YES | StudioPage series view (#/studio/series/<id>): title, episodes list, create episode, start run | HIGH | series detail header, description field (API accepts), progress summary |
| Episode | YES | StudioPage episode view (#/studio/episodes/<id>): state/version/revision/run dl, start/resume, lock, RunProgress, ApprovalBar, artifacts | HIGH | Episode Workspace layout (tabs) |
| Idea | YES | IdeaSetView (candidate cards + select) + selectIdea flow (server-validated hash/version) | HIGH | candidate ranking/compare UI, empty/loading states are inline |
| Story (Bible) | PARTIAL | StoryBibleView, WorldBibleView, CharacterCanonView, BeatsView render server artifacts read-only | HIGH (view) | no editable story workflow UI (Story Bible editor); read-only viewer only |
| Outline | YES | OutlineView + OUTLINE checkpoint approval (ApprovalBar CHECKPOINT_PRIMARY_ARTIFACT) | HIGH | outline editor/beat-sheet interaction |
| Screenplay | YES | ScreenplayView + ScreenplayDiffView (2 drafts diff) + SCREENPLAY checkpoint + lock | HIGH | screenplay editor (production-ui StructuredEditor exists but is dead export + separate domain) |
| Review | YES | ReviewReportView (findings render) + approval decision bar + RevisionProposalView | HIGH | review findings navigation, filter by severity |
| Lock | YES | lockScreenplay (hash-bound) + LockReceiptView/LockPackageView + READ_ONLY_STATES LOCKED/READY_FOR_PRODUCTION banner | HIGH | lock summary page, lineage display |
| Run progress | YES | RunProgress (status colors, WAIT_LABEL, event feed, cursor) | HIGH | stage timeline rendering |
| Episode Workspace tabs (IDEA/STORY/OUTLINE/SCREENPLAY/REVIEW) | PARTIAL | all rendered as stacked sections on one page, gated by awaiting_checkpoint | MEDIUM | tabbed workspace layout = redesign task |

## Itemized checks

| Item | Status | Evidence |
|---|---|---|
| Idea candidate cards | EXISTS | ArtifactViews.tsx:281 IdeaSetView; select via StudioPage.tsx:211 |
| Story Bible editor/viewer | VIEWER ONLY | ArtifactViews.tsx:363 StoryBibleView (read-only render) |
| World Bible | VIEWER | ArtifactViews.tsx:385 |
| Character Canon | VIEWER | ArtifactViews.tsx:430 |
| Beat Sheet | VIEWER | ArtifactViews.tsx:472 BeatsView |
| Episode Outline | VIEWER + approval | ArtifactViews.tsx:497; OUTLINE in CHECKPOINT_PRIMARY_ARTIFACT |
| Screenplay editor | NONE in studio | ScreenplayView read-only; production-ui StructuredEditor/TextEditor are production-domain dead exports |
| Review findings | VIEWER | ArtifactViews.tsx:588 ReviewReportView |
| Revision viewer | PARTIAL | RevisionProposalView (633); ScreenplayDiffView between last 2 drafts (StudioPage.tsx:514-529) |
| Approve / Reject / Request revision | EXISTS | ApprovalBar (APPROVED/REJECTED/REQUEST_REVISION), recordApproval |
| Lock | EXISTS | lockScreenplay + read-only banner |
| Run progress | EXISTS | RunProgress |
| deriveRevision UI | NOT EXPOSED | client+store have it; StudioPage never calls (server-side revision derivation path) |

## Verdict

Story READ path is complete end-to-end (idea -> bible -> outline -> screenplay -> review -> lock -> READY_FOR_PRODUCTION). What's missing is presentation structure: episode workspace tabs, rich editors, review navigation, and design polish — all redesign-task scope. No backend work implied by the gap matrix.

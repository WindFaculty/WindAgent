# WindAgent Frontend Dependency Graph

Runtime roots: apps/desktop/index.html, apps/desktop/src/main.tsx, apps/web/index.html, apps/web/src/main.tsx

Files in scope (SOURCE/TEST/STYLE, excl. src-tauri): 226
Reachable from roots: 129
Not reachable: 99

## Reachability map (current HEAD + deletions applied)

- apps/desktop/src/App.tsx
- apps/desktop/src/api/client.ts
- apps/desktop/src/api/types.ts
- apps/desktop/src/components/assets/AssetAcquisitionWizard.tsx
- apps/desktop/src/components/assets/AssetInspector.tsx
- apps/desktop/src/components/assets/AssetJobMonitor.tsx
- apps/desktop/src/components/assets/AssetVersionImpactModal.tsx
- apps/desktop/src/components/assets/AssetWorkspace.tsx
- apps/desktop/src/components/assets/NonThreeDPreviewViewer.tsx
- apps/desktop/src/components/assets/ThreeDPreviewViewer.tsx
- apps/desktop/src/components/ui/Alert.tsx
- apps/desktop/src/components/ui/Badge.tsx
- apps/desktop/src/components/ui/Button.tsx
- apps/desktop/src/components/ui/Card.tsx
- apps/desktop/src/components/ui/Dropdown.tsx
- apps/desktop/src/components/ui/EmptyState.tsx
- apps/desktop/src/components/ui/Icon.tsx
- apps/desktop/src/components/ui/IconButton.tsx
- apps/desktop/src/components/ui/Panel.tsx
- apps/desktop/src/components/ui/ProgressBar.tsx
- apps/desktop/src/components/ui/SectionHeader.tsx
- apps/desktop/src/components/ui/Skeleton.tsx
- apps/desktop/src/components/ui/StatusBadge.tsx
- apps/desktop/src/components/ui/Tabs.tsx
- apps/desktop/src/components/ui/Tooltip.tsx
- apps/desktop/src/components/ui/index.ts
- apps/desktop/src/lib/apiBase.ts
- apps/desktop/src/main.tsx
- apps/desktop/src/pages/Agents.tsx
- apps/desktop/src/pages/Browser.tsx
- apps/desktop/src/pages/Dashboard.tsx
- apps/desktop/src/pages/Endpoints.tsx
- apps/desktop/src/pages/Files.tsx
- apps/desktop/src/pages/Memory.tsx
- apps/desktop/src/pages/Models.tsx
- apps/desktop/src/pages/MultiAgentWorkspace.tsx
- apps/desktop/src/pages/ProductionWorkspacePage.tsx
- apps/desktop/src/pages/Router.tsx
- apps/desktop/src/pages/Settings.tsx
- apps/desktop/src/pages/StudioPage.tsx
- apps/desktop/src/pages/Workflows.tsx
- apps/desktop/src/services/conversationSocketManager.ts
- apps/desktop/src/state/multiAgentStore.tsx
- apps/desktop/src/state/theme.tsx
- apps/web/src/app/App.tsx
- apps/web/src/main.tsx
- frontend/packages/production-client/src/ProductionApiClient.ts
- frontend/packages/production-client/src/index.ts
- frontend/packages/production-contracts/src/index.ts
- frontend/packages/production-contracts/src/routing/routeCodec.ts
- frontend/packages/production-contracts/src/screenplay/types.ts
- frontend/packages/production-contracts/src/types.ts
- frontend/packages/production-platform/src/adapters/BrowserWebAdapter.ts
- frontend/packages/production-platform/src/adapters/DesktopStorageRecoveryAdapter.ts
- frontend/packages/production-platform/src/adapters/FakeTestAdapter.ts
- frontend/packages/production-platform/src/adapters/TauriDesktopAdapter.ts
- frontend/packages/production-platform/src/adapters/WebStorageRecoveryAdapter.ts
- frontend/packages/production-platform/src/errors.ts
- frontend/packages/production-platform/src/index.ts
- frontend/packages/production-platform/src/types.ts
- frontend/packages/production-ui/src/components/AssetLibraryPlaceholder.tsx
- frontend/packages/production-ui/src/components/ImportFileDialog.tsx
- frontend/packages/production-ui/src/components/ProductionHeader.tsx
- frontend/packages/production-ui/src/components/ProductionShell.tsx
- frontend/packages/production-ui/src/components/ScriptEditorPlaceholder.tsx
- frontend/packages/production-ui/src/components/VideoWorkspacePlaceholder.tsx
- frontend/packages/production-ui/src/components/collaboration/ActivityTimelinePanel.tsx
- frontend/packages/production-ui/src/components/collaboration/ProposalInboxPanel.tsx
- frontend/packages/production-ui/src/components/conflict/ConflictResolverModal.tsx
- frontend/packages/production-ui/src/components/conflict/SemanticDiffViewer.tsx
- frontend/packages/production-ui/src/components/recovery/RecoveryPromptBanner.tsx
- frontend/packages/production-ui/src/components/screenplay/AIProposalView.tsx
- frontend/packages/production-ui/src/components/screenplay/AssetPickerModal.tsx
- frontend/packages/production-ui/src/components/screenplay/CrossNavigationLinks.tsx
- frontend/packages/production-ui/src/components/screenplay/MissingAssetResolverModal.tsx
- frontend/packages/production-ui/src/components/screenplay/ProductionImpactView.tsx
- frontend/packages/production-ui/src/components/screenplay/SceneInspector.tsx
- frontend/packages/production-ui/src/components/screenplay/SceneTree.tsx
- frontend/packages/production-ui/src/components/screenplay/ScreenplayBottomPanel.tsx
- frontend/packages/production-ui/src/components/screenplay/ScreenplayDiffView.tsx
- frontend/packages/production-ui/src/components/screenplay/ScreenplayHeader.tsx
- frontend/packages/production-ui/src/components/screenplay/ScreenplayWorkspaceView.tsx
- frontend/packages/production-ui/src/components/screenplay/StructuredEditor.tsx
- frontend/packages/production-ui/src/components/screenplay/TextEditor.tsx
- frontend/packages/production-ui/src/components/screenplay/ValidationGatePanel.tsx
- frontend/packages/production-ui/src/index.ts
- frontend/packages/story-ui/src/approval/ApprovalBar.tsx
- frontend/packages/story-ui/src/idea/IdeaSetView.tsx
- frontend/packages/story-ui/src/index.ts
- frontend/packages/story-ui/src/outline/OutlineView.tsx
- frontend/packages/story-ui/src/review/ReviewReportView.tsx
- frontend/packages/story-ui/src/revisions/RevisionProposalView.tsx
- frontend/packages/story-ui/src/runtime/PipelineProgress.tsx
- frontend/packages/story-ui/src/runtime/RunProgress.tsx
- frontend/packages/story-ui/src/screenplay/ScreenplayView.tsx
- frontend/packages/story-ui/src/shared/ArtifactView.tsx
- frontend/packages/story-ui/src/story/StoryBibleView.tsx
- frontend/packages/story-ui/src/workspace/EpisodeWorkspace.tsx
- frontend/packages/studio-client/src/HttpStudioApiClient.ts
- frontend/packages/studio-client/src/index.ts
- frontend/packages/studio-contracts/src/generated/index.ts
- frontend/packages/studio-contracts/src/generated/studio.approval-mode.ts
- frontend/packages/studio-contracts/src/generated/studio.artifact-envelope.ts
- frontend/packages/studio-contracts/src/generated/studio.episode-state.ts
- frontend/packages/studio-contracts/src/generated/studio.episode.ts
- frontend/packages/studio-contracts/src/generated/studio.error-payload.ts
- frontend/packages/studio-contracts/src/generated/studio.idempotency-headers.ts
- frontend/packages/studio-contracts/src/generated/studio.rabbit-kite-scenario.ts
- frontend/packages/studio-contracts/src/generated/studio.run-resource.ts
- frontend/packages/studio-contracts/src/generated/studio.run-status.ts
- frontend/packages/studio-contracts/src/generated/studio.series.ts
- frontend/packages/studio-contracts/src/index.ts
- frontend/packages/studio-shell/src/index.ts
- frontend/packages/studio-shell/src/layout/AppShell.tsx
- frontend/packages/studio-shell/src/layout/MainWorkspace.tsx
- frontend/packages/studio-shell/src/layout/Sidebar.tsx
- frontend/packages/studio-shell/src/layout/TopBar.tsx
- frontend/packages/studio-shell/src/layout/WorkspaceHeader.tsx
- frontend/packages/studio-shell/src/navigation/NavigationGroup.tsx
- frontend/packages/studio-shell/src/navigation/navigation.config.ts
- frontend/packages/studio-shell/src/navigation/navigation.types.ts
- frontend/packages/studio-shell/src/status/BackendStatus.tsx
- frontend/packages/studio-shell/src/status/RuntimeMetrics.tsx
- frontend/packages/studio-shell/src/status/RuntimeStatusStrip.tsx
- frontend/packages/studio-state/src/StudioStore.ts
- frontend/packages/studio-state/src/index.ts

## Not runtime-reachable (classified; see frontend_cleanup_candidates.json)

| path | classification |
|---|---|
| apps/desktop/src/components/ChatInput.tsx | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/components/ChatPanel.test.tsx | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/components/ChatPanel.tsx | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/components/ControlBar.test.tsx | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/components/ControlBar.tsx | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/components/MessageList.tsx | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/components/PermissionDialog.tsx | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/components/SessionNavigator.tsx | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/components/StatusBar.tsx | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/components/WorkflowPanel.test.tsx | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/components/WorkflowPanel.tsx | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/components/WorkflowStepItem.tsx | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/components/studio/ApprovalBar.tsx | ROADMAP_2_PRESERVED |
| apps/desktop/src/components/studio/ArtifactViews.tsx | ROADMAP_2_PRESERVED |
| apps/desktop/src/components/studio/RunProgress.tsx | ROADMAP_2_PRESERVED |
| apps/desktop/src/components/ui/__tests__/primitives.test.tsx | KEEP/UNKNOWN |
| apps/desktop/src/hooks/useSessionEvents.ts | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/lib/apiBase.test.ts | KEEP/UNKNOWN |
| apps/desktop/src/lib/routerApi.ts | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/services/agentEventReducer.ts | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/services/agentSocketManager.ts | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/services/conversationSocketManager.test.ts | KEEP/UNKNOWN |
| apps/desktop/src/state/agentSessionRecovery.test.ts | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/state/agentSessionSocket.test.ts | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/state/agentSessionStore.test.ts | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/state/agentSessionStore.ts | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/state/multiAgentStore.test.ts | KEEP/UNKNOWN |
| apps/desktop/src/state/sessionStore.test.ts | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/state/sessionStore.ts | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/state/useAgentSession.ts | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/test/productionPackageTests.test.ts | KEEP/UNKNOWN |
| apps/desktop/src/test/routerApi.unit.test.ts | VERIFIED_DELETE_CANDIDATE |
| apps/desktop/src/test/setup.ts | KEEP/UNKNOWN |
| apps/desktop/src/test/studioShellTests.test.tsx | KEEP/UNKNOWN |
| apps/desktop/src/test/studioStoryTests.test.tsx | KEEP/UNKNOWN |
| apps/desktop/vite.config.ts | KEEP/UNKNOWN |
| apps/desktop/vitest.config.ts | KEEP/UNKNOWN |
| apps/web/src/clients/__tests__/api_client.test.ts | VERIFIED_DELETE_CANDIDATE |
| apps/web/src/clients/__tests__/artifact_client.test.ts | VERIFIED_DELETE_CANDIDATE |
| apps/web/src/clients/__tests__/event_stream_client.test.ts | VERIFIED_DELETE_CANDIDATE |
| apps/web/src/clients/__tests__/permission_client.test.ts | VERIFIED_DELETE_CANDIDATE |
| apps/web/src/clients/__tests__/provider_client.test.ts | VERIFIED_DELETE_CANDIDATE |
| apps/web/src/clients/api_client.ts | VERIFIED_DELETE_CANDIDATE |
| apps/web/src/clients/artifact_client.ts | VERIFIED_DELETE_CANDIDATE |
| apps/web/src/clients/event_stream_client.ts | VERIFIED_DELETE_CANDIDATE |
| apps/web/src/clients/permission_client.ts | VERIFIED_DELETE_CANDIDATE |
| apps/web/src/clients/provider_client.ts | VERIFIED_DELETE_CANDIDATE |
| apps/web/src/state/__tests__/state_recovery.test.ts | VERIFIED_DELETE_CANDIDATE |
| apps/web/src/state/state_recovery.ts | VERIFIED_DELETE_CANDIDATE |
| apps/web/src/test/setup.ts | KEEP/UNKNOWN |
| apps/web/vite.config.ts | KEEP/UNKNOWN |
| frontend/packages/production-contracts/src/routing/routingCodec.ts | ROADMAP_2_PRESERVED |
| frontend/packages/production-platform/src/__tests__/architecture.test.ts | KEEP/UNKNOWN |
| frontend/packages/production-state/src/__tests__/projectContext.test.ts | KEEP/UNKNOWN |
| frontend/packages/production-state/src/__tests__/screenplaySlice.test.ts | KEEP/UNKNOWN |
| frontend/packages/production-state/src/hooks/useUnsavedChangesGuard.ts | KEEP/UNKNOWN |
| frontend/packages/production-state/src/index.ts | KEEP/UNKNOWN |
| frontend/packages/production-state/src/slices/bindingSlice.ts | KEEP/UNKNOWN |
| frontend/packages/production-state/src/slices/projectContextSlice.ts | KEEP/UNKNOWN |
| frontend/packages/production-state/src/slices/recoverySlice.ts | KEEP/UNKNOWN |
| frontend/packages/production-state/src/slices/screenplaySlice.ts | KEEP/UNKNOWN |
| frontend/packages/production-state/src/store.ts | KEEP/UNKNOWN |
| frontend/packages/production-ui/src/__tests__/ConsumerParity.test.tsx | KEEP/UNKNOWN |
| frontend/packages/production-ui/src/__tests__/ScreenplayWorkspaceView.test.tsx | KEEP/UNKNOWN |
| frontend/packages/production-ui/src/__tests__/routing.test.ts | KEEP/UNKNOWN |
| frontend/packages/production-ui/src/components/asset/__tests__/AssetManagerBehavioral.test.tsx | KEEP/UNKNOWN |
| frontend/packages/production-ui/src/components/screenplay/__tests__/ScriptEditorBehavioral.test.tsx | KEEP/UNKNOWN |
| frontend/packages/production-ui/vitest.config.ts | KEEP/UNKNOWN |
| frontend/packages/story-ui/src/__tests__/storyUi.test.tsx | KEEP/UNKNOWN |
| frontend/packages/story-ui/src/__tests__/storyUiPhase6.test.tsx | KEEP/UNKNOWN |
| frontend/packages/story-ui/src/__tests__/storyUiPhase7.test.tsx | KEEP/UNKNOWN |
| frontend/packages/story-ui/src/__tests__/storyUiPhase8.test.tsx | KEEP/UNKNOWN |
| frontend/packages/story-ui/vitest.config.ts | KEEP/UNKNOWN |
| frontend/packages/studio-client/src/__tests__/client.test.ts | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/approval-mode.all.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/artifact-envelope.screenplay.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/artifact-envelope.unknown-version.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/episode-state.progression.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/episode-state.valid.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/episode.locked.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/episode.valid.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/error-payload.capability-unavailable.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/error-payload.idempotency-mismatch.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/error-payload.provider-unavailable.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/error-payload.stale-revision.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/idempotency-headers.valid.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/malformed.episode.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/manifest.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/rabbit-kite-scenario.input.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/run-resource.waiting.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/run-status.valid.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/fixtures/series.valid.json | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/scripts/check-drift.mjs | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/scripts/generate-contracts.mjs | KEEP/UNKNOWN |
| frontend/packages/studio-contracts/src/__tests__/roundtrip.test.ts | KEEP/UNKNOWN |
| frontend/packages/studio-shell/src/__tests__/navigation.test.tsx | KEEP/UNKNOWN |
| frontend/packages/studio-shell/src/__tests__/studioShell.test.tsx | KEEP/UNKNOWN |
| frontend/packages/studio-shell/vitest.config.ts | KEEP/UNKNOWN |
| frontend/packages/studio-state/src/__tests__/store.test.ts | KEEP/UNKNOWN |

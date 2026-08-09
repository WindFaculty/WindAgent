import React, { useEffect } from 'react';
import {
  ScreenplayReadModelDTO,
  SceneReadDTO,
  DialogueReadDTO,
  DraftSaveStatus,
  ScreenplayDiffResultDTO,
  ScreenplayChangeImpactDTO,
  ScriptRevisionProposalDTO,
  ScreenplayValidationReportDTO,
} from '@windagent/production-contracts';
import { ScreenplayHeader } from './ScreenplayHeader';
import { SceneTree } from './SceneTree';
import { StructuredEditor } from './StructuredEditor';
import { TextEditor } from './TextEditor';
import { SceneInspector } from './SceneInspector';
import { ScreenplayBottomPanel } from './ScreenplayBottomPanel';

export interface ScreenplayWorkspaceViewProps {
  readModel: ScreenplayReadModelDTO | null;
  selectedSceneId: string | null;
  selectedDialogueId: string | null;
  editorMode: 'STRUCTURED' | 'TEXT';
  saveStatus: DraftSaveStatus;
  canUndo: boolean;
  canRedo: boolean;
  activeDiff: ScreenplayDiffResultDTO | null;
  activeImpact: ScreenplayChangeImpactDTO | null;
  activeProposal: ScriptRevisionProposalDTO | null;
  validationReport: ScreenplayValidationReportDTO | null;
  fountainText: string;

  // Actions
  onSelectScene: (sceneId: string) => void;
  onToggleMode: (mode: 'STRUCTURED' | 'TEXT') => void;
  onUpdateSceneField: (sceneId: string, fieldName: keyof SceneReadDTO, value: unknown) => void;
  onUpdateDialogueField: (sceneId: string, dialogueId: string, fieldName: keyof DialogueReadDTO, value: unknown) => void;
  onAddScene: () => void;
  onReorderScene: (sceneId: string, direction: 'UP' | 'DOWN') => void;
  onUndo: () => void;
  onRedo: () => void;
  onSaveDraft: () => void;
  onCreateDraft: () => void;
  onLockRevision: () => void;
  onApplyParsedText: (text: string) => void;
  onRequestProposal: (actionType: string, instruction: string) => void;
  onApproveProposal: (proposalId: string) => void;
  onRejectProposal: (proposalId: string) => void;
}

export const ScreenplayWorkspaceView: React.FC<ScreenplayWorkspaceViewProps> = ({
  readModel,
  selectedSceneId,
  selectedDialogueId,
  editorMode,
  saveStatus,
  canUndo,
  canRedo,
  activeDiff,
  activeImpact,
  activeProposal,
  validationReport,
  fountainText,
  onSelectScene,
  onToggleMode,
  onUpdateSceneField,
  onUpdateDialogueField,
  onAddScene,
  onReorderScene,
  onUndo,
  onRedo,
  onSaveDraft,
  onCreateDraft,
  onLockRevision,
  onApplyParsedText,
  onRequestProposal,
  onApproveProposal,
  onRejectProposal,
}) => {
  const isReadOnly = readModel?.is_locked ?? false;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        width: '100%',
        backgroundColor: '#1E1E2E',
        color: '#CDD6F4',
        fontFamily: 'Inter, system-ui, sans-serif',
        overflow: 'hidden',
      }}
    >
      {/* Top Header */}
      <ScreenplayHeader
        readModel={readModel}
        editorMode={editorMode}
        saveStatus={saveStatus}
        onToggleMode={onToggleMode}
        onCreateDraft={onCreateDraft}
        onLockRevision={onLockRevision}
        onSaveDraft={onSaveDraft}
      />

      {/* Main 3-Column Content Body */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left Column: Scene Tree */}
        <div style={{ width: '250px', flexShrink: 0 }}>
          <SceneTree
            scenes={readModel?.scenes || []}
            selectedSceneId={selectedSceneId}
            onSelectScene={onSelectScene}
            onAddScene={onAddScene}
            onReorderScene={onReorderScene}
            isReadOnly={isReadOnly}
          />
        </div>

        {/* Center Column: Structured or Text Editor Host */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {editorMode === 'STRUCTURED' ? (
            readModel ? (
              <StructuredEditor
                readModel={readModel}
                selectedSceneId={selectedSceneId}
                onUpdateSceneField={onUpdateSceneField}
                onUpdateDialogueField={onUpdateDialogueField}
                onUndo={onUndo}
                onRedo={onRedo}
                canUndo={canUndo}
                canRedo={canRedo}
                isReadOnly={isReadOnly}
              />
            ) : (
              <div style={{ padding: '2rem', color: '#6C7086' }}>Loading screenplay model...</div>
            )
          ) : (
            <TextEditor
              initialText={fountainText}
              onApplyParsedText={onApplyParsedText}
              isReadOnly={isReadOnly}
            />
          )}
        </div>

        {/* Right Column: Scene Inspector */}
        <div style={{ width: '270px', flexShrink: 0 }}>
          {readModel && <SceneInspector readModel={readModel} selectedSceneId={selectedSceneId} />}
        </div>
      </div>

      {/* Bottom Panel */}
      <ScreenplayBottomPanel
        diffResult={activeDiff}
        impact={activeImpact}
        activeProposal={activeProposal}
        validationReport={validationReport}
        onRequestProposal={onRequestProposal}
        onApproveProposal={onApproveProposal}
        onRejectProposal={onRejectProposal}
        onLockRevision={onLockRevision}
        onSelectEntity={onSelectScene}
      />
    </div>
  );
};

/**
 * Screenplay Redux State Slice (Stage C — UI8, UI10, UI13).
 *
 * Manages normalized screenplay state, selection, active editor mode (STRUCTURED vs TEXT),
 * local edit unit buffer, local undo/redo stack, and draft save lifecycle machine.
 */

import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import {
  ScreenplayReadModelDTO,
  SceneReadDTO,
  DialogueReadDTO,
  EditUnit,
  DraftSaveStatus,
  ScreenplayDiffResultDTO,
  ScreenplayChangeImpactDTO,
  ScriptRevisionProposalDTO,
  ScreenplayValidationReportDTO,
} from '@windagent/production-contracts';

export interface ScreenplayState {
  readModel: ScreenplayReadModelDTO | null;
  selectedSceneId: string | null;
  selectedDialogueId: string | null;
  editorMode: 'STRUCTURED' | 'TEXT';
  saveStatus: DraftSaveStatus;
  editUnitBuffer: EditUnit[];
  undoStack: EditUnit[];
  redoStack: EditUnit[];
  activeDiff: ScreenplayDiffResultDTO | null;
  activeImpact: ScreenplayChangeImpactDTO | null;
  activeProposal: ScriptRevisionProposalDTO | null;
  validationReport: ScreenplayValidationReportDTO | null;
  fountainTextBuffer: string;
  isSaving: boolean;
  error: string | null;
}

const initialState: ScreenplayState = {
  readModel: null,
  selectedSceneId: null,
  selectedDialogueId: null,
  editorMode: 'STRUCTURED',
  saveStatus: 'SERVER',
  editUnitBuffer: [],
  undoStack: [],
  redoStack: [],
  activeDiff: null,
  activeImpact: null,
  activeProposal: null,
  validationReport: null,
  fountainTextBuffer: '',
  isSaving: false,
  error: null,
};

export const screenplaySlice = createSlice({
  name: 'screenplay',
  initialState,
  reducers: {
    setReadModel: (state, action: PayloadAction<ScreenplayReadModelDTO>) => {
      state.readModel = action.payload;
      state.saveStatus = 'SERVER';
      state.editUnitBuffer = [];
      if (!state.selectedSceneId && action.payload.scenes.length > 0) {
        state.selectedSceneId = action.payload.scenes[0].scene_id;
      }
    },
    setSelectedSceneId: (state, action: PayloadAction<string | null>) => {
      state.selectedSceneId = action.payload;
    },
    setSelectedDialogueId: (state, action: PayloadAction<string | null>) => {
      state.selectedDialogueId = action.payload;
    },
    setEditorMode: (state, action: PayloadAction<'STRUCTURED' | 'TEXT'>) => {
      state.editorMode = action.payload;
    },
    updateSceneField: (
      state,
      action: PayloadAction<{ sceneId: string; fieldName: keyof SceneReadDTO; value: unknown }>
    ) => {
      if (!state.readModel) return;
      const scene = state.readModel.scenes.find((s) => s.scene_id === action.payload.sceneId);
      if (scene) {
        const oldValue = scene[action.payload.fieldName];
        (scene as Record<string, unknown>)[action.payload.fieldName] = action.payload.value;

        const editUnit: EditUnit = {
          unit_id: `unit_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
          timestamp: Date.now(),
          target_type: 'SCENE',
          entity_id: action.payload.sceneId,
          field_name: String(action.payload.fieldName),
          old_value: oldValue,
          new_value: action.payload.value,
        };
        state.editUnitBuffer.push(editUnit);
        state.undoStack.push(editUnit);
        state.redoStack = [];
        state.saveStatus = 'LOCAL_MODIFIED';
      }
    },
    updateDialogueField: (
      state,
      action: PayloadAction<{ sceneId: string; dialogueId: string; fieldName: keyof DialogueReadDTO; value: unknown }>
    ) => {
      if (!state.readModel) return;
      const scene = state.readModel.scenes.find((s) => s.scene_id === action.payload.sceneId);
      if (scene) {
        const dlg = scene.dialogue_lines.find((d) => d.dialogue_id === action.payload.dialogueId);
        if (dlg) {
          const oldValue = dlg[action.payload.fieldName];
          (dlg as Record<string, unknown>)[action.payload.fieldName] = action.payload.value;

          const editUnit: EditUnit = {
            unit_id: `unit_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
            timestamp: Date.now(),
            target_type: 'DIALOGUE',
            entity_id: action.payload.dialogueId,
            field_name: String(action.payload.fieldName),
            old_value: oldValue,
            new_value: action.payload.value,
          };
          state.editUnitBuffer.push(editUnit);
          state.undoStack.push(editUnit);
          state.redoStack = [];
          state.saveStatus = 'LOCAL_MODIFIED';
        }
      }
    },
    addScene: (state, action: PayloadAction<{ title: string; locationName: string }>) => {
      if (!state.readModel) return;
      const newOrder = state.readModel.scenes.length + 1;
      const newSceneId = `scene_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
      const newScene: SceneReadDTO = {
        scene_id: newSceneId,
        order: newOrder,
        title: action.payload.title || `INT. NEW LOCATION - DAY`,
        location_id: `loc_${newSceneId}`,
        location_name: action.payload.locationName || 'NEW LOCATION',
        character_ids: [],
        action_description: 'Action description goes here.',
        time_of_day: 'DAY',
        dialogue_lines: [],
        estimated_duration_seconds: 15,
      };
      state.readModel.scenes.push(newScene);
      state.selectedSceneId = newSceneId;
      state.saveStatus = 'LOCAL_MODIFIED';
    },
    reorderScenes: (state, action: PayloadAction<{ sceneId: string; direction: 'UP' | 'DOWN' }>) => {
      if (!state.readModel) return;
      const idx = state.readModel.scenes.findIndex((s) => s.scene_id === action.payload.sceneId);
      if (idx === -1) return;

      const targetIdx = action.payload.direction === 'UP' ? idx - 1 : idx + 1;
      if (targetIdx < 0 || targetIdx >= state.readModel.scenes.length) return;

      const temp = state.readModel.scenes[idx];
      state.readModel.scenes[idx] = state.readModel.scenes[targetIdx];
      state.readModel.scenes[targetIdx] = temp;

      state.readModel.scenes.forEach((s, i) => {
        s.order = i + 1;
      });
      state.saveStatus = 'LOCAL_MODIFIED';
    },
    undoLocalEdit: (state) => {
      const lastUnit = state.undoStack.pop();
      if (!lastUnit || !state.readModel) return;

      if (lastUnit.target_type === 'SCENE') {
        const sc = state.readModel.scenes.find((s) => s.scene_id === lastUnit.entity_id);
        if (sc) {
          (sc as Record<string, unknown>)[lastUnit.field_name] = lastUnit.old_value;
        }
      } else if (lastUnit.target_type === 'DIALOGUE') {
        for (const sc of state.readModel.scenes) {
          const d = sc.dialogue_lines.find((dlg) => dlg.dialogue_id === lastUnit.entity_id);
          if (d) {
            (d as Record<string, unknown>)[lastUnit.field_name] = lastUnit.old_value;
            break;
          }
        }
      }
      state.redoStack.push(lastUnit);
      state.saveStatus = 'LOCAL_MODIFIED';
    },
    redoLocalEdit: (state) => {
      const unit = state.redoStack.pop();
      if (!unit || !state.readModel) return;

      if (unit.target_type === 'SCENE') {
        const sc = state.readModel.scenes.find((s) => s.scene_id === unit.entity_id);
        if (sc) {
          (sc as Record<string, unknown>)[unit.field_name] = unit.new_value;
        }
      } else if (unit.target_type === 'DIALOGUE') {
        for (const sc of state.readModel.scenes) {
          const d = sc.dialogue_lines.find((dlg) => dlg.dialogue_id === unit.entity_id);
          if (d) {
            (d as Record<string, unknown>)[unit.field_name] = unit.new_value;
            break;
          }
        }
      }
      state.undoStack.push(unit);
      state.saveStatus = 'LOCAL_MODIFIED';
    },
    setSaveStatus: (state, action: PayloadAction<DraftSaveStatus>) => {
      state.saveStatus = action.payload;
      if (action.payload === 'SAVED') {
        state.editUnitBuffer = [];
      }
    },
    setFountainTextBuffer: (state, action: PayloadAction<string>) => {
      state.fountainTextBuffer = action.payload;
    },
    setActiveDiff: (state, action: PayloadAction<ScreenplayDiffResultDTO | null>) => {
      state.activeDiff = action.payload;
    },
    setActiveImpact: (state, action: PayloadAction<ScreenplayChangeImpactDTO | null>) => {
      state.activeImpact = action.payload;
    },
    setActiveProposal: (state, action: PayloadAction<ScriptRevisionProposalDTO | null>) => {
      state.activeProposal = action.payload;
    },
    setValidationReport: (state, action: PayloadAction<ScreenplayValidationReportDTO | null>) => {
      state.validationReport = action.payload;
    },
    setError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload;
    },
  },
});

export const {
  setReadModel,
  setSelectedSceneId,
  setSelectedDialogueId,
  setEditorMode,
  updateSceneField,
  updateDialogueField,
  addScene,
  reorderScenes,
  undoLocalEdit,
  redoLocalEdit,
  setSaveStatus,
  setFountainTextBuffer,
  setActiveDiff,
  setActiveImpact,
  setActiveProposal,
  setValidationReport,
  setError,
} = screenplaySlice.actions;

export default screenplaySlice.reducer;

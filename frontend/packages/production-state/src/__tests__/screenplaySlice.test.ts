import { describe, it, expect } from 'vitest';
import { screenplaySlice, setReadModel, updateSceneField, undoLocalEdit, redoLocalEdit, addScene, reorderScenes } from '../slices/screenplaySlice';
import { ScreenplayReadModelDTO } from '@windagent/production-contracts';

describe('screenplaySlice', () => {
  const initialReadModel: ScreenplayReadModelDTO = {
    screenplay_id: 'sp_01',
    project_id: 'proj_01',
    revision_id: 'rev_01',
    title: 'Test Title',
    logline: 'Test Logline',
    status: 'DRAFT',
    is_locked: false,
    current_sequence: 1,
    scenes: [
      {
        scene_id: 'sc_01',
        order: 1,
        title: 'INT. OFFICE - DAY',
        location_id: 'loc_office',
        location_name: 'Office',
        character_ids: ['char_boss'],
        action_description: 'Boss sits at desk.',
        time_of_day: 'DAY',
        dialogue_lines: [],
        estimated_duration_seconds: 10,
      },
      {
        scene_id: 'sc_02',
        order: 2,
        title: 'EXT. STREET - NIGHT',
        location_id: 'loc_street',
        location_name: 'Street',
        character_ids: ['char_hero'],
        action_description: 'Hero walks outside.',
        time_of_day: 'NIGHT',
        dialogue_lines: [],
        estimated_duration_seconds: 15,
      },
    ],
    characters: [],
    locations: [],
    validation: {
      total_issues: 0,
      blocking_count: 0,
      warning_count: 0,
      info_count: 0,
      is_lockable: true,
    },
    estimated_duration_seconds: 25,
    downstream_bindings: [],
  };

  it('sets read model and initializes active selected scene', () => {
    const state = screenplaySlice.reducer(undefined, setReadModel(initialReadModel));
    expect(state.readModel?.screenplay_id).toBe('sp_01');
    expect(state.selectedSceneId).toBe('sc_01');
    expect(state.saveStatus).toBe('SERVER');
  });

  it('handles field update with edit unit accumulation and undo/redo', () => {
    let state = screenplaySlice.reducer(undefined, setReadModel(initialReadModel));

    state = screenplaySlice.reducer(
      state,
      updateSceneField({ sceneId: 'sc_01', fieldName: 'action_description', value: 'Updated action.' })
    );

    expect(state.readModel?.scenes[0].action_description).toBe('Updated action.');
    expect(state.saveStatus).toBe('LOCAL_MODIFIED');
    expect(state.editUnitBuffer.length).toBe(1);
    expect(state.undoStack.length).toBe(1);

    // Test Undo
    state = screenplaySlice.reducer(state, undoLocalEdit());
    expect(state.readModel?.scenes[0].action_description).toBe('Boss sits at desk.');
    expect(state.redoStack.length).toBe(1);

    // Test Redo
    state = screenplaySlice.reducer(state, redoLocalEdit());
    expect(state.readModel?.scenes[0].action_description).toBe('Updated action.');
  });

  it('handles scene reordering', () => {
    let state = screenplaySlice.reducer(undefined, setReadModel(initialReadModel));
    state = screenplaySlice.reducer(state, reorderScenes({ sceneId: 'sc_01', direction: 'DOWN' }));

    expect(state.readModel?.scenes[0].scene_id).toBe('sc_02');
    expect(state.readModel?.scenes[0].order).toBe(1);
    expect(state.readModel?.scenes[1].scene_id).toBe('sc_01');
    expect(state.readModel?.scenes[1].order).toBe(2);
  });
});

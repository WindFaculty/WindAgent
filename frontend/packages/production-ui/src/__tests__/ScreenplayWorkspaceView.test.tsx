import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { ScreenplayHeader } from '../components/screenplay/ScreenplayHeader';
import { ValidationGatePanel } from '../components/screenplay/ValidationGatePanel';
import { ScreenplayReadModelDTO, ScreenplayValidationReportDTO } from '@windagent/production-contracts';

describe('Screenplay UI Components', () => {
  const dummyReadModel: ScreenplayReadModelDTO = {
    screenplay_id: 'sp_01',
    project_id: 'proj_01',
    revision_id: 'rev_001',
    title: 'THE CYBERPUNK CHRONICLES',
    logline: 'A hacker unveils secret artificial intelligence network.',
    status: 'DRAFT',
    is_locked: false,
    current_sequence: 1,
    scenes: [],
    characters: [],
    locations: [],
    validation: {
      total_issues: 0,
      blocking_count: 0,
      warning_count: 0,
      info_count: 0,
      is_lockable: true,
    },
    estimated_duration_seconds: 60,
    downstream_bindings: [],
  };

  it('instantiates ScreenplayHeader element with props', () => {
    const element = (
      <ScreenplayHeader
        readModel={dummyReadModel}
        editorMode="STRUCTURED"
        saveStatus="SERVER"
        onToggleMode={vi.fn()}
        onCreateDraft={vi.fn()}
        onLockRevision={vi.fn()}
        onSaveDraft={vi.fn()}
      />
    );

    expect(element.props.readModel.title).toBe('THE CYBERPUNK CHRONICLES');
    expect(element.props.editorMode).toBe('STRUCTURED');
  });

  it('instantiates ValidationGatePanel element with report props', () => {
    const report: ScreenplayValidationReportDTO = {
      project_id: 'proj_01',
      revision_id: 'rev_001',
      is_lockable: false,
      total_issues: 1,
      blocking_count: 1,
      warning_count: 0,
      info_count: 0,
      issues: [
        {
          code: 'NO_SCENES_PRESENT',
          severity: 'BLOCKING',
          entity_type: 'SCREENPLAY',
          entity_id: 'sp_01',
          message: 'Screenplay contains no valid scenes.',
          remediation_hint: 'Add a scene heading.',
        },
      ],
      asset_requirements: [],
    };

    const element = <ValidationGatePanel report={report} onLockRevision={vi.fn()} />;

    expect(element.props.report.blocking_count).toBe(1);
    expect(element.props.report.is_lockable).toBe(false);
  });
});

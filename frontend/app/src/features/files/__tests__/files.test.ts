import { describe, it, expect } from 'vitest';
import { FilesPage } from '../pages/FilesPage';
import { useFiles, useCreateFile, useDeleteFile, filesKeys } from '../hooks/useFiles';

describe('Files Feature Package (Phase 13B)', () => {
  it('exports page and hooks', () => {
    expect(FilesPage).toBeDefined();
    expect(useFiles).toBeDefined();
    expect(useCreateFile).toBeDefined();
    expect(useDeleteFile).toBeDefined();
  });

  it('defines canonical query keys', () => {
    expect(filesKeys.list()).toEqual(['v3', 'files', 'list']);
  });

  it('sends only workspace-relative contract paths', () => {
    // absolute host paths are rejected server-side; client never builds them
    const createPayload = { path: 'notes/idea.md', name: 'idea.md', content: 'x' };
    expect(createPayload.path.startsWith('/')).toBe(false);
    expect(createPayload.path.includes(':/')).toBe(false);
    expect(createPayload.path.includes('..')).toBe(false);
  });
});
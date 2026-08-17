import { describe, it, expect } from 'vitest';
import { MemoryPage } from '../pages/MemoryPage';
import { useMemoryRecords, useMemorySearch, useCreateMemory, memoryKeys, MEMORY_SCOPES, MEMORY_TYPES } from '../hooks/useMemory';

describe('Memory Feature Package (Phase 13C)', () => {
  it('exports page and hooks', () => {
    expect(MemoryPage).toBeDefined();
    expect(useMemoryRecords).toBeDefined();
    expect(useMemorySearch).toBeDefined();
    expect(useCreateMemory).toBeDefined();
  });

  it('defines canonical query keys', () => {
    expect(memoryKeys.list('agent')).toEqual(['v3', 'memory', 'list', 'agent']);
    expect(memoryKeys.search('needle')).toEqual(['v3', 'memory', 'search', 'needle']);
  });

  it('scopes match the backend contract (Memory != Database)', () => {
    expect(MEMORY_SCOPES).toEqual(['conversation', 'project', 'agent', 'global']);
    expect(MEMORY_TYPES).toEqual(['working', 'short_term', 'long_term']);
  });
});
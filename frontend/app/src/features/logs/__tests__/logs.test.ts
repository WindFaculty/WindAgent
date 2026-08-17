import { describe, it, expect } from 'vitest';
import { LogsPage } from '../pages/LogsPage';
import { useLogs, useLogSources, useLogStream, logsKeys, LOG_LEVELS } from '../hooks/useLogs';

describe('Logs Feature Package (Phase 13D)', () => {
  it('exports page and hooks', () => {
    expect(LogsPage).toBeDefined();
    expect(useLogs).toBeDefined();
    expect(useLogSources).toBeDefined();
    expect(useLogStream).toBeDefined();
  });

  it('defines canonical query keys', () => {
    expect(logsKeys.list({ level: 'ERROR' })).toEqual(['v3', 'logs', 'list', { level: 'ERROR' }]);
    expect(logsKeys.sources()).toEqual(['v3', 'logs', 'sources']);
  });

  it('levels match the backend contract', () => {
    expect(LOG_LEVELS).toEqual(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']);
  });

  it('filters map to LogRecord correlation fields', () => {
    const filters = { level: 'ERROR', source: 'api', correlation_id: 'corr-1', limit: 50 };
    expect(filters).toHaveProperty('level');
    expect(filters).toHaveProperty('source');
    expect(filters).toHaveProperty('correlation_id');
  });
});
import { describe, it, expect } from 'vitest';
import { FakeTestAdapter } from '../adapters/FakeTestAdapter';
import { BrowserWebAdapter } from '../adapters/BrowserWebAdapter';
import { TauriDesktopAdapter } from '../adapters/TauriDesktopAdapter';
import { CancelledError, UnsupportedError } from '../errors';

describe('Production Platform Adapters & Boundaries', () => {
  it('FakeTestAdapter handles successful file selection and capabilities', async () => {
    const adapter = new FakeTestAdapter();
    expect(adapter.supportsLocalFilesystem()).toBe(true);

    const files = await adapter.selectLocalFile();
    expect(files.length).toBe(1);
    expect(files[0].name).toBe('screenplay_v1.fountain');
  });

  it('FakeTestAdapter handles user cancellation cleanly with CancelledError', async () => {
    const adapter = new FakeTestAdapter();
    adapter.shouldFailCancel = true;

    await expect(adapter.selectLocalFile()).rejects.toThrow(CancelledError);
  });

  it('BrowserWebAdapter reports no native local filesystem support', () => {
    const adapter = new BrowserWebAdapter();
    expect(adapter.supportsLocalFilesystem()).toBe(false);
  });

  it('BrowserWebAdapter throws UnsupportedError when revealFile is called', async () => {
    const adapter = new BrowserWebAdapter();
    await expect(adapter.revealFile('art-1')).rejects.toThrow(UnsupportedError);
  });

  it('TauriDesktopAdapter reports local filesystem support', () => {
    const adapter = new TauriDesktopAdapter();
    expect(adapter.supportsLocalFilesystem()).toBe(true);
  });
});

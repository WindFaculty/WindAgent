import { SelectedFile } from '@windagent/production-contracts';
import { ProductionPlatformAdapter, SelectFileOptions, IStateRecoveryStorageAdapter } from '../types';
import { DesktopStorageRecoveryAdapter } from './DesktopStorageRecoveryAdapter';
import { CancelledError, UnsupportedError } from '../errors';

export class FakeTestAdapter implements ProductionPlatformAdapter {
  recoveryStorage: IStateRecoveryStorageAdapter = new DesktopStorageRecoveryAdapter();
  public shouldFailCancel = false;
  public shouldFailUnsupported = false;
  public mockFiles: SelectedFile[] = [
    {
      id: 'fixture-file-1',
      name: 'screenplay_v1.fountain',
      size: 1024,
      type: 'text/plain',
    },
  ];

  supportsLocalFilesystem(): boolean {
    return !this.shouldFailUnsupported;
  }

  async selectLocalFile(_options?: SelectFileOptions): Promise<SelectedFile[]> {
    if (this.shouldFailCancel) {
      throw new CancelledError();
    }
    if (this.shouldFailUnsupported) {
      throw new UnsupportedError();
    }
    return [...this.mockFiles];
  }

  async revealFile(artifactId: string): Promise<void> {
    if (this.shouldFailUnsupported) throw new UnsupportedError();
    console.log(`[FakeTestAdapter] revealed artifact ${artifactId}`);
  }

  async openExternal(url: string): Promise<void> {
    if (this.shouldFailUnsupported) throw new UnsupportedError();
    console.log(`[FakeTestAdapter] opened external ${url}`);
  }

  async downloadArtifact(id: string): Promise<void> {
    if (this.shouldFailUnsupported) throw new UnsupportedError();
    console.log(`[FakeTestAdapter] downloaded artifact ${id}`);
  }
}

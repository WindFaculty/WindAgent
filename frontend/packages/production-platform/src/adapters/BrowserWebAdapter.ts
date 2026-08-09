import { SelectedFile } from '@windagent/production-contracts';
import { ProductionPlatformAdapter, SelectFileOptions, IStateRecoveryStorageAdapter } from '../types';
import { WebStorageRecoveryAdapter } from './WebStorageRecoveryAdapter';
import { CancelledError, UnsupportedError } from '../errors';

export class BrowserWebAdapter implements ProductionPlatformAdapter {
  recoveryStorage: IStateRecoveryStorageAdapter = new WebStorageRecoveryAdapter();

  supportsLocalFilesystem(): boolean {
    return false;
  }

  async selectLocalFile(options?: SelectFileOptions): Promise<SelectedFile[]> {
    return new Promise((resolve, reject) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.multiple = !!options?.multiple;
      if (options?.accept && options.accept.length > 0) {
        input.accept = options.accept.join(',');
      }

      input.onchange = () => {
        if (!input.files || input.files.length === 0) {
          reject(new CancelledError());
          return;
        }

        const selected: SelectedFile[] = Array.from(input.files).map((file, idx) => ({
          id: `web-file-${Date.now()}-${idx}`,
          name: file.name,
          size: file.size,
          type: file.type,
          fileObject: file,
        }));
        resolve(selected);
      };

      input.onerror = () => reject(new CancelledError());
      input.click();
    });
  }

  async revealFile(): Promise<void> {
    throw new UnsupportedError('Local file reveal is not supported in web browser environment');
  }

  async openExternal(url: string): Promise<void> {
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  async downloadArtifact(id: string): Promise<void> {
    const a = document.createElement('a');
    a.href = `/api/v1/artifacts/${encodeURIComponent(id)}/download`;
    a.download = id;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
}

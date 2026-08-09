import { SelectedFile } from '@windagent/production-contracts';
import { ProductionPlatformAdapter, SelectFileOptions, IStateRecoveryStorageAdapter } from '../types';
import { DesktopStorageRecoveryAdapter } from './DesktopStorageRecoveryAdapter';
import { CancelledError, TransferFailedError } from '../errors';

export class TauriDesktopAdapter implements ProductionPlatformAdapter {
  recoveryStorage: IStateRecoveryStorageAdapter = new DesktopStorageRecoveryAdapter();

  supportsLocalFilesystem(): boolean {
    return true;
  }

  async selectLocalFile(options?: SelectFileOptions): Promise<SelectedFile[]> {
    try {
      // Dynamic import to avoid static build-time link error in non-tauri environments
      const tauriDialog = (window as unknown as { __TAURI__?: { dialog?: { open?: (opts: unknown) => Promise<string | string[] | null> } } }).__TAURI__?.dialog;
      if (tauriDialog?.open) {
        const result = await tauriDialog.open({
          multiple: options?.multiple,
          filters: options?.accept ? [{ name: 'Allowed Files', extensions: options.accept }] : undefined,
        });

        if (!result) throw new CancelledError();
        const paths = Array.isArray(result) ? result : [result];
        return paths.map((p, idx) => ({
          id: `tauri-file-${Date.now()}-${idx}`,
          name: p.split(/[/\\]/).pop() || p,
          size: 0,
          type: 'application/octet-stream',
        }));
      }

      // Fallback for browser testing window
      return new Promise((resolve, reject) => {
        const input = document.createElement('input');
        input.type = 'file';
        input.multiple = !!options?.multiple;
        input.onchange = () => {
          if (!input.files || input.files.length === 0) return reject(new CancelledError());
          resolve(
            Array.from(input.files).map((f, idx) => ({
              id: `desktop-fallback-${Date.now()}-${idx}`,
              name: f.name,
              size: f.size,
              type: f.type,
              fileObject: f,
            }))
          );
        };
        input.click();
      });
    } catch (err) {
      if (err instanceof CancelledError) throw err;
      throw new TransferFailedError((err as Error).message);
    }
  }

  async revealFile(artifactId: string): Promise<void> {
    const tauriOpener = (window as unknown as { __TAURI__?: { opener?: { revealItemInDir?: (path: string) => Promise<void> } } }).__TAURI__?.opener;
    if (tauriOpener?.revealItemInDir) {
      await tauriOpener.revealItemInDir(artifactId);
    }
  }

  async openExternal(url: string): Promise<void> {
    window.open(url, '_blank');
  }

  async downloadArtifact(id: string): Promise<void> {
    const a = document.createElement('a');
    a.href = `/api/v1/artifacts/${encodeURIComponent(id)}/download`;
    a.download = id;
    a.click();
  }
}

import { SelectedFile } from '@windagent/production-contracts';

export interface SelectFileOptions {
  multiple?: boolean;
  accept?: string[];
}

export interface IStateRecoveryStorageAdapter {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
  clear(): Promise<void>;
}

export interface ProductionPlatformAdapter {
  selectLocalFile(options?: SelectFileOptions): Promise<SelectedFile[]>;
  revealFile?(artifactId: string): Promise<void>;
  openExternal(url: string): Promise<void>;
  downloadArtifact(id: string): Promise<void>;
  supportsLocalFilesystem(): boolean;
  recoveryStorage?: IStateRecoveryStorageAdapter;
}

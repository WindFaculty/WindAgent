import { SyncStatus } from '@windagent/production-contracts';

export function checkUnsavedChangesGuard(
  syncStatus: SyncStatus,
  onConfirmLeave?: () => boolean
): boolean {
  if (syncStatus === 'unsaved' || syncStatus === 'conflict') {
    if (onConfirmLeave) {
      return onConfirmLeave();
    }
    if (typeof window !== 'undefined' && window.confirm) {
      return window.confirm('You have unsaved changes in current project. Are you sure you want to switch?');
    }
    return false;
  }
  return true;
}

export class PlatformError extends Error {
  constructor(public code: 'CANCELLED' | 'DENIED' | 'UNSUPPORTED' | 'TRANSFER_FAILED', message: string) {
    super(message);
    this.name = 'PlatformError';
  }
}

export class CancelledError extends PlatformError {
  constructor(message = 'User cancelled operation') {
    super('CANCELLED', message);
  }
}

export class DeniedError extends PlatformError {
  constructor(message = 'Permission denied by user or OS') {
    super('DENIED', message);
  }
}

export class UnsupportedError extends PlatformError {
  constructor(message = 'Operation unsupported on current platform') {
    super('UNSUPPORTED', message);
  }
}

export class TransferFailedError extends PlatformError {
  constructor(message = 'File or artifact transfer failed') {
    super('TRANSFER_FAILED', message);
  }
}

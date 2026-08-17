/**
 * Command Receipt Model for HTTP 202 Accepted.
 */

export interface CommandReceipt {
  command_id: string;
  status: 'ACCEPTED' | 'QUEUED' | string;
  resource_id?: string | null;
  correlation_id?: string | null;
  submitted_at: string;
}

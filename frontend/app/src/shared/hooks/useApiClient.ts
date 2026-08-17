/**
 * useApiClient — Canonical access point for the generated V3 API client.
 *
 * Re-exported from the ApiProvider so features never construct their own
 * transport or duplicate client wiring.
 */

export { useApiClient } from '../../api/ApiProvider';
export type { WindAgentClient } from '@windagent/api-client';

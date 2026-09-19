import { apiFetch } from './client';

export interface HealthResponse {
  status: 'ok' | 'degraded';
  database: 'ok' | 'error';
  postgis: string | null;
  migration: string | null;
  detail: string | null;
}

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/api/v1/health');
}

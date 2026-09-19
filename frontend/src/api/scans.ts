import { apiFetch } from './client';

export type ScanStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface ScanParams {
  t_bui: number;
  t_ndvi_drop: number;
  t_sar_db: number;
  overlap: number;
  min_area_m2: number;
  cloud_cover_max: number;
  warnings?: string[];
}

export interface Scan {
  id: string;
  status: ScanStatus;
  step: string | null;
  progress: number;
  message: string | null;
  error_code: string | null;
  baseline_start: string;
  baseline_end: string;
  current_start: string;
  current_end: string;
  params: ScanParams;
  algorithm_version: string;
  rerun_of: string | null;
  schedule_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  detection_count: number;
  parcels: { id: string; name: string; category: string }[];
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ScanCreate {
  parcel_ids: string[];
  baseline_start: string;
  baseline_end: string;
  current_start: string;
  current_end: string;
  params?: Partial<ScanParams>;
}

export const listScans = (page = 1, pageSize = 20) =>
  apiFetch<Page<Scan>>(`scans?page=${page}&page_size=${pageSize}`);
export const getScan = (id: string) => apiFetch<Scan>(`scans/${id}`);
export const createScan = (body: ScanCreate) =>
  apiFetch<Scan>('scans', { method: 'POST', body: JSON.stringify(body) });
export const rerunScan = (id: string) => apiFetch<Scan>(`scans/${id}/rerun`, { method: 'POST' });
export const isOpen = (s: Scan | undefined | null): boolean =>
  s?.status === 'queued' || s?.status === 'running';

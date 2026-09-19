import type { Geometry } from 'geojson';
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

export const DEFAULT_PARAMS: ScanParams = {
  t_bui: 0.15,
  t_ndvi_drop: 0.1,
  t_sar_db: 2.5,
  overlap: 0.3,
  min_area_m2: 400,
  cloud_cover_max: 30,
};

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

export interface Scene {
  sensor: 'sentinel1' | 'sentinel2';
  period: 'baseline' | 'current';
  scene_id: string;
  acquired_at: string;
  cloud_cover: number | null;
  orbit: string | null;
}

export interface ScanDetail extends Scan {
  scenes: Scene[];
  aoi: Geometry | null;
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

export const listScans = (page = 1, pageSize = 20, status?: ScanStatus) =>
  apiFetch<Page<Scan>>(
    `scans?page=${page}&page_size=${pageSize}${status ? `&status=${status}` : ''}`,
  );
export const getScan = (id: string) => apiFetch<ScanDetail>(`scans/${id}`);
export const createScan = (body: ScanCreate) =>
  apiFetch<ScanDetail>('scans', { method: 'POST', body: JSON.stringify(body) });
export const rerunScan = (id: string) =>
  apiFetch<ScanDetail>(`scans/${id}/rerun`, { method: 'POST' });
export const cancelScan = (id: string) =>
  apiFetch<ScanDetail>(`scans/${id}/cancel`, { method: 'POST' });
export const deleteScan = (id: string) =>
  apiFetch<void>(`scans/${id}?confirm=true`, { method: 'DELETE' });
export const isOpen = (s: { status: ScanStatus } | undefined | null): boolean =>
  s?.status === 'queued' || s?.status === 'running';

/** Human wording for failure codes (appflow §6). */
export const FAILURE_HINT: Record<string, string> = {
  no_optical_scenes:
    'No cloud-free optical scenes were found in one of the periods. Try a wider window or a drier season.',
  no_radar_scenes: 'No radar scenes were found in one of the periods. Try a wider window.',
  no_imagery: 'The imagery service returned nothing for this area and period.',
  provider_unavailable: 'The imagery service could not be reached. Try again in a few minutes.',
  bad_aoi: 'The selected parcels do not form a usable area. Check their geometry and total size.',
  worker_restart: 'The application restarted while this scan was running. Re-run it.',
  internal_error:
    'Something went wrong while processing. Re-run; if it repeats, check the server log.',
};

import type { Geometry } from 'geojson';
import { apiFetch } from './client';
import type { ParcelCollection, ParcelProps } from './detections';

export type { ParcelCollection, ParcelProps };

export interface ParcelFeature {
  type: 'Feature';
  id: string;
  geometry: Geometry;
  properties: ParcelProps;
}

export interface ParcelCreateFeature {
  type: 'Feature';
  geometry: Geometry;
  properties: { name?: string; category?: string; notes?: string };
}

export interface ParcelCreateResult {
  created: ParcelFeature[];
  skipped: { index: number; name: string | null; reason: string }[];
}

export interface ParcelDeleteResult {
  deleted: string;
  cascade: boolean;
  scans_removed: number;
  detections_removed: number;
}

export const CATEGORIES = ['wetland', 'forest', 'reserve', 'lake', 'coastal', 'other'] as const;

export const listParcels = (q = '') =>
  apiFetch<ParcelCollection>(`parcels?page_size=200${q ? `&q=${encodeURIComponent(q)}` : ''}`);
export const getParcel = (id: string) => apiFetch<ParcelFeature>(`parcels/${id}`);
export const createParcels = (
  features: ParcelCreateFeature[],
  source: 'upload' | 'drawn',
  defaults: { name?: string; category?: string; source_ref?: string } = {},
) =>
  apiFetch<ParcelCreateResult>('parcels', {
    method: 'POST',
    body: JSON.stringify({ type: 'FeatureCollection', features, source, ...defaults }),
  });
export const patchParcel = (
  id: string,
  body: { name?: string; category?: string; notes?: string | null; geometry?: Geometry },
) => apiFetch<ParcelFeature>(`parcels/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
export const deleteParcel = (id: string, cascade = false) =>
  apiFetch<ParcelDeleteResult>(`parcels/${id}${cascade ? '?cascade=true' : ''}`, {
    method: 'DELETE',
  });

// Phase 9.3 — per-parcel monthly timeline
export interface TimelineMonth {
  month: string; // YYYY-MM-01
  built_frac: number | null;
  ndvi_mean: number | null;
  valid_frac: number | null;
  n_scenes: number;
}
export interface TimelineJob {
  status: 'running' | 'done' | 'failed';
  progress: number;
  message: string | null;
  months_total: number;
  months_done: number;
  started_at: string;
  finished_at: string | null;
}
export interface Timeline {
  parcel_id: string;
  t_bui: number;
  months: TimelineMonth[];
  onset_month: string | null;
  job: TimelineJob | null;
  running: boolean;
  note: string;
}
export const getTimeline = (id: string) => apiFetch<Timeline>(`parcels/${id}/timeline`);
export const startTimeline = (id: string, months = 36) =>
  apiFetch<Timeline>(`parcels/${id}/timeline`, {
    method: 'POST',
    body: JSON.stringify({ months }),
  });

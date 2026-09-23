import type { Geometry } from 'geojson';
import { apiFetch, tokenStore } from './client';
import type { ZoneContext } from './reference';

export type Confidence = 'high' | 'medium' | 'low';
export type DetectionStatus = 'new' | 'confirmed' | 'dismissed' | 'field_visit';
export type ReasonCode =
  'bare_soil' | 'cloud_shadow' | 'seasonal' | 'water_level' | 'existing_structure' | 'other';

export const REASON_LABELS: Record<ReasonCode, string> = {
  bare_soil: 'Bare soil / ploughing',
  cloud_shadow: 'Cloud or shadow artefact',
  seasonal: 'Seasonal vegetation change',
  water_level: 'Water level change',
  existing_structure: 'Structure already existed',
  other: 'Other (add a note)',
};

export interface DetectionProps {
  id: string;
  scan_id: string;
  parcel_id: string;
  parcel_name: string;
  confidence: Confidence;
  score: number;
  area_m2: number;
  sources: string[];
  metrics: {
    d_bui_mean: number | null;
    d_ndvi_mean: number | null;
    d_sigma_vv_mean_db: number | null;
    sar_overlap: number | null;
  };
  status: DetectionStatus;
  status_note: string | null;
  reviewed_at: string | null;
  matches_detection: string | null;
  created_at: string;
  centroid: [number, number];
  zone?: ZoneContext | null;
  persistence?: number;
}

export interface FeatureCollection<P, Id = string> {
  type: 'FeatureCollection';
  features: { type: 'Feature'; id: Id; properties: P; geometry: Geometry }[];
  disclaimer?: string;
}

export interface DetectionCollection extends FeatureCollection<DetectionProps> {
  total: number;
  page: number;
  page_size: number;
}

export interface Evidence {
  kind: 'before_rgb' | 'after_rgb' | 'change_map' | 'overview' | 'field_photo';
  url: string;
  width_px: number | null;
  height_px: number | null;
  bounds: [number, number, number, number] | null;
  meta: {
    lon?: number;
    lat?: number;
    distance_m?: number;
    position_source?: 'exif' | 'browser' | null;
    taken_at?: string;
    note?: string | null;
  };
}

export interface HistoryEntry {
  from_status: DetectionStatus | null;
  to_status: DetectionStatus;
  note: string | null;
  reason_code: string | null;
  changed_by: string | null;
  changed_by_name: string | null;
  changed_at: string;
}

export interface DetectionDetail {
  type: 'Feature';
  id: string;
  geometry: Geometry;
  properties: DetectionProps;
  parcel: { id: string; name: string; category: string; area_m2: number };
  scan: {
    id: string;
    baseline_start: string;
    baseline_end: string;
    current_start: string;
    current_end: string;
    algorithm_version: string;
    created_at: string;
  };
  evidence: Evidence[];
  history: HistoryEntry[];
  allowed_transitions: DetectionStatus[];
  reports: Report[];
  alerts: Alert[];
  disclaimer: string;
}

export interface Report {
  id: string;
  url: string;
  generated_at: string;
  generated_by_name: string | null;
}

export interface Alert {
  id: string;
  provider: string;
  recipient: string;
  status: 'pending' | 'sent' | 'failed';
  attempts: number;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface ParcelProps {
  id: string;
  name: string;
  category: string;
  notes: string | null;
  area_m2: number;
  source: 'upload' | 'drawn';
  source_ref: string | null;
  created_at: string;
  updated_at: string;
}

export interface ParcelCollection extends FeatureCollection<ParcelProps, string> {
  total: number;
  page: number;
  page_size: number;
}

export interface DetectionFilters {
  scan_id?: string;
  parcel_id?: string;
  confidence?: Confidence;
  status?: DetectionStatus;
  date_from?: string;
  date_to?: string;
  bbox?: string;
  in_zone?: 'true' | 'false';
}

const qs = (f: Record<string, string | number | undefined>) =>
  Object.entries(f)
    .filter(([, v]) => v !== undefined && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&');

export const getParcels = () => apiFetch<ParcelCollection>('parcels?page_size=200');
export const getDetections = (filters: DetectionFilters = {}, pageSize = 500) =>
  apiFetch<DetectionCollection>(`detections?${qs({ ...filters, page_size: pageSize })}`);
export const getDetection = (id: string) => apiFetch<DetectionDetail>(`detections/${id}`);
export const setDetectionStatus = (
  id: string,
  status: DetectionStatus,
  note = '',
  reason_code?: ReasonCode,
) =>
  apiFetch<DetectionDetail>(`detections/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status, note: note || null, reason_code: reason_code ?? null }),
  });
export const uploadFieldPhoto = (
  id: string,
  file: File,
  pos: { lon: number; lat: number } | null,
  note = '',
) => {
  const fd = new FormData();
  fd.append('file', file);
  if (pos) {
    fd.append('lon', String(pos.lon));
    fd.append('lat', String(pos.lat));
  }
  if (note) fd.append('note', note);
  return apiFetch<DetectionDetail>(`detections/${id}/field-photo`, { method: 'POST', body: fd });
};
export const createReport = (id: string) =>
  apiFetch<DetectionDetail>(`detections/${id}/report`, { method: 'POST' });
export const retryAlert = (id: string, alertId: string) =>
  apiFetch<DetectionDetail>(`detections/${id}/alerts/${alertId}/retry`, { method: 'POST' });

export const exportUrl = (format: 'geojson' | 'csv', filters: DetectionFilters = {}) =>
  `/api/v1/detections/export?${qs({ ...filters, format })}`;

/** Fetch a protected file (evidence/report) with the session token and return a blob URL. */
export async function fetchBlobUrl(url: string): Promise<string> {
  const token = tokenStore.get();
  const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new Error(`Could not load file (${res.status})`);
  return URL.createObjectURL(await res.blob());
}

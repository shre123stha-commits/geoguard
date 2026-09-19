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

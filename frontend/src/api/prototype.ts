import type { Geometry } from 'geojson';
import { apiFetch } from './client';

export type Confidence = 'high' | 'medium' | 'low';
export type DetectionStatus = 'new' | 'confirmed' | 'dismissed' | 'field_visit';

export interface DetectionProps {
  id: number;
  scan_id: number;
  parcel_id: number | null;
  parcel_name: string;
  confidence: Confidence;
  score: number;
  area_m2: number;
  sources: string[];
  metrics: {
    d_bui_mean: number | null;
    d_sigma_vv_mean_db: number | null;
    sar_overlap: number | null;
    compactness: number | null;
  };
  algorithm_version: string | null;
  status: DetectionStatus;
  status_note?: string;
}

export interface FeatureCollection<P, Id = number> {
  type: 'FeatureCollection';
  features: { type: 'Feature'; id: Id; properties: P; geometry: Geometry }[];
  disclaimer?: string;
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

export interface Scan {
  id: number;
  status: 'running' | 'done' | 'failed';
  created_at: string;
  finished_at?: string;
  params: { t_bui: number; t_sar_db: number; overlap: number };
  detections: number;
  error: string | null;
}

export const getParcels = () => apiFetch<ParcelCollection>('parcels?page_size=200');
export const getDetections = () => apiFetch<FeatureCollection<DetectionProps>>('detections');
export const getScans = () => apiFetch<Scan[]>('scans');
export const createScan = (params: Partial<Scan['params']> = {}) =>
  apiFetch<Scan>('scans', { method: 'POST', body: JSON.stringify(params) });
export const setDetectionStatus = (id: number, status: DetectionStatus, note = '') =>
  apiFetch<DetectionProps>(`detections/${id}/status`, {
    method: 'POST',
    body: JSON.stringify({ status, note }),
  });

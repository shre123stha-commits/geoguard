import type { FeatureCollection as GjFeatureCollection } from 'geojson';
import { apiFetch } from './client';

export type ReferenceKind = 'wetland' | 'water_body' | 'forest' | 'coastal' | 'land_use' | 'custom';
export const REFERENCE_KINDS: { value: ReferenceKind; label: string }[] = [
  { value: 'wetland', label: 'Wetland / marsh' },
  { value: 'water_body', label: 'Lake / tank / river' },
  { value: 'forest', label: 'Reserve forest' },
  { value: 'coastal', label: 'Coastal regulation zone' },
  { value: 'land_use', label: 'Land-use / master plan zone' },
  { value: 'custom', label: 'Other boundary' },
];

export type Priority = 'critical' | 'high' | 'elevated' | 'normal';

export interface ReferenceLayer {
  id: string;
  name: string;
  kind: ReferenceKind;
  source: string | null;
  source_date: string | null;
  notes: string | null;
  buffer_m: number;
  is_active: boolean;
  feature_count: number;
  bounds: [number, number, number, number] | null;
  created_at: string;
}

export interface ZoneHit {
  layer_id: string;
  layer_name: string;
  kind: ReferenceKind;
  feature_name: string | null;
  relation: 'inside' | 'partly_inside' | 'within_buffer';
  inside_pct: number;
  distance_m: number;
  buffer_m: number;
  source: string | null;
  source_date: string | null;
  text: string;
}

export interface ZoneContext {
  priority: Priority;
  summary: string;
  hits: ZoneHit[];
}

export interface ReferenceLayerList {
  layers: ReferenceLayer[];
  disclaimer: string;
}

export interface ReferenceLayerCreate {
  name: string;
  kind: ReferenceKind;
  source?: string;
  source_date?: string;
  notes?: string;
  buffer_m?: number;
  features: GjFeatureCollection['features'];
}

export const listReferenceLayers = () => apiFetch<ReferenceLayerList>('reference-layers');
export const createReferenceLayer = (body: ReferenceLayerCreate) =>
  apiFetch<{ layer: ReferenceLayer; skipped: { index: number; reason: string }[] }>(
    'reference-layers',
    { method: 'POST', body: JSON.stringify({ type: 'FeatureCollection', ...body }) },
  );
export const patchReferenceLayer = (
  id: string,
  body: Partial<
    Pick<
      ReferenceLayer,
      'name' | 'kind' | 'source' | 'source_date' | 'notes' | 'buffer_m' | 'is_active'
    >
  >,
) =>
  apiFetch<ReferenceLayer>(`reference-layers/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
export const deleteReferenceLayer = (id: string) =>
  apiFetch<void>(`reference-layers/${id}`, { method: 'DELETE' });
export const referenceLayerFeatures = (id: string, simplify = 0.00005) =>
  apiFetch<GjFeatureCollection>(`reference-layers/${id}/features?simplify=${simplify}`);

/** Load all active layers' geometry merged into one FeatureCollection for the map overlay. */
export async function loadActiveZones(): Promise<GjFeatureCollection> {
  const { layers } = await listReferenceLayers();
  const active = layers.filter((l) => l.is_active && l.feature_count > 0);
  const parts = await Promise.all(active.map((l) => referenceLayerFeatures(l.id)));
  return { type: 'FeatureCollection', features: parts.flatMap((p) => p.features) };
}

import type { FeatureCollection } from 'geojson';
import type { ParcelCollection } from '@/api/parcels';

export const selectedFC = (
  parcels: ParcelCollection | undefined,
  ids: string[],
): FeatureCollection => ({
  type: 'FeatureCollection',
  features: (parcels?.features ?? []).filter((f) => ids.includes(f.id)),
});

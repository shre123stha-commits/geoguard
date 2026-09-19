import type { Geometry, Position } from 'geojson';

export type BBox = [number, number, number, number];

export function bboxOf(geoms: (Geometry | null | undefined)[]): BBox | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const visit = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === 'number') {
      const [x, y] = c as number[];
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    } else if (Array.isArray(c)) {
      c.forEach(visit);
    }
  };
  geoms.forEach((g) => g && visit((g as { coordinates?: unknown }).coordinates));
  return Number.isFinite(minX) ? [minX, minY, maxX, maxY] : null;
}

/** Geodesic-ish polygon area in m² (spherical excess on WGS84 mean radius; ±0.3 %). */
export function areaM2(geom: Geometry): number {
  const R = 6_371_008.8;
  const ring = (coords: Position[]): number => {
    let sum = 0;
    const n = coords.length;
    if (n < 3) return 0;
    for (let i = 0; i < n; i++) {
      const [lon1, lat1] = coords[i];
      const [lon2, lat2] = coords[(i + 1) % n];
      sum +=
        (((lon2 - lon1) * Math.PI) / 180) *
        (2 + Math.sin((lat1 * Math.PI) / 180) + Math.sin((lat2 * Math.PI) / 180));
    }
    return Math.abs((sum * R * R) / 2);
  };
  const poly = (rings: Position[][]): number =>
    rings.reduce((acc, r, i) => (i === 0 ? ring(r) : acc - ring(r)), 0);
  if (geom.type === 'Polygon') return poly(geom.coordinates);
  if (geom.type === 'MultiPolygon') return geom.coordinates.reduce((a, p) => a + poly(p), 0);
  return 0;
}

/** Simple self-intersection test on the outer ring (O(n²), fine for drawn shapes). */
export function selfIntersects(geom: Geometry): boolean {
  if (geom.type !== 'Polygon') return false;
  const r = geom.coordinates[0];
  const segs = r.length - 1;
  const cross = (a: Position, b: Position, c: Position) =>
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  const hit = (p1: Position, p2: Position, p3: Position, p4: Position) =>
    cross(p1, p2, p3) * cross(p1, p2, p4) < 0 && cross(p3, p4, p1) * cross(p3, p4, p2) < 0;
  for (let i = 0; i < segs; i++) {
    for (let j = i + 2; j < segs; j++) {
      if (i === 0 && j === segs - 1) continue;
      if (hit(r[i], r[i + 1], r[j], r[j + 1])) return true;
    }
  }
  return false;
}

export function centroidOf(geom: Geometry): [number, number] | null {
  const b = bboxOf([geom]);
  return b ? [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2] : null;
}

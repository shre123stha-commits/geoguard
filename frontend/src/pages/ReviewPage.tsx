import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as maplibregl from 'maplibre-gl';
import type { FeatureCollection as GJFeatureCollection, Geometry } from 'geojson';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  getDetections,
  getParcels,
  setDetectionStatus,
  type Confidence,
  type DetectionProps,
  type DetectionStatus,
} from '@/api/prototype';
import { createScan, isOpen, listScans } from '@/api/scans';
import { useAuth } from '@/app/useAuth';
import { Link } from 'react-router-dom';

/** Phase-1 vertical slice: parcels + detections on a map with a review panel (tracker D42). */

const CONF_COLOR: Record<Confidence, string> = {
  high: '#e8735a',
  medium: '#e6b455',
  low: '#9aa79b',
};

/** Basemaps. OSM's public tile server blocks apps behind proxies (403 "Access blocked"),
 *  so the default is Esri World Imagery (free for basemap use with attribution) with a
 *  Carto dark labels option; both are configurable per techspec §4 (BASEMAP_URL). */
const BASEMAPS = {
  satellite: {
    tiles: [
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    ],
    attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
    paint: { 'raster-saturation': -0.35, 'raster-brightness-max': 0.8 },
  },
  dark: {
    tiles: ['https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'],
    attribution: '© OpenStreetMap contributors © CARTO',
    paint: { 'raster-saturation': -1, 'raster-brightness-max': 0.7 },
  },
} as const;
type BasemapKey = keyof typeof BASEMAPS;

function styleFor(key: BasemapKey): maplibregl.StyleSpecification {
  const b = BASEMAPS[key];
  return {
    version: 8,
    sources: {
      base: { type: 'raster', tiles: [...b.tiles], tileSize: 256, attribution: b.attribution },
    },
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': '#0d0b09' } },
      { id: 'base', type: 'raster', source: 'base', paint: { ...b.paint } },
    ],
  };
}

function bboxOf(fc: {
  features: { geometry: Geometry }[];
}): [number, number, number, number] | null {
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
  fc.features.forEach((f) => visit((f.geometry as { coordinates: unknown }).coordinates));
  return Number.isFinite(minX) ? [minX, minY, maxX, maxY] : null;
}

export function ReviewPage() {
  const qc = useQueryClient();
  const { user, logout } = useAuth();
  const parcels = useQuery({ queryKey: ['parcels'], queryFn: getParcels });
  const detections = useQuery({ queryKey: ['detections'], queryFn: getDetections });
  const scans = useQuery({
    queryKey: ['scans'],
    queryFn: () => listScans(1, 1),
    // poll while the newest scan is queued/running so progress shows live
    refetchInterval: (q) => (isOpen(q.state.data?.items[0]) ? 1500 : false),
  });
  const lastScan = scans.data?.items[0];
  const wasOpen = useRef(false);
  useEffect(() => {
    const open = isOpen(lastScan);
    if (wasOpen.current && !open) void qc.invalidateQueries({ queryKey: ['detections'] });
    wasOpen.current = open;
  }, [lastScan, qc]);
  const scan = useMutation({
    mutationFn: () => {
      const ids = parcels.data?.features.map((f) => f.id) ?? [];
      // Same windows as the evaluated sample run; a full scan form arrives with the scans page.
      return createScan({
        parcel_ids: ids,
        baseline_start: '2020-01-15',
        baseline_end: '2020-03-31',
        current_start: '2023-01-15',
        current_end: '2023-03-31',
      });
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['scans'] }),
  });
  const status = useMutation({
    mutationFn: (v: { id: number; status: DetectionStatus; note: string }) =>
      setDetectionStatus(v.id, v.status, v.note),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['detections'] }),
  });

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filter, setFilter] = useState<Confidence | 'all'>('all');
  const [note, setNote] = useState('');
  const mapRef = useRef<maplibregl.Map | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [basemap, setBasemap] = useState<BasemapKey>('satellite');

  const visible = useMemo(() => {
    if (!detections.data) return [];
    return detections.data.features.filter(
      (f) => filter === 'all' || f.properties.confidence === filter,
    );
  }, [detections.data, filter]);
  const selected =
    detections.data?.features.find((f) => f.properties.id === selectedId)?.properties ?? null;

  // Create the map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: styleFor('satellite'),
      center: [80.193, 12.941],
      zoom: 14.5,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    map.on('load', () => {
      map.addSource('parcels', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });
      map.addSource('detections', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });
      map.addLayer({
        id: 'parcel-line',
        type: 'line',
        source: 'parcels',
        paint: { 'line-color': '#f3efe6', 'line-width': 1.5, 'line-opacity': 0.8 },
      });
      map.addLayer({
        id: 'det-fill',
        type: 'fill',
        source: 'detections',
        paint: {
          'fill-color': [
            'match',
            ['get', 'confidence'],
            'high',
            CONF_COLOR.high,
            'medium',
            CONF_COLOR.medium,
            CONF_COLOR.low,
          ],
          'fill-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 0.65, 0.35],
        },
      });
      map.addLayer({
        id: 'det-line',
        type: 'line',
        source: 'detections',
        paint: {
          'line-color': [
            'match',
            ['get', 'confidence'],
            'high',
            CONF_COLOR.high,
            'medium',
            CONF_COLOR.medium,
            CONF_COLOR.low,
          ],
          'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 3, 1.5],
        },
      });
      map.on('click', 'det-fill', (e: maplibregl.MapLayerMouseEvent) => {
        const f = e.features?.[0];
        if (f) setSelectedId(Number(f.id));
      });
      map.on('mouseenter', 'det-fill', () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', 'det-fill', () => (map.getCanvas().style.cursor = ''));
      mapRef.current = map;
      setMapReady(true);
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);
  // Swap basemap tiles without rebuilding overlay layers.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const b = BASEMAPS[basemap];
    map.removeLayer('base');
    map.removeSource('base');
    map.addSource('base', {
      type: 'raster',
      tiles: [...b.tiles],
      tileSize: 256,
      attribution: b.attribution,
    });
    map.addLayer(
      { id: 'base', type: 'raster', source: 'base', paint: { ...b.paint } },
      'parcel-line',
    );
  }, [basemap, mapReady]);

  // Push data into the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !parcels.data) return;
    (map.getSource('parcels') as maplibregl.GeoJSONSource).setData(
      parcels.data as GJFeatureCollection,
    );
    const b = bboxOf(parcels.data);
    if (b) map.fitBounds(b, { padding: 40, duration: 0 });
  }, [parcels.data, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    (map.getSource('detections') as maplibregl.GeoJSONSource).setData({
      type: 'FeatureCollection',
      features: visible,
    } as GJFeatureCollection);
  }, [visible, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !detections.data) return;
    detections.data.features.forEach((f) =>
      map.setFeatureState(
        { source: 'detections', id: f.properties.id },
        { selected: f.properties.id === selectedId },
      ),
    );
  }, [selectedId, detections.data, mapReady, visible]);

  const counts = useMemo(() => {
    const c = { high: 0, medium: 0, low: 0 };
    detections.data?.features.forEach((f) => (c[f.properties.confidence] += 1));
    return c;
  }, [detections.data]);

  return (
    <div className="grid h-dvh grid-rows-[minmax(0,45dvh)_1fr] sm:grid-rows-1 sm:grid-cols-[380px_1fr]">
      <aside className="flex min-h-0 flex-col overflow-hidden border-b border-hair bg-base sm:border-b-0 sm:border-r">
        <header className="border-b border-hair px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-soft">
                Detections · Review
              </p>
              <h1 className="font-display text-[28px] font-medium leading-none tracking-[-0.03em]">
                GeoGuard<sup className="ml-1 text-[0.4em] align-super">EO</sup>
              </h1>
            </div>
            {user && (
              <div className="text-right">
                <p className="max-w-[160px] truncate text-[12px] text-soft" title={user.email}>
                  {user.full_name}
                  <span className="ml-1.5 rounded-full border border-hair px-1.5 py-px font-mono text-[10px] uppercase tracking-[0.08em] text-dim">
                    {user.role}
                  </span>
                </p>
                <p className="mt-1 font-mono text-[11px] text-dim">
                  <Link to="/change-password" className="hover:text-cream">
                    password
                  </Link>
                  <span className="mx-1">·</span>
                  <button type="button" onClick={logout} className="hover:text-cream">
                    sign out
                  </button>
                </p>
              </div>
            )}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button
              className="rounded-ctl border border-hair-strong bg-s2 px-3 py-1.5 text-[13px] font-medium hover:bg-s3 disabled:opacity-50"
              disabled={scan.isPending || isOpen(lastScan) || user?.role !== 'admin'}
              onClick={() => scan.mutate()}
              title={user?.role !== 'admin' ? 'Only administrators can start scans' : undefined}
            >
              {isOpen(lastScan) ? 'Scanning…' : 'Run scan'}
            </button>
            <span className="font-mono text-[12px] text-soft">
              {lastScan
                ? isOpen(lastScan)
                  ? `${lastScan.progress}% · ${lastScan.message ?? lastScan.status}`
                  : `last scan ${lastScan.status} · ${lastScan.detection_count} detections`
                : 'no scans yet'}
            </span>
          </div>
          {scan.isError && (
            <p className="mt-2 text-[13px] text-high">{(scan.error as Error).message}</p>
          )}
          {lastScan?.status === 'failed' && lastScan.message && (
            <p className="mt-2 text-[13px] text-high">{lastScan.message}</p>
          )}
        </header>

        <div className="flex gap-1 border-b border-hair px-5 py-2">
          {(['all', 'high', 'medium', 'low'] as const).map((k) => (
            <button
              key={k}
              onClick={() => setFilter(k)}
              className={`rounded-full px-3 py-1 font-mono text-[12px] ${
                filter === k ? 'bg-s3 text-cream' : 'text-soft hover:bg-s1'
              }`}
            >
              {k}
              {k !== 'all' && <span className="ml-1 text-dim">{counts[k]}</span>}
            </button>
          ))}
          <span className="flex-1" />
          <button
            onClick={() => setBasemap(basemap === 'satellite' ? 'dark' : 'satellite')}
            className="rounded-full px-3 py-1 font-mono text-[12px] text-soft hover:bg-s1"
            title="Toggle basemap"
          >
            {basemap === 'satellite' ? 'satellite' : 'dark map'}
          </button>
        </div>

        <ul className="flex-1 overflow-y-auto">
          {detections.isPending && <li className="px-5 py-4 text-soft">Loading…</li>}
          {detections.isError && (
            <li className="px-5 py-4 text-soft">API not reachable. Start the backend.</li>
          )}
          {visible.map((f) => {
            const p = f.properties;
            const active = p.id === selectedId;
            return (
              <li key={p.id}>
                <button
                  onClick={() => {
                    setSelectedId(p.id);
                    setNote('');
                    const b = bboxOf({ features: [f] });
                    if (b) mapRef.current?.fitBounds(b, { padding: 120, maxZoom: 17 });
                  }}
                  className={`flex w-full items-center gap-3 border-b border-hair px-5 py-3 text-left hover:bg-s1 ${
                    active ? 'bg-s2' : ''
                  }`}
                >
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: CONF_COLOR[p.confidence] }}
                  />
                  <span className="flex-1">
                    <span className="block text-[14px] font-medium">
                      {p.parcel_name?.replace('Pallikaranai-', '')} ·{' '}
                      {Math.round(p.area_m2).toLocaleString()} m²
                    </span>
                    <span className="block font-mono text-[12px] text-soft">
                      {p.confidence} · score {p.score.toFixed(2)} · {p.status}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        {selected && (
          <DetailPanel
            d={selected}
            note={note}
            setNote={setNote}
            onStatus={(s) => status.mutate({ id: selected.id, status: s, note })}
            error={status.error as Error | null}
          />
        )}

        <footer className="border-t border-hair px-5 py-3 text-[12px] text-soft">
          {detections.data?.disclaimer ??
            'Satellite detection is a screening aid. Verify on the ground before acting.'}
        </footer>
      </aside>
      <div ref={containerRef} className="min-h-0" />
    </div>
  );
}

function DetailPanel({
  d,
  note,
  setNote,
  onStatus,
  error,
}: {
  d: DetectionProps;
  note: string;
  setNote: (v: string) => void;
  onStatus: (s: DetectionStatus) => void;
  error: Error | null;
}) {
  const m = d.metrics;
  return (
    <section className="border-t border-hair-strong bg-s1 px-5 py-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-[18px] font-medium tracking-[-0.02em]">
          Detection #{d.id}
        </h2>
        <span className="font-mono text-[12px]" style={{ color: CONF_COLOR[d.confidence] }}>
          {d.confidence.toUpperCase()}
        </span>
      </div>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 font-mono text-[12px]">
        <dt className="text-soft">area</dt>
        <dd>{Math.round(d.area_m2).toLocaleString()} m² (geodesic)</dd>
        <dt className="text-soft">sensors</dt>
        <dd>{d.sources.join(' + ')}</dd>
        <dt className="text-soft">ΔBUI</dt>
        <dd>{m.d_bui_mean != null ? m.d_bui_mean.toFixed(2) : '—'}</dd>
        <dt className="text-soft">Δσ⁰ VV</dt>
        <dd>{m.d_sigma_vv_mean_db != null ? `${m.d_sigma_vv_mean_db.toFixed(1)} dB` : '—'}</dd>
        <dt className="text-soft">radar overlap</dt>
        <dd>{m.sar_overlap != null ? `${Math.round(m.sar_overlap * 100)} %` : '—'}</dd>
        <dt className="text-soft">score</dt>
        <dd>{d.score.toFixed(2)}</dd>
        <dt className="text-soft">algorithm</dt>
        <dd>{d.algorithm_version ?? '—'}</dd>
        <dt className="text-soft">status</dt>
        <dd>
          {d.status}
          {d.status_note ? ` — ${d.status_note}` : ''}
        </dd>
      </dl>
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Note (required to dismiss)"
        className="mt-3 w-full rounded-ctl border border-hair bg-base px-3 py-1.5 text-[13px] placeholder:text-dim"
      />
      <div className="mt-2 flex gap-2">
        {(
          [
            ['confirmed', 'Confirm'],
            ['field_visit', 'Field visit'],
            ['dismissed', 'Dismiss'],
          ] as const
        ).map(([s, label]) => (
          <button
            key={s}
            onClick={() => onStatus(s)}
            className="rounded-ctl border border-hair px-3 py-1 text-[13px] hover:bg-s2"
          >
            {label}
          </button>
        ))}
      </div>
      {error && <p className="mt-2 text-[12px] text-high">{error.message}</p>}
    </section>
  );
}

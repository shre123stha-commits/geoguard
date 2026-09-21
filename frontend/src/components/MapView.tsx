import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import { useEffect, useRef, useState } from 'react';
import type { BBox } from '@/lib/geo';
import { BASEMAPS, CONF_COLOR, type BasemapKey } from '@/lib/basemaps';

/** Basemaps. OSM's public tile server rejects requests from some proxies, so the default is
 *  Esri World Imagery (free for basemap use with attribution) with a Carto dark option; the
 *  raster URL can be overridden with VITE_BASEMAP_URL (techspec §4). */
const CONF_MATCH = [
  'match',
  ['get', 'confidence'],
  'high',
  CONF_COLOR.high,
  'medium',
  CONF_COLOR.medium,
  CONF_COLOR.low,
] as unknown as maplibregl.ExpressionSpecification;

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };
const DEFAULT_CENTER: [number, number] = [80.193, 12.941];

export interface MapViewProps {
  parcels?: FeatureCollection | null;
  detections?: FeatureCollection | null;
  /** Extra geometry drawn with a dashed cream line (AOI, selection). */
  outline?: Geometry | Feature | FeatureCollection | null;
  selectedDetection?: string | null;
  hoverDetection?: string | null;
  selectedParcels?: string[];
  onDetectionClick?: (id: string) => void;
  onParcelClick?: (id: string) => void;
  fitTo?: BBox | null;
  fitKey?: string;
  className?: string;
  /** Receives the map once loaded (draw tools etc.). */
  onReady?: (map: maplibregl.Map) => void;
  legend?: boolean;
  /** Reference zones (Phase 9) drawn as a hatched cream outline under the parcels. */
  zones?: FeatureCollection | null;
}

export function MapView({
  parcels,
  detections,
  outline,
  selectedDetection,
  hoverDetection,
  selectedParcels,
  onDetectionClick,
  onParcelClick,
  fitTo,
  fitKey,
  className,
  onReady,
  legend,
  zones,
}: MapViewProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [basemap, setBasemap] = useState<BasemapKey>('satellite');
  const cb = useRef({ onDetectionClick, onParcelClick, onReady });
  useEffect(() => {
    cb.current = { onDetectionClick, onParcelClick, onReady };
  });
  const fitted = useRef<string | null>(null);

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const b = BASEMAPS.satellite;
    const map = new maplibregl.Map({
      container: ref.current,
      style: {
        version: 8,
        sources: {
          base: { type: 'raster', tiles: [...b.tiles], tileSize: 256, attribution: b.attribution },
        },
        layers: [
          { id: 'bg', type: 'background', paint: { 'background-color': '#0d0b09' } },
          { id: 'base', type: 'raster', source: 'base', paint: { ...b.paint } },
        ],
      },
      center: DEFAULT_CENTER,
      zoom: 14,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
    map.on('load', () => {
      map.addSource('parcels', { type: 'geojson', promoteId: 'id', data: EMPTY });
      map.addSource('detections', { type: 'geojson', promoteId: 'id', data: EMPTY });
      map.addSource('outline', { type: 'geojson', data: EMPTY });
      map.addSource('zones', { type: 'geojson', data: EMPTY });
      map.addLayer({
        id: 'zone-fill',
        type: 'fill',
        source: 'zones',
        paint: { 'fill-color': '#f3efe6', 'fill-opacity': 0.05 },
      });
      map.addLayer({
        id: 'zone-line',
        type: 'line',
        source: 'zones',
        paint: {
          'line-color': '#f3efe6',
          'line-width': 1.2,
          'line-opacity': 0.6,
          'line-dasharray': [1, 1.5],
        },
      });
      map.addLayer({
        id: 'parcel-fill',
        type: 'fill',
        source: 'parcels',
        paint: {
          'fill-color': '#f3efe6',
          'fill-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 0.16, 0.06],
        },
      });
      map.addLayer({
        id: 'parcel-line',
        type: 'line',
        source: 'parcels',
        paint: {
          'line-color': '#f3efe6',
          'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2.5, 1.5],
          'line-opacity': 0.85,
        },
      });
      map.addLayer({
        id: 'det-fill',
        type: 'fill',
        source: 'detections',
        paint: { 'fill-color': CONF_MATCH, 'fill-opacity': 0.16 },
      });
      map.addLayer({
        id: 'det-halo',
        type: 'line',
        source: 'detections',
        paint: {
          'line-color': '#f3efe6',
          'line-width': 5,
          'line-opacity': [
            'case',
            ['boolean', ['feature-state', 'selected'], false],
            0.9,
            ['boolean', ['feature-state', 'hover'], false],
            0.5,
            0,
          ],
        },
      });
      map.addLayer({
        id: 'det-line',
        type: 'line',
        source: 'detections',
        paint: { 'line-color': CONF_MATCH, 'line-width': 2 },
      });
      map.addLayer({
        id: 'outline-line',
        type: 'line',
        source: 'outline',
        paint: { 'line-color': '#f3efe6', 'line-width': 1.5, 'line-dasharray': [2, 2] },
      });
      map.on('click', 'det-fill', (e) => {
        const f = e.features?.[0];
        if (f) cb.current.onDetectionClick?.(String(f.id));
      });
      map.on('click', 'parcel-fill', (e) => {
        // detections sit on top; ignore parcel click when a detection was hit
        if (map.queryRenderedFeatures(e.point, { layers: ['det-fill'] }).length) return;
        const f = e.features?.[0];
        if (f) cb.current.onParcelClick?.(String(f.id));
      });
      for (const l of ['det-fill', 'parcel-fill']) {
        map.on('mouseenter', l, () => (map.getCanvas().style.cursor = 'pointer'));
        map.on('mouseleave', l, () => (map.getCanvas().style.cursor = ''));
      }
      mapRef.current = map;
      if (import.meta.env.DEV) (window as unknown as { __gg_map?: maplibregl.Map }).__gg_map = map;
      setReady(true);
      cb.current.onReady?.(map);
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // basemap swap
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
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
      'zone-fill',
    );
  }, [basemap, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource('parcels') as maplibregl.GeoJSONSource).setData(parcels ?? EMPTY);
  }, [parcels, ready]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource('detections') as maplibregl.GeoJSONSource).setData(detections ?? EMPTY);
  }, [detections, ready]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource('zones') as maplibregl.GeoJSONSource).setData(zones ?? EMPTY);
  }, [zones, ready]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const data: FeatureCollection | Feature | Geometry = outline ?? EMPTY;
    (map.getSource('outline') as maplibregl.GeoJSONSource).setData(
      data.type === 'FeatureCollection' || data.type === 'Feature'
        ? data
        : { type: 'Feature', geometry: data, properties: {} },
    );
  }, [outline, ready]);

  // feature states
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !detections) return;
    for (const f of detections.features) {
      const id = String(f.id ?? f.properties?.id);
      map.setFeatureState(
        { source: 'detections', id },
        { selected: id === selectedDetection, hover: id === hoverDetection },
      );
    }
  }, [selectedDetection, hoverDetection, detections, ready]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !parcels) return;
    const sel = new Set(selectedParcels ?? []);
    for (const f of parcels.features) {
      const id = String(f.id ?? f.properties?.id);
      map.setFeatureState({ source: 'parcels', id }, { selected: sel.has(id) });
    }
  }, [selectedParcels, parcels, ready]);

  // fit once per fitKey (or whenever fitTo changes if no key)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const key = fitKey ?? (fitTo ? fitTo.join(',') : null);
    if (!fitTo || (key && fitted.current === key)) return;
    fitted.current = key;
    map.fitBounds(fitTo, { padding: 60, maxZoom: 17, duration: 600 });
  }, [fitTo, fitKey, ready]);

  return (
    <div className={`relative ${className ?? 'h-full'}`}>
      <div className="absolute inset-0">
        <div ref={ref} className="h-full w-full" />
      </div>
      <div className="absolute left-3 top-3 flex gap-1 rounded-full border border-hair bg-panel p-0.5 backdrop-blur-xl">
        {(['satellite', 'dark'] as const).map((k) => (
          <button
            key={k}
            onClick={() => setBasemap(k)}
            className={`rounded-full px-2.5 py-1 font-mono text-[11px] ${basemap === k ? 'bg-s3 text-cream' : 'text-soft hover:text-cream'}`}
          >
            {k}
          </button>
        ))}
      </div>
      {legend && (
        <div className="absolute bottom-8 left-3 rounded-ctl border border-hair bg-panel px-3 py-2 font-mono text-[11px] backdrop-blur-xl">
          {(['high', 'medium', 'low'] as const).map((c) => (
            <div key={c} className="flex items-center gap-2 py-0.5">
              <span
                className={`inline-block h-2.5 w-2.5 ${c === 'high' ? 'rounded-full' : c === 'medium' ? 'rounded-full border-2 bg-transparent' : 'rounded-sm'}`}
                style={{
                  background: c === 'medium' ? 'transparent' : CONF_COLOR[c],
                  borderColor: CONF_COLOR[c],
                }}
              />
              <span className="uppercase tracking-[0.08em] text-soft">{c}</span>
            </div>
          ))}
          <div className="mt-1 flex items-center gap-2 border-t border-hair pt-1">
            <span className="inline-block h-2.5 w-2.5 border border-cream/80" />
            <span className="uppercase tracking-[0.08em] text-soft">parcel</span>
          </div>
          {zones && zones.features.length > 0 && (
            <div className="flex items-center gap-2 py-0.5">
              <span className="inline-block h-2.5 w-2.5 border border-dotted border-cream/60" />
              <span className="uppercase tracking-[0.08em] text-soft">reference zone</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

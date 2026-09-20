import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import type * as maplibregl from 'maplibre-gl';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { TerraDraw, TerraDrawPolygonMode, TerraDrawSelectMode } from 'terra-draw';
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter';
import { CATEGORIES, createParcels, type ParcelCreateFeature } from '@/api/parcels';
import { useAuth } from '@/app/useAuth';
import { MapView } from '@/components/MapView';
import { Button, Card, Field, Input, PageHeader, Select } from '@/components/ui';
import { fieldCls } from '@/lib/styles';
import { useToast } from '@/components/useToast';
import { fmtArea } from '@/lib/format';
import { areaM2, bboxOf, selfIntersects } from '@/lib/geo';

const MAX_BYTES = 5 * 1024 * 1024;
type Tab = 'upload' | 'draw';

interface Row {
  idx: number;
  geometry: Geometry;
  name: string;
  category: string;
  area: number;
  error?: string;
}

/** Add parcels: Upload GeoJSON or Draw on the map (appflow Flow B). Admin only. */
export function ParcelNewPage() {
  const { user } = useAuth();
  const [sp, setSp] = useSearchParams();
  const tab = (sp.get('tab') as Tab) ?? 'upload';
  if (user?.role !== 'admin') return <Navigate to="/parcels" replace />;
  return (
    <>
      <PageHeader
        eyebrow="Parcels"
        title="Add parcels"
        lead="Boundaries are stored in WGS84 and checked for validity. Anything invalid is listed and skipped, never silently dropped."
      />
      <div
        role="tablist"
        className="mb-6 inline-flex rounded-full border border-hair bg-s1 p-0.5 font-mono text-[12px]"
      >
        {(['upload', 'draw'] as const).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setSp({ tab: t })}
            className={`rounded-full px-4 py-1.5 uppercase tracking-[0.08em] ${tab === t ? 'bg-s3 text-cream' : 'text-soft hover:text-cream'}`}
          >
            {t === 'upload' ? 'Upload GeoJSON' : 'Draw on map'}
          </button>
        ))}
      </div>
      {tab === 'upload' ? <UploadTab /> : <DrawTab />}
    </>
  );
}

function useSave(source: 'upload' | 'drawn') {
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  return useMutation({
    mutationFn: (v: { features: ParcelCreateFeature[]; source_ref?: string }) =>
      createParcels(v.features, source, { source_ref: v.source_ref }),
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ['parcels'] });
      const n = res.created.length;
      toast(
        `${n} parcel${n === 1 ? '' : 's'} saved${res.skipped.length ? `, ${res.skipped.length} skipped` : ''}.`,
        res.skipped.length ? 'info' : 'ok',
      );
      if (res.skipped.length === 0) nav('/parcels');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
}

/* ------------------------------------------------------------------ upload */

function UploadTab() {
  const [rows, setRows] = useState<Row[]>([]);
  const [fileName, setFileName] = useState('');
  const [fileError, setFileError] = useState<string | null>(null);
  const [defaultCat, setDefaultCat] = useState<string>('wetland');
  const save = useSave('upload');
  const skipped = save.data?.skipped ?? [];

  const onFile = async (file: File | undefined) => {
    setRows([]);
    setFileError(null);
    save.reset();
    if (!file) return;
    if (!/\.(geo)?json$/i.test(file.name)) return setFileError('Choose a .geojson or .json file.');
    if (file.size > MAX_BYTES) return setFileError('File is larger than 5 MB. Simplify it first.');
    setFileName(file.name);
    try {
      const gj = JSON.parse(await file.text()) as FeatureCollection | Feature | Geometry;
      const feats: Feature[] =
        gj.type === 'FeatureCollection'
          ? gj.features
          : gj.type === 'Feature'
            ? [gj]
            : [{ type: 'Feature', geometry: gj as Geometry, properties: {} }];
      if (feats.length === 0) return setFileError('The file has no features.');
      if (feats.length > 500) return setFileError('At most 500 features per upload.');
      setRows(
        feats.map((f, idx) => {
          const p = (f.properties ?? {}) as Record<string, unknown>;
          const geom = f.geometry;
          const ok = geom && (geom.type === 'Polygon' || geom.type === 'MultiPolygon');
          return {
            idx,
            geometry: geom,
            name: String(p.name ?? p.Name ?? p.NAME ?? `Parcel ${idx + 1}`),
            category: String(p.category ?? p.Category ?? defaultCat),
            area: ok ? areaM2(geom) : 0,
            error: ok
              ? selfIntersects(geom)
                ? 'self-intersecting'
                : undefined
              : `geometry is ${geom?.type ?? 'missing'}, expected Polygon`,
          };
        }),
      );
    } catch {
      setFileError('Could not read this file as GeoJSON.');
    }
  };

  const valid = rows.filter((r) => !r.error);
  const fc = useMemo<FeatureCollection>(
    () => ({
      type: 'FeatureCollection',
      features: valid.map((r) => ({
        type: 'Feature',
        id: String(r.idx),
        geometry: r.geometry,
        properties: { id: String(r.idx), name: r.name },
      })),
    }),
    [valid],
  );
  const bbox = useMemo(() => bboxOf(valid.map((r) => r.geometry)), [valid]);

  const submit = () =>
    save.mutate({
      source_ref: fileName,
      features: valid.map((r) => ({
        type: 'Feature',
        geometry: r.geometry,
        properties: { name: r.name.trim() || `Parcel ${r.idx + 1}`, category: r.category },
      })),
    });

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
      <div className="space-y-4">
        <Card step="01" title="Choose a file">
          <input
            type="file"
            aria-label="GeoJSON file"
            accept=".geojson,.json,application/geo+json,application/json"
            onChange={(e) => void onFile(e.target.files?.[0])}
            className="block w-full text-[14px] file:mr-3 file:rounded-full file:border file:border-hair file:bg-transparent file:px-4 file:py-1.5 file:text-[13px] file:text-cream"
          />
          <p className="mt-2 text-[12px] text-soft">
            GeoJSON, WGS84 (EPSG:4326), up to 5 MB and 500 features. Properties named{' '}
            <code className="font-mono">name</code> and <code className="font-mono">category</code>{' '}
            are picked up automatically.{' '}
            <a href="/samples/parcels.geojson" download className="underline underline-offset-4">
              Sample file
            </a>
          </p>
          {fileError && (
            <p role="alert" className="mt-2 text-[13px] text-high">
              ⚠ {fileError}
            </p>
          )}
        </Card>
        {rows.length > 0 && (
          <Card
            step="02"
            title={`Name and categorise (${valid.length} of ${rows.length} valid)`}
            action={
              <Select
                value={defaultCat}
                onChange={(e) => {
                  setDefaultCat(e.target.value);
                  setRows((rs) => rs.map((r) => ({ ...r, category: e.target.value })));
                }}
                className="h-9 w-auto text-[13px]"
                aria-label="Set all categories"
              >
                {CATEGORIES.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </Select>
            }
          >
            <ul className="max-h-[360px] divide-y divide-hair overflow-y-auto">
              {rows.map((r) => (
                <li key={r.idx} className="grid grid-cols-[1fr_130px_90px] items-center gap-2 py-2">
                  <input
                    value={r.name}
                    disabled={Boolean(r.error)}
                    onChange={(e) =>
                      setRows((rs) =>
                        rs.map((x) => (x.idx === r.idx ? { ...x, name: e.target.value } : x)),
                      )
                    }
                    className={`${fieldCls} h-9 text-[14px]`}
                    aria-label={`Name of feature ${r.idx + 1}`}
                  />
                  <select
                    value={r.category}
                    disabled={Boolean(r.error)}
                    onChange={(e) =>
                      setRows((rs) =>
                        rs.map((x) => (x.idx === r.idx ? { ...x, category: e.target.value } : x)),
                      )
                    }
                    className={`${fieldCls} h-9 text-[13px]`}
                    aria-label="Category"
                  >
                    {[...CATEGORIES, r.category]
                      .filter((c, i, a) => a.indexOf(c) === i)
                      .map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                  </select>
                  <span className="text-right font-mono text-[12px] text-soft">
                    {r.error ? <span className="text-high">⚠ {r.error}</span> : fmtArea(r.area)}
                  </span>
                </li>
              ))}
            </ul>
            {skipped.length > 0 && (
              <div role="alert" className="mt-3 rounded-ctl border border-hair p-3 text-[13px]">
                <p className="font-medium">Skipped by the server</p>
                <ul className="mt-1 list-disc pl-5 text-soft">
                  {skipped.map((s) => (
                    <li key={s.index}>
                      {s.name ?? `Feature ${s.index + 1}`}: {s.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="mt-4 flex items-center justify-between">
              <span className="font-mono text-[12px] text-soft">
                total {fmtArea(valid.reduce((a, r) => a + r.area, 0))}
              </span>
              <Button
                variant="primary"
                busy={save.isPending}
                disabled={valid.length === 0}
                onClick={submit}
              >
                Save {valid.length} parcel{valid.length === 1 ? '' : 's'}
              </Button>
            </div>
          </Card>
        )}
      </div>
      <div className="min-h-[480px] overflow-hidden rounded-card border border-hair">
        <MapView className="h-full min-h-[480px]" parcels={fc} fitTo={bbox} />
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------- draw */

function DrawTab() {
  const drawRef = useRef<TerraDraw | null>(null);
  const [geom, setGeom] = useState<Geometry | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [name, setName] = useState('');
  const [category, setCategory] = useState<string>('wetland');
  const save = useSave('drawn');
  const toast = useToast();

  const sync = useCallback(() => {
    const snap = drawRef.current?.getSnapshot() ?? [];
    const poly = snap.find((f) => f.geometry.type === 'Polygon');
    setGeom(poly ? (poly.geometry as Geometry) : null);
  }, []);

  const onReady = useCallback(
    (map: maplibregl.Map) => {
      const draw = new TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map }),
        modes: [
          new TerraDrawPolygonMode({
            styles: {
              fillColor: '#f3efe6',
              fillOpacity: 0.12,
              outlineColor: '#f3efe6',
              outlineWidth: 2,
              closingPointColor: '#f3efe6',
              closingPointWidth: 5,
              closingPointOutlineColor: '#0d0b09',
              closingPointOutlineWidth: 1,
            },
          }),
          new TerraDrawSelectMode({
            flags: {
              polygon: {
                feature: {
                  draggable: false,
                  coordinates: { draggable: true, deletable: true, midpoints: true },
                },
              },
            },
            styles: {
              selectedPolygonColor: '#f3efe6',
              selectedPolygonFillOpacity: 0.16,
              selectedPolygonOutlineColor: '#f3efe6',
              selectedPolygonOutlineWidth: 2,
              selectionPointColor: '#f3efe6',
              selectionPointWidth: 5,
              selectionPointOutlineColor: '#0d0b09',
              selectionPointOutlineWidth: 1,
              midPointColor: '#f3efe6',
              midPointWidth: 3,
              midPointOutlineColor: '#0d0b09',
              midPointOutlineWidth: 1,
            },
          }),
        ],
      });
      draw.start();
      draw.on('finish', () => {
        sync();
        setDrawing(false);
        draw.setMode('select');
      });
      draw.on('change', sync);
      drawRef.current = draw;
    },
    [sync],
  );

  useEffect(
    () => () => {
      try {
        drawRef.current?.stop();
      } catch {
        /* map already removed */
      }
    },
    [],
  );

  const start = () => {
    drawRef.current?.clear();
    setGeom(null);
    drawRef.current?.setMode('polygon');
    setDrawing(true);
  };
  const clear = () => {
    drawRef.current?.clear();
    drawRef.current?.setMode('select');
    setGeom(null);
    setDrawing(false);
  };
  const area = geom ? areaM2(geom) : 0;
  const bad = geom && selfIntersects(geom);
  const submit = () => {
    if (!geom) return;
    if (bad) return toast('The shape crosses itself. Move the vertices apart.', 'error');
    save.mutate({
      features: [{ type: 'Feature', geometry: geom, properties: { name: name.trim(), category } }],
    });
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
      <Card title="Draw a boundary">
        <ol className="space-y-1 text-[14px] text-soft">
          <li>
            1. Press <b className="text-cream">Start drawing</b>, then click to place corners.
          </li>
          <li>2. Click the first corner again (or double-click) to close the shape.</li>
          <li>3. Drag corners to adjust; midpoints add new corners.</li>
        </ol>
        <div className="mt-4 flex gap-2">
          <Button variant="primary" onClick={start} disabled={drawing}>
            {geom ? 'Redraw' : drawing ? 'Drawing…' : 'Start drawing'}
          </Button>
          <Button onClick={clear} disabled={!geom && !drawing}>
            Clear
          </Button>
        </div>
        <p className="mt-3 font-mono text-[12px] text-soft" aria-live="polite">
          {geom ? `area ${fmtArea(area)}` : drawing ? 'click on the map…' : 'no shape yet'}
          {bad && <span className="ml-2 text-high">⚠ self-intersecting</span>}
        </p>
        <div className="mt-5 space-y-3 border-t border-hair pt-4">
          <Field label="Name">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Pallikaranai north edge"
            />
          </Field>
          <Field label="Category">
            <Select value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATEGORIES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </Select>
          </Field>
          <Button
            variant="primary"
            className="w-full justify-center"
            busy={save.isPending}
            disabled={!geom || Boolean(bad) || name.trim().length === 0}
            onClick={submit}
          >
            Save parcel
          </Button>
        </div>
      </Card>
      <div className="min-h-[560px] overflow-hidden rounded-card border border-hair">
        <MapView className="h-full min-h-[560px]" onReady={onReady} />
      </div>
    </div>
  );
}

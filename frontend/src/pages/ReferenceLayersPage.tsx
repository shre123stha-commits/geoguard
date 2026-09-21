import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import { Plus } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Navigate } from 'react-router-dom';
import {
  createReferenceLayer,
  deleteReferenceLayer,
  listReferenceLayers,
  patchReferenceLayer,
  REFERENCE_KINDS,
  referenceLayerFeatures,
  type ReferenceKind,
  type ReferenceLayer,
} from '@/api/reference';
import { useAuth } from '@/app/useAuth';
import { MapView } from '@/components/MapView';
import { ConfirmModal, Modal } from '@/components/Modal';
import {
  Button,
  Chip,
  EmptyState,
  ErrorState,
  Field,
  Input,
  PageHeader,
  Select,
  Skeleton,
  Table,
  Textarea,
} from '@/components/ui';
import { useToast } from '@/components/useToast';
import { fmtDate } from '@/lib/format';
import { bboxOf } from '@/lib/geo';
import { fieldCls, rowCls } from '@/lib/styles';

const MAX_BYTES = 20 * 1024 * 1024;
const MAX_FEATURES = 5000;

/** Reference layers: protected / restricted boundaries used for zone context (Phase 9). */
export function ReferenceLayersPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const layers = useQuery({ queryKey: ['reference-layers'], queryFn: listReferenceLayers });
  const [adding, setAdding] = useState(false);
  const [toDelete, setToDelete] = useState<ReferenceLayer | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const previewFc = useQuery({
    queryKey: ['reference-layer-features', preview],
    queryFn: () => referenceLayerFeatures(preview!, 0.0001),
    enabled: Boolean(preview),
  });

  const toggle = useMutation({
    mutationFn: (l: ReferenceLayer) => patchReferenceLayer(l.id, { is_active: !l.is_active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reference-layers'] });
      qc.invalidateQueries({ queryKey: ['zones'] });
      qc.invalidateQueries({ queryKey: ['detections'] });
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const setBuffer = useMutation({
    mutationFn: ({ id, buffer_m }: { id: string; buffer_m: number }) =>
      patchReferenceLayer(id, { buffer_m }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reference-layers'] });
      qc.invalidateQueries({ queryKey: ['detections'] });
      toast('Buffer updated.');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteReferenceLayer(id),
    onSuccess: () => {
      setToDelete(null);
      if (preview === toDelete?.id) setPreview(null);
      qc.invalidateQueries({ queryKey: ['reference-layers'] });
      qc.invalidateQueries({ queryKey: ['zones'] });
      qc.invalidateQueries({ queryKey: ['detections'] });
      toast('Layer removed.');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });

  const bbox = useMemo(
    () => bboxOf((previewFc.data?.features ?? []).map((f) => f.geometry)),
    [previewFc.data],
  );

  if (user?.role !== 'admin') return <Navigate to="/" replace />;

  return (
    <>
      <PageHeader
        eyebrow="Reference layers"
        title="Boundaries that raise priority"
        lead="Upload official or self-digitised zone boundaries — wetlands, lake beds, reserve forests, CRZ lines. Detections inside (or within a buffer of) an active layer are marked as higher priority and carry the source in reports and alerts."
        action={
          <Button icon={Plus} onClick={() => setAdding(true)}>
            Add layer
          </Button>
        }
      />

      {layers.isPending ? (
        <Skeleton rows={4} />
      ) : layers.isError ? (
        <ErrorState error={layers.error} onRetry={() => layers.refetch()} />
      ) : layers.data.layers.length === 0 ? (
        <EmptyState
          eyebrow="No layers yet"
          title="Add a boundary to start prioritising"
          text="A GeoJSON file with one or more polygons in latitude/longitude. Convert shapefiles or KML with QGIS (Export → Save Features As → GeoJSON, CRS EPSG:4326) or mapshaper.org."
          action={
            <Button icon={Plus} onClick={() => setAdding(true)}>
              Add layer
            </Button>
          }
        />
      ) : (
        <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="min-w-0">
            <Table head={['Layer', 'Kind', 'Polygons', 'Buffer', 'Active', '']}>
              {layers.data.layers.map((l) => (
                <tr
                  key={l.id}
                  className={`${rowCls} cursor-pointer ${preview === l.id ? 'bg-s2' : ''}`}
                  onClick={() => setPreview(l.id)}
                >
                  <td>
                    <div className="font-medium">{l.name}</div>
                    <div className="font-mono text-[11px] text-soft">
                      {l.source ?? 'source not recorded'}
                      {l.source_date ? ` · ${l.source_date}` : ''} · added {fmtDate(l.created_at)}
                    </div>
                  </td>
                  <td>
                    <Chip>{l.kind.replace('_', ' ')}</Chip>
                  </td>
                  <td className="text-right font-mono text-[13px]">{l.feature_count}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <BufferInput
                      value={l.buffer_m}
                      onCommit={(v) =>
                        v !== l.buffer_m && setBuffer.mutate({ id: l.id, buffer_m: v })
                      }
                    />
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <label className="inline-flex items-center gap-2 text-[13px]">
                      <input
                        type="checkbox"
                        checked={l.is_active}
                        onChange={() => toggle.mutate(l)}
                        aria-label={`Layer ${l.name} active`}
                      />
                      {l.is_active ? 'on' : 'off'}
                    </label>
                  </td>
                  <td className="text-right" onClick={(e) => e.stopPropagation()}>
                    <Button variant="ghost" size="sm" onClick={() => setToDelete(l)}>
                      Remove
                    </Button>
                  </td>
                </tr>
              ))}
            </Table>
            <p className="mt-4 text-[12px] text-soft">{layers.data.disclaimer}</p>
          </div>
          <div className="min-h-[420px] overflow-hidden rounded-card border border-hair lg:sticky lg:top-24 lg:h-[calc(100dvh-8rem)]">
            {preview ? (
              <MapView
                className="h-full min-h-[420px]"
                zones={previewFc.data ?? null}
                fitTo={bbox}
                fitKey={preview}
              />
            ) : (
              <div className="flex h-full min-h-[420px] items-center justify-center text-[13px] text-soft">
                Select a layer to preview it.
              </div>
            )}
          </div>
        </div>
      )}

      <AddLayerModal
        open={adding}
        onClose={() => setAdding(false)}
        onSaved={() => {
          setAdding(false);
          qc.invalidateQueries({ queryKey: ['reference-layers'] });
          qc.invalidateQueries({ queryKey: ['zones'] });
          qc.invalidateQueries({ queryKey: ['detections'] });
        }}
      />
      <ConfirmModal
        open={Boolean(toDelete)}
        title="Remove this layer?"
        text={`"${toDelete?.name}" will no longer influence priority. Existing review decisions are unchanged.`}
        confirmLabel="Remove"
        danger
        busy={remove.isPending}
        onConfirm={() => toDelete && remove.mutate(toDelete.id)}
        onClose={() => setToDelete(null)}
      />
    </>
  );
}

function BufferInput({ value, onCommit }: { value: number; onCommit: (v: number) => void }) {
  const [v, setV] = useState(String(value));
  return (
    <span className="inline-flex items-center gap-1 font-mono text-[13px]">
      <input
        className={`${fieldCls} h-8 w-20 text-right text-[13px]`}
        inputMode="numeric"
        value={v}
        aria-label="Buffer in metres"
        onChange={(e) => setV(e.target.value.replace(/[^\d]/g, ''))}
        onBlur={() => onCommit(Math.min(5000, Math.max(0, Number(v) || 0)))}
        onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
      />
      m
    </span>
  );
}

function AddLayerModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState('');
  const [kind, setKind] = useState<ReferenceKind>('wetland');
  const [source, setSource] = useState('');
  const [sourceDate, setSourceDate] = useState('');
  const [notes, setNotes] = useState('');
  const [buffer, setBuffer] = useState('0');
  const [features, setFeatures] = useState<Feature[]>([]);
  const [fileName, setFileName] = useState('');
  const [fileError, setFileError] = useState<string | null>(null);

  const reset = () => {
    setName('');
    setKind('wetland');
    setSource('');
    setSourceDate('');
    setNotes('');
    setBuffer('0');
    setFeatures([]);
    setFileName('');
    setFileError(null);
  };

  const onFile = async (file: File | undefined) => {
    setFileError(null);
    setFeatures([]);
    if (!file) return;
    if (!/\.(geo)?json$/i.test(file.name)) return setFileError('Choose a .geojson or .json file.');
    if (file.size > MAX_BYTES) return setFileError('File is larger than 20 MB. Simplify it first.');
    setFileName(file.name);
    try {
      const gj = JSON.parse(await file.text()) as FeatureCollection | Feature | Geometry;
      const feats: Feature[] =
        gj.type === 'FeatureCollection'
          ? gj.features
          : gj.type === 'Feature'
            ? [gj]
            : [{ type: 'Feature', geometry: gj as Geometry, properties: {} }];
      const polys = feats.filter(
        (f) => f.geometry && (f.geometry.type === 'Polygon' || f.geometry.type === 'MultiPolygon'),
      );
      if (polys.length === 0) return setFileError('No Polygon or MultiPolygon features found.');
      if (polys.length > MAX_FEATURES)
        return setFileError(`At most ${MAX_FEATURES} polygons per layer.`);
      const first = polys[0].geometry as { coordinates: unknown };
      const flat =
        JSON.stringify(first.coordinates)
          .match(/-?\d+(\.\d+)?/g)
          ?.slice(0, 2) ?? [];
      if (
        flat.length === 2 &&
        (Math.abs(Number(flat[0])) > 180 || Math.abs(Number(flat[1])) > 90)
      ) {
        return setFileError('Coordinates are not latitude/longitude. Re-export in EPSG:4326.');
      }
      setFeatures(polys);
      if (!name) setName(file.name.replace(/\.(geo)?json$/i, '').replace(/[_-]+/g, ' '));
    } catch {
      setFileError('Could not read this file as GeoJSON.');
    }
  };

  const save = useMutation({
    mutationFn: () =>
      createReferenceLayer({
        name: name.trim(),
        kind,
        source: source.trim() || undefined,
        source_date: sourceDate || undefined,
        notes: notes.trim() || undefined,
        buffer_m: Math.min(5000, Math.max(0, Number(buffer) || 0)),
        features,
      }),
    onSuccess: (r) => {
      toast(
        `Layer added with ${r.layer.feature_count} polygon${r.layer.feature_count === 1 ? '' : 's'}` +
          (r.skipped.length ? ` (${r.skipped.length} skipped)` : '') +
          '.',
      );
      reset();
      onSaved();
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });

  return (
    <Modal
      open={open}
      title="Add reference layer"
      onClose={() => {
        reset();
        onClose();
      }}
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!features.length || !name.trim()) return;
          save.mutate();
        }}
      >
        <Field
          label="GeoJSON file"
          hint="Polygons in latitude/longitude (EPSG:4326)."
          error={fileError}
        >
          <input
            type="file"
            accept=".geojson,.json,application/geo+json,application/json"
            aria-label="GeoJSON file"
            className="block w-full text-[14px] file:mr-3 file:rounded-ctl file:border file:border-hair file:bg-s1 file:px-3 file:py-2 file:text-cream"
            onChange={(e) => onFile(e.target.files?.[0])}
          />
          {features.length > 0 && (
            <p className="mt-1 font-mono text-[12px] text-soft">
              {fileName} · {features.length} polygon{features.length === 1 ? '' : 's'}
            </p>
          )}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={200}
            />
          </Field>
          <Field label="Kind">
            <Select value={kind} onChange={(e) => setKind(e.target.value as ReferenceKind)}>
              {REFERENCE_KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Source" hint="Who published it — cited in reports.">
            <Input
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="e.g. TN Forest Dept G.O. 2022"
              maxLength={300}
            />
          </Field>
          <Field label="Source date">
            <Input type="date" value={sourceDate} onChange={(e) => setSourceDate(e.target.value)} />
          </Field>
          <Field
            label="Buffer (m)"
            hint="Also flag detections this close to the boundary. 0 = only inside."
          >
            <Input
              inputMode="numeric"
              value={buffer}
              onChange={(e) => setBuffer(e.target.value.replace(/[^\d]/g, ''))}
            />
          </Field>
        </div>
        <Field label="Notes">
          <Textarea
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={2000}
          />
        </Field>
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              reset();
              onClose();
            }}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            busy={save.isPending}
            disabled={!features.length || !name.trim()}
          >
            Add layer
          </Button>
        </div>
      </form>
    </Modal>
  );
}

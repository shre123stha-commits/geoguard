import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  exportUrl,
  fetchBlobUrl,
  getDetections,
  type Confidence,
  type DetectionFilters,
  type DetectionStatus,
} from '@/api/detections';
import { listParcels } from '@/api/parcels';
import { listScans } from '@/api/scans';
import { MapView } from '@/components/MapView';
import {
  Button,
  Chip,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  PriorityChip,
  Select,
  Skeleton,
  StatusChip,
  Table,
} from '@/components/ui';
import { rowCls } from '@/lib/styles';
import { useToast } from '@/components/useToast';
import { loadActiveZones } from '@/api/reference';
import { fmtArea, fmtDate } from '@/lib/format';
import { bboxOf } from '@/lib/geo';

const KEYS = [
  'scan_id',
  'parcel_id',
  'confidence',
  'status',
  'date_from',
  'date_to',
  'in_zone',
] as const;

/** Split list/map with filters + export (appflow Flow D step 2, design §8). */
export function DetectionsPage() {
  const nav = useNavigate();
  const toast = useToast();
  const [sp, setSp] = useSearchParams();
  const filters = useMemo(() => {
    const f: DetectionFilters = {};
    KEYS.forEach((k) => {
      const v = sp.get(k);
      if (v) (f as Record<string, string>)[k] = v;
    });
    return f;
  }, [sp]);
  const set = (k: (typeof KEYS)[number], v: string) => {
    const next = new URLSearchParams(sp);
    if (v) next.set(k, v);
    else next.delete(k);
    setSp(next, { replace: true });
  };

  const dets = useQuery({
    queryKey: ['detections', filters],
    queryFn: () => getDetections(filters, 500),
  });
  const parcels = useQuery({ queryKey: ['parcels'], queryFn: () => listParcels() });
  const zones = useQuery({ queryKey: ['zones'], queryFn: loadActiveZones, staleTime: 60_000 });
  const scans = useQuery({
    queryKey: ['scans', 1, 50, 'succeeded'],
    queryFn: () => listScans(1, 50, 'succeeded'),
  });
  const [hover, setHover] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const bbox = useMemo(
    () => bboxOf((dets.data?.features ?? []).map((f) => f.geometry)),
    [dets.data],
  );
  const parcelBbox = useMemo(
    () => bboxOf((parcels.data?.features ?? []).map((f) => f.geometry)),
    [parcels.data],
  );

  const download = async (format: 'geojson' | 'csv') => {
    setBusy(format);
    try {
      const url = await fetchBlobUrl(exportUrl(format, filters));
      const a = document.createElement('a');
      a.href = url;
      a.download = `detections.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(null);
    }
  };

  const active = Object.keys(filters).length > 0;
  return (
    <>
      <PageHeader
        eyebrow="Detections"
        title="Flagged change"
        lead="Sorted by confidence and size within each scan. Open a row to review it."
        action={
          <>
            <Button
              size="sm"
              icon={Download}
              busy={busy === 'geojson'}
              onClick={() => void download('geojson')}
            >
              GeoJSON
            </Button>
            <Button
              size="sm"
              icon={Download}
              busy={busy === 'csv'}
              onClick={() => void download('csv')}
            >
              CSV
            </Button>
          </>
        }
      />
      <div className="mb-4 grid gap-2 sm:grid-cols-3 lg:grid-cols-7">
        <Select
          value={filters.scan_id ?? ''}
          onChange={(e) => set('scan_id', e.target.value)}
          aria-label="Scan"
          className="h-9 text-[13px]"
        >
          <option value="">All scans</option>
          {scans.data?.items.map((s) => (
            <option key={s.id} value={s.id}>
              {fmtDate(s.created_at)} · {s.detection_count} ·{' '}
              {s.parcels
                .map((p) => p.name)
                .join(', ')
                .slice(0, 30)}
            </option>
          ))}
        </Select>
        <Select
          value={filters.parcel_id ?? ''}
          onChange={(e) => set('parcel_id', e.target.value)}
          aria-label="Parcel"
          className="h-9 text-[13px]"
        >
          <option value="">All parcels</option>
          {parcels.data?.features.map((p) => (
            <option key={p.id} value={p.id}>
              {p.properties.name}
            </option>
          ))}
        </Select>
        <Select
          value={filters.confidence ?? ''}
          onChange={(e) => set('confidence', e.target.value)}
          aria-label="Confidence"
          className="h-9 text-[13px]"
        >
          <option value="">Any confidence</option>
          {(['high', 'medium', 'low'] as Confidence[]).map((c) => (
            <option key={c}>{c}</option>
          ))}
        </Select>
        <Select
          value={filters.status ?? ''}
          onChange={(e) => set('status', e.target.value)}
          aria-label="Status"
          className="h-9 text-[13px]"
        >
          <option value="">Any status</option>
          {(['new', 'confirmed', 'field_visit', 'dismissed'] as DetectionStatus[]).map((s) => (
            <option key={s} value={s}>
              {s.replace('_', ' ')}
            </option>
          ))}
        </Select>
        <Select
          value={filters.in_zone ?? ''}
          onChange={(e) => set('in_zone', e.target.value)}
          aria-label="Reference zone"
          className="h-9 text-[13px]"
        >
          <option value="">Any zone context</option>
          <option value="true">Inside / near a reference zone</option>
          <option value="false">Outside reference zones</option>
        </Select>
        <Input
          type="date"
          value={filters.date_from ?? ''}
          onChange={(e) => set('date_from', e.target.value)}
          aria-label="From date"
          className="h-9 text-[13px]"
        />
        <Input
          type="date"
          value={filters.date_to ?? ''}
          onChange={(e) => set('date_to', e.target.value)}
          aria-label="To date"
          className="h-9 text-[13px]"
        />
      </div>
      {active && (
        <button
          onClick={() => setSp({}, { replace: true })}
          className="mb-4 text-[13px] text-soft underline underline-offset-4"
        >
          Clear filters
        </button>
      )}

      <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          {dets.isPending ? (
            <Skeleton rows={8} />
          ) : dets.isError ? (
            <ErrorState error={dets.error} onRetry={() => void dets.refetch()} />
          ) : dets.data.total === 0 ? (
            <EmptyState
              eyebrow="Nothing to show"
              title={active ? 'No detections match these filters' : 'No detections yet'}
              text={
                active
                  ? 'Loosen a filter or clear them all.'
                  : 'Run a scan to look for change on your parcels.'
              }
            />
          ) : (
            <>
              <p className="mb-2 font-mono text-[12px] text-soft">
                {dets.data.total} detection{dets.data.total === 1 ? '' : 's'}
                {dets.data.total > dets.data.features.length &&
                  ` · showing first ${dets.data.features.length}`}
              </p>
              <div
                className="max-h-[70vh] overflow-y-auto"
                tabIndex={0}
                aria-label="Detections list"
              >
                <Table head={['Confidence', 'Parcel', 'Area', 'Sensors', 'Status', 'Found']}>
                  {dets.data.features.map((f) => {
                    const p = f.properties;
                    return (
                      <tr
                        key={f.id}
                        className={`${rowCls} cursor-pointer ${hover === f.id ? 'bg-s2' : ''}`}
                        onMouseEnter={() => setHover(f.id)}
                        onMouseLeave={() => setHover(null)}
                        onClick={() => nav(`/detections/${f.id}`)}
                      >
                        <td>
                          <Chip tone={p.confidence} dot>
                            {p.confidence}
                          </Chip>
                          <span className="ml-2 font-mono text-[11px] text-soft">
                            {p.score.toFixed(2)}
                          </span>
                          {p.zone && p.zone.priority !== 'normal' && (
                            <PriorityChip priority={p.zone.priority} className="ml-2" />
                          )}
                        </td>
                        <td className="max-w-[160px] truncate">
                          {p.parcel_name}
                          {p.zone && p.zone.hits.length > 0 && (
                            <span className="block truncate font-mono text-[11px] text-soft">
                              {p.zone.summary}
                            </span>
                          )}
                        </td>
                        <td className="text-right font-mono text-[13px]">{fmtArea(p.area_m2)}</td>
                        <td className="font-mono text-[11px] text-soft">
                          {p.sources.map((s) => (s === 'optical' ? 'OPT' : 'SAR')).join('+')}
                        </td>
                        <td>
                          <StatusChip status={p.status} />
                        </td>
                        <td className="font-mono text-[12px] text-soft">{fmtDate(p.created_at)}</td>
                      </tr>
                    );
                  })}
                </Table>
              </div>
            </>
          )}
        </div>
        <div className="min-h-[520px] overflow-hidden rounded-card border border-hair lg:sticky lg:top-24 lg:h-[calc(100dvh-8rem)]">
          <MapView
            className="h-full min-h-[520px]"
            parcels={parcels.data ?? null}
            detections={dets.data ?? null}
            zones={zones.data ?? null}
            hoverDetection={hover}
            onDetectionClick={(id) => nav(`/detections/${id}`)}
            fitTo={bbox ?? parcelBbox}
            fitKey={JSON.stringify(filters) + (bbox ? 'd' : 'p')}
            legend
          />
        </div>
      </div>
    </>
  );
}

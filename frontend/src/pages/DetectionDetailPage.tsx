import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { ApiRequestError } from '@/api/client';
import {
  fetchBlobUrl,
  getDetection,
  REASON_LABELS,
  setDetectionStatus,
  type DetectionStatus,
  type ReasonCode,
} from '@/api/detections';
import { getParcel } from '@/api/parcels';
import { BeforeAfter } from '@/components/BeforeAfter';
import { MapView } from '@/components/MapView';
import {
  Button,
  Card,
  Chip,
  ErrorState,
  Field,
  PageHeader,
  Select,
  Skeleton,
  StatusChip,
  Textarea,
} from '@/components/ui';
import { useToast } from '@/components/useToast';
import { fmtArea, fmtDateTime } from '@/lib/format';
import { bboxOf } from '@/lib/geo';

const DISCLAIMER = 'Satellite detection is a screening aid. Verify on the ground before acting.';
const ACTION_LABEL: Record<DetectionStatus, string> = {
  confirmed: 'Confirm',
  field_visit: 'Needs field visit',
  dismissed: 'Dismiss',
  new: 'Reopen',
};

/** Review screen (appflow Flow D step 3–5; design §8 "Detection detail"). */
export function DetectionDetailPage() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const det = useQuery({ queryKey: ['detection', id], queryFn: () => getDetection(id) });
  const parcel = useQuery({
    queryKey: ['parcel', det.data?.parcel.id],
    queryFn: () => getParcel(det.data!.parcel.id),
    enabled: Boolean(det.data),
  });
  const [note, setNote] = useState('');
  const [reason, setReason] = useState<ReasonCode>('bare_soil');
  const [pending, setPending] = useState<DetectionStatus | null>(null);
  const status = useMutation({
    mutationFn: (v: { status: DetectionStatus; reason?: ReasonCode }) =>
      setDetectionStatus(id, v.status, note, v.reason),
    onSuccess: (d) => {
      qc.setQueryData(['detection', id], d);
      void qc.invalidateQueries({ queryKey: ['detections'] });
      setNote('');
      setPending(null);
      toast(`Marked as ${d.properties.status.replace('_', ' ')}.`);
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });

  const geoms = useMemo(() => [det.data?.geometry], [det.data]);
  const bbox = useMemo(() => bboxOf(geoms), [geoms]);
  const fc = useMemo(
    () =>
      det.data
        ? {
            type: 'FeatureCollection' as const,
            features: [
              {
                type: 'Feature' as const,
                id: det.data.id,
                geometry: det.data.geometry,
                properties: det.data.properties,
              },
            ],
          }
        : null,
    [det.data],
  );

  if (det.isError) {
    const e = det.error;
    if (e instanceof ApiRequestError && e.status === 404)
      return <Navigate to="/detections" replace />;
    return <ErrorState error={e} onRetry={() => void det.refetch()} />;
  }
  if (det.isPending) return <Skeleton rows={8} />;
  const d = det.data;
  const p = d.properties;
  const ev = Object.fromEntries(d.evidence.map((e) => [e.kind, e]));
  const allowed = d.allowed_transitions;
  const dismissBlocked = reason === 'other' && !note.trim();

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <Link to="/detections" className="hover:text-cream">
              Detections
            </Link>{' '}
            · {p.parcel_name}
          </>
        }
        title={`${fmtArea(p.area_m2)} of likely new built-up surface`}
        lead={
          <span className="flex flex-wrap items-center gap-2">
            <Chip tone={p.confidence} dot>
              {p.confidence} · {p.score.toFixed(2)}
            </Chip>
            <StatusChip status={p.status} />
            <Chip>
              {p.sources.length === 2
                ? 'optical + radar agree'
                : p.sources[0] === 'radar'
                  ? 'radar only'
                  : 'optical only'}
            </Chip>
            {p.matches_detection && (
              <Link to={`/detections/${p.matches_detection}`}>
                <Chip>previously flagged →</Chip>
              </Link>
            )}
          </span>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-[1fr_1fr]">
            <div className="min-h-[340px] overflow-hidden rounded-card border border-hair">
              <MapView
                className="h-full min-h-[340px]"
                parcels={
                  parcel.data ? { type: 'FeatureCollection', features: [parcel.data] } : null
                }
                detections={fc}
                selectedDetection={d.id}
                fitTo={bbox}
                fitKey={id}
              />
            </div>
            {ev.before_rgb && ev.after_rgb ? (
              <BeforeAfter
                before={ev.before_rgb.url}
                after={ev.after_rgb.url}
                beforeLabel={`${d.scan.baseline_start.slice(0, 7)}`}
                afterLabel={`${d.scan.current_start.slice(0, 7)}`}
              />
            ) : (
              <div className="flex aspect-square items-center justify-center rounded-card border border-dashed border-hair text-[13px] text-soft">
                No evidence images for this detection.
              </div>
            )}
          </div>
          {ev.change_map && (
            <Card title="Change map">
              <div className="flex gap-4">
                <EvidenceImg
                  url={ev.change_map.url}
                  alt="Optical change magnitude"
                  className="w-48"
                />
                <p className="text-[14px] text-soft">
                  Brighter areas show a stronger rise in the built-up index between the two
                  composites (false colour: shortwave infrared, near infrared, red). The outline on
                  the map is the part above threshold that also passed the size and radar checks.
                </p>
              </div>
            </Card>
          )}
          <Card title="History">
            {d.history.length === 0 ? (
              <p className="text-[14px] text-soft">No review actions yet.</p>
            ) : (
              <ol className="space-y-2">
                {d.history.map((h) => (
                  <li
                    key={h.changed_at}
                    className="flex flex-wrap items-baseline gap-x-3 text-[14px]"
                  >
                    <span className="font-mono text-[12px] text-soft">
                      {fmtDateTime(h.changed_at)}
                    </span>
                    <span>
                      {h.from_status ? `${h.from_status.replace('_', ' ')} → ` : ''}
                      <b>{h.to_status.replace('_', ' ')}</b>
                    </span>
                    {h.changed_by_name && <span className="text-soft">by {h.changed_by_name}</span>}
                    {h.reason_code && <Chip>{h.reason_code.replace('_', ' ')}</Chip>}
                    {h.note && <span className="w-full text-[13px] text-soft">“{h.note}”</span>}
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="Metrics">
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-[14px] tabular-nums">
              <Row k="area" v={`${Math.round(p.area_m2).toLocaleString()} m²`} />
              <Row k="confidence" v={`${p.confidence} (score ${p.score.toFixed(2)})`} />
              <Row k="optical ΔBUI" v={fmt(p.metrics.d_bui_mean, 2)} />
              <Row k="optical ΔNDVI" v={fmt(p.metrics.d_ndvi_mean, 2)} />
              <Row
                k="radar Δσ⁰ VV"
                v={
                  p.metrics.d_sigma_vv_mean_db != null
                    ? `${p.metrics.d_sigma_vv_mean_db.toFixed(1)} dB`
                    : '—'
                }
              />
              <Row
                k="radar overlap"
                v={
                  p.metrics.sar_overlap != null
                    ? `${Math.round(p.metrics.sar_overlap * 100)} %`
                    : '—'
                }
              />
              <Row
                k="parcel"
                v={
                  <Link to={`/parcels/${d.parcel.id}`} className="underline underline-offset-4">
                    {d.parcel.name}
                  </Link>
                }
              />
              <Row k="category" v={d.parcel.category} />
              <Row
                k="centre"
                v={
                  <span className="font-mono text-[12px]">
                    {p.centroid[1].toFixed(5)}, {p.centroid[0].toFixed(5)}
                  </span>
                }
              />
              <Row k="baseline" v={`${d.scan.baseline_start} → ${d.scan.baseline_end}`} />
              <Row k="current" v={`${d.scan.current_start} → ${d.scan.current_end}`} />
              <Row
                k="scan"
                v={
                  <Link to={`/scans/${d.scan.id}`} className="underline underline-offset-4">
                    {fmtDateTime(d.scan.created_at)}
                  </Link>
                }
              />
              <Row
                k="algorithm"
                v={<span className="font-mono text-[12px]">{d.scan.algorithm_version}</span>}
              />
            </dl>
          </Card>

          <Card title="Review">
            {allowed.length === 0 ? (
              <p className="text-[14px] text-soft">
                No further action is available to you on this detection.
              </p>
            ) : (
              <>
                <Field label="Note" hint="Optional, kept in the history">
                  <Textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="What did you see?"
                  />
                </Field>
                <div className="mt-3 flex flex-wrap gap-2">
                  {allowed
                    .filter((s) => s !== 'dismissed')
                    .map((s) => (
                      <Button
                        key={s}
                        variant={s === 'confirmed' ? 'primary' : 'secondary'}
                        busy={status.isPending && pending === s}
                        disabled={status.isPending}
                        onClick={() => {
                          setPending(s);
                          status.mutate({ status: s });
                        }}
                      >
                        {ACTION_LABEL[s]}
                      </Button>
                    ))}
                </div>
                {allowed.includes('dismissed') && (
                  <div className="mt-4 border-t border-hair pt-4">
                    <Field
                      label="Dismiss as a false positive"
                      hint={dismissBlocked ? 'Add a note when the reason is “Other”.' : undefined}
                    >
                      <div className="flex gap-2">
                        <Select
                          value={reason}
                          onChange={(e) => setReason(e.target.value as ReasonCode)}
                        >
                          {(Object.keys(REASON_LABELS) as ReasonCode[]).map((r) => (
                            <option key={r} value={r}>
                              {REASON_LABELS[r]}
                            </option>
                          ))}
                        </Select>
                        <Button
                          variant="danger"
                          busy={status.isPending && pending === 'dismissed'}
                          disabled={status.isPending || dismissBlocked}
                          onClick={() => {
                            setPending('dismissed');
                            status.mutate({ status: 'dismissed', reason });
                          }}
                        >
                          Dismiss
                        </Button>
                      </div>
                    </Field>
                  </div>
                )}
              </>
            )}
            <p className="mt-4 text-[12px] text-soft">{DISCLAIMER}</p>
          </Card>
        </div>
      </div>
    </>
  );
}

const fmt = (v: number | null, nd: number) => (v == null ? '—' : v.toFixed(nd));

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <>
      <dt className="text-soft">{k}</dt>
      <dd>{v}</dd>
    </>
  );
}

function EvidenceImg({ url, alt, className }: { url: string; alt: string; className?: string }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    let obj: string | null = null;
    fetchBlobUrl(url)
      .then((u) => {
        obj = u;
        if (alive) setSrc(u);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      if (obj) URL.revokeObjectURL(obj);
    };
  }, [url]);
  return src ? (
    <img
      src={src}
      alt={alt}
      className={`shrink-0 rounded-ctl border border-hair ${className ?? ''}`}
    />
  ) : (
    <div className={`aspect-square shrink-0 animate-pulse rounded-ctl bg-s2 ${className ?? ''}`} />
  );
}

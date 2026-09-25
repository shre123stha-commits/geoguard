import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileText } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { ApiRequestError } from '@/api/client';
import {
  createReport,
  fetchBlobUrl,
  getDetection,
  REASON_LABELS,
  retryAlert,
  setDetectionStatus,
  type DetectionStatus,
  type ReasonCode,
} from '@/api/detections';
import { getParcel } from '@/api/parcels';
import { loadActiveZones } from '@/api/reference';
import { BeforeAfter } from '@/components/BeforeAfter';
import { MapView } from '@/components/MapView';
import {
  Button,
  Card,
  Chip,
  ErrorState,
  Field,
  PageHeader,
  PriorityChip,
  Select,
  Skeleton,
  StatusChip,
  Textarea,
} from '@/components/ui';
import { useToast } from '@/components/useToast';
import { EvidenceImg } from '@/components/EvidenceImg';
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
  const zones = useQuery({ queryKey: ['zones'], queryFn: loadActiveZones, staleTime: 60_000 });
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
  const report = useMutation({
    mutationFn: () => createReport(id),
    onSuccess: (d) => {
      qc.setQueryData(['detection', id], d);
      toast('Report ready.');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const retry = useMutation({
    mutationFn: (alertId: string) => retryAlert(id, alertId),
    onSuccess: (d) => {
      qc.setQueryData(['detection', id], d);
      const a = d.alerts.find((x) => x.status === 'failed');
      toast(
        a ? 'Still failing — see the error next to the alert.' : 'Alert sent.',
        a ? 'error' : 'info',
      );
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const openReport = async (url: string) => {
    try {
      const blob = await fetchBlobUrl(url);
      window.open(blob, '_blank', 'noopener');
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  };

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
  const fieldPhotos = d.evidence.filter((e) => e.kind === 'field_photo');
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
            {p.zone && <PriorityChip priority={p.zone.priority} />}
            {(p.persistence ?? 1) > 1 && <Chip>seen in {p.persistence} scans in a row</Chip>}
            {p.onset_month && <Chip>began {monthLabel(p.onset_month)}</Chip>}
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
                zones={zones.data ?? null}
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
          {fieldPhotos.length > 0 && (
            <Card title="Field photos">
              <ul className="grid grid-cols-2 gap-3 md:grid-cols-3">
                {fieldPhotos.map((ph) => (
                  <li key={ph.url} className="space-y-1">
                    <EvidenceImg url={ph.url} alt="Field photo" className="w-full" />
                    <p className="font-mono text-[11px] text-soft">
                      {ph.meta.taken_at ? new Date(ph.meta.taken_at).toLocaleString() : ''}
                      {ph.meta.distance_m != null ? ` · ${ph.meta.distance_m} m from site` : ''}
                    </p>
                    {ph.meta.note && <p className="text-[13px] text-soft">{ph.meta.note}</p>}
                  </li>
                ))}
              </ul>
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
          <Card
            title="Report"
            action={
              <Button
                variant={d.properties.status === 'confirmed' ? 'primary' : 'secondary'}
                icon={FileText}
                busy={report.isPending}
                onClick={() => report.mutate()}
              >
                Generate report
              </Button>
            }
          >
            {d.reports.length === 0 ? (
              <p className="text-[14px] text-soft">
                A one-page PDF with the evidence, measurements and review history, ready to hand to
                a field team.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {d.reports.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-baseline gap-x-3 text-[14px]">
                    <button
                      type="button"
                      className="underline underline-offset-4 hover:text-cream"
                      onClick={() => void openReport(r.url)}
                    >
                      PDF · {fmtDateTime(r.generated_at)}
                    </button>
                    {r.generated_by_name && (
                      <span className="text-soft">by {r.generated_by_name}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {d.alerts.length > 0 && (
            <Card title="Alerts">
              <ul className="space-y-2">
                {d.alerts.map((a) => (
                  <li
                    key={a.id}
                    className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[14px]"
                  >
                    <Chip
                      tone={
                        a.status === 'sent' ? 'ok' : a.status === 'failed' ? 'danger' : 'neutral'
                      }
                    >
                      {a.status}
                    </Chip>
                    <span className="font-mono text-[12px] text-soft">{a.provider}</span>
                    <span>{a.recipient}</span>
                    <span className="font-mono text-[12px] text-soft">
                      {fmtDateTime(a.sent_at ?? a.created_at)}
                    </span>
                    {a.status === 'failed' && (
                      <>
                        <span className="w-full text-[13px] text-soft">{a.last_error}</span>
                        <Button size="sm" busy={retry.isPending} onClick={() => retry.mutate(a.id)}>
                          Retry ({a.attempts}/5)
                        </Button>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          {p.zone && p.zone.hits.length > 0 && (
            <Card title="Zone context">
              <p className="mb-3 text-[14px]">
                Priority <span className="font-mono uppercase">{p.zone.priority}</span> — this
                footprint {p.zone.hits[0].relation === 'within_buffer' ? 'is close to' : 'overlaps'}{' '}
                a reference boundary. Check this one first.
              </p>
              <ul className="space-y-2 text-[14px]">
                {p.zone.hits.map((h) => (
                  <li key={h.layer_id} className="border-t border-hair pt-2">
                    <div>{h.text}</div>
                    <div className="font-mono text-[11px] text-soft">
                      {h.kind.replace('_', ' ')}
                      {h.source ? ` · source: ${h.source}` : ''}
                      {h.source_date ? ` · ${h.source_date}` : ''}
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-[12px] text-soft">
                Boundaries can be outdated or offset by tens of metres; permissions are not known to
                this tool. A zone hit is a reason to check, not a finding.
              </p>
            </Card>
          )}
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

          <Card
            title="Review"
            action={
              <Link
                to={`/detections/${d.id}/field`}
                className="text-[13px] underline underline-offset-4"
              >
                On site? Open field page
              </Link>
            }
          >
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

function monthLabel(iso: string): string {
  const [y, m] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleString('en-GB', {
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

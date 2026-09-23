import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { getDetections } from '@/api/detections';
import {
  CATEGORIES,
  deleteParcel,
  getParcel,
  getTimeline,
  patchParcel,
  startTimeline,
} from '@/api/parcels';
import { TimelineChart } from '@/components/TimelineChart';
import { ApiRequestError } from '@/api/client';
import { useAuth } from '@/app/useAuth';
import { MapView } from '@/components/MapView';
import { ConfirmModal } from '@/components/Modal';
import {
  Button,
  Card,
  Chip,
  ErrorState,
  Field,
  Input,
  PageHeader,
  Select,
  Skeleton,
  StatusChip,
  Table,
  Textarea,
} from '@/components/ui';
import { rowCls } from '@/lib/styles';
import { useToast } from '@/components/useToast';
import { fmtArea, fmtDate, fmtDateTime } from '@/lib/format';
import { bboxOf } from '@/lib/geo';

export function ParcelDetailPage() {
  const { id = '' } = useParams();
  const { user } = useAuth();
  const admin = user?.role === 'admin';
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const parcel = useQuery({ queryKey: ['parcel', id], queryFn: () => getParcel(id) });
  const dets = useQuery({
    queryKey: ['detections', { parcel_id: id }],
    queryFn: () => getDetections({ parcel_id: id }, 200),
  });
  const [edit, setEdit] = useState<{ name: string; category: string; notes: string } | null>(null);
  const [confirm, setConfirm] = useState<null | 'ask' | 'cascade'>(null);
  const [usage, setUsage] = useState<string | null>(null);

  const patch = useMutation({
    mutationFn: (v: { name: string; category: string; notes: string }) =>
      patchParcel(id, { ...v, notes: v.notes || null }),
    onSuccess: (p) => {
      qc.setQueryData(['parcel', id], p);
      void qc.invalidateQueries({ queryKey: ['parcels'] });
      setEdit(null);
      toast('Parcel updated.');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const del = useMutation({
    mutationFn: (cascade: boolean) => deleteParcel(id, cascade),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ['parcels'] });
      void qc.invalidateQueries({ queryKey: ['detections'] });
      void qc.invalidateQueries({ queryKey: ['scans'] });
      toast(
        r.cascade
          ? `Parcel removed with ${r.scans_removed} scan(s) and ${r.detections_removed} detection(s).`
          : 'Parcel removed.',
      );
      nav('/parcels');
    },
    onError: (e: Error) => {
      if (e instanceof ApiRequestError && e.status === 409) {
        setUsage(e.message);
        setConfirm('cascade');
      } else toast(e.message, 'error');
    },
  });

  const bbox = useMemo(() => bboxOf([parcel.data?.geometry]), [parcel.data]);
  if (parcel.isError) {
    const e = parcel.error;
    if (e instanceof ApiRequestError && e.status === 404) return <Navigate to="/parcels" replace />;
    return <ErrorState error={e} onRetry={() => void parcel.refetch()} />;
  }
  if (parcel.isPending) return <Skeleton rows={6} />;
  const p = parcel.data.properties;
  const counts = { new: 0, confirmed: 0, dismissed: 0, field_visit: 0 };
  dets.data?.features.forEach((f) => counts[f.properties.status]++);

  return (
    <>
      <PageHeader
        eyebrow={`Parcel · ${p.category}`}
        title={p.name}
        lead={`${fmtArea(p.area_m2)} · ${p.source === 'drawn' ? 'drawn on the map' : 'uploaded'}${p.source_ref ? ` from ${p.source_ref}` : ''} · added ${fmtDate(p.created_at)}`}
        action={
          admin && (
            <>
              <Button
                onClick={() =>
                  setEdit({ name: p.name, category: p.category, notes: p.notes ?? '' })
                }
              >
                Edit
              </Button>
              <Button variant="danger" icon={Trash2} onClick={() => setConfirm('ask')}>
                Delete
              </Button>
            </>
          )
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-6">
          {edit && (
            <Card title="Edit parcel">
              <div className="space-y-3">
                <Field label="Name">
                  <Input
                    value={edit.name}
                    onChange={(e) => setEdit({ ...edit, name: e.target.value })}
                  />
                </Field>
                <Field label="Category">
                  <Select
                    value={edit.category}
                    onChange={(e) => setEdit({ ...edit, category: e.target.value })}
                  >
                    {[...CATEGORIES, edit.category]
                      .filter((c, i, a) => a.indexOf(c) === i)
                      .map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                  </Select>
                </Field>
                <Field label="Notes">
                  <Textarea
                    value={edit.notes}
                    onChange={(e) => setEdit({ ...edit, notes: e.target.value })}
                  />
                </Field>
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" onClick={() => setEdit(null)}>
                    Cancel
                  </Button>
                  <Button
                    variant="primary"
                    busy={patch.isPending}
                    disabled={!edit.name.trim()}
                    onClick={() => patch.mutate(edit)}
                  >
                    Save
                  </Button>
                </div>
              </div>
            </Card>
          )}
          {p.notes && !edit && (
            <Card title="Notes">
              <p className="whitespace-pre-wrap text-[14px] text-soft">{p.notes}</p>
            </Card>
          )}
          <TimelineCard id={id} canStart={user?.role === 'admin' || user?.role === 'officer'} />
          <Card
            title="Detection history"
            action={
              <div className="flex gap-1">
                {(Object.keys(counts) as (keyof typeof counts)[]).map(
                  (k) =>
                    counts[k] > 0 && (
                      <Chip key={k}>
                        {counts[k]} {k.replace('_', ' ')}
                      </Chip>
                    ),
                )}
              </div>
            }
          >
            {dets.isPending ? (
              <Skeleton rows={3} />
            ) : dets.data?.features.length === 0 ? (
              <p className="text-[14px] text-soft">
                No change has been flagged on this parcel yet.{' '}
                {admin && (
                  <Link to="/scans/new" className="underline underline-offset-4">
                    Run a scan
                  </Link>
                )}
              </p>
            ) : (
              <Table head={['Confidence', 'Area', 'Status', 'Found']}>
                {dets.data?.features.map((f) => (
                  <tr
                    key={f.id}
                    className={`${rowCls} cursor-pointer`}
                    onClick={() => nav(`/detections/${f.id}`)}
                  >
                    <td>
                      <Chip tone={f.properties.confidence} dot>
                        {f.properties.confidence}
                      </Chip>
                    </td>
                    <td className="text-right font-mono text-[13px]">
                      {fmtArea(f.properties.area_m2)}
                    </td>
                    <td>
                      <StatusChip status={f.properties.status} />
                    </td>
                    <td className="font-mono text-[12px] text-soft">
                      {fmtDateTime(f.properties.created_at)}
                    </td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </div>
        <div className="min-h-[420px] overflow-hidden rounded-card border border-hair">
          <MapView
            className="h-full min-h-[420px]"
            parcels={{ type: 'FeatureCollection', features: [parcel.data] }}
            detections={dets.data ?? null}
            onDetectionClick={(d) => nav(`/detections/${d}`)}
            fitTo={bbox}
            fitKey={id}
            legend
          />
        </div>
      </div>
      <ConfirmModal
        open={confirm === 'ask'}
        title="Delete this parcel?"
        text={`“${p.name}” will be removed from the watch list. Scans and detections that reference it are kept unless you confirm a full removal in the next step.`}
        confirmLabel="Delete"
        danger
        busy={del.isPending}
        onConfirm={() => del.mutate(false)}
        onClose={() => setConfirm(null)}
      />
      <ConfirmModal
        open={confirm === 'cascade'}
        title="Parcel is in use"
        text={
          <>
            <p>{usage}</p>
            <p className="mt-2">
              Removing it anyway deletes those scans and detections, including their review history
              and evidence images. This cannot be undone.
            </p>
          </>
        }
        confirmLabel="Remove everything"
        danger
        busy={del.isPending}
        onConfirm={() => del.mutate(true)}
        onClose={() => setConfirm(null)}
      />
    </>
  );
}

function TimelineCard({ id, canStart }: { id: string; canStart: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({
    queryKey: ['timeline', id],
    queryFn: () => getTimeline(id),
    refetchInterval: (query) => (query.state.data?.running ? 3000 : false),
  });
  const start = useMutation({
    mutationFn: () => startTimeline(id, 36),
    onSuccess: (t) => {
      qc.setQueryData(['timeline', id], t);
      toast('Timeline started — months appear as they are computed.');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const t = q.data;
  const months = t?.months ?? [];
  const clear = months.filter((m) => m.built_frac != null);
  const first = clear[0];
  const last = clear[clear.length - 1];
  const delta = first && last ? (last.built_frac! - first.built_frac!) * 100 : null;
  return (
    <Card
      title="Change over time"
      action={
        canStart && (
          <Button
            size="sm"
            busy={start.isPending || Boolean(t?.running)}
            disabled={Boolean(t?.running)}
            onClick={() => start.mutate()}
          >
            {months.length ? 'Update' : 'Compute 3 years'}
          </Button>
        )
      }
    >
      {q.isPending ? (
        <Skeleton rows={3} />
      ) : months.length === 0 ? (
        <p className="text-[14px] text-soft">
          {t?.running
            ? (t.job?.message ?? 'Starting…')
            : 'Monthly built-up share of this parcel from Sentinel-2. Shows when a change began, not just that it happened. Takes a few minutes online.'}
        </p>
      ) : (
        <>
          <TimelineChart months={months} onset={t?.onset_month ?? null} />
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-[14px] tabular-nums">
            {first && last && (
              <>
                <dt className="text-soft">built-up share</dt>
                <dd>
                  {(first.built_frac! * 100).toFixed(1)} % → {(last.built_frac! * 100).toFixed(1)} %
                  {delta != null && (
                    <span className="ml-2 font-mono text-[12px] text-soft">
                      ({delta >= 0 ? '+' : ''}
                      {delta.toFixed(1)} pts, {first.month.slice(0, 7)} → {last.month.slice(0, 7)})
                    </span>
                  )}
                </dd>
              </>
            )}
            <dt className="text-soft">change began</dt>
            <dd>
              {t?.onset_month
                ? new Date(t.onset_month).toLocaleDateString(undefined, {
                    month: 'long',
                    year: 'numeric',
                  })
                : 'no sustained step detected'}
            </dd>
            <dt className="text-soft">clear months</dt>
            <dd>
              {clear.length} of {months.length}
            </dd>
          </dl>
          {t?.running && t.job && (
            <p className="mt-2 font-mono text-[12px] text-soft">
              computing… {t.job.months_done}/{t.job.months_total} · {t.job.message}
            </p>
          )}
          {t?.job?.status === 'failed' && (
            <p className="mt-2 text-[13px] text-soft">Last run failed: {t.job.message}</p>
          )}
          <p className="mt-3 text-[12px] text-soft">{t?.note}</p>
        </>
      )}
    </Card>
  );
}

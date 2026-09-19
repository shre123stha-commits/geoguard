import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { ApiRequestError } from '@/api/client';
import { getDetections } from '@/api/detections';
import { listParcels } from '@/api/parcels';
import { cancelScan, deleteScan, FAILURE_HINT, getScan, isOpen, rerunScan } from '@/api/scans';
import { useAuth } from '@/app/useAuth';
import { MapView } from '@/components/MapView';
import { ConfirmModal } from '@/components/Modal';
import {
  Button,
  Card,
  Chip,
  ErrorState,
  LinkButton,
  PageHeader,
  Progress,
  Skeleton,
  StatusChip,
} from '@/components/ui';
import { useToast } from '@/components/useToast';
import { fmtArea, fmtDateTime } from '@/lib/format';
import { bboxOf } from '@/lib/geo';

const STEP_LABEL: Record<string, string> = {
  aoi: 'preparing area',
  search: 'searching scenes',
  baseline: 'baseline composite',
  current: 'current composite',
  change: 'optical + radar change',
  fusion: 'fusion',
  persist: 'saving results',
};

export function ScanDetailPage() {
  const { id = '' } = useParams();
  const { user } = useAuth();
  const admin = user?.role === 'admin';
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const scan = useQuery({
    queryKey: ['scan', id],
    queryFn: () => getScan(id),
    refetchInterval: (q) => (isOpen(q.state.data) ? 3000 : false),
  });
  const done = scan.data?.status === 'succeeded';
  const dets = useQuery({
    queryKey: ['detections', { scan_id: id }],
    queryFn: () => getDetections({ scan_id: id }, 500),
    enabled: done,
  });
  const parcels = useQuery({ queryKey: ['parcels'], queryFn: () => listParcels() });
  const [confirmDel, setConfirmDel] = useState(false);

  const rerun = useMutation({
    mutationFn: () => rerunScan(id),
    onSuccess: (s) => {
      void qc.invalidateQueries({ queryKey: ['scans'] });
      nav(`/scans/${s.id}`);
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const cancel = useMutation({
    mutationFn: () => cancelScan(id),
    onSuccess: (s) => {
      qc.setQueryData(['scan', id], s);
      void qc.invalidateQueries({ queryKey: ['scans'] });
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const del = useMutation({
    mutationFn: () => deleteScan(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['scans'] });
      void qc.invalidateQueries({ queryKey: ['detections'] });
      toast('Scan deleted.');
      nav('/scans');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });

  const scanParcels = useMemo(() => {
    const ids = new Set(scan.data?.parcels.map((p) => p.id) ?? []);
    return {
      type: 'FeatureCollection' as const,
      features: (parcels.data?.features ?? []).filter((f) => ids.has(f.id)),
    };
  }, [scan.data, parcels.data]);
  const bbox = useMemo(
    () => bboxOf([scan.data?.aoi, ...scanParcels.features.map((f) => f.geometry)]),
    [scan.data, scanParcels],
  );

  if (scan.isError) {
    const e = scan.error;
    if (e instanceof ApiRequestError && e.status === 404) return <Navigate to="/scans" replace />;
    return <ErrorState error={e} onRetry={() => void scan.refetch()} />;
  }
  if (scan.isPending) return <Skeleton rows={6} />;
  const s = scan.data;
  const counts = { high: 0, medium: 0, low: 0 };
  dets.data?.features.forEach((f) => counts[f.properties.confidence]++);
  const scenes = {
    baseline: s.scenes.filter((x) => x.period === 'baseline'),
    current: s.scenes.filter((x) => x.period === 'current'),
  };
  const warnings = s.params.warnings ?? [];

  return (
    <>
      <PageHeader
        eyebrow={`Scan · ${fmtDateTime(s.created_at)}`}
        title={s.parcels.map((p) => p.name).join(', ') || 'Scan'}
        lead={
          <>
            Baseline {s.baseline_start} → {s.baseline_end} · Current {s.current_start} →{' '}
            {s.current_end} · {s.algorithm_version}
            {s.rerun_of && (
              <>
                {' '}
                · re-run of{' '}
                <Link to={`/scans/${s.rerun_of}`} className="underline underline-offset-4">
                  earlier scan
                </Link>
              </>
            )}
            {s.schedule_id && ' · started by a schedule'}
          </>
        }
        action={
          admin && (
            <>
              {isOpen(s) && s.status === 'queued' && (
                <Button busy={cancel.isPending} onClick={() => cancel.mutate()}>
                  Cancel
                </Button>
              )}
              {!isOpen(s) && (
                <>
                  <Button busy={rerun.isPending} onClick={() => rerun.mutate()}>
                    Re-run with same parameters
                  </Button>
                  <LinkButton to={`/scans/new?clone=${s.id}`}>Clone and edit</LinkButton>
                  <Button variant="danger" onClick={() => setConfirmDel(true)}>
                    Delete
                  </Button>
                </>
              )}
            </>
          )
        }
      />

      {isOpen(s) && (
        <Card className="mb-6">
          <div className="mb-3 flex items-center justify-between">
            <StatusChip status={s.status} />
            <span className="font-mono text-[12px] text-soft">
              {s.status === 'queued' ? 'waiting for the worker' : (s.message ?? '')}
            </span>
          </div>
          <Progress
            value={s.progress}
            label={`${(s.step && STEP_LABEL[s.step]) ?? s.status} ${s.progress}%`}
          />
        </Card>
      )}
      {s.status === 'failed' && (
        <Card className="mb-6" title="This scan did not finish">
          <p className="text-[15px]">{s.message ?? 'Unknown error.'}</p>
          {s.error_code && FAILURE_HINT[s.error_code] && (
            <p className="mt-1 text-[14px] text-soft">{FAILURE_HINT[s.error_code]}</p>
          )}
          {admin && (
            <div className="mt-4 flex gap-2">
              <LinkButton to={`/scans/new?clone=${s.id}`} variant="primary">
                Adjust and re-run
              </LinkButton>
              <Button busy={rerun.isPending} onClick={() => rerun.mutate()}>
                Retry as is
              </Button>
            </div>
          )}
        </Card>
      )}
      {s.status === 'cancelled' && (
        <Card className="mb-6">
          <p className="text-[15px] text-soft">This scan was cancelled before it started.</p>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-6">
          {done && (
            <Card
              title={
                s.detection_count === 0
                  ? 'No new change found'
                  : `${s.detection_count} detection${s.detection_count === 1 ? '' : 's'}`
              }
              action={
                s.detection_count > 0 && (
                  <LinkButton to={`/detections?scan_id=${s.id}`} variant="primary" size="sm">
                    View detections
                  </LinkButton>
                )
              }
            >
              {s.detection_count === 0 ? (
                <p className="text-[14px] text-soft">
                  Nothing above the thresholds in these periods. If you expected change, widen the
                  periods or lower the thresholds under Advanced when cloning this scan.
                </p>
              ) : (
                <div className="flex gap-2">
                  {(['high', 'medium', 'low'] as const).map((c) => (
                    <Link
                      key={c}
                      to={`/detections?scan_id=${s.id}&confidence=${c}`}
                      className="flex-1 rounded-ctl border border-hair p-3 hover:border-hair-strong"
                    >
                      <Chip tone={c} dot>
                        {c}
                      </Chip>
                      <p className="mt-2 font-display text-[28px] font-medium leading-none tabular-nums">
                        {dets.isPending ? '…' : counts[c]}
                      </p>
                    </Link>
                  ))}
                </div>
              )}
              {warnings.length > 0 && (
                <ul className="mt-4 space-y-1 text-[13px] text-medium">
                  {warnings.map((w) => (
                    <li key={w}>⚠ {w}</li>
                  ))}
                </ul>
              )}
            </Card>
          )}
          <Card title="Scenes used">
            {s.scenes.length === 0 ? (
              <p className="text-[14px] text-soft">
                {isOpen(s) ? 'Scene search has not finished yet.' : 'No scenes recorded.'}
              </p>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                {(['baseline', 'current'] as const).map((p) => (
                  <div key={p}>
                    <p className="mb-1 font-mono text-[11px] uppercase tracking-[0.12em] text-soft">
                      {p} · {scenes[p].length}
                    </p>
                    <ul className="max-h-[200px] space-y-0.5 overflow-y-auto font-mono text-[12px]">
                      {scenes[p].map((x) => (
                        <li key={x.scene_id} className="flex justify-between gap-2">
                          <span className="truncate text-soft" title={x.scene_id}>
                            {x.sensor === 'sentinel2' ? 'S2' : 'S1'} {x.acquired_at.slice(0, 10)}
                          </span>
                          <span className="text-soft">
                            {x.cloud_cover != null
                              ? `${Math.round(x.cloud_cover)}% cloud`
                              : (x.orbit ?? '')}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card title="Parameters">
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 font-mono text-[12px]">
              {Object.entries(s.params)
                .filter(([k]) => k !== 'warnings')
                .map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-soft">{k}</dt>
                    <dd>{String(v)}</dd>
                  </div>
                ))}
              <dt className="text-soft">parcels</dt>
              <dd>
                {s.parcels.map((p) => (
                  <Link
                    key={p.id}
                    to={`/parcels/${p.id}`}
                    className="mr-2 underline underline-offset-4"
                  >
                    {p.name}
                  </Link>
                ))}
              </dd>
              <dt className="text-soft">area</dt>
              <dd>{fmtArea(scanParcels.features.reduce((a, f) => a + f.properties.area_m2, 0))}</dd>
            </dl>
          </Card>
        </div>
        <div className="min-h-[480px] overflow-hidden rounded-card border border-hair">
          <MapView
            className="h-full min-h-[480px]"
            parcels={scanParcels}
            outline={s.aoi}
            detections={dets.data ?? null}
            onDetectionClick={(d) => nav(`/detections/${d}`)}
            fitTo={bbox}
            fitKey={id}
            legend={done}
          />
        </div>
      </div>
      <ConfirmModal
        open={confirmDel}
        title="Delete this scan?"
        text="Its detections, review history and evidence images are removed too. Parcels are kept."
        confirmLabel="Delete scan"
        danger
        busy={del.isPending}
        onConfirm={() => del.mutate()}
        onClose={() => setConfirmDel(false)}
      />
    </>
  );
}

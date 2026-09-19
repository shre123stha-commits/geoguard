import { useQuery } from '@tanstack/react-query';
import { ArrowRight } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { getDetections } from '@/api/detections';
import { listParcels } from '@/api/parcels';
import { listScans, isOpen } from '@/api/scans';
import { listSchedules } from '@/api/schedules';
import { getAlertSettings } from '@/api/settings';
import { useAuth } from '@/app/useAuth';
import { MapView } from '@/components/MapView';
import { Card, Chip, LinkButton, PageHeader, Skeleton, StatusChip } from '@/components/ui';
import { fmtArea, relTime } from '@/lib/format';
import { bboxOf } from '@/lib/geo';

const LAST_VISIT_KEY = 'geoguard.lastVisit';

export function DashboardPage() {
  const { user } = useAuth();
  const admin = user?.role === 'admin';
  const parcels = useQuery({ queryKey: ['parcels'], queryFn: () => listParcels() });
  const scans = useQuery({
    queryKey: ['scans', 1, 5],
    queryFn: () => listScans(1, 5),
    refetchInterval: (q) => (q.state.data?.items.some(isOpen) ? 3000 : false),
  });
  const fresh = useQuery({
    queryKey: ['detections', { status: 'new' }],
    queryFn: () => getDetections({ status: 'new' }, 200),
  });
  const schedules = useQuery({
    queryKey: ['schedules'],
    queryFn: listSchedules,
    enabled: admin,
  });
  const alertsOn = useQuery({
    queryKey: ['alert-settings'],
    queryFn: getAlertSettings,
    enabled: admin,
  });

  // "new since your last visit" (appflow Flow G/H): compare to a per-browser timestamp.
  const lastVisit = useMemo(() => sessionStorage.getItem(LAST_VISIT_KEY), []);
  useEffect(() => {
    const t = setTimeout(() => sessionStorage.setItem(LAST_VISIT_KEY, new Date().toISOString()), 0);
    return () => clearTimeout(t);
  }, []);
  const since = useMemo(() => {
    const items = fresh.data?.features ?? [];
    if (!lastVisit) return items.slice(0, 6);
    return items.filter((f) => f.properties.created_at > lastVisit).slice(0, 6);
  }, [fresh.data, lastVisit]);

  const lastScan = scans.data?.items[0];
  const parcelCount = parcels.data?.total ?? 0;
  const reviewed = (fresh.data?.total ?? 0) < (lastScan?.detection_count ?? 0);
  const steps = [
    { n: '01', label: 'Add a parcel', done: parcelCount > 0, to: '/parcels/new', admin: true },
    { n: '02', label: 'Run a scan', done: Boolean(lastScan), to: '/scans/new', admin: true },
    { n: '03', label: 'Review a detection', done: reviewed, to: '/detections?status=new' },
    {
      n: '04',
      label: 'Set up alerts',
      done: alertsOn.data?.enabled ?? false,
      to: '/settings',
      admin: true,
    },
  ];
  const bbox = useMemo(
    () => bboxOf((parcels.data?.features ?? []).map((f) => f.geometry)),
    [parcels.data],
  );

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title={`Good ${greeting()}, ${user?.full_name.split(' ')[0] ?? ''}`}
        lead="Screening results from the latest satellite passes over your protected parcels."
        action={
          admin &&
          parcelCount > 0 && (
            <LinkButton to="/scans/new" variant="primary" icon={ArrowRight}>
              New scan
            </LinkButton>
          )
        }
      />
      <div className="grid gap-4 md:grid-cols-3">
        <Stat
          label="New detections"
          value={fresh.isPending ? '…' : String(fresh.data?.total ?? 0)}
          to="/detections?status=new"
          sub="awaiting review"
        />
        <Stat
          label="Last scan"
          value={lastScan ? relTime(lastScan.created_at) : '—'}
          to={lastScan ? `/scans/${lastScan.id}` : '/scans'}
          sub={
            lastScan ? (
              <span className="flex items-center gap-2">
                <StatusChip status={lastScan.status} />
                {isOpen(lastScan) ? `${lastScan.progress} %` : `${lastScan.detection_count} found`}
              </span>
            ) : (
              'no scans yet'
            )
          }
        />
        <Stat
          label={admin ? 'Active schedules' : 'Parcels watched'}
          value={
            admin
              ? String(schedules.data?.items.filter((s) => s.is_active).length ?? '…')
              : String(parcelCount)
          }
          to={admin ? '/schedules' : '/parcels'}
          sub={
            admin
              ? `${parcelCount} parcel${parcelCount === 1 ? '' : 's'} watched`
              : fmtArea(parcels.data?.features.reduce((a, f) => a + f.properties.area_m2, 0) ?? 0)
          }
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <div className="space-y-6">
          <Card
            title={lastVisit ? 'New since your last visit' : 'Newest detections'}
            action={
              <Link to="/detections?status=new" className="text-[13px] text-soft hover:text-cream">
                View all →
              </Link>
            }
          >
            {fresh.isPending ? (
              <Skeleton rows={3} />
            ) : since.length === 0 ? (
              <p className="text-[14px] text-soft">
                {fresh.data?.total
                  ? 'Nothing new since you were last here.'
                  : 'No detections awaiting review.'}
              </p>
            ) : (
              <ul className="divide-y divide-hair">
                {since.map((f) => (
                  <li key={f.id}>
                    <Link
                      to={`/detections/${f.id}`}
                      className="flex items-center justify-between gap-3 py-2.5 hover:bg-s2"
                    >
                      <span className="flex items-center gap-3">
                        <Chip tone={f.properties.confidence} dot>
                          {f.properties.confidence}
                        </Chip>
                        <span className="text-[14px]">{f.properties.parcel_name}</span>
                      </span>
                      <span className="font-mono text-[12px] text-soft">
                        {fmtArea(f.properties.area_m2)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Getting started">
            <ol className="grid gap-3 sm:grid-cols-2">
              {steps.map((s) => {
                const locked = s.admin && !admin;
                return (
                  <li key={s.n}>
                    <Link
                      to={locked ? '#' : s.to}
                      aria-disabled={locked}
                      className={`flex items-start gap-3 rounded-ctl border border-hair p-3 ${locked ? 'cursor-default opacity-60' : 'hover:border-hair-strong'}`}
                    >
                      <span className="font-mono text-[12px] text-soft">{s.n}</span>
                      <span className="flex-1">
                        <span className="block text-[14px]">{s.label}</span>
                        <span className="block font-mono text-[11px] uppercase tracking-[0.08em] text-soft">
                          {s.done ? '✓ done' : locked ? 'admin' : 'to do'}
                        </span>
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ol>
          </Card>
        </div>
        <Card className="min-h-[360px] p-0 overflow-hidden">
          <MapView
            className="h-full min-h-[360px]"
            parcels={parcels.data ?? null}
            detections={fresh.data ?? null}
            fitTo={bbox}
            fitKey="dash"
            legend
          />
        </Card>
      </div>
    </>
  );
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening';
}

function Stat({
  label,
  value,
  sub,
  to,
}: {
  label: string;
  value: string;
  sub?: React.ReactNode;
  to: string;
}) {
  return (
    <Link
      to={to}
      className="rounded-card border border-hair bg-s1 p-6 transition hover:-translate-y-px hover:border-hair-strong"
    >
      <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-soft">{label}</p>
      <p className="mt-2 font-display text-[36px] font-medium leading-none tracking-[-0.03em] tabular-nums">
        {value}
      </p>
      <div className="mt-2 text-[13px] text-soft">{sub}</div>
    </Link>
  );
}

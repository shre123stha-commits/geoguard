import { useMutation, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { listParcels } from '@/api/parcels';
import { createScan, getScan, type ScanParams } from '@/api/scans';
import { useAuth } from '@/app/useAuth';
import { AdvancedParams } from '@/components/AdvancedParams';
import { MapView } from '@/components/MapView';
import { ParcelPicker } from '@/components/ParcelPicker';
import { selectedFC } from '@/lib/parcels';
import { Button, Card, Field, Input, LinkButton, PageHeader } from '@/components/ui';
import { useToast } from '@/components/useToast';
import { addDays, isoDate } from '@/lib/format';
import { bboxOf } from '@/lib/geo';

const monthOf = (iso: string) => Number(iso.slice(5, 7));
const seasonGap = (a: string, b: string) => {
  const d = Math.abs(monthOf(a) - monthOf(b));
  return Math.min(d, 12 - d);
};

/** Create a scan (appflow Flow C). Prefills from ?clone=<scanId> for "Clone and edit". */
export function ScanNewPage() {
  const { user } = useAuth();
  const nav = useNavigate();
  const toast = useToast();
  const [sp] = useSearchParams();
  const clone = sp.get('clone');
  const parcels = useQuery({ queryKey: ['parcels'], queryFn: () => listParcels() });
  const source = useQuery({
    queryKey: ['scan', clone],
    queryFn: () => getScan(clone as string),
    enabled: Boolean(clone),
  });

  const today = new Date();
  const [ids, setIds] = useState<string[]>([]);
  const [cur, setCur] = useState({ start: isoDate(addDays(today, -60)), end: isoDate(today) });
  const [base, setBase] = useState({
    start: isoDate(addDays(today, -60 - 365)),
    end: isoDate(addDays(today, -365)),
  });
  const [params, setParams] = useState<Partial<ScanParams>>({});
  const [seeded, setSeeded] = useState(false);
  if (clone && source.data && !seeded) {
    const s = source.data;
    setIds(s.parcels.map((p) => p.id));
    setCur({ start: s.current_start, end: s.current_end });
    setBase({ start: s.baseline_start, end: s.baseline_end });
    const rest = { ...s.params };
    delete rest.warnings;
    setParams(rest);
    setSeeded(true);
  }

  const create = useMutation({
    mutationFn: () =>
      createScan({
        parcel_ids: ids,
        baseline_start: base.start,
        baseline_end: base.end,
        current_start: cur.start,
        current_end: cur.end,
        params,
      }),
    onSuccess: (s) => nav(`/scans/${s.id}`),
    onError: (e: Error) => toast(e.message, 'error'),
  });

  const fc = useMemo(() => selectedFC(parcels.data, ids), [parcels.data, ids]);
  const bbox = useMemo(() => bboxOf(fc.features.map((f) => f.geometry)), [fc]);
  const allBbox = useMemo(
    () => bboxOf((parcels.data?.features ?? []).map((f) => f.geometry)),
    [parcels.data],
  );

  if (user?.role !== 'admin') return <Navigate to="/scans" replace />;

  const seasonal = params.mode === 'seasonal';
  const errors: string[] = [];
  const days = (a: string, b: string) => (new Date(b).getTime() - new Date(a).getTime()) / 86400000;
  if (ids.length === 0) errors.push('Select at least one parcel.');
  if (seasonal) {
    if (days(base.start, base.end) < 360)
      errors.push('The reference period must cover at least 12 months (24 recommended).');
    if (days(base.start, base.end) > 3 * 366)
      errors.push('The reference period cannot exceed three years.');
    if (days(cur.start, cur.end) < 85) errors.push('Monitor at least 3 months.');
    if (days(cur.start, cur.end) > 2 * 366) errors.push('Monitor at most two years.');
  } else {
    if (days(base.start, base.end) < 4 || days(cur.start, cur.end) < 4)
      errors.push('Each period must span at least 5 days.');
    if (days(base.start, base.end) > 366 || days(cur.start, cur.end) > 366)
      errors.push('A period cannot exceed one year.');
  }
  if (base.end >= cur.start) errors.push('The baseline must end before the current period starts.');
  if (cur.end > isoDate(today)) errors.push('The current period cannot end in the future.');
  const seasonWarn = !seasonal && seasonGap(base.start, cur.start) > 1;

  const setMode = (mode: 'two_window' | 'seasonal') => {
    setParams({ ...params, mode });
    if (mode === 'seasonal') {
      // sensible default: 24 reference months, then monitor the last 12
      const curStart = addDays(today, -365);
      setCur({ start: isoDate(curStart), end: isoDate(today) });
      setBase({ start: isoDate(addDays(curStart, -731)), end: isoDate(addDays(curStart, -1)) });
    } else {
      setCur({ start: isoDate(addDays(today, -60)), end: isoDate(today) });
      setBase({ start: isoDate(addDays(today, -60 - 365)), end: isoDate(addDays(today, -365)) });
    }
  };

  const suggestSameSeason = () => {
    const len = Math.max(5, Math.round(days(cur.start, cur.end)));
    const bs = addDays(new Date(cur.start), -365);
    setBase({ start: isoDate(bs), end: isoDate(addDays(bs, len)) });
  };

  return (
    <>
      <PageHeader
        eyebrow="Scans"
        title={clone ? 'Clone and edit' : 'New scan'}
        lead="Choose parcels and periods. The scan flags likely new built-up surfaces, either by comparing two composites or by fitting a seasonal model to a longer history."
      />
      {parcels.data?.total === 0 ? (
        <Card>
          <p className="text-[15px]">There are no parcels to scan yet.</p>
          <LinkButton to="/parcels/new" variant="primary" className="mt-4">
            Add parcels first
          </LinkButton>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[440px_1fr]">
          <div className="space-y-4">
            <Card step="01" title="Parcels">
              <ParcelPicker parcels={parcels.data} value={ids} onChange={setIds} />
            </Card>
            <Card step="02" title="Method and periods">
              <div className="mb-4 grid grid-cols-2 gap-2" role="radiogroup" aria-label="Method">
                {(
                  [
                    ['two_window', 'Two periods', 'Compare two short, same-season composites.'],
                    ['seasonal', 'Seasonal model', 'Learn a year of seasons, then date changes.'],
                  ] as const
                ).map(([m, label, hint]) => (
                  <button
                    key={m}
                    type="button"
                    role="radio"
                    aria-checked={(params.mode ?? 'two_window') === m}
                    onClick={() => setMode(m)}
                    className={`rounded-md border px-3 py-2 text-left transition ${
                      (params.mode ?? 'two_window') === m
                        ? 'border-cream bg-s3'
                        : 'border-hair hover:border-cream/40'
                    }`}
                  >
                    <span className="block text-[14px] font-medium">{label}</span>
                    <span className="block text-[12px] text-soft">{hint}</span>
                  </button>
                ))}
              </div>
              <p className="mb-3 text-[13px] text-soft">
                {seasonal
                  ? 'The reference period (baseline) teaches the model what each month normally looks like — at least 12 months, ideally 24. Changes are then dated to the month they began within the monitored (current) period. Builds one composite per month, so it takes longer.'
                  : 'Same season in both periods gives the most reliable comparison.'}
              </p>
              <div className="grid grid-cols-2 gap-3">
                <Field label={seasonal ? 'Monitor from' : 'Current from'}>
                  <Input
                    type="date"
                    value={cur.start}
                    onChange={(e) => setCur({ ...cur, start: e.target.value })}
                  />
                </Field>
                <Field label={seasonal ? 'Monitor to' : 'Current to'}>
                  <Input
                    type="date"
                    value={cur.end}
                    onChange={(e) => setCur({ ...cur, end: e.target.value })}
                  />
                </Field>
                <Field label={seasonal ? 'Reference from' : 'Baseline from'}>
                  <Input
                    type="date"
                    value={base.start}
                    onChange={(e) => setBase({ ...base, start: e.target.value })}
                  />
                </Field>
                <Field label={seasonal ? 'Reference to' : 'Baseline to'}>
                  <Input
                    type="date"
                    value={base.end}
                    onChange={(e) => setBase({ ...base, end: e.target.value })}
                  />
                </Field>
              </div>
              {!seasonal && (
                <button
                  type="button"
                  onClick={suggestSameSeason}
                  className="mt-3 text-[13px] text-soft underline underline-offset-4 hover:text-cream"
                >
                  Use the same season one year earlier
                </button>
              )}
              {seasonWarn && (
                <p className="mt-2 text-[13px] text-medium" role="status">
                  ⚠ The two periods start in different seasons; vegetation and water differences may
                  look like change.
                </p>
              )}
              <div className="mt-4">
                <AdvancedParams value={params} onChange={setParams} />
              </div>
            </Card>
            <Card step="03" title="Run">
              {errors.length > 0 && (
                <ul className="mb-3 space-y-1 text-[13px] text-soft">
                  {errors.map((e) => (
                    <li key={e}>· {e}</li>
                  ))}
                </ul>
              )}
              <Button
                variant="primary"
                className="w-full justify-center"
                disabled={errors.length > 0}
                busy={create.isPending}
                onClick={() => create.mutate()}
              >
                Start scan
              </Button>
              <p className="mt-2 text-center text-[12px] text-soft">
                A scan over a few km² usually finishes within a few minutes.
              </p>
            </Card>
          </div>
          <div className="min-h-[560px] overflow-hidden rounded-card border border-hair">
            <MapView
              className="h-full min-h-[560px]"
              parcels={parcels.data ?? null}
              selectedParcels={ids}
              onParcelClick={(id) =>
                setIds((v) => (v.includes(id) ? v.filter((x) => x !== id) : [...v, id]))
              }
              fitTo={bbox ?? allBbox}
              fitKey={bbox ? 'sel' : 'all'}
            />
          </div>
        </div>
      )}
    </>
  );
}

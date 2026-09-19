import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { listParcels } from '@/api/parcels';
import { DEFAULT_PARAMS, type ScanParams } from '@/api/scans';
import {
  createSchedule,
  deleteSchedule,
  listSchedules,
  patchSchedule,
  runSchedule,
  type BaselineRule,
  type Schedule,
  type ScheduleCreate,
} from '@/api/schedules';
import { useAuth } from '@/app/useAuth';
import { AdvancedParams } from '@/components/AdvancedParams';
import { ConfirmModal, Modal } from '@/components/Modal';
import { ParcelPicker } from '@/components/ParcelPicker';
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
  StatusChip,
  Table,
} from '@/components/ui';
import { rowCls } from '@/lib/styles';
import { useToast } from '@/components/useToast';
import { fmtDateTime, relTime } from '@/lib/format';

type Freq = 'weekly' | 'monthly' | 'custom';
const freqOf = (cron: string): Freq => (cron === 'weekly' || cron === 'monthly' ? cron : 'custom');

interface Form {
  name: string;
  parcel_ids: string[];
  freq: Freq;
  cron: string;
  current_window_days: number;
  rule: BaselineRule;
  params: Partial<ScanParams>;
}
const blank = (): Form => ({
  name: '',
  parcel_ids: [],
  freq: 'monthly',
  cron: '',
  current_window_days: 30,
  rule: { mode: 'same_season_previous_year' },
  params: {},
});
const fromSchedule = (s: Schedule): Form => {
  const params = { ...s.params };
  delete params.warnings;
  return {
    name: s.name,
    parcel_ids: s.parcels.map((p) => p.id),
    freq: freqOf(s.cron),
    cron: freqOf(s.cron) === 'custom' ? s.cron : '',
    current_window_days: s.current_window_days,
    rule: s.baseline_rule,
    params: Object.fromEntries(
      Object.entries(params).filter(([k, v]) => v !== DEFAULT_PARAMS[k as keyof ScanParams]),
    ),
  };
};

/** Recurring scans (appflow Flow H). Admin only. */
export function SchedulesPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const schedules = useQuery({
    queryKey: ['schedules'],
    queryFn: listSchedules,
    enabled: user?.role === 'admin',
  });
  const parcels = useQuery({ queryKey: ['parcels'], queryFn: () => listParcels() });
  const [editing, setEditing] = useState<{ id: string | null; form: Form } | null>(null);
  const [del, setDel] = useState<Schedule | null>(null);
  const invalidate = () => void qc.invalidateQueries({ queryKey: ['schedules'] });

  const save = useMutation({
    mutationFn: ({ id, form }: { id: string | null; form: Form }) => {
      const body: ScheduleCreate = {
        name: form.name.trim(),
        parcel_ids: form.parcel_ids,
        cron: form.freq === 'custom' ? form.cron.trim() : form.freq,
        current_window_days: form.current_window_days,
        baseline_rule: form.rule,
        params: form.params,
      };
      return id ? patchSchedule(id, body) : createSchedule(body);
    },
    onSuccess: () => {
      invalidate();
      setEditing(null);
      toast('Schedule saved.');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const toggle = useMutation({
    mutationFn: (s: Schedule) => patchSchedule(s.id, { is_active: !s.is_active }),
    onSuccess: invalidate,
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const run = useMutation({
    mutationFn: (s: Schedule) => runSchedule(s.id),
    onSuccess: (scan) => {
      invalidate();
      void qc.invalidateQueries({ queryKey: ['scans'] });
      toast(`Scan queued (${scan.parcels.length} parcels).`);
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const remove = useMutation({
    mutationFn: (s: Schedule) => deleteSchedule(s.id),
    onSuccess: () => {
      invalidate();
      setDel(null);
      toast('Schedule deleted. Past scans are kept.');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });

  if (user?.role !== 'admin') return <Navigate to="/" replace />;

  return (
    <>
      <PageHeader
        eyebrow="Schedules"
        title="Recurring scans"
        lead="When a schedule is due, a normal scan is queued with the current window ending that day. Missed runs are skipped, not replayed."
        action={
          <Button
            variant="primary"
            icon={Plus}
            onClick={() => setEditing({ id: null, form: blank() })}
          >
            New schedule
          </Button>
        }
      />
      {schedules.isPending ? (
        <Skeleton rows={4} />
      ) : schedules.isError ? (
        <ErrorState error={schedules.error} onRetry={() => void schedules.refetch()} />
      ) : schedules.data.total === 0 ? (
        <EmptyState
          eyebrow="No schedules"
          title="Let GeoGuard check on its own"
          text="A weekly or monthly schedule keeps watching your parcels without anyone starting scans by hand."
          action={
            <Button variant="primary" onClick={() => setEditing({ id: null, form: blank() })}>
              New schedule
            </Button>
          }
        />
      ) : (
        <Table head={['Name', 'Parcels', 'Frequency', 'Next run', 'Last run', '']}>
          {schedules.data.items.map((s) => (
            <tr key={s.id} className={rowCls}>
              <td>
                <span className="font-medium">{s.name}</span>
                <span className="ml-2">
                  <Chip tone={s.is_active ? 'ok' : 'neutral'}>
                    {s.is_active ? 'active' : 'paused'}
                  </Chip>
                </span>
              </td>
              <td className="max-w-[220px] truncate text-soft">
                {s.parcels.map((p) => p.name).join(', ')}
              </td>
              <td className="font-mono text-[12px] text-soft">
                {s.cron} · {s.current_window_days} d window
              </td>
              <td className="font-mono text-[12px] text-soft" title={fmtDateTime(s.next_run_at)}>
                {s.is_active ? relTime(s.next_run_at) : '—'}
              </td>
              <td className="font-mono text-[12px] text-soft">
                {s.last_scan_id ? (
                  <Link
                    to={`/scans/${s.last_scan_id}`}
                    className="flex items-center gap-2 hover:underline"
                  >
                    {relTime(s.last_run_at)} <StatusChip status={s.last_scan_status ?? 'queued'} />
                  </Link>
                ) : (
                  'never'
                )}
              </td>
              <td className="text-right">
                <div className="flex justify-end gap-1">
                  <Button
                    size="sm"
                    busy={run.isPending && run.variables?.id === s.id}
                    onClick={() => run.mutate(s)}
                  >
                    Run now
                  </Button>
                  <Button size="sm" onClick={() => toggle.mutate(s)}>
                    {s.is_active ? 'Pause' : 'Resume'}
                  </Button>
                  <Button size="sm" onClick={() => setEditing({ id: s.id, form: fromSchedule(s) })}>
                    Edit
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => setDel(s)}>
                    Delete
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}

      {editing && (
        <ScheduleForm
          form={editing.form}
          parcels={parcels.data}
          busy={save.isPending}
          isNew={editing.id === null}
          onChange={(form) => setEditing({ ...editing, form })}
          onClose={() => setEditing(null)}
          onSave={() => save.mutate(editing)}
        />
      )}
      <ConfirmModal
        open={del !== null}
        title="Delete this schedule?"
        text={`“${del?.name}” will stop running. Scans it already created, and their detections, are kept.`}
        confirmLabel="Delete"
        danger
        busy={remove.isPending}
        onConfirm={() => del && remove.mutate(del)}
        onClose={() => setDel(null)}
      />
    </>
  );
}

function ScheduleForm({
  form,
  parcels,
  busy,
  isNew,
  onChange,
  onClose,
  onSave,
}: {
  form: Form;
  parcels: ReturnType<typeof useQuery<Awaited<ReturnType<typeof listParcels>>>>['data'];
  busy: boolean;
  isNew: boolean;
  onChange: (f: Form) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  const cronOk = form.freq !== 'custom' || /^\S+\s+\S+\s+\S+\s+\S+\s+\S+$/.test(form.cron.trim());
  const ruleOk =
    form.rule.mode !== 'fixed' ||
    (Boolean(form.rule.baseline_start) &&
      Boolean(form.rule.baseline_end) &&
      form.rule.baseline_start! < form.rule.baseline_end!);
  const valid = form.name.trim() && form.parcel_ids.length > 0 && cronOk && ruleOk;
  return (
    <Modal
      open
      title={isNew ? 'New schedule' : 'Edit schedule'}
      onClose={onClose}
      footer={
        <Button variant="primary" busy={busy} disabled={!valid} onClick={onSave}>
          {isNew ? 'Create' : 'Save'}
        </Button>
      }
    >
      <div className="max-h-[70vh] space-y-3 overflow-y-auto pr-1">
        <Field label="Name">
          <Input
            value={form.name}
            onChange={(e) => onChange({ ...form, name: e.target.value })}
            placeholder="e.g. Marsh edge · monthly"
          />
        </Field>
        <Field label="Parcels">
          <ParcelPicker
            parcels={parcels}
            value={form.parcel_ids}
            onChange={(ids) => onChange({ ...form, parcel_ids: ids })}
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Frequency">
            <Select
              value={form.freq}
              onChange={(e) => onChange({ ...form, freq: e.target.value as Freq })}
            >
              <option value="weekly">Weekly (Monday 03:00 UTC)</option>
              <option value="monthly">Monthly (1st, 03:00 UTC)</option>
              <option value="custom">Custom cron</option>
            </Select>
          </Field>
          <Field label="Current window (days)" hint="Ends on the run day">
            <Input
              type="number"
              min={5}
              max={120}
              value={form.current_window_days}
              onChange={(e) => onChange({ ...form, current_window_days: Number(e.target.value) })}
            />
          </Field>
        </div>
        {form.freq === 'custom' && (
          <Field
            label="Cron (UTC)"
            hint="minute hour day month weekday, e.g. 0 3 * * 1"
            error={cronOk ? null : 'Five space-separated fields'}
          >
            <Input
              value={form.cron}
              onChange={(e) => onChange({ ...form, cron: e.target.value })}
              className="font-mono"
            />
          </Field>
        )}
        <Field label="Baseline">
          <Select
            value={form.rule.mode}
            onChange={(e) =>
              onChange({ ...form, rule: { mode: e.target.value as BaselineRule['mode'] } })
            }
          >
            <option value="same_season_previous_year">Same season, previous year</option>
            <option value="years_back">Same season, N years back</option>
            <option value="fixed">Fixed dates</option>
          </Select>
        </Field>
        {form.rule.mode === 'years_back' && (
          <Field label="Years back">
            <Input
              type="number"
              min={1}
              max={8}
              value={form.rule.years ?? 2}
              onChange={(e) =>
                onChange({ ...form, rule: { ...form.rule, years: Number(e.target.value) } })
              }
            />
          </Field>
        )}
        {form.rule.mode === 'fixed' && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Baseline from">
              <Input
                type="date"
                value={form.rule.baseline_start ?? ''}
                onChange={(e) =>
                  onChange({ ...form, rule: { ...form.rule, baseline_start: e.target.value } })
                }
              />
            </Field>
            <Field label="Baseline to">
              <Input
                type="date"
                value={form.rule.baseline_end ?? ''}
                onChange={(e) =>
                  onChange({ ...form, rule: { ...form.rule, baseline_end: e.target.value } })
                }
              />
            </Field>
          </div>
        )}
        <AdvancedParams value={form.params} onChange={(params) => onChange({ ...form, params })} />
      </div>
    </Modal>
  );
}

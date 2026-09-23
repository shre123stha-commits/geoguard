import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import type { Confidence } from '@/api/detections';
import { getHealth } from '@/api/health';
import { DEFAULT_PARAMS } from '@/api/scans';
import {
  getAlertSettings,
  getInsights,
  PROVIDER_LABEL,
  putAlertSettings,
  RECIPIENT_HINT,
  testAlert,
  type AlertProvider,
  type AlertSettings,
} from '@/api/settings';
import { useAuth } from '@/app/useAuth';
import {
  Button,
  Card,
  Chip,
  ErrorState,
  Field,
  Input,
  LinkButton,
  PageHeader,
  Select,
  Skeleton,
  Textarea,
} from '@/components/ui';
import { useToast } from '@/components/useToast';

/** Settings (admin): service status, default thresholds, alert delivery (appflow Flow E). */
export function SettingsPage() {
  const { user } = useAuth();
  const h = useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 30_000 });
  if (user?.role !== 'admin') return <Navigate to="/" replace />;
  return (
    <>
      <PageHeader
        eyebrow="Settings"
        title="Configuration"
        lead="What this installation is set up to do."
      />
      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-6">
          <AlertsCard />
          <InsightsCard />
        </div>
        <div className="space-y-6">
          <Card title="Service">
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-[14px]">
              <dt className="text-soft">API</dt>
              <dd>
                <Chip tone={h.data?.status === 'ok' ? 'ok' : h.isError ? 'danger' : 'neutral'}>
                  {h.data?.status ?? (h.isError ? 'unreachable' : '…')}
                </Chip>
              </dd>
              <dt className="text-soft">Database</dt>
              <dd>
                <Chip tone={h.data?.database === 'ok' ? 'ok' : 'neutral'}>
                  {h.data?.database ?? '…'}
                </Chip>
              </dd>
              <dt className="text-soft">PostGIS</dt>
              <dd className="font-mono text-[13px]">{h.data?.postgis ?? '…'}</dd>
              <dt className="text-soft">Schema</dt>
              <dd className="font-mono text-[13px]">{h.data?.migration ?? '…'}</dd>
            </dl>
          </Card>
          <Card title="Default thresholds">
            <p className="mb-3 text-[13px] text-soft">
              Prefilled in every new scan and schedule; adjustable per run under Advanced.
            </p>
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 font-mono text-[12px]">
              {Object.entries(DEFAULT_PARAMS).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-soft">{k}</dt>
                  <dd>{String(v)}</dd>
                </div>
              ))}
            </dl>
          </Card>
          <Card title="Recurring scans">
            <p className="text-[14px] text-soft">
              Weekly or monthly scans run on their own and queue like any other scan.
            </p>
            <LinkButton to="/schedules" className="mt-4">
              Manage schedules
            </LinkButton>
          </Card>
        </div>
      </div>
    </>
  );
}

const CONF: Confidence[] = ['high', 'medium', 'low'];

function AlertsCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ['alert-settings'], queryFn: getAlertSettings });
  const [form, setForm] = useState<AlertSettings | null>(null);
  const [recipientsText, setRecipientsText] = useState('');
  const [testTo, setTestTo] = useState('');
  useEffect(() => {
    if (q.data && form === null) {
      const d = q.data;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time hydration from the server
      setForm({
        enabled: d.enabled,
        provider: d.provider,
        recipients: d.recipients,
        min_confidence: d.min_confidence,
        min_persistence: d.min_persistence ?? 1,
        app_url: d.app_url,
      });
      setRecipientsText(d.recipients.join('\n'));
    }
  }, [q.data, form]);

  const save = useMutation({
    mutationFn: (body: AlertSettings) => putAlertSettings(body),
    onSuccess: (d) => {
      qc.setQueryData(['alert-settings'], d);
      toast(d.enabled ? 'Alerts are on.' : 'Alerts are off.');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const test = useMutation({
    mutationFn: () => testAlert(testTo),
    onSuccess: () => toast('Test message sent.'),
    onError: (e: Error) => toast(e.message, 'error'),
  });

  if (q.isPending || form === null)
    return (
      <Card title="Alerts">
        <Skeleton rows={5} />
      </Card>
    );
  if (q.isError)
    return (
      <Card title="Alerts">
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </Card>
    );

  const recipients = recipientsText
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const providerOk = q.data.available_providers.includes(form.provider);
  const needsRecipients = form.provider !== 'console' && recipients.length === 0;
  const body: AlertSettings = { ...form, recipients };
  const testOk =
    testTo.trim().length > 0 &&
    (q.data.provider !== 'email' || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(testTo.trim()));
  const saved: AlertSettings = {
    enabled: q.data.enabled,
    provider: q.data.provider,
    recipients: q.data.recipients,
    min_confidence: q.data.min_confidence,
    min_persistence: q.data.min_persistence ?? 1,
    app_url: q.data.app_url,
  };
  const dirty = JSON.stringify(body) !== JSON.stringify(saved);

  return (
    <Card
      title="Alerts"
      action={<Chip tone={q.data.enabled ? 'ok' : 'neutral'}>{q.data.enabled ? 'on' : 'off'}</Chip>}
    >
      <p className="mb-4 text-[14px] text-soft">
        When a reviewer confirms a detection at or above the chosen confidence, a short message with
        the parcel, location and a link goes to every recipient. Confirmations are recorded in the
        detection’s history either way.
      </p>
      <div className="space-y-3">
        <Field label="Channel">
          <Select
            value={form.provider}
            onChange={(e) => setForm({ ...form, provider: e.target.value as AlertProvider })}
          >
            {(Object.entries(PROVIDER_LABEL) as [AlertProvider, string][]).map(([p, label]) => (
              <option key={p} value={p}>
                {label}
                {q.data.available_providers.includes(p) ? '' : ' — not configured on the server'}
              </option>
            ))}
          </Select>
        </Field>
        {!providerOk && (
          <p className="rounded-ctl border border-hair bg-s1 px-3 py-2 text-[13px] text-soft">
            E-mail is not configured on the server yet. In <code>backend\.env</code> set{' '}
            <code>SMTP_HOST=smtp.gmail.com</code>, <code>SMTP_PORT=587</code>,{' '}
            <code>SMTP_USER</code> and <code>SMTP_FROM</code> to your Gmail address and{' '}
            <code>SMTP_PASSWORD</code> to a Google App Password, restart the server, then reload
            this page.
          </p>
        )}
        <Field label="Recipients" hint={RECIPIENT_HINT[form.provider]}>
          <Textarea
            value={recipientsText}
            onChange={(e) => setRecipientsText(e.target.value)}
            placeholder={
              form.provider === 'telegram'
                ? '123456789'
                : form.provider === 'email'
                  ? 'officer@example.org'
                  : ''
            }
            disabled={form.provider === 'console'}
            className="font-mono text-[13px]"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Minimum confidence">
            <Select
              value={form.min_confidence}
              onChange={(e) => setForm({ ...form, min_confidence: e.target.value as Confidence })}
            >
              {CONF.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Seen in scans" hint="Alert only after this many consecutive scans">
            <Select
              value={String(form.min_persistence)}
              onChange={(e) => setForm({ ...form, min_persistence: Number(e.target.value) })}
            >
              {[1, 2, 3].map((n) => (
                <option key={n} value={n}>
                  {n === 1 ? 'first sighting' : `${n} scans in a row`}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Public address" hint="Used for the link in messages">
            <Input
              value={form.app_url}
              onChange={(e) => setForm({ ...form, app_url: e.target.value })}
              placeholder="https://geoguard.example.org"
            />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-[14px]">
          <input
            type="checkbox"
            checked={form.enabled}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
            className="h-4 w-4 accent-cream"
          />
          Send alerts
        </label>
        <div className="flex flex-wrap items-center gap-2 border-t border-hair pt-3">
          <Button
            variant="primary"
            busy={save.isPending}
            disabled={!dirty || (form.enabled && (!providerOk || needsRecipients))}
            onClick={() => save.mutate(body)}
          >
            Save
          </Button>
          {form.enabled && needsRecipients && (
            <span className="text-[13px] text-soft">Add at least one recipient.</span>
          )}
        </div>
        {q.data.enabled && (
          <Field
            label="Send a test message"
            hint={
              q.data.provider === 'email'
                ? 'Enter the e-mail address that should receive the test.'
                : 'Any label; the message is written to the server log.'
            }
            error={testTo.trim() && !testOk ? 'That is not an e-mail address.' : null}
          >
            <div className="flex gap-2">
              <Input
                type={q.data.provider === 'email' ? 'email' : 'text'}
                value={testTo}
                onChange={(e) => setTestTo(e.target.value)}
                placeholder={
                  q.data.provider === 'email' ? (q.data.recipients[0] ?? 'you@example.org') : 'log'
                }
                className="font-mono text-[13px]"
              />
              <Button
                className="shrink-0 whitespace-nowrap"
                busy={test.isPending}
                disabled={!testOk}
                onClick={() => test.mutate()}
              >
                Send test
              </Button>
            </div>
          </Field>
        )}
      </div>
    </Card>
  );
}

function InsightsCard() {
  const q = useQuery({ queryKey: ['insights'], queryFn: getInsights });
  if (q.isPending) return <Skeleton rows={3} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  return (
    <Card title="What your reviews say">
      <p className="mb-3 text-[14px] text-soft">
        Every confirm or dismiss is a label. {d.reviewed} reviewed so far ({d.confirmed} confirmed,{' '}
        {d.dismissed} dismissed).
      </p>
      <dl className="mb-3 grid grid-cols-[auto_1fr_1fr] gap-x-6 gap-y-1 font-mono text-[12px]">
        <dt className="text-soft">class</dt>
        <dd className="text-soft">confirmed / dismissed</dd>
        <dd className="text-soft">precision</dd>
        {d.by_class.map((c) => (
          <div key={c.confidence} className="contents">
            <dt>{c.confidence}</dt>
            <dd>
              {c.confirmed} / {c.dismissed}
            </dd>
            <dd>{c.precision == null ? '—' : `${Math.round(c.precision * 100)} %`}</dd>
          </div>
        ))}
      </dl>
      {Object.keys(d.dismiss_reasons).length > 0 && (
        <p className="mb-3 font-mono text-[12px] text-soft">
          dismissed because:{' '}
          {Object.entries(d.dismiss_reasons)
            .sort((a, b) => b[1] - a[1])
            .map(([k, v]) => `${k.replace('_', ' ')} ×${v}`)
            .join(' · ')}
        </p>
      )}
      {d.suggestions.length > 0 ? (
        <ul className="space-y-2 text-[14px]">
          {d.suggestions.map((s) => (
            <li key={s.param} className="border-t border-hair pt-2">
              {s.text}{' '}
              <span className="text-soft">
                Set it under Advanced when creating a scan or schedule.
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[13px] text-soft">{d.note}</p>
      )}
    </Card>
  );
}

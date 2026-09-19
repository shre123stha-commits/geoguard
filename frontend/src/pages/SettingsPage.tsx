import { useQuery } from '@tanstack/react-query';
import { Navigate } from 'react-router-dom';
import { getHealth } from '@/api/health';
import { DEFAULT_PARAMS } from '@/api/scans';
import { useAuth } from '@/app/useAuth';
import { Card, Chip, LinkButton, PageHeader } from '@/components/ui';

/** Settings (admin). Alert delivery settings appear here once the alert service is enabled. */
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
        <Card title="Alerts">
          <p className="text-[14px] text-soft">
            Alert delivery (console log, Telegram, e-mail) for confirmed high-confidence detections
            is not enabled on this installation yet. Confirmations are always recorded in each
            detection’s history regardless.
          </p>
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
    </>
  );
}

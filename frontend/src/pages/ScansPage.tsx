import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { isOpen, listScans, type ScanStatus } from '@/api/scans';
import { useAuth } from '@/app/useAuth';
import {
  Button,
  EmptyState,
  ErrorState,
  LinkButton,
  PageHeader,
  Skeleton,
  StatusChip,
  Table,
} from '@/components/ui';
import { rowCls } from '@/lib/styles';
import { fmtDateTime, relTime } from '@/lib/format';

const PAGE = 20;

export function ScansPage() {
  const { user } = useAuth();
  const admin = user?.role === 'admin';
  const nav = useNavigate();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<ScanStatus | undefined>();
  const scans = useQuery({
    queryKey: ['scans', page, PAGE, status],
    queryFn: () => listScans(page, PAGE, status),
    refetchInterval: (q) => (q.state.data?.items.some(isOpen) ? 3000 : false),
  });
  const pages = Math.max(1, Math.ceil((scans.data?.total ?? 0) / PAGE));

  return (
    <>
      <PageHeader
        eyebrow="Scans"
        title="Scan history"
        lead="Each scan compares a baseline period with a current period over the selected parcels."
        action={
          admin && (
            <LinkButton to="/scans/new" variant="primary" icon={Plus}>
              New scan
            </LinkButton>
          )
        }
      />
      <div className="mb-4 flex flex-wrap gap-1">
        {([undefined, 'queued', 'running', 'succeeded', 'failed', 'cancelled'] as const).map(
          (s) => (
            <button
              key={s ?? 'all'}
              onClick={() => {
                setStatus(s);
                setPage(1);
              }}
              className={`rounded-full px-3 py-1 font-mono text-[12px] ${status === s ? 'bg-s3 text-cream' : 'text-soft hover:bg-s1'}`}
            >
              {s ?? 'all'}
            </button>
          ),
        )}
      </div>
      {scans.isPending ? (
        <Skeleton rows={6} />
      ) : scans.isError ? (
        <ErrorState error={scans.error} onRetry={() => void scans.refetch()} />
      ) : scans.data.total === 0 ? (
        <EmptyState
          eyebrow={status ? `No ${status} scans` : 'No scans yet'}
          title={status ? 'Nothing here' : 'Run your first scan'}
          text={
            status
              ? undefined
              : admin
                ? 'Pick parcels and two periods; the worker fetches Sentinel imagery and flags change.'
                : 'An administrator can start scans; results appear here.'
          }
          action={
            admin &&
            !status && (
              <LinkButton to="/scans/new" variant="primary">
                New scan
              </LinkButton>
            )
          }
        />
      ) : (
        <>
          <Table head={['Started', 'Status', 'Parcels', 'Baseline', 'Current', 'Detections']}>
            {scans.data.items.map((s) => (
              <tr
                key={s.id}
                className={`${rowCls} cursor-pointer`}
                onClick={() => nav(`/scans/${s.id}`)}
              >
                <td>
                  <Link to={`/scans/${s.id}`} className="hover:underline">
                    {relTime(s.created_at)}
                  </Link>
                  <span className="block font-mono text-[11px] text-soft">
                    {fmtDateTime(s.created_at)}
                  </span>
                </td>
                <td>
                  <StatusChip status={s.status} />
                  {isOpen(s) && (
                    <span className="ml-2 font-mono text-[11px] text-soft">{s.progress} %</span>
                  )}
                  {s.schedule_id && (
                    <span className="ml-2 font-mono text-[11px] text-soft">scheduled</span>
                  )}
                </td>
                <td className="max-w-[240px] truncate text-soft">
                  {s.parcels.map((p) => p.name).join(', ') || '—'}
                </td>
                <td className="font-mono text-[12px] text-soft">
                  {s.baseline_start} → {s.baseline_end}
                </td>
                <td className="font-mono text-[12px] text-soft">
                  {s.current_start} → {s.current_end}
                </td>
                <td className="text-right font-mono text-[13px]">
                  {s.status === 'succeeded' ? s.detection_count : '—'}
                </td>
              </tr>
            ))}
          </Table>
          {pages > 1 && (
            <div className="mt-4 flex items-center justify-end gap-2 font-mono text-[12px] text-soft">
              <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Prev
              </Button>
              <span>
                {page} / {pages}
              </span>
              <Button size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}

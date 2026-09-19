import { useQuery } from '@tanstack/react-query';
import { getHealth } from '@/api/health';

/** Temporary Phase 0 page proving the frontend↔backend wiring. Replaced in Phase 6. */
export function HealthPage() {
  const q = useQuery({ queryKey: ['health'], queryFn: getHealth });

  return (
    <main className="mx-auto max-w-[1200px] p-4 md:p-8">
      <p className="rise font-mono text-[11px] uppercase tracking-[0.12em] text-soft">System</p>
      <h1 className="rise font-display text-[clamp(36px,4.5vw,64px)] font-medium leading-[1.02] tracking-[-0.03em]">
        GeoGuard<sup className="ml-1 text-[0.4em] align-super">EO</sup>
      </h1>
      <p className="rise mt-3 max-w-[68ch] text-lg text-soft [animation-delay:120ms]">
        Watch protected land from above. Verify on the ground.
      </p>

      <section
        aria-live="polite"
        className="rise mt-8 rounded-card border border-hair bg-s1 p-6 [animation-delay:240ms]"
      >
        <h2 className="font-display text-[22px] font-medium tracking-[-0.02em]">Backend health</h2>
        {q.isPending && <p className="mt-2 text-soft">Checking…</p>}
        {q.isError && (
          <p className="mt-2 text-soft">
            Could not reach the API. Start the backend and retry.{' '}
            <button className="underline" onClick={() => void q.refetch()}>
              Retry
            </button>
          </p>
        )}
        {q.data && (
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 font-mono text-[13px]">
            <dt className="text-soft">status</dt>
            <dd>{q.data.status}</dd>
            <dt className="text-soft">database</dt>
            <dd>{q.data.database}</dd>
            <dt className="text-soft">postgis</dt>
            <dd>{q.data.postgis ?? '—'}</dd>
            <dt className="text-soft">migration</dt>
            <dd>{q.data.migration ?? '—'}</dd>
          </dl>
        )}
      </section>
      <p className="mt-6 text-[13px] text-soft">
        Satellite detection is a screening aid. Verify on the ground before acting.
      </p>
    </main>
  );
}

/** Shared primitives per docs/04-design.md §6. Cream/dark chrome only; colour is data-only. */
import { Loader2, type LucideIcon } from 'lucide-react';
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from 'react';
import { Link } from 'react-router-dom';
import { fieldCls } from '@/lib/styles';

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ');

/* ---------- buttons ---------- */

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
const BTN: Record<Variant, string> = {
  primary:
    'bg-glass border border-hair-strong text-cream backdrop-blur-md hover:-translate-y-px hover:bg-s3',
  secondary: 'border border-hair text-cream hover:bg-s2',
  ghost: 'text-soft hover:text-cream hover:underline underline-offset-4',
  danger: 'border border-hair text-high hover:bg-s2',
};

export function Button({
  variant = 'secondary',
  size = 'md',
  icon: Icon,
  busy,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: 'sm' | 'md';
  icon?: LucideIcon;
  busy?: boolean;
}) {
  return (
    <button
      type="button"
      {...rest}
      disabled={rest.disabled || busy}
      aria-disabled={rest.disabled || busy}
      className={cx(
        'inline-flex items-center gap-2 rounded-full font-medium transition disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0',
        size === 'sm' ? 'px-3 py-1.5 text-[13px]' : 'px-5 py-2.5 text-[15px]',
        BTN[variant],
        className,
      )}
    >
      {busy ? <Loader2 size={16} className="animate-spin" /> : Icon && <Icon size={16} />}
      {children}
    </button>
  );
}

export function LinkButton({
  to,
  variant = 'secondary',
  size = 'md',
  icon: Icon,
  className,
  children,
}: {
  to: string;
  variant?: Variant;
  size?: 'sm' | 'md';
  icon?: LucideIcon;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link
      to={to}
      className={cx(
        'inline-flex items-center gap-2 rounded-full font-medium transition',
        size === 'sm' ? 'px-3 py-1.5 text-[13px]' : 'px-5 py-2.5 text-[15px]',
        BTN[variant],
        className,
      )}
    >
      {Icon && <Icon size={16} />}
      {children}
    </Link>
  );
}

/* ---------- form controls ---------- */

export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cx('block', className)}>
      <span className="mb-1 block text-[13px] font-medium">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-[12px] text-soft">{hint}</span>}
      {error && (
        <span role="alert" className="mt-1 block text-[12px] text-high">
          ⚠ {error}
        </span>
      )}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(fieldCls, props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(fieldCls, 'appearance-none', props.className)} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cx(fieldCls, 'h-auto min-h-[88px] py-2 leading-relaxed', props.className)}
    />
  );
}

/* ---------- layout ---------- */

export function PageHeader({
  eyebrow,
  title,
  lead,
  action,
}: {
  eyebrow: ReactNode;
  title: string;
  lead?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4 rise">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-soft">{eyebrow}</p>
        <h1 className="mt-1 font-display text-[clamp(28px,3vw,44px)] font-medium leading-[1.1] tracking-[-0.03em]">
          {title}
        </h1>
        {lead && <p className="mt-2 max-w-[68ch] text-[15px] text-soft">{lead}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  );
}

export function Card({
  title,
  step,
  children,
  className,
  action,
}: {
  title?: string;
  step?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  return (
    <section className={cx('rounded-card border border-hair bg-s1 p-6', className)}>
      {(title || step || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div>
            {step && <p className="font-mono text-[11px] tracking-[0.12em] text-soft">{step}</p>}
            {title && <h3 className="text-[18px] font-medium tracking-[-0.02em]">{title}</h3>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Chip({
  children,
  tone = 'neutral',
  dot,
  className,
}: {
  children: ReactNode;
  tone?: 'neutral' | 'high' | 'medium' | 'low' | 'ok' | 'danger';
  dot?: boolean;
  className?: string;
}) {
  const color =
    tone === 'neutral'
      ? undefined
      : tone === 'ok'
        ? 'var(--sem-ok)'
        : tone === 'danger'
          ? 'var(--sem-danger)'
          : `var(--sem-${tone})`;
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full border border-hair px-2 py-px font-mono text-[11px] uppercase tracking-[0.08em]',
        className,
      )}
      style={color ? { color } : undefined}
    >
      {dot && (
        <span
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ background: color ?? 'var(--text-soft)' }}
        />
      )}
      {children}
    </span>
  );
}

export function StatusChip({ status }: { status: string }) {
  const tone =
    status === 'succeeded' || status === 'confirmed'
      ? 'ok'
      : status === 'failed'
        ? 'danger'
        : 'neutral';
  const icon =
    {
      new: '●',
      confirmed: '✓',
      dismissed: '×',
      field_visit: '⚑',
      queued: '…',
      running: '▶',
      succeeded: '✓',
      failed: '!',
      cancelled: '–',
    }[status] ?? '';
  return (
    <Chip tone={tone}>
      <span aria-hidden>{icon}</span> {status.replace('_', ' ')}
    </Chip>
  );
}

/* ---------- states ---------- */

export function EmptyState({
  eyebrow,
  title,
  text,
  action,
}: {
  eyebrow: string;
  title: string;
  text?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-card border border-dashed border-hair px-6 py-14 text-center">
      <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-soft">{eyebrow}</p>
      <h3 className="mt-2 text-[22px] font-medium tracking-[-0.02em]">{title}</h3>
      {text && <p className="mx-auto mt-2 max-w-[48ch] text-[15px] text-soft">{text}</p>}
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  );
}

export function Skeleton({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cx('space-y-2', className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-10 animate-pulse rounded-ctl bg-s1" />
      ))}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof Error ? error.message : 'Something went wrong.';
  return (
    <div role="alert" className="rounded-card border border-hair bg-s1 px-6 py-8 text-center">
      <p className="text-[15px]">Could not load this view.</p>
      <p className="mt-1 text-[13px] text-soft">{msg}</p>
      {onRetry && (
        <Button className="mt-4" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function Progress({ value, label }: { value: number; label?: string }) {
  return (
    <div>
      <div className="h-px w-full bg-hair">
        <div
          className="h-0.5 -translate-y-px bg-cream transition-[width] duration-500"
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
          role="progressbar"
          aria-valuenow={value}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
      {label && (
        <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.12em] text-soft">{label}</p>
      )}
    </div>
  );
}

/* ---------- table ---------- */

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[14px] tabular-nums">
        <thead className="sticky top-0 bg-base">
          <tr>
            {head.map((h, i) => (
              <th
                key={i}
                className="border-b border-hair-strong px-3 py-2.5 text-left font-mono text-[11px] font-normal uppercase tracking-[0.12em] text-soft first:pl-0 last:pr-0"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

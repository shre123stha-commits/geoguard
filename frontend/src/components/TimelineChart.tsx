import type { TimelineMonth } from '@/api/parcels';

/** Monthly built-up share as a bar chart. Inline SVG: no chart library, no colour accents
 * (design §3) — cream bars, dim bars for low-quality months, hatched gaps for no view. */
export function TimelineChart({
  months,
  onset,
  height = 140,
}: {
  months: TimelineMonth[];
  onset: string | null;
  height?: number;
}) {
  if (months.length === 0) return null;
  const w = 640;
  const padL = 34;
  const padB = 22;
  const padT = 8;
  const innerW = w - padL - 8;
  const innerH = height - padB - padT;
  const max = Math.max(0.1, ...months.map((m) => m.built_frac ?? 0)) * 1.15;
  const bw = innerW / months.length;
  const y = (v: number) => padT + innerH - (v / max) * innerH;
  const ticks = [0, max / 2, max].map((v) => Math.round(v * 100) / 100);
  return (
    <svg
      viewBox={`0 0 ${w} ${height}`}
      className="w-full"
      role="img"
      aria-label={`Built-up share per month, ${months[0].month.slice(0, 7)} to ${months[months.length - 1].month.slice(0, 7)}`}
    >
      <defs>
        <pattern
          id="gap"
          width="4"
          height="4"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <line x1="0" y1="0" x2="0" y2="4" stroke="var(--text-dim)" strokeWidth="1" />
        </pattern>
      </defs>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={padL} x2={w - 8} y1={y(t)} y2={y(t)} stroke="var(--hairline)" strokeWidth="1" />
          <text
            x={padL - 6}
            y={y(t) + 3}
            textAnchor="end"
            fontSize="9"
            fill="var(--text-soft)"
            className="font-mono"
          >
            {Math.round(t * 100)}%
          </text>
        </g>
      ))}
      {months.map((m, i) => {
        const x = padL + i * bw + 1;
        const label = m.month.slice(0, 7);
        const isOnset = onset != null && m.month === onset;
        if (m.built_frac == null) {
          return (
            <g key={m.month}>
              <rect
                x={x}
                y={padT}
                width={Math.max(1, bw - 2)}
                height={innerH}
                fill="url(#gap)"
                opacity="0.6"
              >
                <title>
                  {label}: no clear view ({m.n_scenes} scenes)
                </title>
              </rect>
            </g>
          );
        }
        const h = innerH - (y(m.built_frac) - padT);
        const weak = (m.valid_frac ?? 1) < 0.5;
        return (
          <g key={m.month}>
            <rect
              x={x}
              y={y(m.built_frac)}
              width={Math.max(1, bw - 2)}
              height={Math.max(1, h)}
              fill="var(--text)"
              opacity={weak ? 0.35 : 0.85}
            >
              <title>
                {label}: {(m.built_frac * 100).toFixed(1)}% built-up · NDVI{' '}
                {m.ndvi_mean?.toFixed(2)} · {Math.round((m.valid_frac ?? 0) * 100)}% clear ·{' '}
                {m.n_scenes} scenes
              </title>
            </rect>
            {isOnset && (
              <line
                x1={x - 1}
                x2={x - 1}
                y1={padT}
                y2={padT + innerH}
                stroke="var(--text)"
                strokeWidth="1.5"
                strokeDasharray="3 2"
              />
            )}
          </g>
        );
      })}
      {months.map((m, i) =>
        m.month.endsWith('-01-01') || i === 0 ? (
          <text
            key={m.month}
            x={padL + i * bw + 1}
            y={height - 8}
            fontSize="9"
            fill="var(--text-soft)"
            className="font-mono"
          >
            {m.month.slice(0, 4)}
          </text>
        ) : null,
      )}
    </svg>
  );
}

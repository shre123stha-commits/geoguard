export const fmtArea = (m2: number): string =>
  m2 >= 10_000 ? `${(m2 / 10_000).toFixed(1)} ha` : `${Math.round(m2).toLocaleString()} m²`;

export const fmtDate = (iso: string | null | undefined): string => (iso ? iso.slice(0, 10) : '—');

export const fmtDateTime = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { hour12: false });
};

export const relTime = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.round(ms / 60000);
  if (Math.abs(m) < 1) return 'just now';
  if (Math.abs(m) < 60) return m > 0 ? `${m} min ago` : `in ${-m} min`;
  const h = Math.round(m / 60);
  if (Math.abs(h) < 48) return h > 0 ? `${h} h ago` : `in ${-h} h`;
  const d = Math.round(h / 24);
  return d > 0 ? `${d} d ago` : `in ${-d} d`;
};

export const isoDate = (d: Date): string => d.toISOString().slice(0, 10);
export const addDays = (d: Date, n: number): Date => new Date(d.getTime() + n * 86_400_000);

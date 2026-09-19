import { useMemo, useState } from 'react';
import type { ParcelCollection } from '@/api/parcels';
import { fmtArea } from '@/lib/format';
import { fieldCls } from '@/lib/styles';

/** Multi-select of parcels with "all" and a search box (appflow Flow C step 2). */
export function ParcelPicker({
  parcels,
  value,
  onChange,
}: {
  parcels: ParcelCollection | undefined;
  value: string[];
  onChange: (ids: string[]) => void;
}) {
  const [q, setQ] = useState('');
  const feats = useMemo(
    () =>
      (parcels?.features ?? []).filter((f) =>
        `${f.properties.name} ${f.properties.category}`.toLowerCase().includes(q.toLowerCase()),
      ),
    [parcels, q],
  );
  const all = parcels?.features.map((f) => f.id) ?? [];
  const set = new Set(value);
  const total = (parcels?.features ?? [])
    .filter((f) => set.has(f.id))
    .reduce((a, f) => a + f.properties.area_m2, 0);
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter parcels"
          aria-label="Filter parcels"
          className={`${fieldCls} h-9 text-[13px]`}
        />
        <button
          type="button"
          onClick={() => onChange(set.size === all.length ? [] : all)}
          className="shrink-0 rounded-full border border-hair px-3 py-1.5 text-[12px] hover:bg-s2"
        >
          {set.size === all.length && all.length > 0 ? 'None' : 'All'}
        </button>
      </div>
      <ul className="max-h-[260px] divide-y divide-hair overflow-y-auto rounded-ctl border border-hair">
        {feats.map((f) => (
          <li key={f.id}>
            <label className="flex cursor-pointer items-center gap-3 px-3 py-2 text-[14px] hover:bg-s2">
              <input
                type="checkbox"
                checked={set.has(f.id)}
                onChange={(e) =>
                  onChange(e.target.checked ? [...value, f.id] : value.filter((v) => v !== f.id))
                }
                className="h-4 w-4 accent-[#f3efe6]"
              />
              <span className="flex-1">
                {f.properties.name}
                <span className="ml-2 text-[12px] text-soft">{f.properties.category}</span>
              </span>
              <span className="font-mono text-[12px] text-soft">
                {fmtArea(f.properties.area_m2)}
              </span>
            </label>
          </li>
        ))}
        {feats.length === 0 && (
          <li className="px-3 py-4 text-center text-[13px] text-soft">No parcels match.</li>
        )}
      </ul>
      <p className="mt-2 font-mono text-[12px] text-soft" aria-live="polite">
        {set.size} selected · {fmtArea(total)}
      </p>
    </div>
  );
}

import { useState } from 'react';
import { DEFAULT_PARAMS, type ScanParams } from '@/api/scans';
import { Field, Input } from './ui';

type Key = keyof Omit<ScanParams, 'warnings'>;
const FIELDS: { k: Key; label: string; hint: string; step: number; min: number; max: number }[] = [
  {
    k: 'cloud_cover_max',
    label: 'Max cloud cover (%)',
    hint: 'Scenes above this are skipped',
    step: 5,
    min: 0,
    max: 100,
  },
  {
    k: 'min_area_m2',
    label: 'Min detection area (m²)',
    hint: '400 m² ≈ 4 Sentinel pixels',
    step: 100,
    min: 100,
    max: 100000,
  },
  {
    k: 't_bui',
    label: 'Optical threshold (ΔBUI)',
    hint: 'Higher = fewer, stronger optical flags',
    step: 0.01,
    min: 0,
    max: 1,
  },
  {
    k: 't_ndvi_drop',
    label: 'Vegetation loss (ΔNDVI)',
    hint: 'Drop required to count as loss',
    step: 0.01,
    min: 0,
    max: 1,
  },
  {
    k: 't_sar_db',
    label: 'Radar threshold (dB)',
    hint: 'Backscatter rise for a radar flag',
    step: 0.1,
    min: 0,
    max: 10,
  },
  {
    k: 'overlap',
    label: 'Sensor overlap',
    hint: 'Share of optical area radar must cover',
    step: 0.05,
    min: 0,
    max: 1,
  },
];

/** Collapsible "Advanced" thresholds with defaults prefilled (appflow Flow C step 4). */
export function AdvancedParams({
  value,
  onChange,
}: {
  value: Partial<ScanParams>;
  onChange: (v: Partial<ScanParams>) => void;
}) {
  const [open, setOpen] = useState(false);
  const changed = FIELDS.some(
    (f) => value[f.k] !== undefined && value[f.k] !== DEFAULT_PARAMS[f.k],
  );
  return (
    <div className="border-t border-hair pt-4">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between text-[14px]"
      >
        <span>
          Advanced thresholds{' '}
          {changed && <span className="ml-2 font-mono text-[11px] text-soft">(edited)</span>}
        </span>
        <span className="font-mono text-[12px] text-soft">{open ? 'hide' : 'show'}</span>
      </button>
      {open && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {FIELDS.map((f) => (
            <Field key={f.k} label={f.label} hint={f.hint}>
              <Input
                type="number"
                step={f.step}
                min={f.min}
                max={f.max}
                value={value[f.k] ?? DEFAULT_PARAMS[f.k]}
                onChange={(e) => onChange({ ...value, [f.k]: Number(e.target.value) })}
              />
            </Field>
          ))}
          <button
            type="button"
            onClick={() => onChange({})}
            className="text-left text-[12px] text-soft underline underline-offset-4"
          >
            Reset to defaults
          </button>
        </div>
      )}
    </div>
  );
}

import { Suspense, lazy } from 'react';
import type { MapViewProps } from './MapViewImpl';

export type { MapViewProps } from './MapViewImpl';

// MapLibre is ~1 MB of JS; load it only when a page actually shows a map so the login,
// dashboard and list pages start fast (design §14 performance budget).
const Impl = lazy(() => import('./MapViewImpl').then((m) => ({ default: m.MapView })));

export function MapView(props: MapViewProps) {
  return (
    <Suspense
      fallback={
        <div
          className={`relative ${props.className ?? 'h-full'}`}
          role="status"
          aria-label="Loading map"
          style={{ background: 'var(--surface-1)' }}
        />
      }
    >
      <Impl {...props} />
    </Suspense>
  );
}

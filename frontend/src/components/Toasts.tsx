import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { ToastContext, type Toast, type ToastKind } from './toastContext';

/** Bottom-centre toasts (04-design §6): auto-dismiss 5 s, errors stay until closed. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, kind: ToastKind = 'ok') => {
    const id = Date.now() + Math.random();
    setItems((s) => [...s, { id, kind, text }]);
    if (kind !== 'error') setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), 5000);
  }, []);
  const api = useMemo(() => ({ push }), [push]);
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-5 z-50 flex flex-col items-center gap-2 px-4">
        {items.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            className="pointer-events-auto flex max-w-lg items-center gap-3 rounded-ctl border border-hair bg-panel px-4 py-2.5 text-[14px] backdrop-blur-xl"
          >
            <span aria-hidden className={t.kind === 'error' ? 'text-high' : 'text-ok'}>
              {t.kind === 'error' ? '!' : t.kind === 'info' ? 'i' : '✓'}
            </span>
            <span>{t.text}</span>
            {t.kind === 'error' && (
              <button
                onClick={() => setItems((s) => s.filter((x) => x.id !== t.id))}
                className="ml-2 text-soft hover:text-cream"
                aria-label="Dismiss"
              >
                ×
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

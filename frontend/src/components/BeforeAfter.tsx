import { useEffect, useRef, useState } from 'react';
import { fetchBlobUrl } from '@/api/detections';

/** Before/after slider per 04-design §6: draggable handle, keyboard ←/→ (Shift = 20 %). */
export function BeforeAfter({
  before,
  after,
  beforeLabel,
  afterLabel,
}: {
  before: string;
  after: string;
  beforeLabel: string;
  afterLabel: string;
}) {
  const [pos, setPos] = useState(50);
  const [srcs, setSrcs] = useState<{ b: string; a: string } | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);
  const dragging = useRef(false);

  useEffect(() => {
    let alive = true;
    let urls: string[] = [];
    Promise.all([fetchBlobUrl(before), fetchBlobUrl(after)])
      .then(([b, a]) => {
        urls = [b, a];
        if (alive) setSrcs({ b, a });
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      urls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [before, after]);

  const move = (clientX: number) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    setPos(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)));
  };
  return (
    <div
      ref={ref}
      className="relative aspect-square w-full select-none overflow-hidden rounded-card border border-hair bg-s1"
      onPointerDown={(e) => {
        dragging.current = true;
        (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
        move(e.clientX);
      }}
      onPointerMove={(e) => dragging.current && move(e.clientX)}
      onPointerUp={() => (dragging.current = false)}
      onPointerCancel={() => (dragging.current = false)}
    >
      {srcs ? (
        <>
          <img
            src={srcs.a}
            alt={afterLabel}
            className="absolute inset-0 h-full w-full object-cover"
            draggable={false}
          />
          <img
            src={srcs.b}
            alt={beforeLabel}
            className="absolute inset-0 h-full w-full object-cover"
            style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}
            draggable={false}
          />
        </>
      ) : (
        <div className="absolute inset-0 animate-pulse bg-s2" />
      )}
      <div
        className="pointer-events-none absolute inset-y-0 w-px bg-cream"
        style={{ left: `${pos}%` }}
      />
      <button
        role="slider"
        aria-label="Compare before and after"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pos)}
        onKeyDown={(e) => {
          const step = e.shiftKey ? 20 : 5;
          if (e.key === 'ArrowLeft') setPos((p) => Math.max(0, p - step));
          if (e.key === 'ArrowRight') setPos((p) => Math.min(100, p + step));
        }}
        className="absolute top-1/2 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-hair bg-panel font-mono text-[12px] backdrop-blur-xl"
        style={{ left: `${pos}%` }}
      >
        ⇔
      </button>
      <span className="absolute left-2 top-2 max-w-[45%] truncate rounded-full border border-hair bg-panel px-2 py-px font-mono text-[10px] uppercase tracking-[0.1em] backdrop-blur-xl">
        before · {beforeLabel}
      </span>
      <span className="absolute bottom-2 right-2 max-w-[45%] truncate rounded-full border border-hair bg-panel px-2 py-px font-mono text-[10px] uppercase tracking-[0.1em] backdrop-blur-xl">
        after · {afterLabel}
      </span>
    </div>
  );
}

import { useEffect, useState } from 'react';

import { fetchBlobUrl } from '@/api/detections';

/** Protected evidence image: fetched with the session token, shown from a blob URL. */
export function EvidenceImg({
  url,
  alt,
  className,
}: {
  url: string;
  alt: string;
  className?: string;
}) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    let obj: string | null = null;
    fetchBlobUrl(url)
      .then((u) => {
        obj = u;
        if (alive) setSrc(u);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      if (obj) URL.revokeObjectURL(obj);
    };
  }, [url]);
  return src ? (
    <img
      src={src}
      alt={alt}
      className={`shrink-0 rounded-ctl border border-hair ${className ?? ''}`}
    />
  ) : (
    <div className={`aspect-square shrink-0 animate-pulse rounded-ctl bg-s2 ${className ?? ''}`} />
  );
}

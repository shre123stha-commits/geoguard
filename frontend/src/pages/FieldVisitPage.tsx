import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Camera, Check, MapPin, Navigation, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import {
  getDetection,
  REASON_LABELS,
  setDetectionStatus,
  uploadFieldPhoto,
  type ReasonCode,
} from '@/api/detections';
import { EvidenceImg } from '@/components/EvidenceImg';
import { Button, Chip, ErrorState, Select, Skeleton, Textarea } from '@/components/ui';
import { useToast } from '@/components/useToast';

const REASONS = Object.keys(REASON_LABELS) as ReasonCode[];

function distanceM(a: [number, number], b: [number, number]): number {
  const R = 6371000;
  const p1 = (a[1] * Math.PI) / 180;
  const p2 = (b[1] * Math.PI) / 180;
  const dphi = p2 - p1;
  const dl = ((b[0] - a[0]) * Math.PI) / 180;
  const h = Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/** Phone-first field page (Phase 9.4): one column, big buttons, camera capture, GPS distance
 * to the flagged site, confirm/dismiss on the spot. Desktop users get the same page narrow. */
export function FieldVisitPage() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ['detection', id], queryFn: () => getDetection(id) });
  const [pos, setPos] = useState<{ lon: number; lat: number; acc: number } | null>(null);
  const [posErr, setPosErr] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [reason, setReason] = useState<ReasonCode>('existing_structure');
  const [decide, setDecide] = useState<null | 'confirmed' | 'dismissed'>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!('geolocation' in navigator)) {
      const t = setTimeout(() => setPosErr('This device has no location service.'), 0);
      return () => clearTimeout(t);
    }
    const w = navigator.geolocation.watchPosition(
      (p) => setPos({ lon: p.coords.longitude, lat: p.coords.latitude, acc: p.coords.accuracy }),
      (e) => setPosErr(e.message),
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 },
    );
    return () => navigator.geolocation.clearWatch(w);
  }, []);

  const upload = useMutation({
    mutationFn: (f: File) =>
      uploadFieldPhoto(id, f, pos ? { lon: pos.lon, lat: pos.lat } : null, note),
    onSuccess: (d) => {
      qc.setQueryData(['detection', id], d);
      setNote('');
      toast('Photo attached.');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const status = useMutation({
    mutationFn: (s: 'confirmed' | 'dismissed') =>
      setDetectionStatus(id, s, note, s === 'dismissed' ? reason : undefined),
    onSuccess: (d) => {
      qc.setQueryData(['detection', id], d);
      void qc.invalidateQueries({ queryKey: ['detections'] });
      setDecide(null);
      setNote('');
      toast(d.properties.status === 'confirmed' ? 'Confirmed.' : 'Dismissed.');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });

  if (q.isPending) return <Skeleton rows={6} />;
  if (q.isError || !q.data) return <ErrorState error={q.error} />;
  const d = q.data;
  const p = d.properties;
  const target: [number, number] = [p.centroid[0], p.centroid[1]];
  const dist = pos ? distanceM([pos.lon, pos.lat], target) : null;
  const photos = d.evidence.filter((e) => e.kind === 'field_photo');
  const after = d.evidence.find((e) => e.kind === 'after_rgb');
  const can = (s: 'confirmed' | 'dismissed') => d.allowed_transitions.includes(s);
  const mapsHref = `https://www.openstreetmap.org/?mlat=${target[1]}&mlon=${target[0]}#map=18/${target[1]}/${target[0]}`;

  return (
    <div className="mx-auto max-w-[520px] space-y-4 pb-24">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-wider text-soft">Field visit</p>
        <h1 className="text-[24px] font-semibold leading-tight">{d.parcel.name}</h1>
        <p className="text-[14px] text-soft">
          {Math.round(p.area_m2).toLocaleString()} m² · {p.confidence} confidence ·{' '}
          {p.status.replace('_', ' ')}
        </p>
      </div>

      <section className="rounded-card border border-hair bg-s1 p-4">
        <div className="flex items-center gap-2">
          <Navigation className="size-4 text-soft" aria-hidden />
          <span className="text-[14px]">
            {dist != null ? (
              <>
                <span className="font-mono text-[18px] tabular-nums">
                  {dist < 1000 ? `${Math.round(dist)} m` : `${(dist / 1000).toFixed(1)} km`}
                </span>{' '}
                to the flagged area
                {pos && pos.acc > 50 && (
                  <span className="text-soft"> (±{Math.round(pos.acc)} m)</span>
                )}
              </>
            ) : posErr ? (
              <span className="text-soft">Location unavailable: {posErr}</span>
            ) : (
              <span className="text-soft">Finding your location…</span>
            )}
          </span>
        </div>
        <p className="mt-2 font-mono text-[12px] text-soft">
          site {target[1].toFixed(5)}, {target[0].toFixed(5)}
        </p>
        <a
          href={mapsHref}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-flex items-center gap-1 text-[14px] underline underline-offset-4"
        >
          <MapPin className="size-4" aria-hidden /> open in map app
        </a>
      </section>

      {after && (
        <section>
          <p className="mb-2 font-mono text-[11px] uppercase tracking-wider text-soft">
            Satellite view (current window)
          </p>
          <EvidenceImg url={after.url} alt="Current satellite view" className="w-full" />
        </section>
      )}

      <section className="space-y-3">
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="sr-only"
          aria-label="Take a photo"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload.mutate(f);
            e.target.value = '';
          }}
        />
        <Button
          variant="primary"
          icon={Camera}
          busy={upload.isPending}
          className="w-full py-4 text-[16px]"
          onClick={() => fileRef.current?.click()}
        >
          Take a photo
        </Button>
        {photos.length > 0 && (
          <ul className="grid grid-cols-2 gap-2">
            {photos.map((ph) => (
              <li key={ph.url} className="space-y-1">
                <EvidenceImg url={ph.url} alt="Field photo" className="w-full" />
                <p className="font-mono text-[11px] text-soft">
                  {ph.meta.distance_m != null ? `${ph.meta.distance_m} m from site` : 'no position'}
                  {ph.meta.note ? ` · ${ph.meta.note}` : ''}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <Textarea
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What do you see? (saved with the next photo or decision)"
          maxLength={500}
        />
        {decide === 'dismissed' && (
          <Select value={reason} onChange={(e) => setReason(e.target.value as ReasonCode)}>
            {REASONS.map((r) => (
              <option key={r} value={r}>
                {REASON_LABELS[r]}
              </option>
            ))}
          </Select>
        )}
        {decide ? (
          <div className="grid grid-cols-2 gap-2">
            <Button className="py-4" onClick={() => setDecide(null)}>
              Back
            </Button>
            <Button
              variant={decide === 'confirmed' ? 'primary' : 'danger'}
              className="py-4"
              busy={status.isPending}
              disabled={decide === 'dismissed' && reason === 'other' && !note.trim()}
              onClick={() => status.mutate(decide)}
            >
              {decide === 'confirmed' ? 'Yes, confirm' : 'Yes, dismiss'}
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            <Button
              variant="primary"
              icon={Check}
              className="py-4"
              disabled={!can('confirmed')}
              onClick={() => setDecide('confirmed')}
            >
              Confirm change
            </Button>
            <Button
              variant="danger"
              icon={X}
              className="py-4"
              disabled={!can('dismissed')}
              onClick={() => setDecide('dismissed')}
            >
              Dismiss
            </Button>
          </div>
        )}
        {!can('confirmed') && !can('dismissed') && (
          <Chip>already {p.status.replace('_', ' ')}</Chip>
        )}
      </section>

      <p className="text-[12px] text-soft">{d.disclaimer}</p>
      <Link to={`/detections/${id}`} className="block text-[14px] underline underline-offset-4">
        Full detection page
      </Link>
    </div>
  );
}

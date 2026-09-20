import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { listParcels } from '@/api/parcels';
import { useAuth } from '@/app/useAuth';
import { MapView } from '@/components/MapView';
import {
  EmptyState,
  ErrorState,
  Input,
  LinkButton,
  PageHeader,
  Skeleton,
  Table,
} from '@/components/ui';
import { rowCls } from '@/lib/styles';
import { fmtArea, fmtDate } from '@/lib/format';
import { bboxOf } from '@/lib/geo';

export function ParcelsPage() {
  const { user } = useAuth();
  const admin = user?.role === 'admin';
  const nav = useNavigate();
  const [q, setQ] = useState('');
  const parcels = useQuery({ queryKey: ['parcels', q], queryFn: () => listParcels(q) });
  const [hover, setHover] = useState<string | null>(null);
  const bbox = useMemo(
    () => bboxOf((parcels.data?.features ?? []).map((f) => f.geometry)),
    [parcels.data],
  );
  const total = parcels.data?.features.reduce((a, f) => a + f.properties.area_m2, 0) ?? 0;

  return (
    <>
      <PageHeader
        eyebrow="Parcels"
        title="Protected land"
        lead={
          parcels.data
            ? `${parcels.data.total} parcel${parcels.data.total === 1 ? '' : 's'} · ${fmtArea(total)} under watch`
            : 'The areas GeoGuard watches for change.'
        }
        action={
          admin && (
            <LinkButton to="/parcels/new" variant="primary" icon={Plus}>
              Add parcels
            </LinkButton>
          )
        }
      />
      {parcels.isPending ? (
        <Skeleton rows={6} />
      ) : parcels.isError ? (
        <ErrorState error={parcels.error} onRetry={() => void parcels.refetch()} />
      ) : parcels.data.total === 0 && !q ? (
        <EmptyState
          eyebrow="No parcels yet"
          title="Add the land you want to watch"
          text={
            admin
              ? 'Upload a GeoJSON file of your protected areas, or draw a boundary directly on the map.'
              : 'An administrator needs to add parcels before scans can run.'
          }
          action={
            admin && (
              <div className="flex gap-2">
                <LinkButton to="/parcels/new?tab=upload" variant="primary">
                  Upload GeoJSON
                </LinkButton>
                <LinkButton to="/parcels/new?tab=draw">Draw on map</LinkButton>
              </div>
            )
          }
        />
      ) : (
        <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="min-w-0">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by name or category"
              aria-label="Search parcels"
              className="mb-4"
            />
            <Table head={['Name', 'Category', 'Area', 'Source', 'Added']}>
              {parcels.data.features.map((f) => (
                <tr
                  key={f.id}
                  className={`${rowCls} cursor-pointer ${hover === f.id ? 'bg-s2' : ''}`}
                  onMouseEnter={() => setHover(f.id)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => nav(`/parcels/${f.id}`)}
                >
                  <td>
                    <Link to={`/parcels/${f.id}`} className="font-medium hover:underline">
                      {f.properties.name}
                    </Link>
                  </td>
                  <td className="text-soft">{f.properties.category}</td>
                  <td className="text-right font-mono text-[13px]">
                    {fmtArea(f.properties.area_m2)}
                  </td>
                  <td className="font-mono text-[12px] text-soft">{f.properties.source}</td>
                  <td className="font-mono text-[12px] text-soft">
                    {fmtDate(f.properties.created_at)}
                  </td>
                </tr>
              ))}
              {parcels.data.features.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-soft">
                    No parcels match “{q}”.
                  </td>
                </tr>
              )}
            </Table>
          </div>
          <div className="min-h-[420px] overflow-hidden rounded-card border border-hair">
            <MapView
              className="h-full min-h-[420px]"
              parcels={parcels.data}
              selectedParcels={hover ? [hover] : []}
              onParcelClick={(id) => nav(`/parcels/${id}`)}
              fitTo={bbox}
              fitKey={`parcels-${parcels.data.total}`}
            />
          </div>
        </div>
      )}
    </>
  );
}

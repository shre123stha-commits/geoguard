import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from '@/app/useAuth';
import { AppShell } from '@/components/AppShell';
import { ChangePasswordPage } from '@/pages/ChangePasswordPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { FieldVisitPage } from '@/pages/FieldVisitPage';
import { DetectionDetailPage } from '@/pages/DetectionDetailPage';
import { DetectionsPage } from '@/pages/DetectionsPage';
import { HealthPage } from '@/pages/HealthPage';
import { LoginPage } from '@/pages/LoginPage';
import { ParcelDetailPage } from '@/pages/ParcelDetailPage';
import { ParcelNewPage } from '@/pages/ParcelNewPage';
import { ParcelsPage } from '@/pages/ParcelsPage';
import { ScanDetailPage } from '@/pages/ScanDetailPage';
import { ScanNewPage } from '@/pages/ScanNewPage';
import { ScansPage } from '@/pages/ScansPage';
import { SchedulesPage } from '@/pages/SchedulesPage';
import { ReferenceLayersPage } from '@/pages/ReferenceLayersPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { UsersPage } from '@/pages/UsersPage';

/** Signed-in users only; users with a pending password change are sent to that screen. */
function RequireAuth() {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-base">
        <p className="font-mono text-[12px] uppercase tracking-[0.12em] text-soft">Loading…</p>
      </main>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
  if (user.must_change_password && loc.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }
  return <Outlet />;
}

/** Screen map per docs/03-appflow.md §2. */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/health" element={<HealthPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/change-password" element={<ChangePasswordPage />} />
        <Route element={<AppShell />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/parcels" element={<ParcelsPage />} />
          <Route path="/parcels/new" element={<ParcelNewPage />} />
          <Route path="/parcels/:id" element={<ParcelDetailPage />} />
          <Route path="/scans" element={<ScansPage />} />
          <Route path="/scans/new" element={<ScanNewPage />} />
          <Route path="/scans/:id" element={<ScanDetailPage />} />
          <Route path="/detections" element={<DetectionsPage />} />
          <Route path="/detections/:id" element={<DetectionDetailPage />} />
          <Route path="/detections/:id/field" element={<FieldVisitPage />} />
          <Route path="/schedules" element={<SchedulesPage />} />
          <Route path="/reference-layers" element={<ReferenceLayersPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          {/* the earlier single-screen review map now lives at /detections */}
          <Route path="/review" element={<Navigate to="/detections" replace />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

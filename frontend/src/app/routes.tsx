import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from '@/app/useAuth';
import { ChangePasswordPage } from '@/pages/ChangePasswordPage';
import { HealthPage } from '@/pages/HealthPage';
import { LoginPage } from '@/pages/LoginPage';
import { ReviewPage } from '@/pages/ReviewPage';

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
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (user.must_change_password && loc.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }
  return <Outlet />;
}

// The review map is still the landing screen; the full navigation (dashboard, parcels,
// scans, …) arrives in Phase 6 (docs/03-appflow.md §2).
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/health" element={<HealthPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<ReviewPage />} />
        <Route path="/change-password" element={<ChangePasswordPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

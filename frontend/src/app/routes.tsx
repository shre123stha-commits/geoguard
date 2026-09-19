import { Navigate, Route, Routes } from 'react-router-dom';
import { HealthPage } from '@/pages/HealthPage';

// Real screens (login, dashboard, parcels, …) arrive in Phase 6 (docs/03-appflow.md §2).
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/health" replace />} />
      <Route path="/health" element={<HealthPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

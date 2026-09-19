import { Navigate, Route, Routes } from 'react-router-dom';
import { HealthPage } from '@/pages/HealthPage';
import { ReviewPage } from '@/pages/ReviewPage';

// Phase-1 prototype: the review map is the landing screen. Full app flow (login,
// dashboard, parcels, …) arrives in Phase 6 (docs/03-appflow.md §2).
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<ReviewPage />} />
      <Route path="/health" element={<HealthPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

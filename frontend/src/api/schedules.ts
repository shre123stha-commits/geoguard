import { apiFetch } from './client';
import type { Page, ScanDetail, ScanParams } from './scans';

export interface BaselineRule {
  mode: 'same_season_previous_year' | 'years_back' | 'fixed';
  window_days?: number | null;
  years?: number | null;
  baseline_start?: string | null;
  baseline_end?: string | null;
}

export interface Schedule {
  id: string;
  name: string;
  is_active: boolean;
  cron: string;
  current_window_days: number;
  baseline_rule: BaselineRule;
  params: ScanParams;
  last_run_at: string | null;
  next_run_at: string | null;
  created_by: string | null;
  created_at: string;
  parcels: { id: string; name: string; category: string }[];
  last_scan_id: string | null;
  last_scan_status: string | null;
}

export interface ScheduleCreate {
  name: string;
  parcel_ids: string[];
  cron: string;
  current_window_days: number;
  baseline_rule: BaselineRule;
  params?: Partial<ScanParams>;
}

export type SchedulePatch = Partial<ScheduleCreate> & { is_active?: boolean };

export const listSchedules = () => apiFetch<Page<Schedule>>('schedules?page_size=100');
export const createSchedule = (body: ScheduleCreate) =>
  apiFetch<Schedule>('schedules', { method: 'POST', body: JSON.stringify(body) });
export const patchSchedule = (id: string, body: SchedulePatch) =>
  apiFetch<Schedule>(`schedules/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
export const runSchedule = (id: string) =>
  apiFetch<ScanDetail>(`schedules/${id}/run`, { method: 'POST' });
export const deleteSchedule = (id: string) =>
  apiFetch<void>(`schedules/${id}`, { method: 'DELETE' });

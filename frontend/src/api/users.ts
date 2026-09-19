import type { Role, User } from './auth';
import { apiFetch } from './client';
import type { Page } from './scans';

export const listUsers = () => apiFetch<Page<User>>('users?page_size=200');
export const createUser = (body: {
  email: string;
  full_name: string;
  password: string;
  role: Role;
}) => apiFetch<User>('users', { method: 'POST', body: JSON.stringify(body) });
export const patchUser = (
  id: string,
  body: { full_name?: string; role?: Role; is_active?: boolean; new_password?: string },
) => apiFetch<User>(`users/${id}`, { method: 'PATCH', body: JSON.stringify(body) });

import { apiFetch } from './client';

export type Role = 'admin' | 'officer';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: User;
}

export const login = (email: string, password: string) =>
  apiFetch<TokenResponse>('auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
export const me = () => apiFetch<User>('auth/me');
export const changePassword = (current_password: string, new_password: string) =>
  apiFetch<User>('auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password, new_password }),
  });

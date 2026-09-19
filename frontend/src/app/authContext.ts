import { createContext } from 'react';
import type { User } from '@/api/auth';

export interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
  refresh: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

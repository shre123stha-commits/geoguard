import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { onUnauthorized, tokenStore } from '@/api/client';
import { login as apiLogin, me, type User } from '@/api/auth';
import { AuthContext, type AuthState } from './authContext';

/** Restores the session from the stored token on first render, then tracks 401s. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ user: User | null; loading: boolean }>({
    user: null,
    loading: Boolean(tokenStore.get()),
  });

  const refresh = useCallback(async () => {
    let next: User | null = null;
    if (tokenStore.get()) {
      try {
        next = await me();
      } catch {
        tokenStore.clear();
      }
    }
    setState({ user: next, loading: false });
  }, []);

  useEffect(() => {
    // Only restore from a stored token; a login in the same tick already set the user.
    const timer = setTimeout(() => {
      if (tokenStore.get()) void refresh();
      else setState((s) => (s.loading ? { ...s, loading: false } : s));
    }, 0);
    const off = onUnauthorized(() => setState({ user: null, loading: false }));
    return () => {
      clearTimeout(timer);
      off();
    };
  }, [refresh]);

  const value = useMemo<AuthState>(
    () => ({
      user: state.user,
      loading: state.loading,
      login: async (email, password) => {
        const res = await apiLogin(email, password);
        tokenStore.set(res.access_token);
        setState({ user: res.user, loading: false });
        return res.user;
      },
      logout: () => {
        tokenStore.clear();
        setState({ user: null, loading: false });
      },
      refresh,
    }),
    [state, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

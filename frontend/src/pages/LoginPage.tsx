import { useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ApiRequestError } from '@/api/client';
import { useAuth } from '@/app/useAuth';

const field =
  'mt-1 w-full rounded-ctl border border-hair bg-s1 px-3 py-2.5 text-[15px] text-cream outline-none placeholder:text-dim focus:border-hair-strong';

export function LoginPage() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={user.must_change_password ? '/change-password' : '/'} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await login(email, password);
      nav(u.must_change_password ? '/change-password' : (loc.state?.from ?? '/'), {
        replace: true,
      });
    } catch (err) {
      setError(
        err instanceof ApiRequestError ? err.message : 'Could not reach the server. Try again.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-dvh items-center justify-center bg-base p-6">
      <form
        onSubmit={(e) => void submit(e)}
        className="rise w-full max-w-[400px] rounded-card border border-hair bg-s1 p-7"
      >
        <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-soft">Sign in</p>
        <h1 className="mt-1 font-display text-[32px] font-medium leading-none tracking-[-0.03em]">
          GeoGuard<sup className="ml-1 text-[0.4em] align-super">EO</sup>
        </h1>
        <p className="mt-3 text-[14px] text-soft">Watch protected land from above.</p>

        <label className="mt-6 block text-[13px] text-soft">
          Email
          <input
            className={field}
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="mt-4 block text-[13px] text-soft">
          Password
          <input
            className={field}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && (
          <p role="alert" className="mt-3 text-[13px] text-high">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="mt-6 w-full rounded-ctl border border-hair-strong bg-s3 py-2.5 text-[15px] font-medium text-cream hover:bg-glass disabled:opacity-50"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        <p className="mt-4 text-[12px] text-dim">
          Accounts are created by an administrator. Forgotten password? Ask an admin to reset it.
        </p>
      </form>
    </main>
  );
}

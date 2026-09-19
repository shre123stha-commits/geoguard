import { useState } from 'react';
import type { FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { changePassword } from '@/api/auth';
import { ApiRequestError } from '@/api/client';
import { useAuth } from '@/app/useAuth';

const MIN = 10;
const field =
  'mt-1 w-full rounded-ctl border border-hair bg-s1 px-3 py-2.5 text-[15px] text-cream outline-none placeholder:text-dim focus:border-hair-strong';

export function ChangePasswordPage() {
  const { user, refresh, logout } = useAuth();
  const nav = useNavigate();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!user) return <Navigate to="/login" replace />;
  const forced = user.must_change_password;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (next.length < MIN) return setError(`Use at least ${MIN} characters.`);
    if (next !== confirm) return setError('The two new passwords do not match.');
    setBusy(true);
    try {
      await changePassword(current, next);
      await refresh();
      nav('/', { replace: true });
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : 'Could not reach the server.');
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
        <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-soft">
          {forced ? 'First sign-in' : 'Account'}
        </p>
        <h1 className="mt-1 font-display text-[26px] font-medium leading-tight tracking-[-0.03em]">
          {forced ? 'Choose a new password' : 'Change password'}
        </h1>
        {forced && (
          <p className="mt-2 text-[14px] text-soft">
            Your temporary password must be replaced before you continue.
          </p>
        )}
        <label className="mt-6 block text-[13px] text-soft">
          Current password
          <input
            className={field}
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </label>
        <label className="mt-4 block text-[13px] text-soft">
          New password <span className="text-dim">(min {MIN} characters)</span>
          <input
            className={field}
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN}
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </label>
        <label className="mt-4 block text-[13px] text-soft">
          Repeat new password
          <input
            className={field}
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
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
          {busy ? 'Saving…' : 'Save password'}
        </button>
        <button
          type="button"
          onClick={() => {
            logout();
            nav('/login', { replace: true });
          }}
          className="mt-3 w-full py-2 text-[13px] text-soft hover:text-cream"
        >
          {forced ? 'Sign out instead' : 'Cancel'}
        </button>
      </form>
    </main>
  );
}

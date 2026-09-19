import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '@/app/auth';
import { LoginPage } from './LoginPage';

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<p>home</p>} />
          <Route path="/change-password" element={<p>change</p>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

describe('LoginPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it('shows the API error message on a failed login', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        json(
          {
            error: {
              code: 'unauthorized',
              message: 'Incorrect email or password',
              details: null,
            },
          },
          401,
        ),
      ),
    );
    renderLogin();
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'a@b.co' } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'wrong-pass-1' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password');
  });

  it('stores the token and redirects to the password screen when a change is required', async () => {
    const user = {
      id: '1',
      email: 'a@b.co',
      full_name: 'A',
      role: 'admin',
      is_active: true,
      must_change_password: true,
      created_at: '2026-01-01T00:00:00Z',
    };
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockImplementation((url: string) =>
          url.endsWith('/auth/me')
            ? json(user)
            : json({ access_token: 'tok', token_type: 'bearer', expires_in: 10, user }),
        ),
    );
    renderLogin();
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'a@b.co' } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'temporary-1' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
    await waitFor(() => expect(screen.getByText('change')).toBeInTheDocument());
    expect(sessionStorage.getItem('geoguard.token')).toBe('tok');
  });
});

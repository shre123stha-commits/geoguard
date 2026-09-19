import { Menu, X } from 'lucide-react';
import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '@/app/useAuth';

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/parcels', label: 'Parcels' },
  { to: '/scans', label: 'Scans' },
  { to: '/detections', label: 'Detections' },
  { to: '/schedules', label: 'Schedules', admin: true },
  { to: '/users', label: 'Users', admin: true },
  { to: '/settings', label: 'Settings', admin: true },
];

/** Top bar + content area (04-design §6 "Top bar", §8 "App shell"). */
export function AppShell() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const links = NAV.filter((n) => !n.admin || user?.role === 'admin');
  const linkCls = ({ isActive }: { isActive: boolean }) =>
    `border-b pb-0.5 text-[14px] transition ${isActive ? 'border-cream text-cream' : 'border-transparent text-soft hover:text-cream'}`;
  return (
    <div className="min-h-dvh bg-base">
      <header className="sticky top-0 z-40 h-16 border-b border-hair bg-base/90 backdrop-blur-xl">
        <div className="mx-auto flex h-full max-w-[1400px] items-center gap-8 px-4 md:px-8">
          <NavLink
            to="/"
            className="font-display text-[22px] font-medium leading-none tracking-[-0.04em]"
          >
            GeoGuard<sup className="ml-0.5 text-[0.45em] align-super">EO</sup>
          </NavLink>
          <nav className="hidden items-center gap-6 md:flex" aria-label="Main">
            {links.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className={linkCls}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto hidden items-center gap-3 md:flex">
            {user && (
              <>
                <span className="text-[13px] text-soft" title={user.email}>
                  {user.full_name}
                </span>
                <span className="rounded-full border border-hair px-2 py-px font-mono text-[10px] uppercase tracking-[0.08em] text-soft">
                  {user.role}
                </span>
                <button
                  onClick={() => nav('/change-password')}
                  className="font-mono text-[11px] text-soft hover:text-cream"
                >
                  password
                </button>
                <button
                  onClick={logout}
                  className="font-mono text-[11px] text-soft hover:text-cream"
                >
                  sign out
                </button>
              </>
            )}
          </div>
          <button
            className="ml-auto rounded-full border border-hair p-2 md:hidden"
            onClick={() => setOpen((o) => !o)}
            aria-label="Menu"
            aria-expanded={open}
          >
            {open ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
        {open && (
          <nav
            className="border-t border-hair bg-base px-4 py-3 md:hidden"
            aria-label="Main"
            onClick={() => setOpen(false)}
          >
            {links.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className="block py-2 text-[16px]">
                {n.label}
              </NavLink>
            ))}
            <div className="mt-2 flex gap-4 border-t border-hair pt-3 font-mono text-[12px] text-soft">
              <span>{user?.full_name}</span>
              <button onClick={() => nav('/change-password')}>password</button>
              <button onClick={logout}>sign out</button>
            </div>
          </nav>
        )}
      </header>
      <main className="mx-auto max-w-[1400px] px-4 py-8 md:px-8">
        <Outlet />
      </main>
    </div>
  );
}

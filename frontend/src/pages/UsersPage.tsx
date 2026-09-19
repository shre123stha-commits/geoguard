import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import type { Role, User } from '@/api/auth';
import { createUser, listUsers, patchUser } from '@/api/users';
import { useAuth } from '@/app/useAuth';
import { Modal } from '@/components/Modal';
import {
  Button,
  Chip,
  ErrorState,
  Field,
  Input,
  PageHeader,
  Select,
  Skeleton,
  Table,
} from '@/components/ui';
import { rowCls } from '@/lib/styles';
import { useToast } from '@/components/useToast';
import { fmtDate } from '@/lib/format';

const MIN = 10;

/** User management (appflow Flow I). Admin only. */
export function UsersPage() {
  const { user: me } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const users = useQuery({
    queryKey: ['users'],
    queryFn: listUsers,
    enabled: me?.role === 'admin',
  });
  const [creating, setCreating] = useState(false);
  const [reset, setReset] = useState<User | null>(null);
  const [form, setForm] = useState({
    email: '',
    full_name: '',
    password: '',
    role: 'officer' as Role,
  });
  const [pw, setPw] = useState('');
  const invalidate = () => void qc.invalidateQueries({ queryKey: ['users'] });

  const create = useMutation({
    mutationFn: () => createUser(form),
    onSuccess: () => {
      invalidate();
      setCreating(false);
      setForm({ email: '', full_name: '', password: '', role: 'officer' });
      toast('User created. They must change the temporary password at first sign-in.');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });
  const patch = useMutation({
    mutationFn: (v: { id: string; body: Parameters<typeof patchUser>[1] }) =>
      patchUser(v.id, v.body),
    onSuccess: () => {
      invalidate();
      setReset(null);
      setPw('');
      toast('Saved.');
    },
    onError: (e: Error) => toast(e.message, 'error'),
  });

  if (me?.role !== 'admin') return <Navigate to="/" replace />;
  const admins = users.data?.items.filter((u) => u.role === 'admin' && u.is_active).length ?? 0;

  return (
    <>
      <PageHeader
        eyebrow="Users"
        title="Who can sign in"
        lead="Administrators manage parcels, scans and settings. Officers review detections."
        action={
          <Button variant="primary" icon={Plus} onClick={() => setCreating(true)}>
            Add user
          </Button>
        }
      />
      {users.isPending ? (
        <Skeleton rows={4} />
      ) : users.isError ? (
        <ErrorState error={users.error} onRetry={() => void users.refetch()} />
      ) : (
        <Table head={['Name', 'Email', 'Role', 'State', 'Added', '']}>
          {users.data.items.map((u) => {
            const lastAdmin = u.role === 'admin' && u.is_active && admins <= 1;
            const self = u.id === me.id;
            return (
              <tr key={u.id} className={rowCls}>
                <td className="font-medium">
                  {u.full_name}
                  {self && <span className="ml-2 font-mono text-[11px] text-soft">you</span>}
                </td>
                <td className="text-soft">{u.email}</td>
                <td>
                  <Select
                    value={u.role}
                    disabled={lastAdmin || self}
                    onChange={(e) =>
                      patch.mutate({ id: u.id, body: { role: e.target.value as Role } })
                    }
                    className="h-9 w-auto text-[13px]"
                    aria-label={`Role of ${u.full_name}`}
                    title={
                      lastAdmin ? 'The last active administrator cannot be demoted' : undefined
                    }
                  >
                    <option value="admin">admin</option>
                    <option value="officer">officer</option>
                  </Select>
                </td>
                <td>
                  <Chip tone={u.is_active ? 'ok' : 'neutral'}>
                    {u.is_active ? 'active' : 'inactive'}
                  </Chip>
                  {u.must_change_password && <Chip className="ml-1">temp password</Chip>}
                </td>
                <td className="font-mono text-[12px] text-soft">{fmtDate(u.created_at)}</td>
                <td className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button size="sm" onClick={() => setReset(u)}>
                      Reset password
                    </Button>
                    <Button
                      size="sm"
                      variant={u.is_active ? 'danger' : 'secondary'}
                      disabled={lastAdmin || self}
                      title={
                        lastAdmin
                          ? 'The last active administrator cannot be deactivated'
                          : undefined
                      }
                      onClick={() => patch.mutate({ id: u.id, body: { is_active: !u.is_active } })}
                    >
                      {u.is_active ? 'Deactivate' : 'Reactivate'}
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </Table>
      )}

      <Modal
        open={creating}
        title="Add user"
        onClose={() => setCreating(false)}
        footer={
          <Button
            variant="primary"
            busy={create.isPending}
            disabled={!form.email || !form.full_name || form.password.length < MIN}
            onClick={() => create.mutate()}
          >
            Create
          </Button>
        }
      >
        <div className="space-y-3">
          <Field label="Full name">
            <Input
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
          </Field>
          <Field label="Email">
            <Input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </Field>
          <Field label="Role">
            <Select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
            >
              <option value="officer">officer — review detections</option>
              <option value="admin">admin — everything</option>
            </Select>
          </Field>
          <Field
            label="Temporary password"
            hint={`At least ${MIN} characters; they must change it at first sign-in.`}
          >
            <Input
              type="text"
              autoComplete="off"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              className="font-mono"
            />
          </Field>
        </div>
      </Modal>
      <Modal
        open={reset !== null}
        title={`Reset password for ${reset?.full_name ?? ''}`}
        onClose={() => setReset(null)}
        footer={
          <Button
            variant="primary"
            busy={patch.isPending}
            disabled={pw.length < MIN}
            onClick={() => reset && patch.mutate({ id: reset.id, body: { new_password: pw } })}
          >
            Set password
          </Button>
        }
      >
        <Field
          label="New temporary password"
          hint={`At least ${MIN} characters. Hand it over securely; the user must change it at next sign-in.`}
        >
          <Input
            type="text"
            autoComplete="off"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            className="font-mono"
          />
        </Field>
      </Modal>
    </>
  );
}

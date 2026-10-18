import { useEffect, useState } from 'react';
import { RefreshCw, UserPlus } from 'lucide-react';
import { useAuth } from '../auth';
import { apiRequest } from '../api';
import { Button, Card, DataTable, ErrorState, LoadingState, PageHeader, StatusBadge } from '../components/ui';

const roles = ['VIEWER', 'ANALYST', 'OPERATIONS_OFFICER', 'BANK_MANAGER', 'SUPER_ADMIN'];
const usernamePattern = /^[A-Za-z0-9_.@-]{3,128}$/;

function formatDate(value) {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleString();
}

function requestMessage(error, action) {
  const code = error?.message;
  if (code === 'API_403') return 'Your account does not have permission to manage users.';
  if (code === 'API_409') return 'That username already exists. Choose another username.';
  if (code === 'API_422') return `The user could not be ${action}. Check the submitted fields.`;
  if (code === 'NETWORK_ERROR') return 'The service could not be reached. Check the connection and try again.';
  return `The user ${action} could not be completed. Please try again.`;
}

export default function UserManagementPage() {
  const { user } = useAuth();
  const canManage = user?.role === 'SUPER_ADMIN';
  const [users, setUsers] = useState({ loading: true, data: null, error: null });
  const [form, setForm] = useState({ username: '', password: '', role: 'VIEWER' });
  const [formError, setFormError] = useState('');
  const [success, setSuccess] = useState('');
  const [saving, setSaving] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!canManage) {
      setUsers({ loading: false, data: null, error: null });
      return undefined;
    }
    const controller = new AbortController();
    setUsers((current) => ({ ...current, loading: true, error: null }));
    apiRequest('/auth/users', { signal: controller.signal })
      .then((data) => setUsers({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setUsers({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, [canManage, reloadKey]);

  function updateField(event) {
    setForm((current) => ({ ...current, [event.target.name]: event.target.value }));
    setFormError('');
    setSuccess('');
  }

  async function createUser(event) {
    event.preventDefault();
    const username = form.username.trim();
    if (!usernamePattern.test(username)) {
      setFormError('Username must be 3-128 characters and use only letters, numbers, ., _, @, or -.');
      return;
    }
    if (form.password.length < 12 || form.password.length > 72) {
      setFormError('Password must be between 12 and 72 characters.');
      return;
    }
    setSaving(true);
    setFormError('');
    setSuccess('');
    try {
      await apiRequest('/auth/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Action-Source': 'WEB' },
        body: JSON.stringify({ username, password: form.password, role: form.role }),
      });
      setForm({ username: '', password: '', role: 'VIEWER' });
      setSuccess(`User ${username} was created. Share the credentials securely with the new user.`);
      setReloadKey((current) => current + 1);
    } catch (error) {
      setFormError(requestMessage(error, 'created'));
    } finally {
      setSaving(false);
    }
  }

  if (!canManage) {
    return (
      <main className="user-management-page">
        <PageHeader eyebrow="Administration" title="User Management" description="Manage authenticated workspace accounts." breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'User Management' }]} />
        <ErrorState title="User management access is restricted" description="Only SUPER_ADMIN accounts can manage workspace users." />
      </main>
    );
  }

  return (
    <main className="user-management-page">
      <PageHeader
        eyebrow="Administration"
        title="User Management"
        description="Create and review workspace accounts without exposing stored credentials."
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'User Management' }]}
        actions={<Button variant="secondary" onClick={() => setReloadKey((current) => current + 1)} disabled={users.loading}><RefreshCw size={15} />Refresh</Button>}
      />
      <div className="user-management-layout">
        <Card title="Create User" className="user-management-create-card">
          <form className="user-management-form" onSubmit={createUser}>
            <p className="user-management-form__intro">Assign one of the existing roles. The password is used only for creation and is never displayed afterward.</p>
            <label htmlFor="user-username">Username</label>
            <input id="user-username" name="username" value={form.username} onChange={updateField} autoComplete="off" required maxLength={128} />
            <label htmlFor="user-password">Initial password</label>
            <input id="user-password" name="password" type="password" value={form.password} onChange={updateField} autoComplete="new-password" required minLength={12} maxLength={72} />
            <label htmlFor="user-role">Role</label>
            <select id="user-role" name="role" value={form.role} onChange={updateField}>
              {roles.map((role) => <option key={role} value={role}>{role}</option>)}
            </select>
            {formError && <p className="user-management-feedback user-management-feedback--error" role="alert">{formError}</p>}
            {success && <p className="user-management-feedback user-management-feedback--success" role="status">{success}</p>}
            <Button type="submit" disabled={saving}><UserPlus size={16} />{saving ? 'Creating user...' : 'Create user'}</Button>
          </form>
        </Card>
        <Card title="Workspace Users" className="user-management-list-card">
          {users.loading ? <LoadingState label="Loading users" /> : users.error ? <ErrorState title="User list unavailable" description={requestMessage(users.error, 'listed')} action={<Button variant="secondary" onClick={() => setReloadKey((current) => current + 1)}>Retry</Button>} /> : (
            <DataTable
              rowKey="user_id"
              rows={users.data || []}
              emptyMessage="No workspace users found."
              columns={[
                { key: 'username', label: 'Username' },
                { key: 'role', label: 'Role' },
                { key: 'is_active', label: 'Status', render: (row) => <StatusBadge status={row.is_active ? 'Active' : 'Inactive'} /> },
                { key: 'created_at', label: 'Created', render: (row) => formatDate(row.created_at) },
                { key: 'last_login_at', label: 'Last login', render: (row) => formatDate(row.last_login_at) },
              ]}
            />
          )}
        </Card>
      </div>
    </main>
  );
}

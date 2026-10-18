import { useState } from 'react';
import { LogOut } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth';
import { Button, Card, PageHeader, StatusBadge } from '../components/ui';

function formatDate(value) {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleString();
}

export default function ProfilePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [loggingOut, setLoggingOut] = useState(false);

  async function handleLogout() {
    if (loggingOut) return;
    setLoggingOut(true);
    await logout();
    navigate('/login', { replace: true });
  }

  return (
    <main className="profile-page">
      <PageHeader
        eyebrow="Account"
        title="Profile"
        description="Your authenticated account details and session security."
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Profile' }]}
      />
      <Card title="Account Information" className="profile-card">
        <dl className="profile-fields">
          <div><dt>Name</dt><dd>{user?.name || 'Not provided'}</dd></div>
          <div><dt>Username</dt><dd>{user?.username || '—'}</dd></div>
          <div><dt>Role</dt><dd>{user?.role || '—'}</dd></div>
          <div><dt>Account Status</dt><dd><StatusBadge status={user?.is_active ? 'Active' : 'Inactive'} /></dd></div>
          <div><dt>Last Login</dt><dd>{formatDate(user?.last_login_at)}</dd></div>
        </dl>
      </Card>
      <Card title="Security" className="profile-security-card">
        <div className="profile-logout-row">
          <p>End your authenticated session on this device.</p>
          <Button variant="secondary" disabled={loggingOut} onClick={handleLogout}>
            <LogOut size={16} />{loggingOut ? 'Signing out' : 'Logout'}
          </Button>
        </div>
      </Card>
    </main>
  );
}
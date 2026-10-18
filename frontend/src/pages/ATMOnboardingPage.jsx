import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiRequest } from '../api';
import { Button, Card, ErrorState, PageHeader } from '../components/ui';

const initialForm = { atm_code: '', location: '', branch_id: '', region: '', capacity: '', status: 'PENDING', activation_date: '' };

export default function ATMOnboardingPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  function update(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setError('');
    setSaving(true);
    try {
      const record = await apiRequest('/atms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Action-Source': 'WEB' },
        body: JSON.stringify({ ...form, capacity: Number(form.capacity), activation_date: form.activation_date || null }),
      });
      navigate(`/atms/${encodeURIComponent(record.atm_code)}`);
    } catch (requestError) {
      setError(requestError.message === 'API_409' ? 'An ATM with this ID already exists.' : 'The ATM could not be created. Check the fields and try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="atm-detail-page">
      <PageHeader eyebrow="Network operations" title="Add ATM" description="Register an ATM without inventing operational metadata that was not supplied." breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'ATMs', to: '/atms' }, { label: 'Add ATM' }]} />
      <Card title="ATM onboarding" className="atm-detail-card">
        {error && <ErrorState title="Unable to create ATM" description={error} />}
        <form className="replenishment-form" onSubmit={submit}>
          <label>ATM ID<input required value={form.atm_code} onChange={(event) => update('atm_code', event.target.value)} placeholder="ATM-021" /></label>
          <label>Location<input value={form.location} onChange={(event) => update('location', event.target.value)} placeholder="Optional location" /></label>
          <label>Branch<input required value={form.branch_id} onChange={(event) => update('branch_id', event.target.value)} /></label>
          <label>Region<input required value={form.region} onChange={(event) => update('region', event.target.value)} /></label>
          <label>Capacity<input required min="0" step="0.01" type="number" value={form.capacity} onChange={(event) => update('capacity', event.target.value)} /></label>
          <label>Status<select value={form.status} onChange={(event) => update('status', event.target.value)}><option>PENDING</option><option>ACTIVE</option><option>INACTIVE</option><option>RETIRED</option></select></label>
          <label>Installed / activation date<input type="date" value={form.activation_date} onChange={(event) => update('activation_date', event.target.value)} /></label>
          <div className="dialog-actions"><Button variant="secondary" onClick={() => navigate('/atms')}>Cancel</Button><Button type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create ATM'}</Button></div>
        </form>
      </Card>
    </main>
  );
}

import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiRequest, API_URL } from '../api';
import { getStoredToken, useAuth } from '../auth';
import { Button, Card, DataTable, EmptyState, ErrorState, LoadingState, PageHeader, StatusBadge } from '../components/ui';

export default function DataImportPage() {
  const { user } = useAuth();
  const { versionId } = useParams();
  const [file, setFile] = useState(null);
  const [current, setCurrent] = useState(null);
  const [imports, setImports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const canApprove = ['SUPER_ADMIN', 'BANK_MANAGER'].includes(user?.role);

  async function load() {
    setLoading(true);
    try {
      if (versionId) setCurrent(await apiRequest(`/data-imports/${versionId}`));
      else setImports(await apiRequest('/data-imports'));
    } catch (requestError) { setError(requestError.message); } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, [versionId]);

  async function upload(event) {
    event.preventDefault();
    if (!file) return;
    setBusy(true); setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      const response = await fetch(`${API_URL}/data-imports/validate`, { method: 'POST', headers: { Authorization: `Bearer ${getStoredToken()}`, 'X-Action-Source': 'WEB' }, body: form });
      if (!response.ok) throw new Error(`API_${response.status}`);
      setCurrent(await response.json());
      await load();
    } catch (requestError) { setError(requestError.message === 'API_415' ? 'Only CSV files are supported.' : 'The upload could not be validated.'); } finally { setBusy(false); }
  }

  async function transition(action) {
    if (!current) return;
    setBusy(true); setError('');
    try { setCurrent(await apiRequest(`/data-imports/${current.dataset_version_id}/${action}`, { method: 'POST', headers: { 'X-Action-Source': 'WEB' } })); await load(); } catch (requestError) { setError('The dataset transition could not be completed.'); } finally { setBusy(false); }
  }

  async function downloadRejected() {
    if (!current) return;
    const response = await fetch(`${API_URL}/data-imports/${current.dataset_version_id}/rejected.csv`, { headers: { Authorization: `Bearer ${getStoredToken()}` } });
    if (!response.ok) return;
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `dataset-${current.dataset_version_id}-rejected.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="data-import-page">
      <PageHeader eyebrow="Data operations" title="Data Import Center" description="Validate historical ATM operations before they enter production history." breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Data Import' }]} />
      <Card title="Upload CSV">
        <form className="replenishment-form" onSubmit={upload}>
          <p className="replenishment-form-note">Required columns: atm_id, datetime, operation_type, amount. Upload parses and previews only; it does not mutate production history.</p>
          <input type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] || null)} />
          <Button type="submit" disabled={!file || busy}>{busy ? 'Validating…' : 'Upload and validate'}</Button>
        </form>
      </Card>
      {error && <ErrorState title="Import error" description={error} />}
      {current && <Card title={`Dataset #${current.dataset_version_id} · ${current.status}`}>
        <p>Rows received: <strong>{current.rows_received}</strong> · accepted: <strong>{current.rows_accepted}</strong> · rejected: <strong>{current.rows_rejected}</strong> · duplicates: <strong>{current.duplicate_rows}</strong></p>
        <p>Date range: {current.date_from || '—'} to {current.date_to || '—'} · ATMs: {(current.atm_codes || []).join(', ') || '—'}</p>
        {current.validation_report?.rejected_rows?.length ? <Button variant="secondary" onClick={downloadRejected}>Download rejected rows</Button> : null}
        <div className="dialog-actions">{current.status === 'VALIDATED' && canApprove && <Button onClick={() => transition('approve')} disabled={busy}>Approve</Button>}{current.status === 'APPROVED' && canApprove && <Button onClick={() => transition('ingest')} disabled={busy}>Ingest into history</Button>}</div>
      </Card>}
      <Card title="Dataset versions">
        {loading ? <LoadingState label="Loading dataset versions" /> : imports.length ? <DataTable rowKey="dataset_version_id" rows={imports} columns={[{ key: 'dataset_version_id', label: 'Version', render: (row) => <Link to={`/data-imports/${row.dataset_version_id}`}>#{row.dataset_version_id}</Link> }, { key: 'name', label: 'Source' }, { key: 'status', label: 'Status', render: (row) => <StatusBadge status={row.status} /> }, { key: 'rows_accepted', label: 'Accepted' }, { key: 'rows_rejected', label: 'Rejected' }, { key: 'uploaded_at', label: 'Uploaded' }]} /> : <EmptyState title="No dataset uploads" description="Validated dataset versions will appear here." />}
      </Card>
    </main>
  );
}

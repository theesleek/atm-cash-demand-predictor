import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth';
import { apiRequest } from '../api';
import { Button, Card, ConfirmDialog, DataTable, EmptyState, ErrorState, LoadingState, Modal, PageHeader, StatusBadge } from '../components/ui';
import { consumeUnseenRealtimeEvents } from '../realtime';

const emptyResource = { loading: true, data: null, error: null };
const statuses = ['DRAFT', 'REQUESTED', 'APPROVED', 'REJECTED', 'SCHEDULED', 'COMPLETED', 'CANCELLED'];
const createRoles = new Set(['SUPER_ADMIN', 'BANK_MANAGER', 'OPERATIONS_OFFICER']);
const approverRoles = new Set(['SUPER_ADMIN', 'BANK_MANAGER']);

function numberLabel(value) {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
}

function dateLabel(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
}

function SummaryMetric({ label, count, loading }) {
  return <article className="replenishment-summary-item"><span>{label}</span><strong>{loading ? '…' : count ?? '—'}</strong></article>;
}

function ActionError({ message }) {
  return message ? <p className="replenishment-action-error" role="alert">{message}</p> : null;
}

export default function ReplenishmentsPage() {
  const { user, realtimeEvents } = useAuth();
  const role = user?.role;
  const mayRead = createRoles.has(role);
  const mayCreate = createRoles.has(role);
  const mayApprove = approverRoles.has(role);
  const [requests, setRequests] = useState(emptyResource);
  const [atms, setAtms] = useState({ loading: false, data: null, error: null });
  const [requestModalOpen, setRequestModalOpen] = useState(false);
  const [selectedAtm, setSelectedAtm] = useState('');
  const [atmIntelligence, setAtmIntelligence] = useState({ loading: false, data: null, error: null });
  const [requestedAmount, setRequestedAmount] = useState('');
  const [notes, setNotes] = useState('');
  const [requestError, setRequestError] = useState('');
  const [confirm, setConfirm] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [actionError, setActionError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const seenRealtimeEvents = useRef(null);

  useEffect(() => {
    if (!mayRead) {
      setRequests({ loading: false, data: null, error: 'FORBIDDEN' });
      return undefined;
    }
    const controller = new AbortController();
    setRequests((current) => ({ ...current, loading: true, error: null }));
    apiRequest('/replenishments', { signal: controller.signal })
      .then((data) => setRequests({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setRequests({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, [mayRead, reloadKey]);

  useEffect(() => {
    const requestIds = mayRead
      ? [...new Set(consumeUnseenRealtimeEvents(realtimeEvents, seenRealtimeEvents)
        .filter((event) => event.event_type?.startsWith('replenishment.'))
        .map((event) => event.entity_id)
        .filter(Boolean))]
      : [];
    if (!requestIds.length) return undefined;
    const controller = new AbortController();
    for (const requestId of requestIds) {
      apiRequest(`/replenishments/${encodeURIComponent(requestId)}`, { signal: controller.signal })
        .then((updated) => setRequests((current) => ({
          ...current,
          loading: false,
          error: null,
          data: [updated, ...(current.data || []).filter((item) => item.replenishment_id !== updated.replenishment_id)],
        })))
        .catch((error) => { if (error.name !== 'AbortError') return; });
    }
    return () => controller.abort();
  }, [mayRead, realtimeEvents]);

  useEffect(() => {
    if (!requestModalOpen || !mayCreate) return undefined;
    const controller = new AbortController();
    setAtms({ loading: true, data: null, error: null });
    apiRequest('/atms', { signal: controller.signal })
      .then((data) => {
        setAtms({ loading: false, data, error: null });
        setSelectedAtm((current) => current || data[0]?.atm_code || '');
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setAtms({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, [requestModalOpen, mayCreate]);

  useEffect(() => {
    if (!requestModalOpen || !selectedAtm) {
      setAtmIntelligence({ loading: false, data: null, error: null });
      return undefined;
    }
    const controller = new AbortController();
    setAtmIntelligence({ loading: true, data: null, error: null });
    apiRequest(`/atms/${encodeURIComponent(selectedAtm)}/intelligence`, { signal: controller.signal })
      .then((data) => {
        setAtmIntelligence({ loading: false, data, error: null });
        setRequestedAmount(data.recommended_replenishment === null ? '' : String(data.recommended_replenishment));
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setAtmIntelligence({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, [requestModalOpen, selectedAtm]);

  const rows = requests.data || [];
  const summary = useMemo(() => ({
    pending: rows.filter((request) => request.status === 'REQUESTED').length,
    approved: rows.filter((request) => request.status === 'APPROVED').length,
    scheduled: rows.filter((request) => request.status === 'SCHEDULED').length,
    completed: rows.filter((request) => request.status === 'COMPLETED').length,
  }), [rows]);

  function refreshRequests() {
    setReloadKey((key) => key + 1);
  }

  async function createRequest(event) {
    event.preventDefault();
    if (!selectedAtm || !requestedAmount || Number(requestedAmount) <= 0) {
      setRequestError('Select an ATM and enter a positive requested amount.');
      return;
    }
    if (atmIntelligence.data?.capacity && Number(requestedAmount) > atmIntelligence.data.capacity) {
      setRequestError('Requested amount exceeds the ATM cash capacity.');
      return;
    }
    setBusyId('create');
    setRequestError('');
    try {
      await apiRequest('/replenishments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Action-Source': 'WEB' },
        body: JSON.stringify({
          atm_id: selectedAtm,
          requested_amount: Number(requestedAmount),
          submit: true,
          notes: notes.trim() || null,
        }),
      });
      setRequestModalOpen(false);
      setSelectedAtm('');
      setRequestedAmount('');
      setNotes('');
      refreshRequests();
    } catch (error) {
      setRequestError(error.message === 'NETWORK_ERROR' ? 'The backend is unavailable. Please try again.' : 'The request could not be created. Verify the amount and ATM, then retry.');
    } finally {
      setBusyId(null);
    }
  }

  async function confirmAction() {
    if (!confirm) return;
    const { action, request } = confirm;
    setBusyId(request.replenishment_id);
    setActionError('');
    try {
      const path = action === 'approve'
        ? `/replenishments/${request.replenishment_id}/approve`
        : `/replenishments/${request.replenishment_id}/submit`;
      const options = action === 'approve'
        ? {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Action-Source': 'WEB' },
          body: JSON.stringify({ approved_amount: request.requested_amount }),
        }
        : { method: 'POST', headers: { 'X-Action-Source': 'WEB' } };
      await apiRequest(path, options);
      setConfirm(null);
      refreshRequests();
    } catch {
      setConfirm(null);
      setActionError(`Could not ${action} request #${request.replenishment_id}. Refresh the queue and try again.`);
    } finally {
      setBusyId(null);
    }
  }

  const atmOptions = atms.data || [];
  const requestedExceedsCapacity = Boolean(atmIntelligence.data?.capacity && Number(requestedAmount) > atmIntelligence.data.capacity);

  return (
    <main className="replenishments-page">
      <PageHeader
        eyebrow="Cash operations"
        title="Replenishments"
        description="Review requests and track replenishment status across the ATM network."
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Replenishment' }]}
        actions={mayCreate && <Button onClick={() => { setRequestError(''); setRequestModalOpen(true); }}>New request</Button>}
      />

      {!mayRead ? (
        <ErrorState title="Replenishment access is restricted" description="Your role does not have permission to read replenishment requests." />
      ) : (
        <>
          <section className="replenishment-summary" aria-label="Replenishment status summary">
            <SummaryMetric label="Pending" count={summary.pending} loading={requests.loading} />
            <SummaryMetric label="Approved" count={summary.approved} loading={requests.loading} />
            <SummaryMetric label="Scheduled" count={summary.scheduled} loading={requests.loading} />
            <SummaryMetric label="Completed" count={summary.completed} loading={requests.loading} />
          </section>

          <ActionError message={actionError} />
          <Card title="Request Queue" className="replenishment-queue-card" actions={!mayApprove && <span className="replenishment-readonly-note">Approval restricted to Bank Manager and Super Admin</span>}>
            {requests.loading ? <LoadingState label="Loading replenishment requests" /> :
              requests.error ? <ErrorState title="Replenishment queue unavailable" description="The backend could not provide request data." action={<Button variant="secondary" onClick={refreshRequests}>Retry</Button>} /> :
                rows.length ? (
                  <DataTable
                    rowKey="replenishment_id"
                    rows={rows}
                    columns={[
                      { key: 'replenishment_id', label: 'Request ID', render: (row) => <Link className="dashboard-row-link" to={`/replenishments/${row.replenishment_id}`}>#{row.replenishment_id}</Link> },
                      { key: 'atm_id', label: 'ATM', render: (row) => <Link className="atm-id-link" to={`/atms/${encodeURIComponent(row.atm_id)}`}>{row.atm_id}</Link> },
                      { key: 'requested_amount', label: 'Amount', render: (row) => numberLabel(row.requested_amount) },
                      { key: 'status', label: 'Status', render: (row) => <StatusBadge status={row.status} /> },
                      { key: 'requested_by', label: 'Requested By', render: (row) => `User #${row.requested_by}` },
                      { key: 'approved_by', label: 'Approved By', render: (row) => row.approved_by ? `User #${row.approved_by}` : '—' },
                      { key: 'created_at', label: 'Created', render: (row) => dateLabel(row.created_at) },
                      { key: 'action', label: 'Action', render: (row) => (
                        <div className="replenishment-row-actions">
                          {mayApprove && row.status === 'REQUESTED' && <Button variant="secondary" disabled={busyId === row.replenishment_id} onClick={() => setConfirm({ action: 'approve', request: row })}>Approve</Button>}
                          {mayCreate && role === 'OPERATIONS_OFFICER' && row.status === 'DRAFT' && <Button variant="text" disabled={busyId === row.replenishment_id} onClick={() => setConfirm({ action: 'submit', request: row })}>Submit</Button>}
                          <Link className="dashboard-row-link" to={`/replenishments/${row.replenishment_id}`}>Details</Link>
                        </div>
                      ) },
                    ]}
                  />
                ) : <EmptyState title="No replenishment requests" description="Requests created by authorized operators will appear here." />}
          </Card>
        </>
      )}

      <Modal open={requestModalOpen} title="New replenishment request" onClose={() => !busyId && setRequestModalOpen(false)} size="medium">
        <form className="replenishment-form" onSubmit={createRequest}>
          <label htmlFor="request-atm">ATM</label>
          {atms.loading ? <LoadingState label="Loading ATMs" /> : atms.error ? <ErrorState title="ATM list unavailable" description="The request cannot be created without ATM data." /> : (
            <select id="request-atm" required value={selectedAtm} onChange={(event) => setSelectedAtm(event.target.value)}>
              {atmOptions.map((atm) => <option key={atm.id} value={atm.atm_code}>{atm.atm_code} · {atm.branch_id}, {atm.region}</option>)}
            </select>
          )}

          {atmIntelligence.loading ? <LoadingState label="Loading recommendation and capacity" /> : atmIntelligence.error ? <p className="replenishment-form-note">Recommendation and capacity could not be loaded. The backend will validate the submitted amount.</p> : atmIntelligence.data && (
            <dl className="replenishment-guidance">
              <div><dt>Recommended amount</dt><dd>{atmIntelligence.data.recommended_replenishment === null ? 'No persisted forecast recommendation' : numberLabel(atmIntelligence.data.recommended_replenishment)}</dd></div>
              <div><dt>ATM capacity</dt><dd>{numberLabel(atmIntelligence.data.capacity)}</dd></div>
            </dl>
          )}

          <label htmlFor="requested-amount">Requested amount</label>
          <input id="requested-amount" type="number" min="0.01" step="0.01" required value={requestedAmount} onChange={(event) => setRequestedAmount(event.target.value)} aria-invalid={requestedExceedsCapacity} />
          {requestedExceedsCapacity && <p className="replenishment-field-error">Amount exceeds ATM capacity.</p>}
          <label htmlFor="request-notes">Notes</label>
          <textarea id="request-notes" rows="3" maxLength="2000" value={notes} onChange={(event) => setNotes(event.target.value)} />
          {requestError && <p className="replenishment-field-error" role="alert">{requestError}</p>}
          <div className="dialog-actions">
            <Button variant="secondary" disabled={Boolean(busyId)} onClick={() => setRequestModalOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={Boolean(busyId) || requestedExceedsCapacity || atms.loading || atmIntelligence.loading}>{busyId === 'create' ? 'Submitting…' : 'Create request'}</Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(confirm)}
        title={confirm?.action === 'approve' ? 'Approve replenishment?' : 'Submit replenishment request?'}
        message={confirm ? confirm.action === 'approve'
          ? `Approve request #${confirm.request.replenishment_id} for ${confirm.request.atm_id} at ${numberLabel(confirm.request.requested_amount)}? This approval will be recorded through the authenticated web application.`
          : `Submit draft request #${confirm.request.replenishment_id} for review?` : ''}
        confirmLabel={confirm?.action === 'approve' ? 'Approve on Web' : 'Submit request'}
        onConfirm={confirmAction}
        onCancel={() => setConfirm(null)}
      />
    </main>
  );
}
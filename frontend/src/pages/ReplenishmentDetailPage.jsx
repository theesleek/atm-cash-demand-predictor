import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../auth';
import { apiRequest } from '../api';
import { Button, Card, ConfirmDialog, EmptyState, ErrorState, LoadingState, Modal, PageHeader, StatusBadge } from '../components/ui';
import { consumeUnseenRealtimeEvents } from '../realtime';

const roles = {
  create: new Set(['SUPER_ADMIN', 'BANK_MANAGER', 'OPERATIONS_OFFICER']),
  approve: new Set(['SUPER_ADMIN', 'BANK_MANAGER']),
  schedule: new Set(['SUPER_ADMIN', 'BANK_MANAGER', 'OPERATIONS_OFFICER']),
  complete: new Set(['SUPER_ADMIN', 'BANK_MANAGER', 'OPERATIONS_OFFICER']),
  cancel: new Set(['SUPER_ADMIN', 'BANK_MANAGER', 'OPERATIONS_OFFICER']),
};

const emptyResource = { loading: true, data: null, error: null };

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

function DetailField({ label, value }) {
  if (value === null || value === undefined || value === '') return null;
  return <div className="replenishment-detail-field"><dt>{label}</dt><dd>{value}</dd></div>;
}

function LifecycleTimeline({ status, request }) {
  const rejected = status === 'REJECTED';
  const cancelled = status === 'CANCELLED';
  const steps = [
    { key: 'REQUESTED', title: 'Requested', at: request.created_at },
    { key: 'DECISION', title: rejected ? 'Rejected' : 'Approved', at: rejected ? request.updated_at : request.approved_at },
    { key: 'SCHEDULED', title: 'Scheduled', at: request.scheduled_at },
    { key: 'COMPLETED', title: 'Completed', at: request.completed_at },
  ];
  const progression = { DRAFT: 0, REQUESTED: 1, APPROVED: 2, REJECTED: 2, SCHEDULED: 3, COMPLETED: 4, CANCELLED: 1 };
  const current = progression[status] ?? 0;

  return (
    <ol className={`replenishment-timeline ${rejected ? 'is-rejected' : ''} ${cancelled ? 'is-cancelled' : ''}`}>
      {steps.map((step, index) => {
        const active = index + 1 <= current;
        const currentStep = index + 1 === current && status !== 'COMPLETED' && status !== 'REJECTED' && status !== 'CANCELLED';
        const skipped = (rejected && index > 1) || (cancelled && index > 0);
        return (
          <li key={step.key} className={`${active ? 'is-complete' : ''} ${currentStep ? 'is-current' : ''} ${skipped ? 'is-skipped' : ''}`}>
            <span className="replenishment-timeline__marker" aria-hidden="true" />
            <div><strong>{step.title}</strong><time>{step.at ? dateLabel(step.at) : skipped ? 'Not reached' : 'Pending'}</time></div>
          </li>
        );
      })}
    </ol>
  );
}

export default function ReplenishmentDetailPage() {
  const { recordId } = useParams();
  const { user, realtimeEvents } = useAuth();
  const [request, setRequest] = useState(emptyResource);
  const [forecast, setForecast] = useState({ loading: false, data: null, error: null });
  const [audit, setAudit] = useState({ loading: true, data: null, error: null });
  const [formAction, setFormAction] = useState('');
  const [confirmAction, setConfirmAction] = useState('');
  const [reason, setReason] = useState('');
  const [scheduledAt, setScheduledAt] = useState('');
  const [actionNotes, setActionNotes] = useState('');
  const [actionError, setActionError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const seenRealtimeEvents = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    setRequest(emptyResource);
    setAudit({ loading: true, data: null, error: null });
    apiRequest(`/replenishments/${encodeURIComponent(recordId)}`, { signal: controller.signal })
      .then((data) => setRequest({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setRequest({ loading: false, data: null, error });
      });
    apiRequest(`/replenishments/${encodeURIComponent(recordId)}/audit`, { signal: controller.signal })
      .then((data) => setAudit({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setAudit({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, [recordId, reloadKey]);

  useEffect(() => {
    const hasUpdate = consumeUnseenRealtimeEvents(realtimeEvents, seenRealtimeEvents)
      .some((event) => event.event_type?.startsWith('replenishment.') && String(event.entity_id) === String(recordId));
    if (!hasUpdate) return undefined;
    const controller = new AbortController();
    apiRequest(`/replenishments/${encodeURIComponent(recordId)}`, { signal: controller.signal })
      .then((data) => setRequest({ loading: false, data, error: null }))
      .catch((error) => { if (error.name !== 'AbortError') return; });
    return () => controller.abort();
  }, [recordId, realtimeEvents]);

  useEffect(() => {
    const forecastId = request.data?.forecast_id;
    if (!forecastId) {
      setForecast({ loading: false, data: null, error: null });
      return undefined;
    }
    const controller = new AbortController();
    setForecast({ loading: true, data: null, error: null });
    apiRequest(`/forecasts/${forecastId}`, { signal: controller.signal })
      .then((data) => setForecast({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setForecast({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, [request.data]);

  const record = request.data;
  const auditEntries = audit.data || [];
  const createdBy = auditEntries.find((entry) => entry.action === 'REPLENISHMENT_CREATED')?.username;
  const approvedBy = auditEntries.find((entry) => entry.action === 'REPLENISHMENT_APPROVED')?.username;
  const role = user?.role;
  const isOwner = record?.requested_by === user?.user_id;
  const mayCreate = roles.create.has(role) && (role !== 'OPERATIONS_OFFICER' || isOwner);
  const mayCancel = roles.cancel.has(role) && (role !== 'OPERATIONS_OFFICER' || isOwner) && ['DRAFT', 'REQUESTED'].includes(record?.status);
  const mayApprove = roles.approve.has(role) && record?.status === 'REQUESTED';
  const mayReject = roles.approve.has(role) && record?.status === 'REQUESTED';
  const maySchedule = roles.schedule.has(role) && (role !== 'OPERATIONS_OFFICER' || isOwner) && record?.status === 'APPROVED';
  const mayComplete = roles.complete.has(role) && (role !== 'OPERATIONS_OFFICER' || isOwner) && record?.status === 'SCHEDULED';

  async function performAction() {
    if (!confirmAction || !record) return;
    setBusy(true);
    setActionError('');
    const base = `/replenishments/${record.replenishment_id}`;
    let path = '';
    let body = {};
    if (confirmAction === 'submit') path = `${base}/submit`;
    if (confirmAction === 'cancel') path = `${base}/cancel`;
    if (confirmAction === 'approve') {
      path = `${base}/approve`;
      body = { approved_amount: Number(record.requested_amount) };
    }
    if (confirmAction === 'reject') {
      path = `${base}/reject`;
      body = { reason: reason.trim() };
    }
    if (confirmAction === 'schedule') {
      path = `${base}/schedule`;
      body = { scheduled_at: new Date(scheduledAt).toISOString(), notes: actionNotes.trim() || null };
    }
    if (confirmAction === 'complete') {
      path = `${base}/complete`;
      body = { notes: actionNotes.trim() || null };
    }

    try {
      await apiRequest(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Action-Source': 'WEB' },
        body: JSON.stringify(body),
      });
      setConfirmAction('');
      setFormAction('');
      setReason('');
      setScheduledAt('');
      setActionNotes('');
      setReloadKey((key) => key + 1);
    } catch {
      setActionError('The action could not be completed. The request may have changed; reload and try again.');
      setConfirmAction('');
      setFormAction('');
    } finally {
      setBusy(false);
    }
  }

  function startAction(action) {
    setActionError('');
    if (action === 'reject' || action === 'schedule') {
      setFormAction(action);
      setReason('');
      setScheduledAt('');
      setActionNotes('');
      return;
    }
    setConfirmAction(action);
  }

  function continueFormAction(event) {
    event.preventDefault();
    if (formAction === 'reject' && !reason.trim()) return;
    if (formAction === 'schedule' && !scheduledAt) return;
    setConfirmAction(formAction);
    setFormAction('');
  }

  const decisionLabel = confirmAction === 'submit' ? 'Submit this draft request?' :
    confirmAction === 'cancel' ? 'Cancel this request?' :
      confirmAction === 'approve' ? 'Approve this request?' :
        confirmAction === 'reject' ? 'Reject this request?' :
          confirmAction === 'schedule' ? 'Schedule this replenishment?' : 'Complete this replenishment?';

  return (
    <main className="replenishment-detail-page">
      <PageHeader
        eyebrow="Replenishment lifecycle"
        title={record ? `Request #${record.replenishment_id}` : `Request ${recordId}`}
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Replenishment', to: '/replenishments' }, { label: `#${recordId}` }]}
        actions={<Link className="button button--secondary" to="/replenishments">Back to Replenishments</Link>}
      />

      {actionError && <p className="replenishment-action-error" role="alert">{actionError}</p>}
      {request.loading ? <LoadingState label="Loading replenishment request" /> :
        request.error ? <ErrorState title="Request unavailable" description="This request could not be loaded." action={<Link className="button button--secondary" to="/replenishments">Back to Replenishments</Link>} /> :
          !record ? <EmptyState title="Request not found" action={<Link className="button button--secondary" to="/replenishments">Back to Replenishments</Link>} /> : (
            <>
              <Card title="Lifecycle" className="replenishment-lifecycle-card" actions={<StatusBadge status={record.status} />}>
                <LifecycleTimeline status={record.status} request={record} />
              </Card>

              <div className="replenishment-detail-grid">
                <Card title="Request Details" className="replenishment-detail-info">
                  <dl className="replenishment-detail-fields">
                    <DetailField label="ATM" value={<Link className="atm-id-link" to={`/atms/${encodeURIComponent(record.atm_id)}`}>{record.atm_id}</Link>} />
                    <DetailField label="Forecast" value={record.forecast_id ? <Link className="dashboard-row-link" to={`/forecast?atm_id=${encodeURIComponent(record.atm_id)}`}>Forecast #{record.forecast_id}</Link> : 'No linked forecast'} />
                    <DetailField label="Recommended amount" value={forecast.loading ? 'Loading…' : forecast.data ? numberLabel(forecast.data.recommended_replenishment) : '—'} />
                    <DetailField label="Requested amount" value={numberLabel(record.requested_amount)} />
                    <DetailField label="Approved amount" value={numberLabel(record.approved_amount)} />
                    <DetailField label="Requester" value={createdBy || `User #${record.requested_by}`} />
                    <DetailField label="Approver" value={approvedBy || (record.approved_by ? `User #${record.approved_by}` : '—')} />
                    <DetailField label="Created" value={dateLabel(record.created_at)} />
                    <DetailField label="Approved at" value={dateLabel(record.approved_at)} />
                    <DetailField label="Scheduled at" value={dateLabel(record.scheduled_at)} />
                    <DetailField label="Completed at" value={dateLabel(record.completed_at)} />
                    <DetailField label="Notes" value={record.notes} />
                    <DetailField label="Rejection reason" value={record.reason} />
                  </dl>
                  {forecast.error && <p className="replenishment-detail-note">Linked forecast details are unavailable.</p>}
                </Card>

                <Card title="Available Actions" className="replenishment-actions-card">
                  <div className="replenishment-detail-actions">
                    {mayCreate && record.status === 'DRAFT' && <Button variant="secondary" disabled={busy} onClick={() => startAction('submit')}>Submit request</Button>}
                    {mayApprove && <Button disabled={busy} onClick={() => startAction('approve')}>Approve on Web</Button>}
                    {mayReject && <Button variant="danger" disabled={busy} onClick={() => startAction('reject')}>Reject</Button>}
                    {maySchedule && <Button variant="secondary" disabled={busy} onClick={() => startAction('schedule')}>Schedule</Button>}
                    {mayComplete && <Button disabled={busy} onClick={() => startAction('complete')}>Complete</Button>}
                    {mayCancel && <Button variant="text" disabled={busy} onClick={() => startAction('cancel')}>Cancel request</Button>}
                    {!mayCreate && !mayApprove && !mayReject && !maySchedule && !mayComplete && !mayCancel && <p className="replenishment-detail-note">No actions are available for your role and this request state.</p>}
                  </div>
                </Card>

                <Card title="Audit Information" className="replenishment-audit-card">
                  {audit.loading ? <LoadingState label="Loading audit history" /> :
                    audit.error ? <ErrorState title="Audit history unavailable" description="This request is available, but its audit records could not be loaded." /> :
                      audit.data?.length ? (
                        <ol className="replenishment-audit-list">
                          {audit.data.map((entry) => (
                            <li key={entry.audit_id}>
                              <div><strong>{entry.action.replaceAll('_', ' ').toLowerCase()}</strong><small>{entry.username || (entry.user_id ? `User #${entry.user_id}` : 'System')} · {entry.source}</small></div>
                              <time>{dateLabel(entry.timestamp)}</time>
                            </li>
                          ))}
                        </ol>
                      ) : <EmptyState title="No audit events recorded" />}
                </Card>
              </div>
            </>
          )}

      <Modal open={Boolean(formAction)} title={formAction === 'reject' ? 'Reject request' : 'Schedule replenishment'} onClose={() => !busy && setFormAction('')} size="small">
        <form className="replenishment-detail-form" onSubmit={continueFormAction}>
          {formAction === 'reject' ? (
            <>
              <label htmlFor="rejection-reason">Reason</label>
              <textarea id="rejection-reason" rows="4" required value={reason} onChange={(event) => setReason(event.target.value)} />
            </>
          ) : (
            <>
              <label htmlFor="schedule-date">Scheduled date and time</label>
              <input id="schedule-date" type="datetime-local" required value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} />
              <label htmlFor="schedule-notes">Notes</label>
              <textarea id="schedule-notes" rows="3" value={actionNotes} onChange={(event) => setActionNotes(event.target.value)} />
            </>
          )}
          <div className="dialog-actions">
            <Button variant="secondary" onClick={() => setFormAction('')}>Cancel</Button>
            <Button type="submit">Continue</Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(confirmAction)}
        title={decisionLabel}
        message={`Confirm ${confirmAction} for replenishment request #${recordId}.`}
        confirmLabel={confirmAction === 'approve' ? 'Approve on Web' : decisionLabel.replaceAll('?', '')}
        onConfirm={performAction}
        onCancel={() => setConfirmAction('')}
      />
    </main>
  );
}
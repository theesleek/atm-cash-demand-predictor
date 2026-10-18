import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../auth';
import { apiRequest } from '../api';
import { Button, Card, ConfirmDialog, DataTable, EmptyState, ErrorState, LoadingState, PageHeader, RiskBadge, StatusBadge } from '../components/ui';
import { consumeUnseenRealtimeEvents } from '../realtime';

const emptyResource = { loading: true, data: null, error: null };
const canAcknowledge = new Set(['SUPER_ADMIN', 'BANK_MANAGER', 'OPERATIONS_OFFICER']);

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
}

function dateKey(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toISOString().slice(0, 10);
}

function numberLabel(value) {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
}

function ErrorPanel({ title, onRetry }) {
  return <ErrorState title={title} description="The backend could not provide this alert data." action={<Button variant="secondary" onClick={onRetry}>Retry</Button>} />;
}

function AlertActions({ alert, permitted, busy, onRequest }) {
  if (!permitted || alert.status === 'RESOLVED') return <span className="alert-no-action">—</span>;
  return (
    <div className="alert-actions">
      {alert.status === 'OPEN' && <Button variant="secondary" disabled={busy} onClick={() => onRequest('acknowledge', alert)}>Acknowledge</Button>}
      <Button variant="text" disabled={busy} onClick={() => onRequest('resolve', alert)}>Resolve</Button>
    </div>
  );
}

export default function AlertsPage() {
  const { user, realtimeEvents } = useAuth();
  const permitted = canAcknowledge.has(user?.role);
  const [alerts, setAlerts] = useState(emptyResource);
  const [atms, setAtms] = useState({ loading: true, data: null, error: null });
  const [filters, setFilters] = useState({ severity: 'ALL', status: 'ALL', atm: 'ALL', from: '', to: '' });
  const [reloadKey, setReloadKey] = useState(0);
  const [confirm, setConfirm] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [actionError, setActionError] = useState('');
  const seenRealtimeEvents = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    setAlerts((current) => ({ ...current, loading: true, error: null }));
    apiRequest('/alerts', { signal: controller.signal })
      .then((data) => setAlerts({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setAlerts({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, [reloadKey]);

  useEffect(() => {
    const alertIds = [...new Set(consumeUnseenRealtimeEvents(realtimeEvents, seenRealtimeEvents)
      .filter((event) => event.event_type?.startsWith('alert.'))
      .map((event) => event.entity_id)
      .filter(Boolean))];
    if (!alertIds.length) return undefined;
    const controller = new AbortController();
    for (const alertId of alertIds) {
      apiRequest(`/alerts/${encodeURIComponent(alertId)}`, { signal: controller.signal })
        .then((updated) => setAlerts((current) => ({
          ...current,
          loading: false,
          error: null,
          data: [updated, ...(current.data || []).filter((item) => item.alert_id !== updated.alert_id)],
        })))
        .catch((error) => { if (error.name !== 'AbortError') return; });
    }
    return () => controller.abort();
  }, [realtimeEvents]);

  useEffect(() => {
    const controller = new AbortController();
    apiRequest('/atms', { signal: controller.signal })
      .then((data) => setAtms({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setAtms({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, []);

  const filteredAlerts = useMemo(() => (alerts.data || [])
    .filter((alert) => filters.severity === 'ALL' || alert.severity === filters.severity)
    .filter((alert) => filters.status === 'ALL' || alert.status === filters.status)
    .filter((alert) => filters.atm === 'ALL' || alert.atm_id === filters.atm)
    .filter((alert) => {
      const created = dateKey(alert.created_at);
      return (!filters.from || created >= filters.from) && (!filters.to || created <= filters.to);
    }), [alerts.data, filters]);

  function requestAction(action, alert) {
    setActionError('');
    setConfirm({ action, alert });
  }

  async function confirmAction() {
    if (!confirm) return;
    const { action, alert } = confirm;
    setBusyId(alert.alert_id);
    setActionError('');
    try {
      const updated = await apiRequest(`/alerts/${alert.alert_id}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'WEB' }),
      });
      setAlerts((current) => ({ ...current, data: current.data.map((item) => item.alert_id === updated.alert_id ? updated : item) }));
      setConfirm(null);
    } catch {
      setActionError(`Could not ${action} this alert. Its status may have changed; refresh and try again.`);
      setConfirm(null);
    } finally {
      setBusyId(null);
    }
  }

  const atmOptions = atms.data || [...new Map((alerts.data || []).map((alert) => [alert.atm_id, { atm_code: alert.atm_id }])).values()];

  return (
    <main className="alerts-page">
      <PageHeader
        eyebrow="Operational queue"
        title="Alerts"
        description="Review cash-risk alerts, follow their linked forecasts, and record authorized actions."
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Alerts' }]}
      />

      <section className="alert-filters" aria-label="Alert filters">
        <label><span>Severity</span><select value={filters.severity} onChange={(event) => setFilters((current) => ({ ...current, severity: event.target.value }))}>
          <option value="ALL">All severities</option><option value="WARNING">Warning</option><option value="HIGH">High</option><option value="CRITICAL">Critical</option>
        </select></label>
        <label><span>Status</span><select value={filters.status} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value }))}>
          <option value="ALL">All statuses</option><option value="OPEN">Open</option><option value="ACKNOWLEDGED">Acknowledged</option><option value="RESOLVED">Resolved</option>
        </select></label>
        <label><span>ATM</span><select value={filters.atm} onChange={(event) => setFilters((current) => ({ ...current, atm: event.target.value }))}>
          <option value="ALL">All ATMs</option>{atmOptions.map((atm) => <option key={atm.atm_code} value={atm.atm_code}>{atm.atm_code}</option>)}
        </select></label>
        <label><span>From</span><input type="date" value={filters.from} onChange={(event) => setFilters((current) => ({ ...current, from: event.target.value }))} /></label>
        <label><span>To</span><input type="date" value={filters.to} onChange={(event) => setFilters((current) => ({ ...current, to: event.target.value }))} /></label>
      </section>

      {actionError && <p className="alert-action-error" role="alert">{actionError}</p>}
      <Card title="Alert Queue" className="alerts-queue-card" actions={!permitted && <span className="alert-readonly-note">Read only</span>}>
        {alerts.loading ? <LoadingState label="Loading alerts" /> :
          alerts.error ? <ErrorPanel title="Alert queue unavailable" onRetry={() => setReloadKey((key) => key + 1)} /> :
            filteredAlerts.length ? (
              <DataTable
                rowKey="alert_id"
                rows={filteredAlerts}
                columns={[
                  { key: 'alert_id', label: 'Alert ID', render: (alert) => <Link className="dashboard-row-link" to={`/alerts/${alert.alert_id}`}>#{alert.alert_id}</Link> },
                  { key: 'atm_id', label: 'ATM', render: (alert) => <Link className="atm-id-link" to={`/atms/${encodeURIComponent(alert.atm_id)}`}>{alert.atm_id}</Link> },
                  { key: 'severity', label: 'Severity', render: (alert) => <RiskBadge risk={alert.severity} /> },
                  { key: 'message', label: 'Message' },
                  { key: 'created_at', label: 'Created', render: (alert) => formatDate(alert.created_at) },
                  { key: 'status', label: 'Status', render: (alert) => <StatusBadge status={alert.status} /> },
                  { key: 'action', label: 'Action', render: (alert) => <AlertActions alert={alert} permitted={permitted} busy={busyId === alert.alert_id} onRequest={requestAction} /> },
                ]}
              />
            ) : <EmptyState title={alerts.data?.length ? 'No alerts match these filters' : 'No alerts recorded'} description={alerts.data?.length ? 'Adjust the filters to see other alerts.' : 'Alerts created by the backend will appear here.'} />}
      </Card>

      <ConfirmDialog
        open={Boolean(confirm)}
        title={confirm?.action === 'acknowledge' ? 'Acknowledge alert?' : 'Resolve alert?'}
        message={confirm ? `Confirm ${confirm.action} for alert #${confirm.alert.alert_id} at ${confirm.alert.atm_id}.` : ''}
        confirmLabel={confirm?.action === 'acknowledge' ? 'Acknowledge' : 'Resolve'}
        onConfirm={confirmAction}
        onCancel={() => setConfirm(null)}
      />
    </main>
  );
}

export function AlertDetailPage() {
  const { recordId } = useParams();
  const { user, realtimeEvents } = useAuth();
  const permitted = canAcknowledge.has(user?.role);
  const [alert, setAlert] = useState(emptyResource);
  const [forecast, setForecast] = useState({ loading: false, data: null, error: null });
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const seenRealtimeEvents = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    setAlert(emptyResource);
    apiRequest(`/alerts/${encodeURIComponent(recordId)}`, { signal: controller.signal })
      .then((data) => setAlert({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setAlert({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, [recordId, reloadKey]);

  useEffect(() => {
    const hasUpdate = consumeUnseenRealtimeEvents(realtimeEvents, seenRealtimeEvents)
      .some((event) => event.event_type?.startsWith('alert.') && String(event.entity_id) === String(recordId));
    if (!hasUpdate) return undefined;
    const controller = new AbortController();
    apiRequest(`/alerts/${encodeURIComponent(recordId)}`, { signal: controller.signal })
      .then((data) => setAlert({ loading: false, data, error: null }))
      .catch((error) => { if (error.name !== 'AbortError') return; });
    return () => controller.abort();
  }, [recordId, realtimeEvents]);

  useEffect(() => {
    const forecastId = alert.data?.forecast_id;
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
  }, [alert.data]);

  async function performAction() {
    if (!confirm || !alert.data) return;
    setBusy(true);
    setActionError('');
    try {
      const updated = await apiRequest(`/alerts/${alert.data.alert_id}/${confirm}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'WEB' }),
      });
      setAlert({ loading: false, data: updated, error: null });
      setConfirm('');
    } catch {
      setActionError('The alert action could not be completed. Refresh the record and try again.');
      setConfirm('');
    } finally {
      setBusy(false);
    }
  }

  const record = alert.data;
  return (
    <main className="alert-detail-page">
      <PageHeader
        eyebrow="Alert record"
        title={record ? `Alert #${record.alert_id}` : `Alert ${recordId}`}
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Alerts', to: '/alerts' }, { label: `#${recordId}` }]}
        actions={<Link className="button button--secondary" to="/alerts">Back to Alerts</Link>}
      />
      {alert.loading ? <LoadingState label="Loading alert" /> :
        alert.error ? <ErrorPanel title="Alert unavailable" onRetry={() => setReloadKey((key) => key + 1)} /> :
          !record ? <EmptyState title="Alert not found" /> : (
            <>
              {actionError && <p className="alert-action-error" role="alert">{actionError}</p>}
              <div className="alert-detail-grid">
                <Card title="Alert Details" className="alert-detail-card">
                  <dl className="alert-detail-fields">
                    <div><dt>ATM</dt><dd><Link className="atm-id-link" to={`/atms/${encodeURIComponent(record.atm_id)}`}>{record.atm_id}</Link></dd></div>
                    <div><dt>Severity</dt><dd><RiskBadge risk={record.severity} /></dd></div>
                    <div><dt>Message</dt><dd>{record.message}</dd></div>
                    <div><dt>Status</dt><dd><StatusBadge status={record.status} /></dd></div>
                    <div><dt>Alert type</dt><dd>{record.alert_type}</dd></div>
                    <div><dt>Created</dt><dd>{formatDate(record.created_at)}</dd></div>
                    <div><dt>Forecast</dt><dd>{record.forecast_id ? `Forecast #${record.forecast_id}` : 'No linked forecast'}</dd></div>
                    <div><dt>Acknowledged by</dt><dd>{record.acknowledged_by || '—'}</dd></div>
                    <div><dt>Acknowledged at</dt><dd>{formatDate(record.acknowledged_at)}</dd></div>
                    <div><dt>Resolved by</dt><dd>{record.resolved_by || '—'}</dd></div>
                    <div><dt>Resolved at</dt><dd>{formatDate(record.resolved_at)}</dd></div>
                    <div><dt>Action source</dt><dd>{record.action_source || '—'}</dd></div>
                  </dl>
                  {permitted && record.status !== 'RESOLVED' && (
                    <div className="alert-detail-actions">
                      {record.status === 'OPEN' && <Button variant="secondary" disabled={busy} onClick={() => setConfirm('acknowledge')}>Acknowledge</Button>}
                      <Button variant="danger" disabled={busy} onClick={() => setConfirm('resolve')}>Resolve</Button>
                    </div>
                  )}
                </Card>

                <Card title="Linked Forecast" className="alert-forecast-card">
                  {!record.forecast_id ? <EmptyState title="No forecast linked" /> :
                    forecast.loading ? <LoadingState label="Loading linked forecast" /> :
                      forecast.error ? <ErrorState title="Forecast details unavailable" description="The linked alert is available, but the forecast record could not be loaded." /> :
                        forecast.data ? (
                          <dl className="alert-detail-fields">
                            <div><dt>Forecast date</dt><dd>{formatDate(forecast.data.forecast_date)}</dd></div>
                            <div><dt>Risk demand basis</dt><dd>{numberLabel(forecast.data.predicted_demand)}</dd></div>
                            <div><dt>Projected cash</dt><dd>{numberLabel(forecast.data.projected_cash)}</dd></div>
                            <div><dt>Warning threshold</dt><dd>{numberLabel(forecast.data.warning_threshold)}</dd></div>
                            <div><dt>High threshold</dt><dd>{numberLabel(forecast.data.high_threshold)}</dd></div>
                            <div><dt>Critical threshold</dt><dd>{numberLabel(forecast.data.critical_threshold)}</dd></div>
                          </dl>
                        ) : <EmptyState title="Forecast not found" />}
                </Card>
              </div>
            </>
          )}
      <ConfirmDialog
        open={Boolean(confirm)}
        title={confirm === 'acknowledge' ? 'Acknowledge alert?' : 'Resolve alert?'}
        message={`Confirm ${confirm} for alert #${recordId}.`}
        confirmLabel={confirm === 'acknowledge' ? 'Acknowledge' : 'Resolve'}
        onConfirm={performAction}
        onCancel={() => setConfirm('')}
      />
    </main>
  );
}

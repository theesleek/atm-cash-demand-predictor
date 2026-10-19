import { useEffect, useRef, useState } from 'react';
import { Activity, Bell, CircleAlert, Landmark, PackageCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useAuth } from '../auth';
import { apiRequest } from '../api';
import { Card, DataTable, EmptyState, ErrorState, LoadingState, MetricCard, PageHeader, RiskBadge, StatusBadge } from '../components/ui';
import { consumeUnseenRealtimeEvents } from '../realtime';

const canReadReplenishments = new Set(['SUPER_ADMIN', 'BANK_MANAGER', 'OPERATIONS_OFFICER']);
const severityRank = { NORMAL: 0, WARNING: 1, HIGH: 2, CRITICAL: 3 };
const emptyResource = { loading: true, data: null, error: null };

function dateLabel(value) {
  if (!value) return 'Date unavailable';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 'Date unavailable' : parsed.toLocaleDateString();
}

function timeLabel(value) {
  if (!value) return 'Time unavailable';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 'Time unavailable' : parsed.toLocaleString();
}

function resourceResult(result) {
  return result.status === 'fulfilled'
    ? { loading: false, data: result.value, error: null }
    : { loading: false, data: null, error: result.reason?.message || 'REQUEST_FAILED' };
}

function resourceErrorMessage(resource, fallback) {
  const error = resource?.error;
  if (typeof error === 'string' && error.trim()) {
    return error;
  }
  if (typeof error?.message === 'string' && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

function ResourceState({ resource, empty, children }) {
  if (resource.loading) return <LoadingState label="Loading live data" />;
  if (resource.error) {
    return <ErrorState title="Data unavailable" description="The backend could not provide this information. Try again shortly." />;
  }
  if (empty) return <EmptyState title={empty} />;
  return children;
}

function MetricValue({ resource, value, detail }) {
  if (resource.loading) return '…';
  if (resource.error || value === undefined || value === null) return '—';
  return <>{value}{detail ? <small>{detail}</small> : null}</>;
}

function buildRiskCounts(atms, alerts) {
  if (!Array.isArray(atms) || !Array.isArray(alerts)) return null;
  const levelByAtm = new Map();
  alerts
    .filter((alert) => ['OPEN', 'ACKNOWLEDGED'].includes(alert.status))
    .forEach((alert) => {
      const severity = String(alert.severity || '').toUpperCase();
      if (!(severity in severityRank) || severity === 'NORMAL') return;
      const previous = levelByAtm.get(alert.atm_id);
      if (!previous || severityRank[severity] > severityRank[previous]) levelByAtm.set(alert.atm_id, severity);
    });
  const counts = { NORMAL: 0, WARNING: 0, HIGH: 0, CRITICAL: 0 };
  for (const atm of atms) counts[levelByAtm.get(atm.atm_code) || 'NORMAL'] += 1;
  return counts;
}

function buildRecentActivity(alerts, replenishments) {
  const entries = [];
  for (const alert of alerts || []) {
    entries.push({
      key: `alert-created-${alert.alert_id}`,
      label: 'Alert raised',
      at: alert.created_at,
      type: 'alert',
      id: alert.alert_id,
      detail: `${alert.atm_id} · ${alert.severity}`,
    });
    if (alert.acknowledged_at) entries.push({
      key: `alert-ack-${alert.alert_id}`,
      label: 'Alert acknowledged',
      at: alert.acknowledged_at,
      type: 'alert',
      id: alert.alert_id,
      detail: `${alert.atm_id} · ${alert.acknowledged_by || 'Operator'}`,
    });
    if (alert.resolved_at) entries.push({
      key: `alert-resolved-${alert.alert_id}`,
      label: 'Alert resolved',
      at: alert.resolved_at,
      type: 'alert',
      id: alert.alert_id,
      detail: alert.atm_id,
    });
  }
  for (const request of replenishments || []) {
    if (request.status !== 'DRAFT') entries.push({
      key: `replenishment-requested-${request.replenishment_id}`,
      label: 'Replenishment requested',
      at: request.created_at,
      type: 'replenishment',
      id: request.replenishment_id,
      detail: `${request.atm_id} · ${request.requested_amount}`,
    });
    if (request.approved_at) entries.push({
      key: `replenishment-approved-${request.replenishment_id}`,
      label: 'Replenishment approved',
      at: request.approved_at,
      type: 'replenishment',
      id: request.replenishment_id,
      detail: request.atm_id,
    });
    if (request.status === 'REJECTED' && request.updated_at) entries.push({
      key: `replenishment-rejected-${request.replenishment_id}`,
      label: 'Replenishment rejected',
      at: request.updated_at,
      type: 'replenishment',
      id: request.replenishment_id,
      detail: request.atm_id,
    });
    if (request.scheduled_at) entries.push({
      key: `replenishment-scheduled-${request.replenishment_id}`,
      label: 'Replenishment scheduled',
      at: request.updated_at,
      type: 'replenishment',
      id: request.replenishment_id,
      detail: request.atm_id,
    });
    if (request.completed_at) entries.push({
      key: `replenishment-completed-${request.replenishment_id}`,
      label: 'Replenishment completed',
      at: request.completed_at,
      type: 'replenishment',
      id: request.replenishment_id,
      detail: request.atm_id,
    });
  }
  return entries
    .filter((entry) => entry.at && !Number.isNaN(new Date(entry.at).getTime()))
    .sort((left, right) => new Date(right.at) - new Date(left.at))
    .slice(0, 8);
}

function CashForecast({ atms, forecast }) {
  if (atms.loading || forecast.loading) return <LoadingState label="Loading cash forecast" />;
  if (atms.error) return <ErrorState title="ATM data unavailable" description="The forecast cannot be selected until ATM data loads." />;
  if (!atms.data?.length) return <EmptyState title="No ATM data available" />;
  if (forecast.error) {
    return (
      <ErrorState
        title="Forecast unavailable"
        description={resourceErrorMessage(
          forecast,
          'The backend could not provide a forecast for the selected ATM.',
        )}
      />
    );
  }
  if (!forecast.data) return <EmptyState title="No forecast available" />;

  const atm = atms.data[0];
  const series = [
    { date: dateLabel(atm.updated_at), recordedBaseline: Number(atm.daily_demand) },
    { date: dateLabel(forecast.data.forecast_date), predictedSignedNetCashFlow: forecast.data.predicted_signed_net_cash_flow === null || forecast.data.predicted_signed_net_cash_flow === undefined ? null : Number(forecast.data.predicted_signed_net_cash_flow) },
  ];
  return (
    <>
      <p className="dashboard-chart-caption">{atm.atm_code} · recorded baseline and next-day signed net cash flow</p>
      <div className="dashboard-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={series} margin={{ top: 12, right: 12, left: 0, bottom: 4 }}>
            <CartesianGrid stroke="#2b373e" strokeDasharray="3 4" vertical={false} />
            <XAxis dataKey="date" tick={{ fill: '#a1adb3', fontSize: 11 }} axisLine={{ stroke: '#40515a' }} tickLine={false} />
            <YAxis tick={{ fill: '#a1adb3', fontSize: 11 }} axisLine={false} tickLine={false} width={55} />
            <Tooltip
              contentStyle={{ background: '#171e23', border: '1px solid #40515a', borderRadius: 4, color: '#eef2f3' }}
              formatter={(value) => [Number(value).toLocaleString(), undefined]}
            />
            <Legend wrapperStyle={{ color: '#cbd3d7', fontSize: 12 }} />
            <Bar dataKey="recordedBaseline" name="Recorded ATM baseline" fill="#6f9cb4" maxBarSize={44} />
            <Bar dataKey="predictedSignedNetCashFlow" name="Predicted signed net cash flow" fill="#55b7e8" maxBarSize={44} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="dashboard-data-note">The baseline is the ATM’s stored operational figure. Forecasts use signed net cash flow in the source dataset’s unspecified units, not verified withdrawal demand.</p>
      {forecast.data.risk_evaluation_status === 'UNAVAILABLE' && <p className="dashboard-data-note">Demand-based risk and replenishment recommendations require verified withdrawal-demand data.</p>}
    </>
  );
}

function DashboardPage() {
  const { user, realtimeStatus: connectionStatus, realtimeEvents } = useAuth();
  const [summary, setSummary] = useState(emptyResource);
  const [atms, setAtms] = useState(emptyResource);
  const [alerts, setAlerts] = useState(emptyResource);
  const [replenishments, setReplenishments] = useState(emptyResource);
  const [automation, setAutomation] = useState(emptyResource);
  const [forecast, setForecast] = useState(emptyResource);
  const forecastAtm = useRef(null);
  const seenRealtimeEvents = useRef(null);
  const canReadRequests = canReadReplenishments.has(user?.role);

  useEffect(() => {
    const controller = new AbortController();

    async function loadOperationalData() {
      const [summaryResult, atmResult, alertResult, replenishmentResult, automationResult] = await Promise.allSettled([
        apiRequest('/dashboard/summary', { signal: controller.signal }),
        apiRequest('/atms', { signal: controller.signal }),
        apiRequest('/alerts', { signal: controller.signal }),
        canReadRequests
          ? apiRequest('/replenishments', { signal: controller.signal })
          : Promise.resolve(null),
        apiRequest('/automation/status', { signal: controller.signal }),
      ]);
      if (controller.signal.aborted) return;
      setSummary(resourceResult(summaryResult));
      setAtms(resourceResult(atmResult));
      setAlerts(resourceResult(alertResult));
      setReplenishments(canReadRequests ? resourceResult(replenishmentResult) : {
        loading: false,
        data: null,
        error: 'PERMISSION_DENIED',
      });
      setAutomation(resourceResult(automationResult));
    }

    loadOperationalData();
    return () => {
      controller.abort();
    };
  }, [canReadRequests]);

  useEffect(() => {
    const unseen = consumeUnseenRealtimeEvents(realtimeEvents, seenRealtimeEvents);
    const alertIds = [...new Set(unseen.filter((event) => event.event_type?.startsWith('alert.')).map((event) => event.entity_id).filter(Boolean))];
    const replenishmentIds = canReadRequests
      ? [...new Set(unseen.filter((event) => event.event_type?.startsWith('replenishment.')).map((event) => event.entity_id).filter(Boolean))]
      : [];
    if (!alertIds.length && !replenishmentIds.length) return undefined;
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
    for (const requestId of replenishmentIds) {
      apiRequest(`/replenishments/${encodeURIComponent(requestId)}`, { signal: controller.signal })
        .then((updated) => setReplenishments((current) => ({
          ...current,
          loading: false,
          error: null,
          data: [updated, ...(current.data || []).filter((item) => item.replenishment_id !== updated.replenishment_id)],
        })))
        .catch((error) => { if (error.name !== 'AbortError') return; });
    }
    return () => controller.abort();
  }, [realtimeEvents, canReadRequests]);

  useEffect(() => {
    const atm = atms.data?.[0];
    if (!atm || forecastAtm.current === atm.atm_code) return;
    forecastAtm.current = atm.atm_code;
    const controller = new AbortController();
    setForecast({ loading: true, data: null, error: null });
    apiRequest(`/atms/${encodeURIComponent(atm.atm_code)}/readiness`, { signal: controller.signal })
      .then((readiness) => {
        if (readiness.status !== 'READY') {
          setForecast({ loading: false, data: null, error: readiness.reason });
          return null;
        }
        return apiRequest(`/forecast?atm_id=${encodeURIComponent(atm.atm_code)}`, { signal: controller.signal })
          .then((data) => setForecast({ loading: false, data, error: null }));
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setForecast({ loading: false, data: null, error: error.message });
      });
    return () => controller.abort();
  }, [atms.data]);

  const openAlerts = alerts.data?.filter((alert) => alert.status === 'OPEN') || [];
  const activeAlerts = alerts.data?.filter((alert) => ['OPEN', 'ACKNOWLEDGED'].includes(alert.status)) || [];
  const atRiskCount = alerts.data && atms.data
    ? new Set(activeAlerts.filter((alert) => alert.severity !== 'NORMAL').map((alert) => alert.atm_id)).size
    : null;
  const riskCounts = buildRiskCounts(atms.data, alerts.data);
  const pendingRequests = replenishments.data?.filter((item) => item.status === 'REQUESTED') || [];
  const activity = buildRecentActivity(alerts.data, replenishments.data || []);
  const activeAtmCount = atms.data?.filter((atm) => String(atm.status).toLowerCase() === 'active').length;
  const totalAtmCount = summary.data?.atms_monitored ?? atms.data?.length;
  const localeAmount = (value) => Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });

  return (
    <main className="dashboard-page">
      <PageHeader
        eyebrow="Operations workspace"
        title="Dashboard"
        description="Live ATM network conditions and operational work."
        breadcrumbs={[{ label: 'Dashboard' }]}
      />

      <section className="dashboard-metrics" aria-label="Network metrics">
        <MetricCard label="Total ATMs" value={<MetricValue resource={summary.error ? atms : summary} value={totalAtmCount} />} icon={Landmark} />
        <MetricCard label="Active ATMs" value={<MetricValue resource={atms} value={activeAtmCount} />} icon={Activity} />
        <MetricCard label="ATMs at Risk" value={<MetricValue resource={{ loading: alerts.loading || atms.loading, error: alerts.error || atms.error }} value={atRiskCount} />} icon={CircleAlert} />
        <MetricCard label="Open Alerts" value={<MetricValue resource={alerts} value={alerts.data && openAlerts.length} />} icon={Bell} />
        <MetricCard label="Pending Replenishments" value={<MetricValue resource={replenishments} value={replenishments.data && pendingRequests.length} />} icon={PackageCheck} />
      </section>

      <Card title="Daily Intelligence Automation" className="dashboard-wide-card">
        <ResourceState resource={automation} empty={automation.data?.enabled && !automation.data?.last_job ? 'No daily automation run has been recorded' : null}>
          {automation.data && !automation.data.enabled ? (
            <p className="dashboard-data-note">Disabled by configuration. Existing validated actual data and on-demand forecasts remain available.</p>
          ) : automation.data?.last_job ? (
            <dl className="dashboard-detail-list">
              <div><dt>Run status</dt><dd><StatusBadge status={automation.data.last_job.run_status || automation.data.last_job.status} /></dd></div>
              <div><dt>Operational date</dt><dd>{automation.data.last_job.operational_date || '—'}</dd></div>
              <div><dt>Last actual date</dt><dd>{automation.data.last_successful_ingestion_date || '—'}</dd></div>
              <div><dt>Forecast target</dt><dd>{automation.data.last_job.last_forecast_target_date || '—'}</dd></div>
              <div><dt>Eligible / created</dt><dd>{automation.data.last_job.eligible_atms} / {automation.data.last_job.forecasts_created}</dd></div>
              <div><dt>Skipped / failed</dt><dd>{automation.data.last_job.skipped_atms?.length || 0} / {automation.data.last_job.failed_atms?.length || 0}</dd></div>
              <div><dt>Notification delivery</dt><dd>{automation.data.last_job.notification_status || automation.data.notification_status || 'not_applicable'}</dd></div>
            </dl>
          ) : (
            <p className="dashboard-data-note">Enabled, but no daily run has completed yet.</p>
          )}
        </ResourceState>
      </Card>

      <div className="dashboard-main-grid">
        <Card title="Cash Demand Forecast" className="dashboard-forecast-card">
          <CashForecast atms={atms} forecast={forecast} />
        </Card>

        <Card title="Risk" className="dashboard-risk-card">
          <ResourceState resource={{ loading: atms.loading || alerts.loading, error: atms.error || alerts.error }} empty={riskCounts && !atms.data?.length ? 'No ATM risk data' : null}>
            <ul className="dashboard-risk-list">
              {Object.entries(riskCounts || {}).map(([risk, count]) => (
                <li key={risk}><RiskBadge risk={risk} /><strong>{count}</strong></li>
              ))}
            </ul>
            <p className="dashboard-data-note">Risk levels are derived from active alerts. ATMs without one are shown as NORMAL for this alert summary; that does not mean demand-based risk has been assessed. Verified withdrawal-demand data is required.</p>
          </ResourceState>
        </Card>

        <Card title="Active Alerts" className="dashboard-wide-card" actions={<Link className="dashboard-section-link" to="/alerts">View alerts</Link>}>
          <ResourceState resource={alerts} empty={!activeAlerts.length ? 'No active alerts' : null}>
            <DataTable
              rowKey="alert_id"
              rows={activeAlerts}
              columns={[
                { key: 'atm_id', label: 'ATM' },
                { key: 'severity', label: 'Severity', render: (row) => <RiskBadge risk={row.severity} /> },
                { key: 'message', label: 'Message' },
                { key: 'created_at', label: 'Time', render: (row) => timeLabel(row.created_at) },
                { key: 'status', label: 'Status', render: (row) => <StatusBadge status={row.status} /> },
                { key: 'action', label: 'Action', render: (row) => <Link className="dashboard-row-link" to={`/alerts/${row.alert_id}`}>View</Link> },
              ]}
            />
          </ResourceState>
        </Card>

        <Card title="Pending Replenishments" className="dashboard-wide-card" actions={<Link className="dashboard-section-link" to="/replenishments">View requests</Link>}>
          {!canReadRequests ? (
            <EmptyState title="Not available for this role" description="Your role does not include replenishment read access." />
          ) : (
            <ResourceState resource={replenishments} empty={!pendingRequests.length ? 'No pending replenishment requests' : null}>
              <DataTable
                rowKey="replenishment_id"
                rows={pendingRequests}
                columns={[
                  { key: 'atm_id', label: 'ATM' },
                  { key: 'requested_amount', label: 'Amount', render: (row) => localeAmount(row.requested_amount) },
                  { key: 'status', label: 'Status', render: (row) => <StatusBadge status={row.status} /> },
                  { key: 'requested_by', label: 'Requested By', render: (row) => `User #${row.requested_by}` },
                  { key: 'action', label: 'Action', render: (row) => <Link className="dashboard-row-link" to={`/replenishments/${row.replenishment_id}`}>View</Link> },
                ]}
              />
            </ResourceState>
          )}
        </Card>

        <Card title="Recent Activity" className="dashboard-wide-card" actions={<Link className="dashboard-section-link" to="/activity">View activity</Link>}>
          {alerts.loading || replenishments.loading ? <LoadingState label="Loading activity" /> :
            alerts.error ? <ErrorState title="Activity unavailable" description="Alert history could not be loaded." /> :
              activity.length ? (
                <ul className="dashboard-activity-list">
                  {activity.map((entry) => (
                    <li key={entry.key}>
                      <span className="dashboard-activity-marker" />
                      <Link to={`/${entry.type === 'alert' ? 'alerts' : 'replenishments'}/${entry.id}`}>
                        <strong>{entry.label}</strong><small>{entry.detail}</small>
                      </Link>
                      <time>{timeLabel(entry.at)}</time>
                    </li>
                  ))}
                </ul>
              ) : <EmptyState title="No recent activity" />}
        </Card>

        <Card title="Live Updates" className="dashboard-wide-card" actions={<span className={`connection-state connection-state--${connectionStatus}`}>{connectionStatus}</span>}>
          {realtimeEvents.length ? (
            <ul className="event-list" aria-live="polite">
              {realtimeEvents.map((event, index) => (
                <li key={`${event.entity_type}-${event.entity_id}-${event.event_type}-${index}`}>
                  <span>{event.event_type}</span><span>{event.entity_type} #{event.entity_id}</span>
                  {event.atm_id && <span>{event.atm_id}</span>}{event.status && <span>{event.status}</span>}
                  <time>{event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : ''}</time>
                </li>
              ))}
            </ul>
          ) : <EmptyState title="No new live events" />}
        </Card>
      </div>
    </main>
  );
}

export default DashboardPage;

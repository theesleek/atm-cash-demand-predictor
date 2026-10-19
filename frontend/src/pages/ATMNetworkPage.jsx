import { useEffect, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, RotateCw } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../auth';
import { apiRequest } from '../api';
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, RiskBadge, StatusBadge } from '../components/ui';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const riskOptions = ['NORMAL', 'WARNING', 'HIGH', 'CRITICAL'];
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

function compareValues(left, right, key) {
  const a = left[key];
  const b = right[key];
  if (a === null || a === undefined || a === '') return b === null || b === undefined || b === '' ? 0 : 1;
  if (b === null || b === undefined || b === '') return -1;
  if (typeof a === 'number' || typeof b === 'number') return Number(a) - Number(b);
  const aDate = Date.parse(a);
  const bDate = Date.parse(b);
  if (Number.isFinite(aDate) && Number.isFinite(bDate)) return aDate - bDate;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

function SortHeading({ label, field, sort, onSort }) {
  const Icon = sort.field !== field ? ArrowUpDown : sort.direction === 'asc' ? ArrowUp : ArrowDown;
  return (
    <button className="atm-sort-button" type="button" onClick={() => onSort(field)} aria-label={`Sort by ${label}`}>
      {label}<Icon size={13} aria-hidden="true" />
    </button>
  );
}

function ATMTable({ rows, sort, setSort }) {
  function toggleSort(field) {
    setSort((current) => ({
      field,
      direction: current.field === field && current.direction === 'asc' ? 'desc' : 'asc',
    }));
  }

  return (
    <div className="data-table-wrap atm-table-wrap" role="region" aria-label="ATM network results" tabIndex={0}>
      <table className="data-table atm-table">
        <thead>
          <tr>
            <th><SortHeading label="ATM ID" field="atm_code" sort={sort} onSort={toggleSort} /></th>
            <th><SortHeading label="Location" field="location" sort={sort} onSort={toggleSort} /></th>
            <th><SortHeading label="Current Cash" field="current_cash" sort={sort} onSort={toggleSort} /></th>
            <th><SortHeading label="Risk Demand Basis" field="predicted_demand" sort={sort} onSort={toggleSort} /></th>
            <th><SortHeading label="Projected Cash" field="projected_cash" sort={sort} onSort={toggleSort} /></th>
            <th><SortHeading label="Risk" field="risk_level" sort={sort} onSort={toggleSort} /></th>
            <th><SortHeading label="Last Replenishment" field="last_replenishment_at" sort={sort} onSort={toggleSort} /></th>
            <th><SortHeading label="Status" field="status" sort={sort} onSort={toggleSort} /></th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((atm) => (
            <tr key={atm.id}>
              <td><Link className="atm-id-link" to={`/atms/${encodeURIComponent(atm.atm_code)}`}>{atm.atm_code}</Link></td>
              <td>{atm.location || [atm.branch_id, atm.region].filter(Boolean).join(', ') || '—'}</td>
              <td>{numberLabel(atm.current_cash)}</td>
              <td>{numberLabel(atm.predicted_demand)}</td>
              <td>{numberLabel(atm.projected_cash)}</td>
              <td>{atm.risk_level ? <RiskBadge risk={atm.risk_level} /> : <span className="atm-unavailable">{atm.risk_evaluation_status === 'UNAVAILABLE' ? 'Unavailable' : 'Not assessed'}</span>}</td>
              <td>
                {atm.last_replenishment_at ? (
                  <span className="atm-replenishment-cell">
                    {dateLabel(atm.last_replenishment_at)}
                    {atm.last_replenishment_status && <StatusBadge status={atm.last_replenishment_status} />}
                  </span>
                ) : <span className="atm-unavailable">No record</span>}
              </td>
              <td><StatusBadge status={atm.status} /></td>
              <td><Link className="dashboard-row-link" to={`/atms/${encodeURIComponent(atm.atm_code)}`}>View</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ATMNetworkPage() {
  const [resource, setResource] = useState(emptyResource);
  const [search, setSearch] = useState('');
  const [riskFilter, setRiskFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [sort, setSort] = useState({ field: 'atm_code', direction: 'asc' });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setResource((current) => ({ ...current, loading: true, error: null }));
    apiRequest('/atms/network', { signal: controller.signal })
      .then((data) => setResource({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setResource({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, [reloadKey]);

  const atms = resource.data || [];
  const statuses = useMemo(() => [...new Set(atms.map((atm) => atm.status).filter(Boolean))].sort(), [atms]);
  const filteredRows = useMemo(() => {
    const query = search.trim().toLowerCase();
    return atms
      .filter((atm) => !query || [atm.atm_code, atm.location, atm.branch_id, atm.region].some((value) => String(value || '').toLowerCase().includes(query)))
      .filter((atm) => riskFilter === 'ALL' || (riskFilter === 'NOT_ASSESSED' ? !atm.risk_level : String(atm.risk_level || '').toUpperCase() === riskFilter))
      .filter((atm) => statusFilter === 'ALL' || String(atm.status || '').toLowerCase() === statusFilter.toLowerCase())
      .sort((left, right) => compareValues(left, right, sort.field) * (sort.direction === 'asc' ? 1 : -1));
  }, [atms, riskFilter, search, sort, statusFilter]);

  return (
    <main className="atm-network-page">
      <PageHeader
        eyebrow="Network operations"
        title="ATM Network"
        description="Search and review current ATM cash position, forecast risk basis, and replenishment activity."
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'ATMs' }]}
      />

      <section className="atm-network-controls" aria-label="ATM network filters">
        <label className="atm-search-field">
          <span>Search ATMs</span>
          <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ATM ID, branch, or region" />
        </label>
        <label>
          <span>Risk</span>
          <select value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)}>
            <option value="ALL">All risk levels</option>
            {riskOptions.map((risk) => <option key={risk} value={risk}>{risk}</option>)}
            <option value="NOT_ASSESSED">Not assessed</option>
          </select>
        </label>
        <label>
          <span>Status</span>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="ALL">All statuses</option>
            {statuses.map((status) => <option key={status} value={status}>{status}</option>)}
          </select>
        </label>
      </section>

      {resource.loading ? <LoadingState label="Loading ATM network" /> :
        resource.error ? (
          <ErrorState
            title="ATM network unavailable"
            description="The network data could not be loaded from the backend."
            action={<Button variant="secondary" onClick={() => setReloadKey((key) => key + 1)}><RotateCw size={15} />Retry</Button>}
          />
        ) : !atms.length ? (
          <EmptyState title="No ATMs available" description="The backend returned no ATM records." />
        ) : filteredRows.length ? (
          <ATMTable rows={filteredRows} sort={sort} setSort={setSort} />
        ) : (
          <EmptyState title="No matching ATMs" description="Adjust the search or filters to see other network records." />
        )}
      <p className="atm-network-note">Signed net cash flow forecasts are shown separately from risk. Demand-based risk requires verified withdrawal-demand data.</p>
    </main>
  );
}

export function ATMDetailPage() {
  const { atmId } = useParams();
  const { user } = useAuth();
  const canReadReplenishments = ['SUPER_ADMIN', 'BANK_MANAGER', 'OPERATIONS_OFFICER'].includes(user?.role);
  const [intelligence, setIntelligence] = useState(emptyResource);
  const [alerts, setAlerts] = useState(emptyResource);
  const [replenishments, setReplenishments] = useState(emptyResource);

  useEffect(() => {
    const controller = new AbortController();
    setIntelligence(emptyResource);
    setAlerts(emptyResource);
    setReplenishments(canReadReplenishments ? emptyResource : { loading: false, data: null, error: 'FORBIDDEN' });

    apiRequest(`/atms/${encodeURIComponent(atmId)}/intelligence`, { signal: controller.signal })
      .then((data) => setIntelligence({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setIntelligence({ loading: false, data: null, error });
      });

    apiRequest(`/alerts?atm_id=${encodeURIComponent(atmId)}`, { signal: controller.signal })
      .then((data) => setAlerts({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setAlerts({ loading: false, data: null, error });
      });

    if (canReadReplenishments) {
      apiRequest('/replenishments', { signal: controller.signal })
        .then((data) => setReplenishments({ loading: false, data: data.filter((item) => item.atm_id === atmId), error: null }))
        .catch((error) => {
          if (error.name !== 'AbortError') setReplenishments({ loading: false, data: null, error });
        });
    }
    return () => controller.abort();
  }, [atmId, canReadReplenishments]);

  const record = intelligence.data;
  const historical = record?.historical_demand || [];
  const chartData = [
    ...historical.map((point) => ({ date: point.date, historicalDemand: point.demand })),
    ...(record?.predicted_signed_net_cash_flow !== null && record?.predicted_signed_net_cash_flow !== undefined && record?.forecast_date
      ? [{ date: record.forecast_date, predictedSignedNetCashFlow: record.predicted_signed_net_cash_flow }]
      : []),
  ];
  const activity = [
    ...(alerts.data || []).flatMap((alert) => [
      { id: `alert-${alert.alert_id}-created`, label: 'Alert raised', at: alert.created_at, detail: `${alert.severity} · ${alert.message}`, to: `/alerts/${alert.alert_id}` },
      ...(alert.acknowledged_at ? [{ id: `alert-${alert.alert_id}-ack`, label: 'Alert acknowledged', at: alert.acknowledged_at, detail: `Acknowledged by ${alert.acknowledged_by || 'operator'}`, to: `/alerts/${alert.alert_id}` }] : []),
      ...(alert.resolved_at ? [{ id: `alert-${alert.alert_id}-resolved`, label: 'Alert resolved', at: alert.resolved_at, detail: `Resolved by ${alert.resolved_by || 'operator'}`, to: `/alerts/${alert.alert_id}` }] : []),
    ]),
    ...(replenishments.data || []).flatMap((request) => [
      { id: `replenishment-${request.replenishment_id}-requested`, label: 'Replenishment requested', at: request.created_at, detail: `Amount ${numberLabel(request.requested_amount)}`, to: `/replenishments/${request.replenishment_id}` },
      ...(request.approved_at ? [{ id: `replenishment-${request.replenishment_id}-approved`, label: 'Replenishment approved', at: request.approved_at, detail: `Approved amount ${numberLabel(request.approved_amount)}`, to: `/replenishments/${request.replenishment_id}` }] : []),
      ...(request.status === 'REJECTED' ? [{ id: `replenishment-${request.replenishment_id}-rejected`, label: 'Replenishment rejected', at: request.updated_at, detail: request.reason || 'Rejected', to: `/replenishments/${request.replenishment_id}` }] : []),
      ...(request.scheduled_at ? [{ id: `replenishment-${request.replenishment_id}-scheduled`, label: 'Replenishment scheduled', at: request.updated_at, detail: `Scheduled for ${dateLabel(request.scheduled_at)}`, to: `/replenishments/${request.replenishment_id}` }] : []),
      ...(request.completed_at ? [{ id: `replenishment-${request.replenishment_id}-completed`, label: 'Replenishment completed', at: request.completed_at, detail: 'Cash load completed', to: `/replenishments/${request.replenishment_id}` }] : []),
    ]),
  ].filter((event) => event.at && !Number.isNaN(new Date(event.at).getTime()))
    .sort((left, right) => new Date(right.at) - new Date(left.at))
    .slice(0, 8);

  return (
    <main className="atm-detail-page">
      <PageHeader
        eyebrow="ATM network record"
        title={record?.atm_code || atmId}
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'ATMs', to: '/atms' }, { label: record?.atm_code || atmId }]}
        actions={(
          <div className="page-header__actions">
            <Link className="button button--secondary" to="/atms">Back to ATMs</Link>
            <Link className="button button--primary" to={`/forecast?atm_id=${encodeURIComponent(atmId)}`}>View Forecast</Link>
          </div>
        )}
      />
      {intelligence.loading ? <LoadingState label="Loading ATM detail" /> :
        intelligence.error ? <ErrorState title="ATM record unavailable" description="This ATM could not be loaded from the backend." /> :
          !record ? <EmptyState title="ATM not found" /> : (
            <>
              <section className="atm-detail-metrics" aria-label="ATM status and cash metrics">
                <article><span>Location</span><strong>{[record.branch_id, record.region].filter(Boolean).join(', ') || '—'}</strong></article>
                <article><span>Operational status</span><StatusBadge status={record.status} /></article>
                <article><span>Current cash</span><strong>{numberLabel(record.current_cash)}</strong></article>
                <article><span>Cash capacity</span><strong>{numberLabel(record.capacity)}</strong></article>
                <article><span>Signed net cash flow</span><strong>{numberLabel(record.predicted_signed_net_cash_flow)}</strong></article>
                <article><span>Risk demand basis</span><strong>{numberLabel(record.predicted_demand)}</strong></article>
                <article><span>Projected cash</span><strong>{numberLabel(record.projected_cash)}</strong></article>
                <article><span>Risk</span>{record.risk_level ? <RiskBadge risk={record.risk_level} /> : <span className="atm-unavailable">Not assessed</span>}</article>
                <article><span>Recommended replenishment</span><strong>{numberLabel(record.recommended_replenishment)}</strong></article>
              </section>

              <div className="atm-detail-sections">
                <Card title="Forecast: Signed Net Cash Flow vs Risk Basis">
                  {historical.length ? (
                    <>
                      <p className="dashboard-chart-caption">Signed net cash flow uses the source dataset's unspecified units; it is not a verified withdrawal-demand basis{record.forecast_date ? ` · forecast date ${dateLabel(record.forecast_date)}` : ''}</p>
                      <div className="atm-detail-chart">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={chartData} margin={{ top: 12, right: 14, left: 0, bottom: 4 }}>
                            <CartesianGrid stroke="#2b373e" strokeDasharray="3 4" vertical={false} />
                            <XAxis dataKey="date" tick={{ fill: '#a1adb3', fontSize: 10 }} tickFormatter={(value) => new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} axisLine={{ stroke: '#40515a' }} tickLine={false} minTickGap={28} />
                            <YAxis tick={{ fill: '#a1adb3', fontSize: 11 }} axisLine={false} tickLine={false} width={56} />
                            <Tooltip
                              labelFormatter={(value) => dateLabel(value)}
                              formatter={(value, name) => [numberLabel(value), name]}
                              contentStyle={{ background: '#171e23', border: '1px solid #40515a', borderRadius: 4, color: '#eef2f3' }}
                            />
                            <Legend wrapperStyle={{ color: '#cbd3d7', fontSize: 12 }} />
                            <Line type="monotone" dataKey="historicalDemand" name="Historical signed net cash flow" stroke="#82a9bb" strokeWidth={2} dot={false} connectNulls />
                            <Line type="monotone" dataKey="predictedSignedNetCashFlow" name="Predicted signed net cash flow" stroke="#55b7e8" strokeWidth={2} strokeDasharray="5 4" dot={{ r: 4 }} connectNulls />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </>
                  ) : <EmptyState title="Historical signed net cash flow unavailable" description="No mapped historical observations are available for this ATM." />}
                  {record.risk_evaluation_status === 'UNAVAILABLE' && <p className="atm-detail-note">{record.risk_evaluation_reason || 'Verified withdrawal-demand data is required for risk evaluation.'}</p>}
                  {record.predicted_signed_net_cash_flow === null && <p className="atm-detail-note">No persisted forecast is available for this ATM.</p>}
                </Card>

                <Card title="Risk Explanation">
                  {record.risk_evaluation_status === 'UNAVAILABLE' ? (
                    <EmptyState title="Risk evaluation unavailable" description={record.risk_evaluation_reason || 'Verified withdrawal-demand data is required for demand-based risk evaluation.'} />
                  ) : record.risk_level ? (
                    <div className="atm-risk-explanation">
                      <RiskBadge risk={record.risk_level} />
                      <p>{record.risk_explanation}</p>
                      <dl>
                        <div><dt>Warning threshold</dt><dd>{numberLabel(record.warning_threshold)}</dd></div>
                        <div><dt>High threshold</dt><dd>{numberLabel(record.high_threshold)}</dd></div>
                        <div><dt>Critical threshold</dt><dd>{numberLabel(record.critical_threshold)}</dd></div>
                      </dl>
                      <small>Thresholds are computed by the backend risk service from the persisted forecast and configured risk ratios.</small>
                    </div>
                  ) : <EmptyState title="Risk not assessed" description="A risk level appears after a forecast has been persisted for this ATM." />}
                </Card>

                <Card title="Recent Alerts" className="atm-detail-wide">
                  {alerts.loading ? <LoadingState label="Loading alerts" /> :
                    alerts.error ? <ErrorState title="Alerts unavailable" description="Alert records could not be loaded." /> :
                      alerts.data?.length ? (
                        <ul className="atm-detail-record-list">
                          {alerts.data.slice(0, 5).map((alert) => (
                            <li key={alert.alert_id}>
                              <Link to={`/alerts/${alert.alert_id}`}><strong>{alert.message}</strong><small>{dateLabel(alert.created_at)}</small></Link>
                              <RiskBadge risk={alert.severity} />
                              <StatusBadge status={alert.status} />
                            </li>
                          ))}
                        </ul>
                      ) : <EmptyState title="No alerts for this ATM" />}
                </Card>

                <Card title="Replenishment Information" className="atm-detail-wide">
                  {replenishments.error === 'FORBIDDEN' ? <EmptyState title="Replenishment access is restricted for your role" /> :
                    replenishments.loading ? <LoadingState label="Loading replenishments" /> :
                      replenishments.error ? <ErrorState title="Replenishments unavailable" description="Replenishment records could not be loaded." /> :
                        replenishments.data?.length ? (
                          <ul className="atm-detail-record-list">
                            {replenishments.data.slice(0, 5).map((request) => (
                              <li key={request.replenishment_id}>
                                <Link to={`/replenishments/${request.replenishment_id}`}>
                                  <strong>Request #{request.replenishment_id} · {numberLabel(request.requested_amount)}</strong>
                                  <small>Requested {dateLabel(request.created_at)} · User #{request.requested_by}</small>
                                </Link>
                                <StatusBadge status={request.status} />
                              </li>
                            ))}
                          </ul>
                        ) : <EmptyState title="No replenishment records available" />}
                </Card>

                <Card title="Recent Activity" className="atm-detail-wide">
                  {alerts.loading || (canReadReplenishments && replenishments.loading) ? <LoadingState label="Loading activity" /> :
                    alerts.error ? <ErrorState title="Activity unavailable" description="Alert history could not be loaded." /> :
                      activity.length ? (
                        <ul className="atm-detail-activity">
                          {activity.map((event) => (
                            <li key={event.id}>
                              <Link to={event.to}><strong>{event.label}</strong><small>{event.detail}</small></Link>
                              <time>{dateLabel(event.at)}</time>
                            </li>
                          ))}
                        </ul>
                      ) : <EmptyState title="No recent activity" />}
                </Card>
              </div>
            </>
          )}
    </main>
  );
}

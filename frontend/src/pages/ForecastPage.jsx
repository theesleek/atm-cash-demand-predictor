import { useEffect, useMemo, useState } from 'react';
import { Activity, CalendarDays, Cpu, Database, Gauge, Landmark } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { apiRequest } from '../api';
import { Card, EmptyState, ErrorState, LoadingState, PageHeader } from '../components/ui';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const emptyResource = { loading: true, data: null, error: null };

const evaluationMetrics = [
  { label: 'MAE', value: '259.69', note: 'Recorded test result' },
  { label: 'RMSE', value: '371.88', note: 'Recorded test result' },
  { label: 'Bias', value: null, note: 'Not reported' },
];

function numberLabel(value) {
  if (value === null || value === undefined || value === '') return '—';
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
}

function dateLabel(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString(undefined, { dateStyle: 'medium' });
}

function ResourceError({ title, resource, onRetry }) {
  return (
    <ErrorState
      title={title}
      description="The backend could not provide this forecast information."
      action={<button className="button button--secondary" type="button" onClick={onRetry}>Retry</button>}
    />
  );
}

export default function ForecastPage() {
  const [searchParams] = useSearchParams();
  const requestedAtm = searchParams.get('atm_id') || '';
  const [atms, setAtms] = useState(emptyResource);
  const [selectedAtm, setSelectedAtm] = useState('');
  const [forecast, setForecast] = useState({ loading: false, data: null, error: null });
  const [history, setHistory] = useState({ loading: false, data: null, error: null });
  const [requestKey, setRequestKey] = useState(0);
  const [atmReloadKey, setAtmReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    apiRequest('/atms', { signal: controller.signal })
      .then((data) => {
        setAtms({ loading: false, data, error: null });
        if (data.length) {
          setSelectedAtm((current) => current || (data.some((atm) => atm.atm_code === requestedAtm) ? requestedAtm : data[0].atm_code));
        }
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setAtms({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, [atmReloadKey, requestedAtm]);

  useEffect(() => {
    if (!selectedAtm) return undefined;
    const controller = new AbortController();
    setForecast({ loading: true, data: null, error: null });
    setHistory({ loading: true, data: null, error: null });

    apiRequest(`/atms/${encodeURIComponent(selectedAtm)}/readiness`, { signal: controller.signal })
      .then((readiness) => {
        if (readiness.status !== 'READY') {
          setForecast({ loading: false, data: null, error: readiness.reason });
          return null;
        }
        return apiRequest(`/forecast?atm_id=${encodeURIComponent(selectedAtm)}`, { signal: controller.signal })
          .then((data) => setForecast({ loading: false, data, error: null }));
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setForecast({ loading: false, data: null, error });
      });

    apiRequest(`/atms/${encodeURIComponent(selectedAtm)}/intelligence`, { signal: controller.signal })
      .then((data) => setHistory({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setHistory({ loading: false, data: null, error });
      });

    return () => controller.abort();
  }, [selectedAtm, requestKey]);

  const chartData = useMemo(() => {
    if (!forecast.data) return [];
    const points = (history.data?.historical_demand || []).map((point) => ({
      date: point.date,
      historicalCashFlow: Number(point.demand),
    }));
    points.push({
      date: forecast.data.forecast_date,
      predictedSignedNetCashFlow: Number(forecast.data.predicted_signed_net_cash_flow ?? forecast.data.predicted_demand),
    });
    return points.sort((left, right) => String(left.date).localeCompare(String(right.date)));
  }, [forecast.data, history.data]);

  return (
    <main className="forecast-page">
      <PageHeader
        eyebrow="Demand planning"
        title="Forecast"
        description="Review the next-day signed net cash flow forecast and its operational risk basis."
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Forecast' }]}
      />

      <section className="forecast-selector">
        <label htmlFor="forecast-atm">ATM</label>
        {atms.loading ? <LoadingState label="Loading ATMs" /> : atms.error ? (
          <ResourceError title="ATM list unavailable" resource={atms} onRetry={() => setAtmReloadKey((key) => key + 1)} />
        ) : !atms.data?.length ? (
          <EmptyState title="No ATMs available" />
        ) : (
          <select id="forecast-atm" value={selectedAtm} onChange={(event) => setSelectedAtm(event.target.value)}>
            {atms.data.map((atm) => <option key={atm.id} value={atm.atm_code}>{atm.atm_code} · {atm.branch_id}, {atm.region}</option>)}
          </select>
        )}
      </section>

      {forecast.loading ? <LoadingState label="Generating forecast" /> :
        forecast.error ? (
          <ResourceError title="Forecast unavailable" resource={forecast} onRetry={() => setRequestKey((key) => key + 1)} />
        ) : forecast.data ? (
          <>
            <section className="forecast-summary" aria-label="Forecast summary">
              <article><span><CalendarDays size={15} /> Forecast date</span><strong>{dateLabel(forecast.data.forecast_date)}</strong></article>
              <article><span><Gauge size={15} /> Signed net cash flow</span><strong>{numberLabel(forecast.data.predicted_signed_net_cash_flow ?? forecast.data.predicted_demand)}</strong></article>
              <article><span><Landmark size={15} /> ATM</span><strong>{forecast.data.atm_id}</strong></article>
              <article><span><Cpu size={15} /> Model</span><strong>50/50 Linear Regression + Random Forest</strong></article>
              <article><span><Activity size={15} /> Model version</span><strong>{forecast.data.model_version || '—'}</strong></article>
              <article><span><Database size={15} /> Data source</span><strong>{forecast.data.forecast_source || '—'}</strong></article>
            </section>

            <Card title="Historical vs Predicted Signed Net Cash Flow" className="forecast-chart-card">
              {history.loading ? <LoadingState label="Loading historical ATM activity" /> : history.error ? (
                <ErrorState title="Historical data unavailable" description="The forecast is available, but its historical series could not be loaded." />
              ) : chartData.length > 1 ? (
                <>
                  <p className="forecast-chart-note">Values are signed net cash flow in the source dataset's unspecified units; this is not a verified withdrawal-demand target.</p>
                  <div className="forecast-chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartData} margin={{ top: 12, right: 16, left: 0, bottom: 5 }}>
                        <CartesianGrid stroke="#2b373e" strokeDasharray="3 4" vertical={false} />
                        <XAxis dataKey="date" tick={{ fill: '#a1adb3', fontSize: 10 }} tickFormatter={(value) => new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} axisLine={{ stroke: '#40515a' }} tickLine={false} minTickGap={32} />
                        <YAxis tick={{ fill: '#a1adb3', fontSize: 11 }} axisLine={false} tickLine={false} width={58} />
                        <Tooltip
                          labelFormatter={(value) => dateLabel(value)}
                          formatter={(value, name) => [numberLabel(value), name]}
                          contentStyle={{ background: '#171e23', border: '1px solid #40515a', borderRadius: 4, color: '#eef2f3' }}
                        />
                        <Legend wrapperStyle={{ color: '#cbd3d7', fontSize: 12 }} />
                        <Line type="monotone" dataKey="historicalCashFlow" name="Historical signed net cash flow" stroke="#82a9bb" strokeWidth={2} dot={false} connectNulls />
                        <Line type="monotone" dataKey="predictedSignedNetCashFlow" name="Predicted signed net cash flow" stroke="#55b7e8" strokeWidth={2} strokeDasharray="5 4" dot={{ r: 4 }} connectNulls />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </>
              ) : <EmptyState title="Historical series unavailable" description="No mapped historical observations are available for this ATM." />}
            </Card>

            <section className="forecast-explanation-grid">
              <Card title="How to read this forecast" className="forecast-explanation">
                <p>The forecast estimates next-day signed net cash flow using historical ATM activity and derived time-based features.</p>
                <p>The model combines Linear Regression and Random Forest predictions in a 50/50 ensemble. Risk calculations use a nonnegative basis derived from the forecast; this output is decision support, not verified withdrawal demand or a replenishment approval.</p>
              </Card>
              <Card title="Measured model metrics" className="forecast-metrics-card">
                <div className="forecast-metrics">
                  {evaluationMetrics.map((metric) => (
                    <article key={metric.label}>
                      <span>{metric.label}</span>
                      <strong>{metric.value ?? 'Not reported'}</strong>
                      <small>{metric.note}</small>
                    </article>
                  ))}
                </div>
                <p className="forecast-chart-note">Recorded ensemble test metrics. Bias is not published in the available evaluation results.</p>
              </Card>
            </section>
          </>
        ) : selectedAtm ? <EmptyState title="No forecast returned" /> : null}
    </main>
  );
}

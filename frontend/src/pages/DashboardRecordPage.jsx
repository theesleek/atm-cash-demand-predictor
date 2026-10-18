import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiRequest } from '../api';
import { EmptyState, ErrorState, LoadingState, PageHeader, RiskBadge, StatusBadge } from '../components/ui';

function DetailField({ label, value }) {
  if (value === null || value === undefined || value === '') return null;
  return <div className="record-detail-field"><dt>{label}</dt><dd>{value}</dd></div>;
}

function displayDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

export default function DashboardRecordPage({ type }) {
  const { recordId } = useParams();
  const [resource, setResource] = useState({ loading: true, data: null, error: null });
  const isAlert = type === 'alert';
  const label = isAlert ? 'Alert' : 'Replenishment';

  useEffect(() => {
    const controller = new AbortController();
    setResource({ loading: true, data: null, error: null });
    apiRequest(`/${isAlert ? 'alerts' : 'replenishments'}/${encodeURIComponent(recordId)}`, { signal: controller.signal })
      .then((data) => setResource({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setResource({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, [isAlert, recordId]);

  const backPath = isAlert ? '/alerts' : '/replenishments';
  return (
    <main className="dashboard-detail-page">
      <PageHeader
        eyebrow="Operations record"
        title={`${label} ${recordId}`}
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label, to: backPath }, { label: `#${recordId}` }]}
      />
      <section className="card dashboard-record-card">
        {resource.loading ? <LoadingState label={`Loading ${label.toLowerCase()}`} /> :
          resource.error ? <ErrorState title={`${label} unavailable`} description="This record could not be loaded from the backend." action={<Link className="button button--secondary" to={backPath}>Back to {label.toLowerCase()} list</Link>} /> :
            !resource.data ? <EmptyState title={`${label} not found`} action={<Link className="button button--secondary" to={backPath}>Back to {label.toLowerCase()} list</Link>} /> : (
              <dl className="record-detail-grid">
                <DetailField label="ATM" value={resource.data.atm_id} />
                {isAlert ? (
                  <>
                    <DetailField label="Severity" value={<RiskBadge risk={resource.data.severity} />} />
                    <DetailField label="Message" value={resource.data.message} />
                    <DetailField label="Status" value={<StatusBadge status={resource.data.status} />} />
                    <DetailField label="Created" value={displayDate(resource.data.created_at)} />
                    <DetailField label="Acknowledged by" value={resource.data.acknowledged_by} />
                    <DetailField label="Acknowledged at" value={displayDate(resource.data.acknowledged_at)} />
                    <DetailField label="Resolved by" value={resource.data.resolved_by} />
                    <DetailField label="Resolved at" value={displayDate(resource.data.resolved_at)} />
                    <DetailField label="Source" value={resource.data.action_source} />
                  </>
                ) : (
                  <>
                    <DetailField label="Requested amount" value={resource.data.requested_amount?.toLocaleString()} />
                    <DetailField label="Approved amount" value={resource.data.approved_amount?.toLocaleString()} />
                    <DetailField label="Status" value={<StatusBadge status={resource.data.status} />} />
                    <DetailField label="Requested by" value={`User #${resource.data.requested_by}`} />
                    <DetailField label="Forecast ID" value={resource.data.forecast_id} />
                    <DetailField label="Created" value={displayDate(resource.data.created_at)} />
                    <DetailField label="Approved at" value={displayDate(resource.data.approved_at)} />
                    <DetailField label="Scheduled at" value={displayDate(resource.data.scheduled_at)} />
                    <DetailField label="Completed at" value={displayDate(resource.data.completed_at)} />
                    <DetailField label="Reason" value={resource.data.reason} />
                    <DetailField label="Notes" value={resource.data.notes} />
                  </>
                )}
              </dl>
            )}
      </section>
    </main>
  );
}
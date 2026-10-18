import { useEffect, useMemo, useState } from 'react';
import { apiRequest } from '../api';
import { ApiErrorState, Button, Card, DataTable, EmptyState, LoadingState, PageHeader, StatusBadge } from '../components/ui';

const emptyResource = { loading: true, data: null, error: null };
const sources = ['WEB', 'API', 'SYSTEM', 'TELEGRAM'];

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
}

function actionLabel(action) {
  return String(action || 'UNKNOWN').toLowerCase().replaceAll('_', ' ');
}

export default function ActivityPage() {
  const [resource, setResource] = useState(emptyResource);
  const [filters, setFilters] = useState({ user: 'ALL', action: 'ALL', source: 'ALL', from: '', to: '', entity: 'ALL' });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setResource((current) => ({ ...current, loading: true, error: null }));
    apiRequest('/activity?limit=500', { signal: controller.signal })
      .then((data) => setResource({ loading: false, data, error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setResource({ loading: false, data: null, error });
      });
    return () => controller.abort();
  }, [reloadKey]);

  const entries = resource.data || [];
  const users = useMemo(() => [...new Map(entries.filter((entry) => entry.user_id !== null).map((entry) => [String(entry.user_id), { id: String(entry.user_id), username: entry.username || `User #${entry.user_id}` }])).values()]
    .sort((left, right) => left.username.localeCompare(right.username)), [entries]);
  const actions = useMemo(() => [...new Set(entries.map((entry) => entry.action).filter(Boolean))].sort(), [entries]);
  const entityTypes = useMemo(() => [...new Set(entries.map((entry) => entry.entity_type).filter(Boolean))].sort(), [entries]);

  const filteredEntries = useMemo(() => entries.filter((entry) => {
    if (filters.user !== 'ALL' && String(entry.user_id) !== filters.user) return false;
    if (filters.action !== 'ALL' && entry.action !== filters.action) return false;
    if (filters.source !== 'ALL' && entry.source !== filters.source) return false;
    if (filters.entity !== 'ALL' && entry.entity_type !== filters.entity) return false;
    const day = entry.timestamp ? new Date(entry.timestamp).toISOString().slice(0, 10) : '';
    if (filters.from && day < filters.from) return false;
    if (filters.to && day > filters.to) return false;
    return true;
  }), [entries, filters]);

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <main className="activity-page">
      <PageHeader
        eyebrow="Governance and traceability"
        title="Activity / Audit"
        description="A record of who performed operational actions, when they occurred, and which channel was used."
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Activity' }]}
      />

      <section className="activity-filters" aria-label="Audit filters">
        <label><span>User</span><select value={filters.user} onChange={(event) => updateFilter('user', event.target.value)}>
          <option value="ALL">All users</option>{users.map((user) => <option key={user.id} value={user.id}>{user.username}</option>)}<option value="null">System</option>
        </select></label>
        <label><span>Action</span><select value={filters.action} onChange={(event) => updateFilter('action', event.target.value)}>
          <option value="ALL">All actions</option>{actions.map((action) => <option key={action} value={action}>{actionLabel(action)}</option>)}
        </select></label>
        <label><span>Source</span><select value={filters.source} onChange={(event) => updateFilter('source', event.target.value)}>
          <option value="ALL">All sources</option>{sources.map((source) => <option key={source} value={source}>{source}</option>)}
        </select></label>
        <label><span>Date from</span><input type="date" value={filters.from} onChange={(event) => updateFilter('from', event.target.value)} /></label>
        <label><span>Date to</span><input type="date" value={filters.to} onChange={(event) => updateFilter('to', event.target.value)} /></label>
        <label><span>Entity type</span><select value={filters.entity} onChange={(event) => updateFilter('entity', event.target.value)}>
          <option value="ALL">All entities</option>{entityTypes.map((type) => <option key={type} value={type}>{type}</option>)}
        </select></label>
      </section>

      <Card title="Audit Timeline" className="activity-table-card" actions={<span className="activity-count">{resource.loading ? 'Loading' : `${filteredEntries.length} events · up to 500 newest`}</span>}>
        {resource.loading ? <LoadingState label="Loading audit records" /> :
          resource.error ? <ApiErrorState error={resource.error} onRetry={() => setReloadKey((key) => key + 1)} /> :
              filteredEntries.length ? (
                <DataTable
                  rowKey="audit_id"
                  rows={filteredEntries}
                  columns={[
                    { key: 'timestamp', label: 'Time', render: (entry) => formatDate(entry.timestamp) },
                    { key: 'username', label: 'User', render: (entry) => entry.username || (entry.user_id ? `User #${entry.user_id}` : 'System') },
                    { key: 'action', label: 'Action', render: (entry) => <span className="activity-action">{actionLabel(entry.action)}</span> },
                    { key: 'entity_type', label: 'Entity', render: (entry) => <StatusBadge status={entry.entity_type} /> },
                    { key: 'entity_id', label: 'Entity ID', render: (entry) => entry.entity_id || '—' },
                    { key: 'source', label: 'Source', render: (entry) => <span className="activity-source">{entry.source}</span> },
                  ]}
                />
              ) : <EmptyState title={entries.length ? 'No audit events match these filters' : 'No audit events recorded'} description={entries.length ? 'Adjust the filters to see other audit events.' : 'Backend-recorded actions will appear here.'} />}
      </Card>
    </main>
  );
}
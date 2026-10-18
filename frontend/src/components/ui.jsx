import { useEffect, useRef } from 'react';
import { ArrowLeft, Home as HomeIcon, X } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

export function Button({ children, variant = 'primary', className = '', type = 'button', ...props }) {
  return (
    <button className={`button button--${variant} ${className}`.trim()} type={type} {...props}>
      {children}
    </button>
  );
}

export function StatusBadge({ status, children }) {
  const value = String(status || children || 'unknown').toLowerCase().replaceAll(/[^a-z0-9]+/g, '-');
  return <span className={`status-badge status-badge--${value}`}>{children || status}</span>;
}

export function RiskBadge({ risk }) {
  const value = String(risk || 'unknown').toLowerCase();
  return <span className={`risk-badge risk-badge--${value}`} aria-label={`Risk level: ${risk}`}>{risk}</span>;
}

export function MetricCard({ label, value, detail, icon: Icon }) {
  return (
    <article className="metric-card">
      <div className="metric-card__top">
        <span>{label}</span>
        {Icon && <Icon aria-hidden="true" size={18} />}
      </div>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </article>
  );
}

export function Card({ title, actions, children, className = '' }) {
  return (
    <section className={`card ${className}`.trim()}>
      {(title || actions) && (
        <header className="card__header">
          {title && <h2>{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function DataTable({ columns, rows, rowKey = 'id', emptyMessage = 'No records to display.' }) {
  if (!rows.length) return <EmptyState title={emptyMessage} />;
  return (
    <div className="data-table-wrap" role="region" aria-label="Scrollable data table" tabIndex={0}>
      <table className="data-table">
        <thead>
          <tr>{columns.map((column) => <th key={column.key} scope="col">{column.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row[rowKey] ?? index}>
              {columns.map((column) => (
                <td key={column.key}>{column.render ? column.render(row) : row[column.key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Modal({ open, title, onClose, children, size = 'medium' }) {
  const dialogRef = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return undefined;

    const previouslyFocused = document.activeElement;
    const bodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const focusFrame = window.requestAnimationFrame(() => {
      const firstFocusable = dialogRef.current?.querySelector(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
      );
      (firstFocusable || dialogRef.current)?.focus();
    });

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        closeRef.current?.();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
      )].filter((element) => element.getClientRects().length > 0);
      if (!focusable.length) {
        event.preventDefault();
        dialogRef.current.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialogRef.current.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialogRef.current.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      window.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = bodyOverflow;
      if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) previouslyFocused.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section ref={dialogRef} className={`modal modal--${size}`} role="dialog" aria-modal="true" aria-labelledby="modal-title" tabIndex={-1}>
        <header className="modal__header">
          <h2 id="modal-title">{title}</h2>
          <Button variant="icon" aria-label="Close dialog" onClick={onClose}><X size={18} /></Button>
        </header>
        {children}
      </section>
    </div>
  );
}

export function ConfirmDialog({ open, title, message, confirmLabel = 'Confirm', onConfirm, onCancel }) {
  return (
    <Modal open={open} title={title} onClose={onCancel} size="small">
      <p className="dialog-message">{message}</p>
      <div className="dialog-actions">
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button variant="danger" onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </Modal>
  );
}

export function Toast({ message, kind = 'info', onDismiss }) {
  return (
    <div className={`toast toast--${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      <span>{message}</span>
      <Button variant="icon" aria-label="Dismiss notification" onClick={onDismiss}><X size={16} /></Button>
    </div>
  );
}

export function LoadingState({ label = 'Loading' }) {
  return <div className="state-panel" role="status"><span className="loading-indicator" />{label}</div>;
}

export function EmptyState({ title, description, action }) {
  return <div className="state-panel"><h2>{title}</h2>{description && <p>{description}</p>}{action}</div>;
}

export function ErrorState({ title = 'Page not found', description, action }) {
  return <div className="state-panel state-panel--error" role="alert"><h2>{title}</h2>{description && <p>{description}</p>}{action}</div>;
}

export function ApiErrorState({ error, onRetry, action }) {
  const code = typeof error === 'string' ? error : error?.message;
  const states = {
    NETWORK_ERROR: ['Connection problem', 'The service could not be reached. Check your connection and try again.'],
    AUTH_REQUIRED: ['Sign-in required', 'Your session is unavailable or has expired. Sign in to continue.'],
    API_403: ['Access restricted', 'Your account does not have permission to view this information.'],
    API_404: ['Record not found', 'The requested record is no longer available.'],
  };
  const mapped = states[code] || ['Service unavailable', 'The request could not be completed. Please try again shortly.'];
  const retryAction = code === 'AUTH_REQUIRED'
    ? <Link className="button button--primary" to="/login">Sign in</Link>
    : code === 'API_403'
      ? <Link className="button button--secondary" to="/dashboard">Back to Dashboard</Link>
      : onRetry && <Button variant="secondary" onClick={onRetry}>Retry</Button>;
  return <ErrorState title={mapped[0]} description={mapped[1]} action={action || retryAction} />;
}

export function Breadcrumbs({ items = [], homeTo = '/' }) {
  const navigate = useNavigate();
  const backFallback = items.find((item) => item.to)?.to || homeTo;

  function goBack() {
    const currentIndex = window.history.state?.idx;
    navigate(typeof currentIndex === 'number' && currentIndex > 0 ? -1 : backFallback);
  }

  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <Button variant="text" onClick={goBack}><ArrowLeft size={15} />Back</Button>
      <Link to={homeTo} aria-label="Home"><HomeIcon size={15} /></Link>
      {items.map((item, index) => (
        <span className="breadcrumbs__item" key={`${item.label}-${index}`}>
          <span aria-hidden="true">/</span>
          {item.to && index < items.length - 1 ? <Link to={item.to}>{item.label}</Link> : <span aria-current="page">{item.label}</span>}
        </span>
      ))}
    </nav>
  );
}

export function PageHeader({ eyebrow, title, description, actions, breadcrumbs }) {
  return (
    <header className="page-header">
      {breadcrumbs && <Breadcrumbs items={breadcrumbs} />}
      <div className="page-header__row">
        <div>
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <h1>{title}</h1>
          {description && <p className="page-header__description">{description}</p>}
        </div>
        {actions && <div className="page-header__actions">{actions}</div>}
      </div>
    </header>
  );
}

export function ToastViewport({ toasts, dismiss }) {
  return (
    <div className="toast-viewport" aria-live="polite" aria-relevant="additions">
      {toasts.map((toast) => <Toast key={toast.id} {...toast} onDismiss={() => dismiss(toast.id)} />)}
    </div>
  );
}
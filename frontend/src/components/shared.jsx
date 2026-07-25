/** Small presentational pieces shared across views. */

import { CONFIDENCE_META, STATUS_META } from '../format';

export function ConfidenceBadge({ value }) {
  if (!value) return null;
  const meta = CONFIDENCE_META[value] || { label: value, cls: '' };
  return <span className={`badge ${meta.cls}`}>{meta.label}</span>;
}

export function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.UNVERIFIED;
  return <span className={`badge ${meta.cls}`}>{meta.label}</span>;
}

export function Stat({ label, value, hint, accent }) {
  return (
    <div className={`stat ${accent ? `stat-accent-${accent}` : ''}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function BarChart({ data, max }) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) {
    return <div className="muted" style={{ fontSize: 'var(--text-sm)' }}>No data yet.</div>;
  }
  const ceiling = max || Math.max(...entries.map(([, v]) => v));
  return (
    <div>
      {entries.slice(0, 8).map(([label, count]) => (
        <div className="bar-row" key={label}>
          <span
            title={label}
            style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          >
            {label}
          </span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(count / ceiling) * 100}%` }} />
          </div>
          <span className="bar-count">{count}</span>
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ title, children, action }) {
  return (
    <div className="card empty">
      <h3>{title}</h3>
      {children && <p className="muted">{children}</p>}
      {action}
    </div>
  );
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="row" style={{ padding: 'var(--sp-5)', color: 'var(--text-secondary)' }}>
      <div className="spinner" />
      <span>{label}</span>
    </div>
  );
}

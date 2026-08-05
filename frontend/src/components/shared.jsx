/** Small presentational pieces shared across views. */

import { CONFIDENCE_META, STATUS_META, urgencyMeta } from '../format';

export function ConfidenceBadge({ value }) {
  if (!value) return null;
  const meta = CONFIDENCE_META[value] || { label: value, cls: '' };
  return <span className={`badge ${meta.cls}`}>{meta.label}</span>;
}

export function DeadlineBadge({ matter }) {
  const meta = urgencyMeta(matter?.urgency);
  const label = matter?.deadline_label;
  if (!label) return <span className="muted">—</span>;
  return (
    <span className={`badge ${meta.cls}`} title={label}>
      {label}
    </span>
  );
}

/**
 * A capability the deployment is missing, stated where a user will see it.
 *
 * The retired free tier failed silently in production for weeks because the
 * only signal was a startup log and a health endpoint, and nobody reads
 * either. Anything that stops the product working has to appear in the
 * product.
 */
export function CapabilityWarning({ title, children }) {
  return (
    <div className="alert alert-warning" style={{ marginBottom: 'var(--sp-5)' }}>
      <strong>{title}</strong> {children}
    </div>
  );
}

export function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.UNVERIFIED;
  return <span className={`badge ${meta.cls}`}>{meta.label}</span>;
}

/**
 * The text a field was read from, shown beside the field.
 *
 * Checking extraction is the slowest step in using this product and the one
 * that decides whether a firm trusts it. What made it slow was reading a
 * value off a form and then hunting through twenty pages of PDF for the
 * sentence it came from. With the source in place the reviewer confirms or
 * corrects without opening the notice at all.
 *
 * A field read by OCR is marked, because a figure recovered from a picture of
 * a notice is a proposal and a figure lifted from its text layer is the
 * document. That distinction has to survive all the way to the person
 * signing.
 */
export function SourceSnippet({ snippet, origin }) {
  if (!snippet?.text) return null;
  const scanned = snippet.scanned || String(origin || '').endsWith('-ocr');
  return (
    <div className={`source-snippet ${scanned ? 'source-snippet-scanned' : ''}`}>
      {scanned && <span className="badge badge-warning">read by OCR — check</span>}
      <span className="source-snippet-text">
        {snippet.truncated_start && '… '}
        {snippet.text}
        {snippet.truncated_end && ' …'}
      </span>
    </div>
  );
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

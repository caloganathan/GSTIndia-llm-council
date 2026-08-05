import { useEffect, useState } from 'react';
import { api } from '../api';
import { ConfidenceBadge, DeadlineBadge, EmptyState, Loading } from './shared';
import { formatCurrency, formatDate } from '../format';

export default function MatterList({ user, onOpenMatter, onNewMatter, onAuthError }) {
  const [matters, setMatters] = useState(null);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');

  const load = async () => {
    try {
      setMatters(await api.listMatters());
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const remove = async (event, id) => {
    event.stopPropagation();
    if (!window.confirm('Delete this matter and its deliberation permanently?')) return;
    try {
      await api.deleteMatter(id);
      setMatters((list) => list.filter((m) => m.id !== id));
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    }
  };

  if (error) return <div className="page"><div className="alert alert-danger">{error}</div></div>;
  if (!matters) return <div className="page"><Loading /></div>;

  const term = query.trim().toLowerCase();
  const filtered = term
    ? matters.filter((m) =>
        [m.client_name, m.notice_type, m.state, m.tax_period]
          .filter(Boolean)
          .some((v) => String(v).toLowerCase().includes(term))
      )
    : matters;

  const canDelete = user?.permissions?.delete_matters;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Matters</h1>
          <div className="page-subtitle">
            {matters.length} matter{matters.length === 1 ? '' : 's'} on file
          </div>
        </div>
        <button className="btn btn-primary" onClick={onNewMatter}>New matter</button>
      </div>

      {matters.length > 0 && (
        <div style={{ marginBottom: 'var(--sp-4)', maxWidth: 340 }}>
          <input
            type="text"
            placeholder="Search client, notice type, state…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      )}

      {filtered.length === 0 ? (
        <EmptyState
          title={matters.length === 0 ? 'No matters yet' : 'No matches'}
          action={
            matters.length === 0 && (
              <button className="btn btn-primary" onClick={onNewMatter}>
                Run your first panel
              </button>
            )
          }
        >
          {matters.length === 0
            ? 'Enter a GST notice and let the panel deliberate.'
            : 'Try a different search term.'}
        </EmptyState>
      ) : (
        <div className="card table-wrap">
          <table>
            <thead>
              <tr>
                <th>Client</th>
                <th>Reply due</th>
                <th>Notice</th>
                <th>State</th>
                <th>Period</th>
                <th>Amount</th>
                <th>Position</th>
                <th>Verification</th>
                <th>Created</th>
                {canDelete && <th />}
              </tr>
            </thead>
            <tbody>
              {filtered.map((matter) => {
                const v = matter.verification_summary;
                return (
                  <tr
                    key={matter.id}
                    onClick={() => onOpenMatter(matter.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ fontWeight: 500 }}>{matter.client_name || 'Unnamed'}</td>
                    <td><DeadlineBadge matter={matter} /></td>
                    <td><span className="badge">{matter.notice_type || '—'}</span></td>
                    <td>{matter.state || '—'}</td>
                    <td>{matter.tax_period || '—'}</td>
                    <td>{formatCurrency(matter.amount_disputed)}</td>
                    <td><ConfidenceBadge value={matter.confidence} /></td>
                    <td>
                      {v ? (
                        <span className="row" style={{ gap: 4 }}>
                          <span className="badge badge-success">{v.verified}</span>
                          {v.superseded > 0 && (
                            <span className="badge badge-danger">{v.superseded}</span>
                          )}
                          {v.unverified > 0 && (
                            <span className="badge badge-warning">{v.unverified}</span>
                          )}
                          {v.not_found > 0 && (
                            <span className="badge badge-danger">{v.not_found}</span>
                          )}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td className="muted">{formatDate(matter.created_at)}</td>
                    {canDelete && (
                      <td>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={(e) => remove(e, matter.id)}
                          title="Delete matter"
                        >
                          ×
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

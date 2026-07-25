import { useEffect, useState } from 'react';
import { api } from '../api';
import { BarChart, ConfidenceBadge, EmptyState, Loading, Stat } from './shared';
import { formatCost, formatCurrency, formatDate } from '../format';

export default function Dashboard({ user, onOpenMatter, onNewMatter, onAuthError }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        setData(await api.dashboard());
      } catch (err) {
        if (!onAuthError(err)) setError(err.message);
      }
    })();
  }, [onAuthError]);

  if (error) return <div className="page"><div className="alert alert-danger">{error}</div></div>;
  if (!data) return <div className="page"><Loading /></div>;

  const { verification } = data;
  const checked =
    verification.verified + verification.unverified + verification.not_found;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <div className="page-subtitle">
            Welcome back{user?.name ? `, ${user.name}` : ''}. Here is where the
            practice stands.
          </div>
        </div>
        <button className="btn btn-primary" onClick={onNewMatter}>
          New matter
        </button>
      </div>

      <div className="stat-grid">
        <Stat
          label="Matters"
          value={data.matter_count}
          hint={`${data.completed} deliberated`}
        />
        <Stat
          label="Authorities verified"
          value={verification.verified}
          hint={checked ? `of ${checked} checked` : 'none checked yet'}
          accent="success"
        />
        <Stat
          label="Unverified"
          value={verification.unverified}
          hint="require manual confirmation"
          accent="warning"
        />
        <Stat
          label="Not found"
          value={verification.not_found}
          hint="remove before filing"
          accent={verification.not_found > 0 ? 'danger' : undefined}
        />
        {data.usage && (
          <Stat
            label="Model spend"
            value={formatCost(data.usage.total_cost)}
            hint={`${(data.usage.total_tokens || 0).toLocaleString()} tokens`}
          />
        )}
        <Stat
          label="Open risk flags"
          value={data.risk_flags}
          hint="raised across all matters"
          accent={data.risk_flags > 0 ? 'warning' : undefined}
        />
      </div>

      {verification.not_found > 0 && (
        <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-5)' }}>
          <strong>{verification.not_found} authority(ies) could not be located.</strong>{' '}
          A citation that cannot be found must be treated as fabricated until
          proven otherwise. Review the affected matters before anything is filed.
        </div>
      )}

      <div className="grid-2" style={{ marginBottom: 'var(--sp-5)' }}>
        <div className="card card-pad">
          <div className="section-title">Matters by state</div>
          <BarChart data={data.by_state} />
        </div>
        <div className="card card-pad">
          <div className="section-title">Matters by notice type</div>
          <BarChart data={data.by_notice_type} />
        </div>
      </div>

      <div className="card">
        <div className="card-pad" style={{ paddingBottom: 0 }}>
          <div className="section-title">Recent matters</div>
        </div>
        {data.recent.length === 0 ? (
          <EmptyState
            title="No matters yet"
            action={
              <button className="btn btn-primary" onClick={onNewMatter}>
                Run your first panel
              </button>
            }
          >
            Start by entering a GST notice and letting the panel deliberate.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Client</th>
                  <th>Notice</th>
                  <th>State</th>
                  <th>Period</th>
                  <th>Amount</th>
                  <th>Position</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {data.recent.map((matter) => (
                  <tr
                    key={matter.id}
                    onClick={() => onOpenMatter(matter.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ fontWeight: 500 }}>{matter.client_name || 'Unnamed'}</td>
                    <td><span className="badge">{matter.notice_type || '—'}</span></td>
                    <td>{matter.state || '—'}</td>
                    <td>{matter.tax_period || '—'}</td>
                    <td>{formatCurrency(matter.amount_disputed)}</td>
                    <td><ConfidenceBadge value={matter.confidence} /></td>
                    <td className="muted">{formatDate(matter.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

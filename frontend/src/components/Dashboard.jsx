import { useEffect, useState } from 'react';
import { api } from '../api';
import {
  BarChart, CapabilityWarning, ConfidenceBadge, DeadlineBadge, EmptyState,
  Loading, Stat,
} from './shared';
import { formatCost, formatCurrency, formatDate } from '../format';

export default function Dashboard({ user, onOpenMatter, onNewMatter, onAuthError }) {
  const [data, setData] = useState(null);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        setData(await api.dashboard());
      } catch (err) {
        if (!onAuthError(err)) setError(err.message);
      }
      // Health is advisory. A failure here must never blank the dashboard,
      // so it is fetched separately and its errors are swallowed.
      try {
        setHealth(await api.health());
      } catch {
        /* the dashboard is still useful without it */
      }
    })();
  }, [onAuthError]);

  if (error) return <div className="page"><div className="alert alert-danger">{error}</div></div>;
  if (!data) return <div className="page"><Loading /></div>;

  const { verification } = data;
  // SUPERSEDED was in neither the sum nor a tile, so "of N checked"
  // undercounted and the status format.js says must be surfaced "as loudly as
  // a fabrication" was invisible on the one screen a partner scans daily.
  const superseded = verification.superseded || 0;
  const checked =
    (verification.verified || 0) + superseded +
    (verification.unverified || 0) + (verification.not_found || 0);
  const deadlines = data.deadlines || { counts: {}, upcoming: [] };
  const staleModels = health?.model_validation?.unknown_models || [];
  const ocrMissing = health?.ocr && health.ocr.available === false;

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

      {staleModels.length > 0 && (
        <CapabilityWarning title={`${staleModels.length} configured model(s) are not in OpenRouter's catalogue.`}>
          Runs using them will fail — and notice reading fails with them,
          because the reader borrows the tier's grounding model. Correct these
          in Administration &rsaquo; Panel configuration before running a
          matter: <code>{staleModels.join(', ')}</code>
        </CapabilityWarning>
      )}

      {ocrMissing && (
        <CapabilityWarning title="Scanned notices cannot be read on this installation.">
          {health.ocr.reason} Until then, a notice that arrives as an image
          must have its text pasted in by hand.
        </CapabilityWarning>
      )}

      {deadlines.attention > 0 && (
        <div
          className={`alert ${deadlines.counts.overdue > 0 ? 'alert-danger' : 'alert-warning'}`}
          style={{ marginBottom: 'var(--sp-5)' }}
        >
          <strong>
            {deadlines.counts.overdue > 0
              ? `${deadlines.counts.overdue} matter(s) are past their reply date.`
              : `${deadlines.attention} matter(s) need a reply this week.`}
          </strong>{' '}
          A reply date that passes turns a reply into an appeal, with a
          pre-deposit and a fresh limitation clock. Matters needing attention
          are listed below.
        </div>
      )}

      <div className="stat-grid">
        <Stat
          label="Needs attention"
          value={deadlines.attention || 0}
          hint={
            deadlines.counts.overdue
              ? `${deadlines.counts.overdue} already overdue`
              : 'due within seven days'
          }
          accent={
            deadlines.counts.overdue > 0
              ? 'danger'
              : deadlines.attention > 0
                ? 'warning'
                : undefined
          }
        />
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
          label="Superseded"
          value={superseded}
          hint="no longer good law — replace"
          accent={superseded > 0 ? 'danger' : undefined}
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
            // Rupees lead. A firm prices its engagements in rupees and nobody
            // in the office converts dollars, so a dollar figure is a number
            // that never becomes an intuition about cost.
            value={data.usage.label || formatCost(data.usage.total_cost)}
            hint={`${formatCost(data.usage.total_cost)} · ${(data.usage.total_tokens || 0).toLocaleString()} tokens`}
          />
        )}
        <Stat
          label="Open risk flags"
          value={data.risk_flags}
          hint="raised across all matters"
          accent={data.risk_flags > 0 ? 'warning' : undefined}
        />
      </div>

      {(verification.not_found > 0 || superseded > 0) && (
        <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-5)' }} role="alert">
          {verification.not_found > 0 && (
            <div>
              <strong>{verification.not_found} authority(ies) could not be located.</strong>{' '}
              A citation that cannot be found must be treated as fabricated
              until proven otherwise.
            </div>
          )}
          {superseded > 0 && (
            <div style={{ marginTop: verification.not_found > 0 ? 6 : 0 }}>
              <strong>{superseded} authority(ies) are no longer good law.</strong>{' '}
              These read as sound authority to a reviewer, which is what makes
              them more dangerous than a citation that plainly does not exist.
            </div>
          )}
          <div style={{ marginTop: 6 }}>
            Review the affected matters before anything is filed.
          </div>
        </div>
      )}

      {deadlines.upcoming.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <div
            className="card-pad row"
            style={{ paddingBottom: 0, justifyContent: 'space-between' }}
          >
            <div className="section-title">Replies due — worst first</div>
            <button
              className="btn btn-secondary"
              onClick={() => api.downloadCalendar()}
              title="Opens in Outlook, Google Calendar or Apple Calendar"
            >
              Add to calendar
            </button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Client</th>
                  <th>Notice</th>
                  <th>Reply due</th>
                  <th>Status</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                {deadlines.upcoming.map((matter) => (
                  <tr
                    key={matter.id}
                    onClick={() => onOpenMatter(matter.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ fontWeight: 500 }}>
                      {matter.client_name || 'Unnamed'}
                    </td>
                    <td><span className="badge">{matter.notice_type || '—'}</span></td>
                    <td>{formatDate(matter.due_date)}</td>
                    <td><DeadlineBadge matter={matter} /></td>
                    <td>{formatCurrency(matter.amount_disputed)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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

import { useEffect, useState } from 'react';
import { api } from '../api';
import Deliberation from './Deliberation';
import { Loading } from './shared';
import { formatCurrency, formatDate } from '../format';

export default function MatterDetail({ matterId, user, onBack, onAuthError }) {
  const [matter, setMatter] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!matterId) return;
    (async () => {
      try {
        setMatter(await api.getMatter(matterId));
      } catch (err) {
        if (!onAuthError(err)) setError(err.message);
      }
    })();
  }, [matterId, onAuthError]);

  // Two documents, never one. The reply is filed with the department; the
  // file note records the firm's own assessment and must not leave the office.
  const download = async (document) => {
    try {
      await api.downloadMatter(matterId, null, document);
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    }
  };

  // A failed LOAD has nothing to show, so it still takes the page. A failed
  // download does not: replacing the whole matter with an alert threw away
  // everything the reviewer was reading, with no route back but the Matters
  // button. Those are rendered inline below instead.
  if (error && !matter) {
    return (
      <div className="page">
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← Matters</button>
        <div className="alert alert-danger" style={{ marginTop: 16 }} role="alert">{error}</div>
      </div>
    );
  }
  if (!matter) return <div className="page"><Loading /></div>;

  const intake = matter.intake || {};
  // A matter is only finished when the panel completed. Anything else —
  // an abandoned run, a crashed one, a tab closed mid-deliberation — was
  // rendering as a finished matter with live export buttons that 400 on
  // "Panel has not completed for this matter".
  const isComplete = matter.status === 'complete';
  const canExport =
    isComplete && user?.permissions?.export &&
    matter.metadata?.allow_export !== false;

  return (
    <div className="page">
      <button className="btn btn-ghost btn-sm" onClick={onBack} style={{ marginBottom: 12 }}>
        ← Matters
      </button>

      <div className="page-header">
        <div>
          <h1 className="page-title">{intake.client_name || 'Matter'}</h1>
          <div className="page-subtitle">
            {intake.notice_type} · {intake.state} · {intake.tax_period}
          </div>
        </div>
        {canExport ? (
          <div className="row" style={{ gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
            <button className="btn btn-primary" onClick={() => download('reply')}>
              Download reply (for filing)
            </button>
            <button className="btn btn-secondary" onClick={() => download('file_note')}>
              Download file note (internal)
            </button>
          </div>
        ) : isComplete && (
          // Buttons that simply vanish read as a broken page. Say why.
          <div className="muted" style={{ fontSize: 'var(--text-sm)', maxWidth: 260 }}>
            {user?.permissions?.export
              ? 'This matter was run on a tier that does not permit export.'
              : 'Export is restricted to partners and managers.'}
          </div>
        )}
      </div>

      {error && (
        <div className="alert alert-danger" role="alert"
             style={{ marginBottom: 'var(--sp-4)',
                      display: 'flex', justifyContent: 'space-between',
                      gap: 'var(--sp-3)' }}>
          <span>{error}</span>
          <button className="btn btn-ghost btn-sm" onClick={() => setError('')}
                  aria-label="Dismiss this message">Dismiss</button>
        </div>
      )}

      {!isComplete && (
        <div className="alert alert-warning" role="alert"
             style={{ marginBottom: 'var(--sp-4)' }}>
          <strong>The panel did not complete for this matter.</strong> The
          deliberation was interrupted before a determination was settled, so
          there is nothing to export and nothing to file. Re-run it from New
          Matter. A run takes two to four minutes and does not survive the tab
          being closed.
        </div>
      )}

      <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
        <div className="section-title">Notice particulars</div>
        <div className="detail-grid">
          <div><span className="muted">Notice type</span><div>{intake.notice_type || '—'}</div></div>
          <div><span className="muted">Section invoked</span><div>{intake.section_invoked || '—'}</div></div>
          <div><span className="muted">State</span><div>{intake.state || '—'}</div></div>
          <div><span className="muted">Tax period</span><div>{intake.tax_period || '—'}</div></div>
          <div><span className="muted">Amount in dispute</span><div>{formatCurrency(intake.amount_disputed)}</div></div>
          <div><span className="muted">Notice date</span><div>{formatDate(intake.notice_date)}</div></div>
          <div><span className="muted">Reply due</span><div>{formatDate(intake.due_date)}</div></div>
          <div><span className="muted">GSTIN</span><div className="mono">{intake.gstin || '—'}</div></div>
        </div>

        {intake.issues && (
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <div className="section-title">Issues raised</div>
            <div className="draft-body">{intake.issues}</div>
          </div>
        )}
      </div>

      {matter.result?._redacted && (
        <div className="alert alert-info" style={{ marginBottom: 'var(--sp-5)' }}>
          The counsel deliberation is restricted to partners and managers. The
          determination and verification trail are shown below.
        </div>
      )}

      {/* Export lives in the page header here, so it is not repeated inline. */}
      <Deliberation
        result={matter.result || {}}
        metadata={matter.metadata}
        user={user}
      />
    </div>
  );
}

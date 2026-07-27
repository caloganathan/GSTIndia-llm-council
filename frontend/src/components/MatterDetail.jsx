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

  if (error) {
    return (
      <div className="page">
        <button className="btn btn-ghost btn-sm" onClick={onBack}>← Matters</button>
        <div className="alert alert-danger" style={{ marginTop: 16 }}>{error}</div>
      </div>
    );
  }
  if (!matter) return <div className="page"><Loading /></div>;

  const intake = matter.intake || {};
  const canExport =
    user?.permissions?.export && matter.metadata?.allow_export !== false;

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
        {canExport && (
          <div className="row" style={{ gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
            <button className="btn btn-primary" onClick={() => download('reply')}>
              Download reply (for filing)
            </button>
            <button className="btn btn-secondary" onClick={() => download('file_note')}>
              Download file note (internal)
            </button>
          </div>
        )}
      </div>

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

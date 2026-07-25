import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { ConfidenceBadge, StatusBadge } from './shared';
import { ROLE_COLOUR, formatCost } from '../format';

function CounselTabs({ analyses, crossExams }) {
  const [active, setActive] = useState(0);
  const [showCross, setShowCross] = useState(false);

  if (!analyses?.length) return null;
  const current = analyses[active];
  const cross = (crossExams || []).find((c) => c.key === current.key);

  return (
    <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
      <div className="counsel-tabs">
        {analyses.map((entry, index) => (
          <button
            key={entry.key}
            className={`counsel-tab ${active === index ? 'active' : ''}`}
            onClick={() => setActive(index)}
            style={{ '--role-colour': ROLE_COLOUR[entry.key] }}
          >
            {entry.short_title}
          </button>
        ))}
      </div>

      <div className="card-pad">
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 'var(--sp-3)' }}>
          <div>
            <div style={{ fontWeight: 600, color: ROLE_COLOUR[current.key] }}>
              {current.title}
            </div>
            <div className="muted mono" style={{ fontSize: 'var(--text-xs)' }}>
              {current.model}
            </div>
          </div>
          {cross && (
            <button
              className="btn btn-sm"
              onClick={() => setShowCross((v) => !v)}
            >
              {showCross ? 'Opening analysis' : 'Cross-examination'}
            </button>
          )}
        </div>

        <div className="markdown-content">
          <ReactMarkdown>
            {showCross && cross ? cross.analysis : current.analysis}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

function Authorities({ verification }) {
  if (!verification?.authorities?.length) {
    return (
      <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
        <div className="section-title">Authorities</div>
        <div className="muted">
          {verification?.note || 'No authorities were extracted.'}
        </div>
      </div>
    );
  }

  const s = verification.summary || {};
  return (
    <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
      <div className="card-pad" style={{ paddingBottom: 'var(--sp-3)' }}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div className="section-title" style={{ margin: 0 }}>
            Authorities and verification
          </div>
          <div className="row" style={{ gap: 'var(--sp-2)' }}>
            <span className="badge badge-success">{s.verified || 0} verified</span>
            <span className="badge badge-warning">{s.unverified || 0} unverified</span>
            {(s.not_found || 0) > 0 && (
              <span className="badge badge-danger">{s.not_found} not found</span>
            )}
          </div>
        </div>
        {verification.note && (
          <div
            className={`alert ${(s.not_found || 0) > 0 ? 'alert-danger' : 'alert-info'}`}
            style={{ marginTop: 'var(--sp-3)' }}
          >
            {verification.note}
          </div>
        )}
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ width: '28%' }}>Citation</th>
              <th style={{ width: '24%' }}>Cited for</th>
              <th style={{ width: '13%' }}>Status</th>
              <th>Verifier note</th>
            </tr>
          </thead>
          <tbody>
            {verification.authorities.map((authority, index) => (
              <tr key={index}>
                <td style={{ fontWeight: 500 }}>{authority.citation}</td>
                <td className="muted">{authority.proposition || '—'}</td>
                <td><StatusBadge status={authority.status} /></td>
                <td className="muted" style={{ fontSize: 'var(--text-sm)' }}>
                  {authority.note}
                  {authority.correction && (
                    <div style={{ marginTop: 4, color: 'var(--warning)' }}>
                      Suggested: {authority.correction}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Deliberation({ result, metadata, user, onExport }) {
  const determination = result?.determination;
  const canSeeDeliberation = user?.permissions?.view_deliberation !== false;

  if (!determination) {
    return canSeeDeliberation ? (
      <CounselTabs analyses={result?.analyses} crossExams={result?.cross_exams} />
    ) : null;
  }

  const failures = [
    ...(metadata?.failures?.stage1 || []),
    ...(metadata?.failures?.stage2 || []),
  ];

  return (
    <>
      {metadata?.watermark && (
        <div className="alert alert-warning" style={{ marginBottom: 'var(--sp-5)' }}>
          <strong>{metadata.watermark}</strong> — this run used free endpoints in
          anonymised mode. Use the Pro tier to produce an exportable reply pack.
        </div>
      )}

      {determination._degraded && (
        <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-5)' }}>
          The chairman did not return a usable determination. The counsel
          analyses below are still valid, but this output must not be filed.
        </div>
      )}

      {failures.length > 0 && (
        <div className="alert alert-warning" style={{ marginBottom: 'var(--sp-5)' }}>
          {failures.map((f, i) => (
            <div key={i}>{f.role} unavailable ({f.model}): {f.error}</div>
          ))}
        </div>
      )}

      {/* Determination */}
      <div className="card card-pad determination" style={{ marginBottom: 'var(--sp-5)' }}>
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 'var(--sp-3)' }}>
          <div className="section-title" style={{ margin: 0 }}>
            Chairman's determination
          </div>
          <div className="row" style={{ gap: 'var(--sp-2)' }}>
            <ConfidenceBadge value={determination.confidence} />
            {onExport && (
              <button className="btn btn-primary btn-sm" onClick={onExport}>
                Export reply pack
              </button>
            )}
          </div>
        </div>

        <p style={{ fontSize: 'var(--text-lg)', lineHeight: 1.6, marginTop: 0 }}>
          {determination.recommended_position}
        </p>

        {determination.lead_argument && (
          <div className="alert alert-info">
            <strong>Lead argument.</strong> {determination.lead_argument}
          </div>
        )}
      </div>

      {/* Risk */}
      {determination.risk_flags?.length > 0 && (
        <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
          <div className="section-title">Risk flags for the signing partner</div>
          <ul style={{ margin: 0, paddingLeft: 'var(--sp-5)' }}>
            {determination.risk_flags.map((flag, i) => (
              <li key={i} style={{ marginBottom: 6 }}>{flag}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Issues */}
      {determination.issues?.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
          <div className="card-pad" style={{ paddingBottom: 0 }}>
            <div className="section-title">Issue-wise analysis</div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Issue</th>
                  <th>Department's contention</th>
                  <th>Our position</th>
                  <th>Authority</th>
                  <th>Strength</th>
                </tr>
              </thead>
              <tbody>
                {determination.issues.map((issue, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 500 }}>{issue.issue}</td>
                    <td className="muted">{issue.department_view}</td>
                    <td>{issue.our_position}</td>
                    <td className="muted" style={{ fontSize: 'var(--text-sm)' }}>
                      {issue.authority}
                    </td>
                    <td><ConfidenceBadge value={issue.strength} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Authorities verification={result.verification} />

      {/* Draft reply */}
      {determination.draft_reply && (
        <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
          <div className="section-title">Draft reply</div>
          <div className="draft-body">{determination.draft_reply}</div>
        </div>
      )}

      {/* Panel disagreements */}
      {determination.panel_disagreements?.length > 0 && (
        <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
          <div className="section-title">Where the panel split</div>
          {determination.panel_disagreements.map((entry, i) => (
            <div key={i} className="disagreement">
              <div style={{ fontWeight: 600 }}>{entry.question}</div>
              <div className="muted" style={{ margin: '4px 0' }}>{entry.positions}</div>
              <div><strong>Ruling.</strong> {entry.resolution}</div>
            </div>
          ))}
        </div>
      )}

      {/* Documents + open questions */}
      {(determination.documents_to_collect?.length > 0 ||
        determination.open_questions?.length > 0) && (
        <div className="grid-2" style={{ marginBottom: 'var(--sp-5)' }}>
          {determination.documents_to_collect?.length > 0 && (
            <div className="card card-pad">
              <div className="section-title">Documents to collect</div>
              <ul style={{ margin: 0, paddingLeft: 'var(--sp-5)' }}>
                {determination.documents_to_collect.map((doc, i) => (
                  <li key={i}>{doc}</li>
                ))}
              </ul>
            </div>
          )}
          {determination.open_questions?.length > 0 && (
            <div className="card card-pad">
              <div className="section-title">Open questions</div>
              <ul style={{ margin: 0, paddingLeft: 'var(--sp-5)' }}>
                {determination.open_questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Board summary */}
      {determination.board_summary && (
        <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
          <div className="section-title">For the board / audit committee</div>
          <p style={{ margin: 0 }}>{determination.board_summary}</p>
        </div>
      )}

      {/* Counsel deliberation */}
      {canSeeDeliberation && (
        <>
          <div className="section-title" style={{ marginTop: 'var(--sp-6)' }}>
            The deliberation
          </div>
          <CounselTabs analyses={result.analyses} crossExams={result.cross_exams} />
        </>
      )}

      {/* Working note */}
      {determination.working_note && (
        <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
          <div className="section-title">Working note for the file</div>
          <div className="draft-body">{determination.working_note}</div>
        </div>
      )}

      {metadata?.usage && (
        <div className="muted" style={{ fontSize: 'var(--text-sm)', textAlign: 'right' }}>
          {metadata.tier_label} · {formatCost(metadata.usage.total_cost)} ·{' '}
          {(metadata.usage.total_tokens || 0).toLocaleString()} tokens
          {metadata.anonymised && ' · client identifiers were anonymised'}
        </div>
      )}
    </>
  );
}

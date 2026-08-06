import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import DefectList from './DefectList';
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
            {(s.superseded || 0) > 0 && (
              <span className="badge badge-danger">{s.superseded} superseded</span>
            )}
            <span className="badge badge-warning">{s.unverified || 0} unverified</span>
            {(s.not_found || 0) > 0 && (
              <span className="badge badge-danger">{s.not_found} not found</span>
            )}
          </div>
        </div>
        <div className="field-help" style={{ marginTop: 'var(--sp-2)' }}>
          Checked against public sources on the open web. This is not a
          licensed citator — an authority shown as Verified should still be
          read before it is relied on.
        </div>
        {verification.note && (
          <div
            className={`alert ${
              (s.not_found || 0) + (s.superseded || 0) > 0 ? 'alert-danger' : 'alert-info'
            }`}
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
                  {authority.as_of && (
                    <div style={{ marginTop: 2, fontSize: 'var(--text-xs)' }}>
                      As at: {authority.as_of}
                    </div>
                  )}
                  {authority.correction && (
                    <div style={{ marginTop: 4, color: 'var(--warning)' }}>
                      Now governed by: {authority.correction}
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

export default function Deliberation({ result, metadata, user }) {
  const determination = result?.determination;
  // Fail closed: the deliberation is privileged working material, so it is
  // shown only on a positive grant. Both auth paths (accounts and the legacy
  // shared token) supply a full permissions object, so a missing key means
  // something is wrong — and wrong must mean hidden, not shown. The server
  // redacts the stream and the stored matter for staff regardless; this
  // check only decides what the UI offers to render.
  const canSeeDeliberation = user?.permissions?.view_deliberation === true;
  const canSeeCosts = user?.permissions?.view_costs === true;

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
        <div className="alert alert-warning" style={{ marginBottom: 'var(--sp-5)' }} role="alert">
          {/* The old copy said this run "used free endpoints" and told the
              user to switch tiers "to produce an exportable reply pack".
              Both were false: the free tier was retired, and the draft tier
              exports — every page stamped with the line below. */}
          <strong>{metadata.watermark}</strong> — prepared on anonymised facts.
          This exports, and every page carries that stamp. Re-run on the Pro
          tier for a document intended for filing.
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
            {/* There is deliberately no export button here. The matter
                produces TWO documents with two audiences — the filing reply
                and the internal file note — and a single "Export reply pack"
                is the merge the whole export design exists to prevent. Both
                downloads live on the matter page, separately labelled. */}
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

      {/* Filing blockers — what must be resolved before this can be filed */}
      {determination.filing_blockers?.length > 0 && (
        <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
          <div className="section-title">Before this reply can be filed</div>
          <div className="alert alert-warning">
            <ul style={{ margin: 0, paddingLeft: 'var(--sp-5)' }}>
              {determination.filing_blockers.map((item, i) => (
                <li key={i} style={{ marginBottom: 6 }}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Defects — the reply is assembled from these, one limb at a time */}
      {determination.defects?.length > 0 && (
        <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
          <div className="section-title">Determination, defect by defect</div>
          <DefectList defects={determination.defects} readOnly />
        </div>
      )}

      {/* Preliminary submissions */}
      {determination.preliminary_submissions && (
        <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
          <div className="section-title">Preliminary submissions</div>
          <div className="draft-body">{determination.preliminary_submissions}</div>
        </div>
      )}

      <Authorities verification={result.verification} />

      {determination.unstructured_output && (
        <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
          <div className="section-title">Unstructured output</div>
          <div className="field-help" style={{ marginBottom: 'var(--sp-2)' }}>
            The determination could not be parsed into defects. Nothing is
            lost, but this matter must not be exported until it is re-run.
          </div>
          <div className="draft-body">{determination.unstructured_output}</div>
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
          {metadata.tier_label}
          {/* The listing and the dashboard strip cost for roles without
              view_costs; this line rendered it unconditionally, so what the
              firm pays per run reached a staff screen by another route. */}
          {canSeeCosts && <> · {formatCost(metadata.usage.total_cost)} ·{' '}
            {(metadata.usage.total_tokens || 0).toLocaleString()} tokens</>}
          {metadata.anonymised && ' · client identifiers were anonymised'}
        </div>
      )}
    </>
  );
}

import { useState } from 'react';
import {
  ARGUED_POSTURES, POSTURES, TAX_HEADS, formatCurrency, headTotal, postureLabel,
} from '../format';

/**
 * The defects read out of a notice, for review before the panel runs.
 *
 * This screen exists because a notice is not one dispute. The department
 * raises limbs separately and disposes of them separately, so the reviewer
 * needs to see them separately — with the department's own figures beside each
 * one — and correct anything that was read wrongly BEFORE any of it reaches a
 * model or a document.
 *
 * Nothing here is presented as settled. A defect whose amount could not be
 * read is shown as an empty field the reviewer fills, never as a zero.
 */

function headSummary(amounts) {
  const parts = TAX_HEADS
    .filter((h) => Number(amounts?.[h]))
    .map((h) => `${h === 'unallocated' ? '' : h.toUpperCase() + ' '}${formatCurrency(amounts[h])}`);
  return parts.join(' + ');
}

export default function DefectList({ defects, onChange, readOnly = false }) {
  const [open, setOpen] = useState(null);

  if (!defects?.length) return null;

  const update = (index, patch) => {
    if (readOnly || !onChange) return;
    onChange(defects.map((d, i) => (i === index ? { ...d, ...patch } : d)));
  };

  const updateHead = (index, head, value) => {
    const defect = defects[index];
    const amounts = { ...(defect.amount_by_head || {}) };
    amounts[head] = value === '' ? 0 : Number(value);
    update(index, { amount_by_head: amounts, amount_unread: false });
  };

  const argued = defects.filter((d) => ARGUED_POSTURES.has(d.posture));
  const settled = defects.filter((d) => !ARGUED_POSTURES.has(d.posture));
  const total = defects.reduce((sum, d) => sum + headTotal(d.amount_by_head), 0);
  const unread = defects.filter((d) => d.amount_unread);

  return (
    <div>
      <div className="row" style={{ gap: 'var(--sp-2)', flexWrap: 'wrap',
                                    marginBottom: 'var(--sp-3)' }}>
        <span className="badge">{defects.length} defects</span>
        <span className="badge">{formatCurrency(total)} in dispute</span>
        <span className="badge badge-warning">{argued.length} argued</span>
        <span className="badge badge-info">{settled.length} settled on documents or payment</span>
      </div>

      {unread.length > 0 && (
        <div className="alert alert-warning" style={{ marginBottom: 'var(--sp-3)' }}>
          <strong>{unread.length} amount{unread.length > 1 ? 's' : ''} could not be
          read</strong> from the notice annexure. Enter {unread.length > 1 ? 'them' : 'it'} below.
          A blank you can see is safe; a wrong figure you cannot see is not.
        </div>
      )}

      <div className="defect-list">
        {defects.map((defect, index) => {
          const amount = headTotal(defect.amount_by_head);
          const expanded = open === index;
          const gaps = defect.evidence_gap || [];
          return (
            <div key={defect.index ?? index} className="card card-pad defect-row">
              <div
                className="row"
                style={{ justifyContent: 'space-between', gap: 'var(--sp-3)',
                         alignItems: 'flex-start', cursor: 'pointer' }}
                onClick={() => setOpen(expanded ? null : index)}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="row" style={{ gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                    <strong>{defect.index}. {defect.heading}</strong>
                    {ARGUED_POSTURES.has(defect.posture) && (
                      <span className="badge badge-warning">Argued</span>
                    )}
                    {defect.unanswered && (
                      <span className="badge badge-danger">Unanswered</span>
                    )}
                    {gaps.length > 0 && (
                      <span className="badge badge-danger">
                        {gaps.length} evidence gap{gaps.length > 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                  <div className="muted" style={{ fontSize: 'var(--text-sm)', marginTop: 4 }}>
                    {defect.amount_unread
                      ? 'Amount not read — enter it from the annexure'
                      : headSummary(defect.amount_by_head) || '—'}
                    {defect.sections?.length > 0 &&
                      ` · s.${defect.sections.slice(0, 4).join(', s.')}`}
                  </div>
                </div>
                <div style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <div><strong>{amount ? formatCurrency(amount) : '—'}</strong></div>
                  <div className="muted" style={{ fontSize: 'var(--text-sm)' }}>
                    {postureLabel(defect.posture)}
                  </div>
                </div>
              </div>

              {expanded && (
                <div style={{ marginTop: 'var(--sp-4)' }}>
                  {!readOnly && (
                    <>
                      <div className="field">
                        <label className="field-label">Position on this defect</label>
                        <select
                          value={defect.posture || 'undecided'}
                          onChange={(e) => update(index, { posture: e.target.value })}
                        >
                          {POSTURES.map((p) => (
                            <option key={p.key} value={p.key}>{p.label}</option>
                          ))}
                        </select>
                        <div className="field-help">
                          {POSTURES.find((p) => p.key === defect.posture)?.hint}
                        </div>
                      </div>

                      <div className="field">
                        <label className="field-label">
                          Amount alleged, by head (from the notice annexure)
                        </label>
                        <div className="row" style={{ gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                          {TAX_HEADS.map((head) => (
                            <div key={head} style={{ flex: '1 1 110px' }}>
                              <input
                                type="number"
                                placeholder={head.toUpperCase()}
                                value={defect.amount_by_head?.[head] || ''}
                                onChange={(e) => updateHead(index, head, e.target.value)}
                              />
                              <div className="field-help">{head.toUpperCase()}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </>
                  )}

                  {defect.our_position && (
                    <div className="field">
                      <label className="field-label">Position taken</label>
                      <div>{defect.our_position}</div>
                    </div>
                  )}

                  {defect.submission && (
                    <div className="field">
                      <label className="field-label">Submission</label>
                      <div><strong>{defect.submission}</strong></div>
                    </div>
                  )}

                  {gaps.length > 0 && (
                    <div className="alert alert-danger" style={{ marginTop: 'var(--sp-3)' }}>
                      <strong>Evidence gap.</strong> The officer will require
                      these before dropping this defect, and the engagement team
                      has not confirmed they are held:
                      <ul style={{ margin: '8px 0 0 18px' }}>
                        {gaps.map((item, i) => <li key={i}>{item}</li>)}
                      </ul>
                    </div>
                  )}

                  {defect.evidence_required?.length > 0 && (
                    <div className="field">
                      <label className="field-label">
                        Evidence this defect is normally disposed of on
                      </label>
                      <ul style={{ margin: '4px 0 0 18px' }}>
                        {defect.evidence_required.map((item, i) => (
                          <li key={i} className="muted">{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {defect.notice_extract && (
                    <details style={{ marginTop: 'var(--sp-3)' }}>
                      <summary className="muted">What the notice says</summary>
                      <pre className="notice-extract">{defect.notice_extract}</pre>
                    </details>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

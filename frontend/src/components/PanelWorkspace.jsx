import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import Deliberation from './Deliberation';
import DefectList from './DefectList';
import { ConfidenceBadge, Loading, SourceSnippet } from './shared';
import { formatCurrency } from '../format';

const STAGE_LABELS = {
  stage1: 'Opening analyses',
  stage2: 'Cross-examination',
  stage3: 'Chairman determination',
  verification: 'Citation verification',
};

export default function PanelWorkspace({ user, onComplete, onAuthError }) {
  const [config, setConfig] = useState(null);
  const [tier, setTier] = useState('pro');
  const [form, setForm] = useState({ notice_type: 'ASMT-10', state: '' });
  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState({});
  const [result, setResult] = useState({ analyses: [], cross_exams: [] });
  const [metadata, setMetadata] = useState(null);
  const [error, setError] = useState('');
  const [reading, setReading] = useState(false);
  const [readResult, setReadResult] = useState(null);
  const [recon, setRecon] = useState(null);
  const [reconciling, setReconciling] = useState(false);
  const [estimate, setEstimate] = useState(null);
  const fileRef = useRef(null);
  const reconRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const cfg = await api.panelConfig();
        setConfig(cfg);
        setTier(cfg.default_tier);
      } catch (err) {
        if (!onAuthError(err)) setError(err.message);
      }
    })();
  }, [onAuthError]);

  // A run takes two to four minutes and the SSE generator is cancelled if the
  // tab goes: the models have been paid for, and storage.complete_matter never
  // fires, so the matter stays "draft" for ever. The browser prompt is the
  // only thing that can intervene.
  useEffect(() => {
    if (!running) return undefined;
    const warn = (event) => {
      event.preventDefault();
      event.returnValue = '';
      return '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [running]);

  // What this run will cost, before it is run. Re-estimated whenever the
  // limbs or the tier change, because both drive it — triage means most limbs
  // never convene counsel, so the cost tracks the argued limbs and not the
  // total.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const quote = await api.estimatePanel({
          intake: { defects: form.defects || [] },
          domain: 'gst',
          tier,
        });
        if (!cancelled) setEstimate(quote);
      } catch {
        // An estimate is a convenience. Never block the run on it.
        if (!cancelled) setEstimate(null);
      }
    })();
    return () => { cancelled = true; };
  }, [form.defects, tier]);

  if (error && !config) {
    return <div className="page"><div className="alert alert-danger">{error}</div></div>;
  }
  if (!config) return <div className="page"><Loading label="Loading intake form…" /></div>;

  const schema = config.schemas.gst;
  const tierMeta = config.tiers.find((t) => t.key === tier) || config.tiers[0];
  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const required = schema.fields.filter((f) => f.required);
  const missing = required.filter((f) => !String(form[f.key] || '').trim());

  // Blockers the run must not proceed over. A figure the panel argues from is
  // a figure that reaches a filed reply, so a limb with no amount is not a
  // detail to fix later; and a GSTIN or a date order that is wrong on its face
  // gets the reply rejected on its face.
  const unreadLimbs = (form.defects || []).filter((d) => d.amount_unread);
  const unnamedLimbs = (form.defects || []).filter(
    (d) => !String(d.heading || '').trim());
  const gstin = String(form.gstin || '').trim().toUpperCase();
  const gstinLooksWrong =
    gstin.length > 0 && !/^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}$/.test(gstin);
  const datesOutOfOrder =
    form.notice_date && form.due_date && form.due_date < form.notice_date;

  const blockers = [
    ...(unreadLimbs.length
      ? [`${unreadLimbs.length} limb(s) carry no amount. Take the figures from ` +
         'the notice annexure — an unread figure must never be filed as a zero.']
      : []),
    ...(unnamedLimbs.length
      ? [`${unnamedLimbs.length} limb(s) have no heading. Use the department's ` +
         'own wording, since the officer disposes of each limb by its heading.']
      : []),
    ...(gstinLooksWrong
      ? ['The GSTIN is not 15 characters in the statutory format. A reply ' +
         'carrying a wrong GSTIN is rejected on its face.']
      : []),
    ...(datesOutOfOrder
      ? ['The reply due date is before the date of the notice. Check both ' +
         'against the notice before running.']
      : []),
  ];

  const canRun = missing.length === 0 && blockers.length === 0 && !running;

  const onFiles = async (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setReading(true);
    setError('');
    setReadResult(null);
    try {
      const result = await api.extractNotice(files, { tier });
      // Everything read from the notice is a PROPOSAL. It pre-fills the form
      // for the user to correct — it is never treated as confirmed.
      setForm((current) => ({ ...current, ...result.fields }));
      setReadResult({ ...result, filename: files.map((f) => f.name).join(', ') });
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    } finally {
      setReading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  // A limb the reviewer adds by hand starts UNDECIDED and UNREAD: it convenes
  // counsel until someone decides otherwise, and it carries no figure until
  // one is taken off the annexure. Both defaults are the safe direction.
  const addDefect = () => {
    setForm((f) => {
      const existing = f.defects || [];
      return {
        ...f,
        defects: [...existing, {
          index: existing.length + 1,
          type: 'other',
          heading: '',
          posture: 'undecided',
          amount_by_head: {},
          amount_unread: true,
          source: 'manual',
          evidence_required: [],
          evidence_gap: [],
        }],
      };
    });
  };

  const onReconFile = async (file) => {
    if (!file) return;
    setReconciling(true);
    setError('');
    try {
      setRecon({ ...(await api.uploadReconciliation(file, { tier })),
                 filename: file.name });
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    } finally {
      setReconciling(false);
      if (reconRef.current) reconRef.current.value = '';
    }
  };

  const run = async () => {
    setRunning(true);
    setError('');
    setStages({ stage1: 'running' });
    setResult({ analyses: [], cross_exams: [] });
    setMetadata(null);

    let matterId = null;
    // Tracked here rather than read back off `error`: that binding is the one
    // captured when this closure was created, so it is always the value from
    // before the run started. An errored run therefore navigated to the matter
    // page as though it had succeeded, and a run started after ANY earlier
    // error never navigated at all.
    let streamError = null;
    // An SSE `error` event and a thrown request failure both leave the same
    // stage spinning, so both end here.
    const markRunningStagesFailed = () =>
      setStages((s) => Object.fromEntries(
        Object.entries(s).map(([k, v]) => [k, v === 'running' ? 'failed' : v])
      ));
    try {
      await api.runPanel(
        { intake: recon ? { ...form, reconciliation: recon } : form,
          domain: 'gst', tier },
        (type, event) => {
          switch (type) {
            case 'matter_created':
              matterId = event.matter_id;
              break;
            case 'stage1_start':
              setStages((s) => ({ ...s, stage1: 'running' }));
              break;
            case 'stage1_complete':
              setStages((s) => ({ ...s, stage1: 'done' }));
              setResult((r) => ({ ...r, analyses: event.data }));
              if (event.failures?.length) {
                setResult((r) => ({ ...r, failures: event.failures }));
              }
              break;
            case 'stage2_start':
              setStages((s) => ({ ...s, stage2: 'running' }));
              break;
            case 'stage2_complete':
              setStages((s) => ({ ...s, stage2: 'done' }));
              setResult((r) => ({ ...r, cross_exams: event.data }));
              break;
            case 'stage3_start':
              setStages((s) => ({ ...s, stage3: 'running' }));
              break;
            case 'stage3_complete':
              setStages((s) => ({ ...s, stage3: 'done' }));
              setResult((r) => ({ ...r, determination: event.data }));
              break;
            case 'verification_start':
              setStages((s) => ({ ...s, verification: 'running' }));
              break;
            case 'verification_complete':
              setStages((s) => ({ ...s, verification: 'done' }));
              setResult((r) => ({ ...r, verification: event.data }));
              break;
            case 'summary':
              setResult(event.data);
              setMetadata(event.metadata);
              break;
            case 'error':
              streamError = event.message;
              setError(event.message);
              markRunningStagesFailed();
              break;
            default:
              break;
          }
        }
      );
      if (matterId && !streamError) onComplete(matterId);
    } catch (err) {
      streamError = err.message;
      if (!onAuthError(err)) setError(err.message);
      markRunningStagesFailed();
    } finally {
      setRunning(false);
    }
  };

  if (running || result.determination) {
    return (
      <div className="page">
        <div className="page-header">
          <div>
            <h1 className="page-title">Panel in session</h1>
            <div className="page-subtitle">
              {form.client_name || 'Matter'} · {form.notice_type} · {form.state}
            </div>
          </div>
        </div>

        <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
          <div className="stage-track">
            {Object.entries(STAGE_LABELS).map(([key, label]) => (
              <div key={key} className={`stage-step ${stages[key] || 'pending'}`}>
                <span className="stage-dot" aria-hidden="true">
                  {stages[key] === 'done' ? '✓' : stages[key] === 'failed' ? '!' : ''}
                </span>
                <span>{label}</span>
                {stages[key] === 'running' && <div className="spinner" />}
              </div>
            ))}
          </div>
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 16 }}>{error}</div>}

        <Deliberation result={result} metadata={metadata} user={user} />
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">New matter</h1>
          <div className="page-subtitle">
            Enter the notice. Four counsel will argue it, cross-examine each
            other, and the chairman will determine the firm's position.
          </div>
        </div>
      </div>

      <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
        <div className="section-title">Panel tier</div>
        <div className="tier-picker">
          {config.tiers.map((t) => (
            <button
              key={t.key}
              className={`tier-option ${tier === t.key ? 'selected' : ''}`}
              onClick={() => setTier(t.key)}
              type="button"
            >
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <strong>{t.label}</strong>
                {t.anonymise && <span className="badge badge-info">Anonymised</span>}
              </div>
              <div className="muted" style={{ fontSize: 'var(--text-sm)', marginTop: 4 }}>
                {t.description}
              </div>
            </button>
          ))}
        </div>
        {tierMeta.anonymise && (
          <div className="alert alert-warning" style={{ marginTop: 'var(--sp-4)' }}>
            <strong>Anonymised mode.</strong> Client name, GSTIN, PAN and exact
            amounts are stripped before any request leaves this machine, and
            restored only in what you read here.
            {tierMeta.watermark && ` Every exported page is stamped "${tierMeta.watermark}".`}
          </div>
        )}
      </div>

      <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
        <div className="section-title">Upload the notice</div>
        <div className="row" style={{ gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
          <input
            ref={fileRef}
            id="notice-files"
            aria-label="Notice documents to upload (PDF, Word or text)"
            type="file"
            multiple
            accept=".pdf,.docx,.txt"
            onChange={(e) => onFiles(e.target.files)}
            disabled={reading}
            style={{ width: 'auto', flex: 1, minWidth: 240 }}
          />
          {reading && (
            <span className="row" style={{ gap: 'var(--sp-2)' }}>
              <span className="spinner" />
              <span className="muted">Reading…</span>
            </span>
          )}
        </div>
        <div className="field-help">
          PDF, Word or text — select several at once. A scrutiny notice
          normally arrives as two files: the one-page portal form carrying the
          reference and the reply date, and the attachment carrying the
          defects. Upload both. Files are read in memory and never stored, and
          identifiers, dates, amounts, provisions and the defect breakdown are
          read locally without any model. Everything below is a proposal for
          you to check.
        </div>

        {readResult && (
          <div style={{ marginTop: 'var(--sp-3)' }}>
            <div className="row" style={{ gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
              <span className="badge badge-success">
                {readResult.filename} read
              </span>
              {readResult.scanned && (
                <span className="badge badge-warning">
                  scanned — read by OCR
                </span>
              )}
              {Object.entries(readResult.sources || {}).map(([field, origin]) => (
                <span
                  key={field}
                  className={`badge ${String(origin).endsWith('-ocr') ? 'badge-warning' : ''}`}
                >
                  {field.replace(/_/g, ' ')} · {origin}
                </span>
              ))}
            </div>
            {(readResult.warnings || []).length > 0 && (
              <div className="alert alert-warning" style={{ marginTop: 'var(--sp-3)' }}>
                {readResult.warnings.map((w, i) => <div key={i}>{w}</div>)}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Rendered even with no defects. When segmentation finds nothing the
          intake tells the user to "add them by hand — a reply that answers a
          multi-limb notice as one issue concedes ground it need not concede",
          and until now there was no way to do that: the card was hidden and
          DefectList returned null, so the only route was prose in the issues
          box, which is the exact failure the instruction warns against. */}
      <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
        <div className="row" style={{ justifyContent: 'space-between',
                                      alignItems: 'flex-start',
                                      gap: 'var(--sp-3)' }}>
          <div className="section-title">Defects raised by the notice</div>
          <button type="button" className="btn btn-sm" onClick={addDefect}>
            Add defect
          </button>
        </div>
        <div className="field-help" style={{ marginBottom: 'var(--sp-3)' }}>
          The department raises these separately and will dispose of them
          separately — so the reply answers them one at a time. Check each
          figure against the notice annexure and set the position before
          running the panel. Only the limbs marked <em>Argued</em> convene
          counsel; the rest are answered by arithmetic, documents or a
          payment.
        </div>
        {form.defects?.length > 0 ? (
          <DefectList
            defects={form.defects}
            onChange={(defects) => setField('defects', defects)}
          />
        ) : (
          <div className="alert alert-warning" role="alert">
            <strong>No defects were read from this notice.</strong> A reply that
            answers a multi-limb notice as a single issue concedes ground it
            need not concede — and an unanswered limb is confirmed unopposed.
            Add each limb the notice raises, with its own heading and its
            head-wise figures from the annexure.
          </div>
        )}
      </div>

      <div className="card card-pad">
        <div className="section-title">Notice particulars</div>
        <div className="form-grid">
          {schema.fields.map((field) => {
            const common = {
              id: field.key,
              value: form[field.key] ?? '',
              onChange: (e) => setField(field.key, e.target.value),
              // No `disabled` key. A sensitive field stays editable on the
              // anonymising tier BY DESIGN: the value is stripped before the
              // request leaves and restored locally afterwards, so the partner
              // reads real names the model never saw. The badge on the label is
              // what tells the user; greying the input would imply the field is
              // not wanted, which is the opposite of true. (The old expression
              // read `cond ? false : false` — always false, condition discarded.)
            };
            const wide = field.type === 'textarea';
            return (
              <div className={`field ${wide ? 'field-wide' : ''}`} key={field.key}>
                <label htmlFor={field.key}>
                  {field.label}
                  {field.required && <span style={{ color: 'var(--danger)' }}> *</span>}
                  {field.sensitive && tierMeta.anonymise && (
                    <span className="badge badge-info" style={{ marginLeft: 8 }}>
                      stripped before sending
                    </span>
                  )}
                </label>

                {field.type === 'select' && field.key === 'notice_type' && (
                  <select {...common}>
                    {schema.notice_types.map((n) => (
                      <option key={n.code} value={n.code}>
                        {n.code} — {n.name}
                      </option>
                    ))}
                  </select>
                )}

                {field.type === 'select' && field.key === 'state' && (
                  <select {...common}>
                    <option value="">Select state…</option>
                    {schema.states.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                )}

                {field.type === 'textarea' && (
                  <textarea {...common} placeholder={field.placeholder} rows={5} />
                )}

                {['text', 'number', 'date'].includes(field.type) && (
                  <input type={field.type} {...common} placeholder={field.placeholder} />
                )}

                {field.help && <div className="field-help">{field.help}</div>}

                <SourceSnippet
                  snippet={readResult?.snippets?.[field.key]}
                  origin={readResult?.sources?.[field.key]}
                />
              </div>
            );
          })}
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 16 }}>{error}</div>}

        <div className="section-title" style={{ marginTop: 'var(--sp-5)' }}>
          Reconciliation (optional)
        </div>
        <div className="row" style={{ gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
          <input
            ref={reconRef}
            id="reconciliation-file"
            aria-label="Reconciliation workbook to upload (xlsx or csv)"
            type="file"
            accept=".xlsx,.xlsm,.csv"
            onChange={(e) => onReconFile(e.target.files?.[0])}
            disabled={reconciling}
            style={{ width: 'auto', flex: 1, minWidth: 240 }}
          />
          {reconciling && (
            <span className="row" style={{ gap: 'var(--sp-2)' }}>
              <span className="spinner" /><span className="muted">Reconciling…</span>
            </span>
          )}
        </div>
        <div className="field-help">
          Your 2A/3B working, as Excel or CSV. Parsed and bucketed on this
          machine — only the totals reach the panel, never the rows. A remarks
          column describing each difference gives a materially better result.
        </div>

        {recon && (
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
              <strong>{recon.filename}</strong>
              <span className="muted">
                {formatCurrency(recon.total)} across {recon.row_count} lines
              </span>
            </div>
            <div className="table-wrap" style={{ marginTop: 'var(--sp-2)' }}>
              <table>
                <thead>
                  <tr>
                    <th>Category</th><th>Amount</th><th>Share</th><th>Position</th>
                  </tr>
                </thead>
                <tbody>
                  {recon.buckets.map((b) => (
                    <tr key={b.key}>
                      <td>{b.label}</td>
                      <td>{formatCurrency(b.amount)}</td>
                      <td>{(b.share * 100).toFixed(0)}%</td>
                      <td><ConfidenceBadge value={b.strength} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {(recon.warnings || []).length > 0 && (
              <div className="alert alert-warning" style={{ marginTop: 'var(--sp-3)' }}>
                {recon.warnings.map((w, i) => <div key={i}>{w}</div>)}
              </div>
            )}
          </div>
        )}

        <div className="row" style={{ justifyContent: 'space-between', marginTop: 'var(--sp-4)' }}>
          <div className="muted" style={{ fontSize: 'var(--text-sm)' }}>
            {missing.length > 0
              ? `Required: ${missing.map((f) => f.label).join(', ')}`
              : blockers.length > 0
                ? null
                : 'Ready. Expect two to four minutes for a full deliberation. '
                  + 'Keep this tab open — a run does not survive it closing.'}
            {/* Say WHICH thing blocks the run. A disabled button with no
                reason reads as a broken page. */}
            {missing.length === 0 && blockers.length > 0 && (
              <div role="alert">
                <strong>Not ready to run:</strong>
                <ul style={{ margin: '4px 0 0', paddingLeft: '1.1rem' }}>
                  {blockers.map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              </div>
            )}
            {estimate && missing.length === 0 && (
              <div style={{ marginTop: 4 }}>
                Estimated cost <strong>{estimate.label}</strong>
                {estimate.triage && estimate.triage.total > 0 && (
                  <> — {estimate.triage.convening_counsel} of{' '}
                    {estimate.triage.total} limbs convene counsel</>
                )}
                <span className="muted"> ({estimate.basis})</span>
              </div>
            )}
          </div>
          <button className="btn btn-primary" disabled={!canRun} onClick={run}>
            Convene the panel
          </button>
        </div>
      </div>
    </div>
  );
}

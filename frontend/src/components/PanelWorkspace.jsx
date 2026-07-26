import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import Deliberation from './Deliberation';
import { Loading } from './shared';

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
  const fileRef = useRef(null);

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

  if (error && !config) {
    return <div className="page"><div className="alert alert-danger">{error}</div></div>;
  }
  if (!config) return <div className="page"><Loading label="Loading intake form…" /></div>;

  const schema = config.schemas.gst;
  const tierMeta = config.tiers.find((t) => t.key === tier) || config.tiers[0];
  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const required = schema.fields.filter((f) => f.required);
  const missing = required.filter((f) => !String(form[f.key] || '').trim());
  const canRun = missing.length === 0 && !running;

  const onFile = async (file) => {
    if (!file) return;
    setReading(true);
    setError('');
    setReadResult(null);
    try {
      const result = await api.extractNotice(file, { tier });
      // Everything read from the notice is a PROPOSAL. It pre-fills the form
      // for the user to correct — it is never treated as confirmed.
      setForm((current) => ({ ...current, ...result.fields }));
      setReadResult({ ...result, filename: file.name });
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    } finally {
      setReading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const run = async () => {
    setRunning(true);
    setError('');
    setStages({ stage1: 'running' });
    setResult({ analyses: [], cross_exams: [] });
    setMetadata(null);

    let matterId = null;
    try {
      await api.runPanel(
        { intake: form, domain: 'gst', tier },
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
              setError(event.message);
              break;
            default:
              break;
          }
        }
      );
      if (matterId && !error) onComplete(matterId);
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
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
                <span className="stage-dot">
                  {stages[key] === 'done' ? '✓' : stages[key] === 'running' ? '' : ''}
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
            restored only in what you read here. Free-tier output is research
            grade and cannot be exported as a reply pack.
          </div>
        )}
      </div>

      <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
        <div className="section-title">Upload the notice</div>
        <div className="row" style={{ gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={(e) => onFile(e.target.files?.[0])}
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
          PDF, Word or text. The file is read in memory and never stored.
          Identifiers, dates, amounts and jurisdiction are read locally without
          any model. Everything below is a proposal for you to check.
        </div>

        {readResult && (
          <div style={{ marginTop: 'var(--sp-3)' }}>
            <div className="row" style={{ gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
              <span className="badge badge-success">
                {readResult.filename} read
              </span>
              {Object.entries(readResult.sources || {}).map(([field, origin]) => (
                <span key={field} className="badge">
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

      <div className="card card-pad">
        <div className="section-title">Notice particulars</div>
        <div className="form-grid">
          {schema.fields.map((field) => {
            const common = {
              id: field.key,
              value: form[field.key] ?? '',
              onChange: (e) => setField(field.key, e.target.value),
              disabled: field.sensitive && tierMeta.anonymise ? false : false,
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
              </div>
            );
          })}
        </div>

        {error && <div className="alert alert-danger" style={{ marginBottom: 16 }}>{error}</div>}

        <div className="row" style={{ justifyContent: 'space-between', marginTop: 'var(--sp-4)' }}>
          <div className="muted" style={{ fontSize: 'var(--text-sm)' }}>
            {missing.length > 0
              ? `Required: ${missing.map((f) => f.label).join(', ')}`
              : 'Ready. Expect two to four minutes for a full deliberation.'}
          </div>
          <button className="btn btn-primary" disabled={!canRun} onClick={run}>
            Convene the panel
          </button>
        </div>
      </div>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { api } from '../api';
import { Loading } from './shared';
import { formatDate } from '../format';

const ROLE_HELP = {
  partner: 'Full deliberation, export, administration and user management.',
  manager: 'Full deliberation and export. No administration.',
  staff: 'Determination and verification only — not the counsel arguments.',
};

function Users({ onAuthError }) {
  const [users, setUsers] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [form, setForm] = useState({ email: '', name: '', password: '', role: 'staff' });

  const load = async () => {
    try {
      setUsers(await api.adminUsers());
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const create = async (e) => {
    e.preventDefault();
    setError('');
    setNotice('');
    try {
      await api.createUser(form);
      setNotice(`Created ${form.email}.`);
      setForm({ email: '', name: '', password: '', role: 'staff' });
      load();
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    }
  };

  const change = async (id, payload) => {
    setError('');
    try {
      await api.updateUser(id, payload);
      load();
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    }
  };

  const remove = async (user) => {
    if (!window.confirm(`Remove ${user.email}?`)) return;
    setError('');
    try {
      await api.deleteUser(user.id);
      load();
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    }
  };

  if (!users) return <Loading label="Loading users…" />;

  return (
    <>
      {error && <div className="alert alert-danger" style={{ marginBottom: 16 }}>{error}</div>}
      {notice && <div className="alert alert-info" style={{ marginBottom: 16 }}>{notice}</div>}

      <div className="card table-wrap" style={{ marginBottom: 'var(--sp-5)' }}>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th>Last sign-in</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td style={{ fontWeight: 500 }}>{user.name || '—'}</td>
                <td className="mono">{user.email}</td>
                <td>
                  <select
                    value={user.role}
                    onChange={(e) => change(user.id, { role: e.target.value })}
                    style={{ width: 120, padding: '4px 8px', fontSize: 'var(--text-sm)' }}
                  >
                    <option value="partner">Partner</option>
                    <option value="manager">Manager</option>
                    <option value="staff">Staff</option>
                  </select>
                </td>
                <td>
                  <button
                    className={`badge ${user.active ? 'badge-success' : 'badge-danger'}`}
                    style={{ cursor: 'pointer', border: 'none' }}
                    onClick={() => change(user.id, { active: !user.active })}
                  >
                    {user.active ? 'Active' : 'Disabled'}
                  </button>
                </td>
                <td className="muted">{user.last_login ? formatDate(user.last_login) : 'Never'}</td>
                <td>
                  <button className="btn btn-ghost btn-sm" onClick={() => remove(user)}>×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card card-pad">
        <div className="section-title">Add user</div>
        <form onSubmit={create}>
          <div className="form-grid">
            <div className="field">
              <label>Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
              />
            </div>
            <div className="field">
              <label>Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Temporary password</label>
              <input
                type="text"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                minLength={8}
                required
              />
              <div className="field-help">At least 8 characters.</div>
            </div>
            <div className="field">
              <label>Role</label>
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                <option value="staff">Staff</option>
                <option value="manager">Manager</option>
                <option value="partner">Partner</option>
              </select>
              <div className="field-help">{ROLE_HELP[form.role]}</div>
            </div>
          </div>
          <button className="btn btn-primary">Create user</button>
        </form>
      </div>
    </>
  );
}

function Settings({ onAuthError }) {
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        setSettings(await api.adminSettings());
      } catch (err) {
        if (!onAuthError(err)) setError(err.message);
      }
    })();
  }, [onAuthError]);

  if (error) return <div className="alert alert-danger">{error}</div>;
  if (!settings) return <Loading label="Loading settings…" />;

  const validation = settings.model_validation || {};
  const unknown = validation.unknown_models || [];

  return (
    <>
      {unknown.length > 0 && (
        <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-5)' }}>
          <strong>Stale model IDs.</strong> These are configured but not present
          in OpenRouter's catalogue and will fail at run time:{' '}
          <span className="mono">{unknown.join(', ')}</span>
        </div>
      )}

      {Object.entries(settings.tiers).map(([key, tier]) => (
        <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }} key={key}>
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 'var(--sp-3)' }}>
            <div className="section-title" style={{ margin: 0 }}>{tier.label}</div>
            <div className="row" style={{ gap: 'var(--sp-2)' }}>
              {tier.anonymise && <span className="badge badge-info">Anonymised</span>}
              {tier.allow_export
                ? <span className="badge badge-success">Export allowed</span>
                : <span className="badge badge-warning">Export blocked</span>}
              {settings.default_tier === key && <span className="badge">Default</span>}
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Seat</th><th>Model</th></tr>
              </thead>
              <tbody>
                {Object.entries(tier.models).map(([role, model]) => (
                  <tr key={role}>
                    <td style={{ textTransform: 'capitalize' }}>{role}</td>
                    <td className="mono">{model}</td>
                  </tr>
                ))}
                <tr>
                  <td>Verifier</td>
                  <td className="mono">{tier.verifier}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      ))}

      <div className="card card-pad" style={{ marginBottom: 'var(--sp-5)' }}>
        <div className="section-title">Runtime</div>
        <div className="detail-grid">
          <div><span className="muted">Reasoning effort</span><div>{settings.reasoning_effort}</div></div>
          <div><span className="muted">Zero data retention</span><div>{settings.zdr_enforced ? 'Enforced' : 'Off'}</div></div>
          <div><span className="muted">Request timeout</span><div>{settings.request_timeout}s</div></div>
          <div><span className="muted">Max retries</span><div>{settings.max_retries}</div></div>
          <div><span className="muted">Data directory</span><div className="mono">{settings.data_dir}</div></div>
        </div>
        <div className="field-help" style={{ marginTop: 'var(--sp-3)' }}>
          These are set by environment variable. Change them in <span className="mono">.env</span> and restart the server.
        </div>
      </div>

      <div className="card card-pad">
        <div className="section-title">Reply pack</div>
        <div className="detail-grid" style={{ marginBottom: 'var(--sp-3)' }}>
          <div>
            <span className="muted">Firm name on exports</span>
            <div>{settings.firm_name || 'Not set — set FIRM_NAME in .env'}</div>
          </div>
          <div>
            <span className="muted">Internal annexure</span>
            <div>{settings.export_provenance ? 'Included' : 'Omitted'}</div>
          </div>
        </div>
        <div className="section-title">Standing review note</div>
        <p className="muted" style={{ margin: 0 }}>{settings.review_note}</p>
      </div>
    </>
  );
}

function Account({ onAuthError }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    try {
      await api.changePassword(current, next);
      setMessage('Password changed.');
      setCurrent('');
      setNext('');
    } catch (err) {
      if (!onAuthError(err)) setError(err.message);
    }
  };

  return (
    <div className="card card-pad" style={{ maxWidth: 420 }}>
      <div className="section-title">Change your password</div>
      <form onSubmit={submit}>
        <div className="field">
          <label>Current password</label>
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
        </div>
        <div className="field">
          <label>New password</label>
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            minLength={8}
            required
          />
          <div className="field-help">At least 8 characters.</div>
        </div>
        {error && <div className="alert alert-danger" style={{ marginBottom: 16 }}>{error}</div>}
        {message && <div className="alert alert-info" style={{ marginBottom: 16 }}>{message}</div>}
        <button className="btn btn-primary">Update password</button>
      </form>
    </div>
  );
}

export default function AdminPanel({ onAuthError }) {
  const [tab, setTab] = useState('users');

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Administration</h1>
          <div className="page-subtitle">Users, panel configuration and your account.</div>
        </div>
      </div>

      <div className="tabs" style={{ marginBottom: 'var(--sp-5)' }}>
        {[
          ['users', 'Users'],
          ['settings', 'Panel configuration'],
          ['account', 'My account'],
        ].map(([key, label]) => (
          <button
            key={key}
            className={`tab ${tab === key ? 'active' : ''}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'users' && <Users onAuthError={onAuthError} />}
      {tab === 'settings' && <Settings onAuthError={onAuthError} />}
      {tab === 'account' && <Account onAuthError={onAuthError} />}
    </div>
  );
}

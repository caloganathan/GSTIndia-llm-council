import { useState } from 'react';
import { api, setAuthToken } from '../api';

export default function Login({ onSuccess, theme, onToggleTheme }) {
  const [mode, setMode] = useState('credentials');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [token, setToken] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submitCredentials = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const session = await api.login(email.trim(), password);
      setAuthToken(session.token);
      onSuccess();
    } catch (err) {
      setError(err.message || 'Sign in failed');
    } finally {
      setBusy(false);
    }
  };

  const submitToken = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    setAuthToken(token.trim());
    try {
      await api.checkAuth();
      onSuccess();
    } catch {
      setAuthToken('');
      setError('That access token was not accepted.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <button className="login-theme" onClick={onToggleTheme}>
        {theme === 'dark' ? '☀ Light' : '☾ Dark'}
      </button>

      <div className="login-card">
        <div className="login-brand">
          <div className="brand-mark">CP</div>
          <div>
            <div className="login-title">Compliance Panel</div>
            <div className="login-sub">GST Advisory</div>
          </div>
        </div>

        {mode === 'credentials' ? (
          <form onSubmit={submitCredentials}>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
            {error && <div className="alert alert-danger" style={{ marginBottom: 16 }}>{error}</div>}
            <button
              className="btn btn-primary"
              style={{ width: '100%' }}
              disabled={busy || !email.trim() || !password}
            >
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        ) : (
          <form onSubmit={submitToken}>
            <div className="field">
              <label htmlFor="token">Access token</label>
              <input
                id="token"
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoFocus
                required
              />
              <div className="field-help">
                The shared secret configured as APP_ACCESS_TOKEN.
              </div>
            </div>
            {error && <div className="alert alert-danger" style={{ marginBottom: 16 }}>{error}</div>}
            <button
              className="btn btn-primary"
              style={{ width: '100%' }}
              disabled={busy || !token.trim()}
            >
              {busy ? 'Checking…' : 'Continue'}
            </button>
          </form>
        )}

        <div className="login-note">
          <button
            className="btn btn-ghost btn-sm"
            style={{ padding: 0 }}
            onClick={() => {
              setMode(mode === 'credentials' ? 'token' : 'credentials');
              setError('');
            }}
          >
            {mode === 'credentials'
              ? 'Use a shared access token instead'
              : 'Sign in with email and password'}
          </button>
          <div style={{ marginTop: 8 }}>
            On first run the server prints a partner account to its console.
          </div>
        </div>
      </div>
    </div>
  );
}

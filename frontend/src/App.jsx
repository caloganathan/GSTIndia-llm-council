import { useCallback, useEffect, useState } from 'react';
import { api, setAuthToken } from './api';
import { useTheme } from './theme';
import Login from './components/Login';
import Dashboard from './components/Dashboard';
import PanelWorkspace from './components/PanelWorkspace';
import MatterList from './components/MatterList';
import MatterDetail from './components/MatterDetail';
import AdminPanel from './components/AdminPanel';
import GeneralCouncil from './components/GeneralCouncil';
import './App.css';

const NAV = [
  { key: 'dashboard', label: 'Dashboard', icon: '▤' },
  { key: 'panel', label: 'New Matter', icon: '✦' },
  { key: 'matters', label: 'Matters', icon: '▦' },
  // The generic council is the upstream project this one grew out of. It
  // still works, but no client engagement uses it, and left in the navigation
  // it doubles what a new user has to understand and invites the question
  // "so is this a chatbot?". Off unless ENABLE_GENERAL_COUNCIL is set.
  { key: 'council', label: 'General Council', icon: '◇', feature: 'general_council' },
  { key: 'admin', label: 'Administration', icon: '⚙', permission: 'admin' },
];

export default function App() {
  const { theme, toggle } = useTheme();
  const [authState, setAuthState] = useState('checking');
  const [user, setUser] = useState(null);
  const [features, setFeatures] = useState({});
  const [view, setView] = useState('dashboard');
  const [activeMatterId, setActiveMatterId] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const loadSession = useCallback(async () => {
    try {
      const result = await api.checkAuth();
      setUser(result.user);
      setFeatures(result.features || {});
      setAuthState('ok');
    } catch (error) {
      if (error.status === 401) {
        setAuthState('needed');
      } else {
        console.error('Backend unreachable:', error);
        setAuthState('error');
      }
    }
  }, []);

  useEffect(() => {
    // Deferred so the state updates land outside the effect body.
    const id = setTimeout(loadSession, 0);
    return () => clearTimeout(id);
  }, [loadSession]);

  const handleAuthError = useCallback((error) => {
    if (error?.status === 401) {
      setAuthToken('');
      setUser(null);
      setAuthState('needed');
      return true;
    }
    return false;
  }, []);

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch {
      /* revoking a dead session is not an error worth surfacing */
    }
    setAuthToken('');
    setUser(null);
    setAuthState('needed');
  };

  const openMatter = (id) => {
    setActiveMatterId(id);
    setView('matter');
  };

  const onMatterComplete = (id) => {
    setRefreshKey((k) => k + 1);
    openMatter(id);
  };

  if (authState === 'checking') {
    return (
      <div className="boot">
        <div className="spinner" />
        <span>Loading…</span>
      </div>
    );
  }

  if (authState === 'error') {
    return (
      <div className="boot">
        <div className="card card-pad" style={{ maxWidth: 460 }}>
          <h2>Cannot reach the server</h2>
          <p className="muted">
            The backend is not responding. Confirm it is running on port 8001,
            then reload this page.
          </p>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (authState === 'needed') {
    return <Login onSuccess={loadSession} theme={theme} onToggleTheme={toggle} />;
  }

  const can = (permission) => Boolean(user?.permissions?.[permission]);
  const nav = NAV.filter(
    (item) =>
      (!item.permission || can(item.permission)) &&
      (!item.feature || features[item.feature])
  );

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">CP</div>
          <div>
            <div className="brand-name">Compliance Panel</div>
            <div className="brand-sub">GST Advisory</div>
          </div>
        </div>

        <nav className="nav">
          {nav.map((item) => (
            <button
              key={item.key}
              className={`nav-item ${
                view === item.key || (view === 'matter' && item.key === 'matters')
                  ? 'active'
                  : ''
              }`}
              onClick={() => setView(item.key)}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button className="theme-toggle" onClick={toggle} title="Toggle theme">
            <span>{theme === 'dark' ? '☀' : '☾'}</span>
            {theme === 'dark' ? 'Light mode' : 'Dark mode'}
          </button>

          <div className="user-chip">
            <div className="user-avatar">
              {(user?.name || user?.email || '?').charAt(0).toUpperCase()}
            </div>
            <div className="user-meta">
              <div className="user-name">{user?.name || user?.email}</div>
              <div className="user-role">{user?.role}</div>
            </div>
          </div>
          <button className="btn btn-ghost btn-sm signout" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="main">
        {view === 'dashboard' && (
          <Dashboard
            key={refreshKey}
            user={user}
            onOpenMatter={openMatter}
            onNewMatter={() => setView('panel')}
            onAuthError={handleAuthError}
          />
        )}
        {view === 'panel' && (
          <PanelWorkspace user={user} onComplete={onMatterComplete} onAuthError={handleAuthError} />
        )}
        {view === 'matters' && (
          <MatterList
            key={refreshKey}
            user={user}
            onOpenMatter={openMatter}
            onNewMatter={() => setView('panel')}
            onAuthError={handleAuthError}
          />
        )}
        {view === 'matter' && (
          <MatterDetail
            matterId={activeMatterId}
            user={user}
            onBack={() => setView('matters')}
            onAuthError={handleAuthError}
          />
        )}
        {view === 'admin' && <AdminPanel user={user} onAuthError={handleAuthError} />}
        {view === 'council' && features.general_council && (
          <GeneralCouncil onAuthError={handleAuthError} />
        )}
      </main>
    </div>
  );
}

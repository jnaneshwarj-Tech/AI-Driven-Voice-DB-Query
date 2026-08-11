import React, { useState } from 'react';
import Dashboard from './components/Dashboard';
import Students from './components/Students';
import AIQuery from './components/AIQuery';
import Upload from './components/Upload';
import Validation from './components/Validation';
import SchemaView from './components/SchemaView';
import Login from './components/Login';

const NAV_ALL = [
  { id: 'dashboard', label: '📊 Dashboard' },
  { id: 'students', label: '🎓 Students' },
  { id: 'query', label: '🤖 AI Query' },
  { id: 'upload', label: '📁 Upload', staffOnly: true },
  { id: 'validation', label: '⚠️ Validation' },
  { id: 'schema', label: '🗄️ Schema' },
];

function getInitialUser() {
  const token = sessionStorage.getItem('token');
  const role = sessionStorage.getItem('role');
  const name = sessionStorage.getItem('name');
  if (token && role && name) return { token, role, name };
  return null;
}

export default function App() {
  const [page, setPage] = useState('dashboard');
  const [user, setUser] = useState(getInitialUser);

  const handleLogin = (userData) => {
    setUser(userData);
    setPage('dashboard');
  };

  const handleLogout = () => {
    sessionStorage.clear();
    setUser(null);
  };

  if (!user) return <Login onLogin={handleLogin} />;

  const isAdmin = user.role === 'admin';
  const nav = NAV_ALL.filter(n => !n.staffOnly || !isAdmin);

  const renderPage = () => {
    // Admin cannot access upload
    if (page === 'upload' && isAdmin) return (
      <div className="alert alert-error">
        ❌ Admins are not allowed to upload or modify data.
      </div>
    );
    switch (page) {
      case 'dashboard': return <Dashboard />;
      case 'students': return <Students role={user.role} />;
      case 'query': return <AIQuery role={user.role} />;
      case 'upload': return <Upload />;
      case 'validation': return <Validation />;
      case 'schema': return <SchemaView />;
      default: return <Dashboard />;
    }
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-logo">🎓 Student DBMS</div>
        <nav>
          {nav.map(n => (
            <button key={n.id} className={page === n.id ? 'active' : ''} onClick={() => setPage(n.id)}>
              {n.label}
            </button>
          ))}
        </nav>
        <div style={{ padding: '12px 16px', borderTop: '1px solid #2d2d4e' }}>
          <div style={{ fontSize: '0.78rem', color: '#aaa', marginBottom: 8, textAlign: 'center' }}>
            👤 {user.name}
            <span style={{
              marginLeft: 6, padding: '2px 7px', borderRadius: 10, fontSize: '0.7rem', fontWeight: 700,
              background: isAdmin ? '#e53935' : '#2e7d32', color: '#fff'
            }}>
              {user.role.toUpperCase()}
            </span>
          </div>
          <button onClick={handleLogout}
            style={{ width: '100%', padding: '9px', background: '#e53935', border: 'none',
              borderRadius: 8, color: '#fff', cursor: 'pointer', fontSize: '0.85rem' }}>
            🚪 Logout
          </button>
        </div>
      </aside>
      <div className="main">
        <div className="topbar">
          <h1>AI-Powered Student Data Management System</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {isAdmin && (
              <span style={{ background: '#fff3e0', color: '#e65100', padding: '4px 10px',
                borderRadius: 8, fontSize: '0.78rem', fontWeight: 600 }}>
                👁️ View-Only Mode
              </span>
            )}
            <span style={{ fontSize: '0.8rem', color: '#666' }}>MySQL · FastAPI · React</span>
          </div>
        </div>
        <div className="content">{renderPage()}</div>
      </div>
    </div>
  );
}

import React, { useState } from 'react';
import { loginUser, registerUser, forgotPassword } from '../api';

export default function Login({ onLogin }) {
  const [tab, setTab] = useState('login');
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const [show, setShow] = useState(false);

  const set = (k, v) => { setForm(f => ({ ...f, [k]: v })); setError(''); setSuccess(''); };

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!form.email || !form.password) { setError('Email and password are required.'); return; }
    setLoading(true);
    try {
      const r = await loginUser(form.email, form.password);
      sessionStorage.setItem('token', r.data.token);
      sessionStorage.setItem('role', r.data.role);
      sessionStorage.setItem('name', r.data.name);
      onLogin(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || 'Login failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    if (!form.name || !form.email || !form.password) { setError('All fields are required.'); return; }
    if (form.password.length < 6) { setError('Password must be at least 6 characters.'); return; }
    setLoading(true);
    try {
      await registerUser(form.name, form.email, form.password);
      setSuccess('✅ Registered successfully! You can now login.');
      setTab('login');
      setForm(f => ({ ...f, name: '', password: '' }));
    } catch (e) {
      setError(e.response?.data?.detail || 'Registration failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleForgot = async (e) => {
    e.preventDefault();
    if (!form.email) { setError('Please enter your registered email.'); return; }
    setLoading(true);
    try {
      const r = await forgotPassword(form.email);
      setSuccess('✅ ' + (r.data?.message || 'If an account exists, a reset link has been sent.'));
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to request reset link.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)'
    }}>
      <div style={{
        background: '#fff', borderRadius: 16, padding: '40px 36px',
        width: 400, boxShadow: '0 20px 60px rgba(0,0,0,0.4)'
      }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ fontSize: '2.8rem' }}>🎓</div>
          <h1 style={{ fontSize: '1.3rem', fontWeight: 700, color: '#1a1a2e', margin: '6px 0 4px' }}>
            Student DBMS
          </h1>
          <p style={{ color: '#888', fontSize: '0.82rem', margin: 0 }}>
            AI-Powered Student Data Management
          </p>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', borderBottom: '2px solid #eee', marginBottom: 24 }}>
          {['login', 'register'].map(t => (
            <button key={t} onClick={() => { setTab(t); setError(''); setSuccess(''); }}
              style={{
                flex: 1, padding: '10px', border: 'none', background: 'none', cursor: 'pointer',
                fontWeight: 600, fontSize: '0.9rem',
                color: tab === t ? '#1a73e8' : '#999',
                borderBottom: tab === t ? '2px solid #1a73e8' : '2px solid transparent',
                marginBottom: -2,
              }}>
              {t === 'login' ? '🔑 Login' : '📝 Register'}
            </button>
          ))}
        </div>

        {success && <div className="alert alert-success" style={{ marginBottom: 16 }}>{success}</div>}
        {error && <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>}

        {tab === 'login' ? (
          <form onSubmit={handleLogin}>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Email</label>
              <input className="search-input" style={{ width: '100%' }} type="email"
                placeholder="your@email.com" value={form.email}
                onChange={e => set('email', e.target.value)} autoFocus />
            </div>
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label style={labelStyle}>Password</label>
                <button type="button" onClick={() => { setTab('forgot'); setError(''); setSuccess(''); }}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#1a73e8', fontSize: '0.78rem', fontWeight: 600 }}>
                  Forgot Password?
                </button>
              </div>
              <div style={{ position: 'relative' }}>
                <input className="search-input" style={{ width: '100%', paddingRight: 40 }}
                  type={show ? 'text' : 'password'} placeholder="••••••••"
                  value={form.password} onChange={e => set('password', e.target.value)} />
                <button type="button" onClick={() => setShow(s => !s)} style={eyeBtn}>
                  {show ? '🙈' : '👁️'}
                </button>
              </div>
            </div>
            <button type="submit" className="btn btn-primary" style={{ width: '100%', padding: 12 }} disabled={loading}>
              {loading ? <span className="spinner" /> : '🔑 Login'}
            </button>
            <div style={{ marginTop: 16, padding: '10px 14px', background: '#f8fbff', borderRadius: 8, border: '1px solid #e0eaff' }}>
              <p style={{ fontSize: '0.78rem', color: '#666', margin: 0, textAlign: 'center' }}>
                Register to get <strong>Staff</strong> access · Admin accounts are created manually
              </p>
            </div>
          </form>
        ) : tab === 'forgot' ? (
          <form onSubmit={handleForgot}>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Registered Email</label>
              <input className="search-input" style={{ width: '100%' }} type="email"
                placeholder="your@email.com" value={form.email}
                onChange={e => set('email', e.target.value)} autoFocus />
            </div>
            <button type="submit" className="btn btn-primary" style={{ width: '100%', padding: 12 }} disabled={loading}>
              {loading ? <span className="spinner" /> : '📧 Send Reset Link'}
            </button>
            <div style={{ marginTop: 16, textCenter: 'center' }}>
              <button type="button" onClick={() => { setTab('login'); setError(''); setSuccess(''); }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#666', fontSize: '0.85rem' }}>
                ← Back to Login
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleRegister}>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Full Name</label>
              <input className="search-input" style={{ width: '100%' }} type="text"
                placeholder="Your full name" value={form.name}
                onChange={e => set('name', e.target.value)} autoFocus />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Email</label>
              <input className="search-input" style={{ width: '100%' }} type="email"
                placeholder="your@email.com" value={form.email}
                onChange={e => set('email', e.target.value)} />
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>Password <span style={{ color: '#999', fontWeight: 400 }}>(min 6 chars)</span></label>
              <div style={{ position: 'relative' }}>
                <input className="search-input" style={{ width: '100%', paddingRight: 40 }}
                  type={show ? 'text' : 'password'} placeholder="••••••••"
                  value={form.password} onChange={e => set('password', e.target.value)} />
                <button type="button" onClick={() => setShow(s => !s)} style={eyeBtn}>
                  {show ? '🙈' : '👁️'}
                </button>
              </div>
            </div>
            <button type="submit" className="btn btn-primary" style={{ width: '100%', padding: 12 }} disabled={loading}>
              {loading ? <span className="spinner" /> : '📝 Create Account'}
            </button>
            <div style={{ marginTop: 16, padding: '10px 14px', background: '#fff8e1', borderRadius: 8, border: '1px solid #ffe082' }}>
              <p style={{ fontSize: '0.78rem', color: '#795548', margin: 0, textAlign: 'center' }}>
                ⚠️ New accounts get <strong>Staff</strong> role by default
              </p>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

const labelStyle = { display: 'block', fontSize: '0.83rem', fontWeight: 600, color: '#444', marginBottom: 5 };
const eyeBtn = { position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', fontSize: '1rem' };

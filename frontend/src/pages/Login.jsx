import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';
import { Database, Lock, User, AlertCircle, Mail } from 'lucide-react';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [forgotMode, setForgotMode] = useState(false);
  const [forgotStep, setForgotStep] = useState('email');
  const [otp, setOtp] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [secondsLeft, setSecondsLeft] = useState(120);
  const navigate = useNavigate();

  useEffect(() => {
    if (!forgotMode || forgotStep !== 'otp') return undefined;
    setSecondsLeft(120);
    const timer = window.setInterval(() => setSecondsLeft((seconds) => Math.max(0, seconds - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [forgotMode, forgotStep]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);

    try {
      const response = await api.post('/auth/login', {
        username,
        password,
      });
      
      localStorage.setItem('token', response.data.access_token);
      localStorage.setItem('role', response.data.user?.role || '');
      localStorage.setItem('username', response.data.user?.username || '');
      if (response.data.user?.theme) {
        localStorage.setItem('theme', response.data.user.theme);
      }
      
      // Force trigger state sync for theme context
      window.dispatchEvent(new Event('storage'));
      
      navigate('/dashboard');
    } catch (err) {
      if (err.response?.status === 401) {
        setError('Invalid username or password.');
      } else if (err.response?.status === 422) {
        setError('Please enter both username and password.');
      } else if (err.response) {
        setError(err.response.data?.detail || 'Login failed. Please try again.');
      } else {
        setError('Failed to connect to the server. Is the backend running?');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleForgotPassword = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);
    try {
      const response = await api.post('/auth/forgot-password', { username, email });
      setMessage(response.data.message);
      setForgotStep('otp');
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to request a password reset.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);
    try {
      const response = await api.post('/auth/verify-reset-otp', { email, otp });
      setResetToken(response.data.reset_token);
      setForgotStep('password');
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to verify OTP.');
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await api.post('/auth/reset-password', { reset_token: resetToken, new_password: newPassword, confirm_password: confirmPassword });
      setForgotMode(false);
      setForgotStep('email');
      setEmail('');
      setOtp('');
      setNewPassword('');
      setConfirmPassword('');
      setMessage('Password reset successful. Please sign in with your new password.');
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to reset password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8 bg-[url('https://images.unsplash.com/photo-1558486012-817176f84c6d?q=80&w=2400&auto=format&fit=crop')] bg-cover bg-center">
      <div className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm"></div>
      
      <div className="relative sm:mx-auto sm:w-full sm:max-w-md z-10">
        <div className="flex justify-center">
          <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-500/30">
            <Database className="w-8 h-8 text-white" />
          </div>
        </div>
        <h2 className="mt-6 text-center text-3xl font-extrabold text-white tracking-tight">
          AI Database System
        </h2>
        <p className="mt-2 text-center text-sm text-slate-300">
          Sign in to access your college workspace
        </p>
      </div>

      <div className="relative mt-8 sm:mx-auto sm:w-full sm:max-w-md z-10">
        <div className="bg-slate-800/50 backdrop-blur-xl py-8 px-4 shadow-2xl sm:rounded-2xl sm:px-10 border border-slate-700">
          {message && (
            <div className="rounded-lg bg-emerald-500/10 p-4 border border-emerald-500/20 text-emerald-300">
              <p className="text-sm font-medium">{message}</p>
            </div>
          )}
          {forgotMode ? (
            <form className="space-y-6" onSubmit={forgotStep === 'email' ? handleForgotPassword : forgotStep === 'otp' ? handleVerifyOtp : handleResetPassword}>
              {error && <div className="rounded-lg bg-red-500/10 p-4 border border-red-500/20 flex items-center gap-3 text-red-400"><AlertCircle className="w-5 h-5" /><p className="text-sm font-medium">{error}</p></div>}
              {forgotStep === 'email' && <>
                <div>
                  <label className="block text-sm font-medium text-slate-300">Username</label>
                  <div className="mt-1 relative"><User className="absolute left-3 top-3 h-5 w-5 text-slate-500" /><input type="text" required value={username} onChange={(e) => setUsername(e.target.value)} className="block w-full pl-10 pr-3 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Your username" /></div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300">Registered email</label>
                  <div className="mt-1 relative"><Mail className="absolute left-3 top-3 h-5 w-5 text-slate-500" /><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="block w-full pl-10 pr-3 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="you@example.com" /></div>
                  <p className="mt-2 text-xs text-slate-400">Enter the email associated with your username</p>
                </div>
              </>}
              {forgotStep === 'otp' && <div>
                <label className="block text-sm font-medium text-slate-300">Enter the OTP sent to your email</label>
                <input type="text" inputMode="numeric" pattern="[0-9]{6}" maxLength="6" required value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))} className="mt-1 block w-full px-3 py-2.5 text-center tracking-[0.5em] border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="000000" />
                <p className="mt-2 text-sm text-slate-400">OTP expires in {String(Math.floor(secondsLeft / 60)).padStart(2, '0')}:{String(secondsLeft % 60).padStart(2, '0')}</p>
              </div>}
              {forgotStep === 'password' && <>
                <div><label className="block text-sm font-medium text-slate-300">New password</label><input type="password" minLength="6" required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="mt-1 block w-full px-3 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500" /></div>
                <div><label className="block text-sm font-medium text-slate-300">Confirm new password</label><input type="password" minLength="6" required value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className="mt-1 block w-full px-3 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500" /></div>
              </>}
              <button type="submit" disabled={loading} className="w-full py-2.5 px-4 rounded-xl text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50">
                {loading ? 'Please wait...' : forgotStep === 'email' ? 'Send OTP' : forgotStep === 'otp' ? 'Verify OTP' : 'Reset password'}
              </button>
              {forgotStep === 'otp' && <button type="button" onClick={handleForgotPassword} disabled={loading} className="w-full text-sm font-medium text-blue-400 hover:text-blue-300">Resend OTP</button>}
              <button type="button" onClick={() => { setForgotMode(false); setError(''); setMessage(''); }} className="w-full text-sm font-medium text-blue-400 hover:text-blue-300">Back to sign in</button>
            </form>
          ) : (
          <form className="space-y-6" onSubmit={handleLogin}>
            {error && (
              <div className="rounded-lg bg-red-500/10 p-4 border border-red-500/20 flex items-center gap-3 text-red-400">
                <AlertCircle className="w-5 h-5 flex-shrink-0" />
                <p className="text-sm font-medium">{error}</p>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-slate-300">Username</label>
              <div className="mt-1 relative rounded-md shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <User className="h-5 w-5 text-slate-500" />
                </div>
                <input
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="block w-full pl-10 pr-3 py-2.5 border border-slate-600 rounded-xl leading-5 bg-slate-900/50 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all sm:text-sm"
                  placeholder="Enter your registered username"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300">Password</label>
              <div className="mt-1 relative rounded-md shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-slate-500" />
                </div>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full pl-10 pr-3 py-2.5 border border-slate-600 rounded-xl leading-5 bg-slate-900/50 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all sm:text-sm"
                  placeholder="••••••••"
                />
              </div>
              <button type="button" onClick={() => { setForgotMode(true); setError(''); setMessage(''); }} className="mt-2 text-sm font-medium text-blue-400 hover:text-blue-300">Forgot password?</button>
            </div>

            <div>
              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-xl shadow-lg text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-600 focus:ring-offset-slate-900 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : 'Sign in'}
              </button>
            </div>
            
            <div className="mt-4 text-center">
              <Link to="/register" className="text-sm font-medium text-blue-400 hover:text-blue-300">
                Register
              </Link>
            </div>
          </form>
          )}
        </div>
      </div>
    </div>
  );
}

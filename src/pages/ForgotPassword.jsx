import { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import { Database, Mail, AlertCircle, CheckCircle2, ArrowLeft } from 'lucide-react';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [devToken, setDevToken] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setDevToken('');

    if (!email.trim()) {
      setError('Please enter your registered email address.');
      return;
    }

    setLoading(true);

    try {
      const response = await api.post('/auth/forgot-password', { email: email.trim() });
      setMessage(response.data?.message || 'If an account exists for this email, a password reset link has been sent.');
      if (response.data?.token) {
        setDevToken(response.data.token);
      }
    } catch (err) {
      if (err.response?.data?.detail) {
        setError(err.response.data.detail);
      } else if (err.response?.status === 422) {
        setError('Please enter a valid email address.');
      } else {
        setError('Failed to send reset link. Please check your connection and try again.');
      }
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
          Reset Password
        </h2>
        <p className="mt-2 text-center text-sm text-slate-300">
          Enter your email address to receive a secure password reset link
        </p>
      </div>

      <div className="relative mt-8 sm:mx-auto sm:w-full sm:max-w-md z-10">
        <div className="bg-slate-800/50 backdrop-blur-xl py-8 px-4 shadow-2xl sm:rounded-2xl sm:px-10 border border-slate-700">
          <form className="space-y-6" onSubmit={handleSubmit}>
            {error && (
              <div className="rounded-lg bg-red-500/10 p-4 border border-red-500/20 flex items-center gap-3 text-red-400">
                <AlertCircle className="w-5 h-5 flex-shrink-0" />
                <p className="text-sm font-medium">{error}</p>
              </div>
            )}

            {message && (
              <div className="rounded-lg bg-emerald-500/10 p-4 border border-emerald-500/20 space-y-4 text-emerald-400">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="w-5 h-5 flex-shrink-0 mt-0.5" />
                  <div className="text-sm font-medium">
                    <p>{message}</p>
                  </div>
                </div>
                {devToken && (
                  <div className="pt-2 border-t border-emerald-500/20">
                    <Link
                      to={`/reset-password/${devToken}`}
                      className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl font-bold text-sm bg-emerald-600 hover:bg-emerald-500 text-white shadow-xl hover:shadow-emerald-500/30 transition-all transform hover:-translate-y-0.5 active:translate-y-0"
                    >
                      👉 🔑 Proceed to Reset Password Now
                    </Link>
                  </div>
                )}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-slate-300">Registered Email Address</label>
              <div className="mt-1 relative rounded-md shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Mail className="h-5 w-5 text-slate-500" />
                </div>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full pl-10 pr-3 py-2.5 border border-slate-600 rounded-xl leading-5 bg-slate-900/50 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all sm:text-sm"
                  placeholder="your.email@college.edu"
                />
              </div>
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
                ) : 'Send Reset Link'}
              </button>
            </div>
            
            <div className="mt-4 text-center">
              <Link to="/login" className="inline-flex items-center gap-2 text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors">
                <ArrowLeft className="w-4 h-4" /> Back to Login
              </Link>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

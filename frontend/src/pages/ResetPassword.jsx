import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Lock, AlertCircle } from 'lucide-react';
import api from '../services/api';

export default function ResetPassword() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      await api.post('/auth/reset-password', {
        token,
        new_password: password,
        confirm_password: confirmPassword,
      });
      navigate('/login', { state: { resetComplete: true } });
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to reset password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-slate-800/70 p-8 rounded-2xl border border-slate-700 shadow-2xl">
        <h1 className="text-2xl font-bold text-white">Set a new password</h1>
        <p className="mt-2 text-sm text-slate-400">Choose a password with at least 6 characters.</p>
        {error && <div className="mt-6 rounded-lg bg-red-500/10 p-4 border border-red-500/20 flex gap-3 text-red-400"><AlertCircle className="w-5 h-5" /><p className="text-sm">{error}</p></div>}
        <form className="mt-6 space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="block text-sm font-medium text-slate-300">New password</label>
            <div className="mt-1 relative"><Lock className="absolute left-3 top-3 h-5 w-5 text-slate-500" /><input type="password" required minLength="6" value={password} onChange={(e) => setPassword(e.target.value)} className="block w-full pl-10 pr-3 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500" /></div>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300">Confirm password</label>
            <div className="mt-1 relative"><Lock className="absolute left-3 top-3 h-5 w-5 text-slate-500" /><input type="password" required minLength="6" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className="block w-full pl-10 pr-3 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500" /></div>
          </div>
          <button type="submit" disabled={loading} className="w-full py-2.5 rounded-xl text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50">{loading ? 'Updating...' : 'Update password'}</button>
        </form>
        <Link to="/login" className="block mt-5 text-center text-sm text-blue-400 hover:text-blue-300">Back to sign in</Link>
      </div>
    </div>
  );
}
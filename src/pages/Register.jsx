import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';
import { Database, AlertCircle } from 'lucide-react';

export default function Register() {
  const [regUsername, setRegUsername] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regRole, setRegRole] = useState('Staff');
  const [regError, setRegError] = useState('');
  const [regLoading, setRegLoading] = useState(false);
  const navigate = useNavigate();

  const handleRegister = async (e) => {
    e.preventDefault();
    setRegError('');
    setRegLoading(true);

    try {
      await api.post('/auth/register', {
        username: regUsername,
        email: regEmail,
        password: regPassword,
        role: regRole,
      });
      alert('Registration successful. You can now sign in with the same credentials.');
      navigate('/login');
    } catch (err) {
      if (err.response) {
        if (err.response.status === 400) {
          setRegError(err.response.data?.detail || 'Registration failed. Please check the details.');
        } else if (err.response.data?.detail) {
          const detail = Array.isArray(err.response.data.detail)
            ? err.response.data.detail[0]?.msg || 'Registration failed. Please check the details.'
            : err.response.data.detail;
          setRegError(detail);
        } else {
          setRegError('Registration failed. Please check the details.');
        }
      } else {
        setRegError('Failed to connect to the server for registration.');
      }
    } finally {
      setRegLoading(false);
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
          Create an Account
        </h2>
      </div>

      <div className="relative mt-8 sm:mx-auto sm:w-full sm:max-w-md z-10">
        <div className="bg-slate-800/50 backdrop-blur-xl py-8 px-4 shadow-2xl sm:rounded-2xl sm:px-10 border border-slate-700">
            
          {regError && (
            <div className="mb-4 rounded-lg bg-red-500/10 p-4 border border-red-500/20 flex items-center gap-3 text-red-400">
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <p className="text-sm font-medium">{regError}</p>
            </div>
          )}

          <form className="space-y-4" onSubmit={handleRegister}>
            <div>
              <label className="block text-sm font-medium text-slate-300">Username</label>
              <input
                type="text"
                required
                value={regUsername}
                onChange={(e) => setRegUsername(e.target.value)}
                className="mt-1 block w-full px-3 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all sm:text-sm"
                placeholder="Choose a unique username"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300">Email</label>
              <input
                type="email"
                required
                value={regEmail}
                onChange={(e) => setRegEmail(e.target.value)}
                className="mt-1 block w-full px-3 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all sm:text-sm"
                placeholder="Enter a valid email address"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300">Password</label>
              <input
                type="password"
                required
                value={regPassword}
                onChange={(e) => setRegPassword(e.target.value)}
                className="mt-1 block w-full px-3 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all sm:text-sm"
                placeholder="Create a strong password"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300">Role</label>
              <select
                value={regRole}
                onChange={(e) => setRegRole(e.target.value)}
                className="mt-1 block w-full px-3 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all sm:text-sm"
              >
                <option value="Staff">Staff</option>
                <option value="Admin">Admin</option>
              </select>
            </div>

            <button
              type="submit"
              disabled={regLoading}
              className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-xl shadow-lg text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-600 focus:ring-offset-slate-900 transition-all disabled:opacity-50 disabled:cursor-not-allowed mt-6"
            >
              {regLoading ? 'Registering...' : 'Register'}
            </button>
            <div className="mt-4 text-center">
              <Link to="/login" className="text-sm font-medium text-blue-400 hover:text-blue-300">
                Already have an account? Sign in
              </Link>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

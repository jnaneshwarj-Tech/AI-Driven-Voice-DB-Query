import { useState, useEffect, useRef, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../services/api';
import {
  Database, Mail, Lock, AlertCircle, CheckCircle2,
  ArrowLeft, Eye, EyeOff, RefreshCw, ShieldCheck,
} from 'lucide-react';

// ── Steps ─────────────────────────────────────────────────────────────────────
const STEP_EMAIL   = 1;
const STEP_OTP     = 2;
const STEP_PASSWORD = 3;
const STEP_SUCCESS  = 4;

const OTP_EXPIRY_SECONDS  = 120; // Must match backend OTP_EXPIRY_SECONDS
const RESEND_COOLDOWN_SEC = 30;  // Must match backend OTP_RESEND_COOLDOWN_SECONDS

// ── Spinner component ─────────────────────────────────────────────────────────
function Spinner() {
  return (
    <svg
      className="animate-spin h-5 w-5 text-white"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
    </svg>
  );
}

// ── Error banner ──────────────────────────────────────────────────────────────
function ErrorBanner({ message }) {
  if (!message) return null;
  return (
    <div className="rounded-lg bg-red-500/10 p-4 border border-red-500/20 flex items-start gap-3 text-red-400">
      <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
      <p className="text-sm font-medium">{message}</p>
    </div>
  );
}

// ── Step indicator ────────────────────────────────────────────────────────────
function StepIndicator({ current }) {
  const steps = ['Email', 'Verify OTP', 'New Password'];
  return (
    <div className="flex items-center justify-center gap-0 mb-6">
      {steps.map((label, idx) => {
        const num   = idx + 1;
        const done  = num < current;
        const active = num === current;
        return (
          <div key={label} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all
                  ${done   ? 'bg-emerald-500 text-white'
                  : active ? 'bg-blue-600 text-white ring-2 ring-blue-400/40 ring-offset-1 ring-offset-slate-900'
                  :          'bg-slate-700 text-slate-400'}`}
              >
                {done ? <CheckCircle2 className="w-4 h-4" /> : num}
              </div>
              <span className={`mt-1 text-[10px] font-medium whitespace-nowrap
                ${active ? 'text-blue-400' : done ? 'text-emerald-400' : 'text-slate-500'}`}>
                {label}
              </span>
            </div>
            {idx < steps.length - 1 && (
              <div className={`h-px w-10 mx-1 mb-4 transition-all
                ${done ? 'bg-emerald-500' : 'bg-slate-700'}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function ForgotPassword() {
  const navigate = useNavigate();

  // Step tracking
  const [step, setStep] = useState(STEP_EMAIL);

  // Shared state
  const [email,      setEmail]      = useState('');
  const [error,      setError]      = useState('');
  const [loading,    setLoading]    = useState(false);

  // Step 2 — OTP
  const [otp,            setOtp]           = useState('');
  const [otpError,       setOtpError]      = useState('');
  const [countdown,      setCountdown]     = useState(OTP_EXPIRY_SECONDS);
  const [otpExpired,     setOtpExpired]    = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [resendLoading,  setResendLoading]  = useState(false);
  const countdownRef  = useRef(null);
  const resendRef     = useRef(null);
  const otpInputRef   = useRef(null);

  // Step 3 — Password
  const [resetToken,       setResetToken]       = useState('');
  const [newPassword,      setNewPassword]      = useState('');
  const [confirmPassword,  setConfirmPassword]  = useState('');
  const [showNew,          setShowNew]          = useState(false);
  const [showConfirm,      setShowConfirm]      = useState(false);
  const [passError,        setPassError]        = useState('');

  // ── Countdown timer ─────────────────────────────────────────────────────────
  const startCountdown = useCallback(() => {
    clearInterval(countdownRef.current);
    setCountdown(OTP_EXPIRY_SECONDS);
    setOtpExpired(false);
    countdownRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(countdownRef.current);
          setOtpExpired(true);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, []);

  // ── Resend cooldown timer ───────────────────────────────────────────────────
  const startResendCooldown = useCallback(() => {
    clearInterval(resendRef.current);
    setResendCooldown(RESEND_COOLDOWN_SEC);
    resendRef.current = setInterval(() => {
      setResendCooldown((prev) => {
        if (prev <= 1) {
          clearInterval(resendRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, []);

  // Cleanup on unmount
  useEffect(() => () => {
    clearInterval(countdownRef.current);
    clearInterval(resendRef.current);
  }, []);

  // Format MM:SS
  const formatTime = (sec) => {
    const m = String(Math.floor(sec / 60)).padStart(2, '0');
    const s = String(sec % 60).padStart(2, '0');
    return `${m}:${s}`;
  };

  // ── Step 1: Send OTP ────────────────────────────────────────────────────────
  const handleSendOtp = async (e) => {
    e?.preventDefault();
    setError('');

    const trimmed = email.trim().toLowerCase();
    if (!trimmed) {
      setError('Please enter your registered email address.');
      return;
    }
    const emailRx = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRx.test(trimmed)) {
      setError('Please enter a valid email address.');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/forgot-password', { email: trimmed });
      setStep(STEP_OTP);
      setOtp('');
      setOtpError('');
      startCountdown();
      startResendCooldown();
      setTimeout(() => otpInputRef.current?.focus(), 100);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 429) {
        setError(detail || 'Too many requests. Please wait before trying again.');
      } else {
        setError(detail || 'Failed to send OTP. Please check your connection and try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  // ── Step 2: Verify OTP ──────────────────────────────────────────────────────
  const handleVerifyOtp = async (e) => {
    e?.preventDefault();
    setOtpError('');

    if (!otp.trim() || otp.trim().length !== 6) {
      setOtpError('Please enter the 6-digit OTP.');
      return;
    }
    if (otpExpired) {
      setOtpError('OTP expired. Please request a new one.');
      return;
    }

    setLoading(true);
    try {
      const res = await api.post('/auth/verify-reset-otp', {
        email: email.trim().toLowerCase(),
        otp: otp.trim(),
      });
      clearInterval(countdownRef.current);
      setResetToken(res.data.reset_token);
      setStep(STEP_PASSWORD);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setOtpError(detail || 'Invalid OTP. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // ── Step 2: Resend OTP ──────────────────────────────────────────────────────
  const handleResendOtp = async () => {
    if (resendCooldown > 0 || resendLoading) return;
    setOtpError('');
    setResendLoading(true);
    try {
      await api.post('/auth/forgot-password', { email: email.trim().toLowerCase() });
      setOtp('');
      setOtpError('');
      startCountdown();
      startResendCooldown();
      setTimeout(() => otpInputRef.current?.focus(), 100);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 429) {
        setOtpError(detail || 'Please wait before requesting a new OTP.');
      } else {
        setOtpError(detail || 'Failed to resend OTP. Please try again.');
      }
    } finally {
      setResendLoading(false);
    }
  };

  // ── Step 3: Reset Password ──────────────────────────────────────────────────
  const handleResetPassword = async (e) => {
    e?.preventDefault();
    setPassError('');

    if (!newPassword) {
      setPassError('Please enter a new password.');
      return;
    }
    if (newPassword.length < 6) {
      setPassError('Password must be at least 6 characters long.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPassError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/reset-password', {
        reset_token: resetToken,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      setStep(STEP_SUCCESS);
      // Auto-redirect after 4 seconds
      setTimeout(() => navigate('/login'), 4000);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setPassError(detail || 'Failed to reset password. Please start the process again.');
    } finally {
      setLoading(false);
    }
  };

  // ── Shared page shell ───────────────────────────────────────────────────────
  const Shell = ({ children }) => (
    <div className="min-h-screen bg-slate-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8 bg-[url('https://images.unsplash.com/photo-1558486012-817176f84c6d?q=80&w=2400&auto=format&fit=crop')] bg-cover bg-center">
      <div className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm" />

      {/* Brand header */}
      <div className="relative sm:mx-auto sm:w-full sm:max-w-md z-10 mb-8">
        <div className="flex justify-center">
          <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-500/30">
            <Database className="w-8 h-8 text-white" />
          </div>
        </div>
        <h2 className="mt-6 text-center text-3xl font-extrabold text-white tracking-tight">
          Reset Password
        </h2>
        <p className="mt-2 text-center text-sm text-slate-300">
          AI Database Automator — Secure Account Recovery
        </p>
      </div>

      {/* Card */}
      <div className="relative sm:mx-auto sm:w-full sm:max-w-md z-10">
        <div className="bg-slate-800/50 backdrop-blur-xl py-8 px-4 shadow-2xl sm:rounded-2xl sm:px-10 border border-slate-700">
          {children}
        </div>
      </div>
    </div>
  );

  // ────────────────────────────────────────────────────────────────────────────
  // STEP 1 — Email Entry
  // ────────────────────────────────────────────────────────────────────────────
  if (step === STEP_EMAIL) {
    return (
      <Shell>
        <StepIndicator current={1} />
        <form className="space-y-5" onSubmit={handleSendOtp}>
          <div className="text-center mb-2">
            <p className="text-sm text-slate-400">
              Enter the email address linked to your account and we'll send you a one-time verification code.
            </p>
          </div>

          <ErrorBanner message={error} />

          <div>
            <label className="block text-sm font-medium text-slate-300">Registered Email</label>
            <div className="mt-1 relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Mail className="h-5 w-5 text-slate-500" />
              </div>
              <input
                id="forgot-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="block w-full pl-10 pr-3 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all sm:text-sm"
                placeholder="your.email@college.edu"
              />
            </div>
          </div>

          <button
            id="send-otp-btn"
            type="submit"
            disabled={loading}
            className="w-full flex justify-center items-center gap-2 py-2.5 px-4 rounded-xl shadow-lg text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-600 focus:ring-offset-slate-900 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? <><Spinner /> Sending OTP…</> : 'Send OTP'}
          </button>

          <div className="text-center pt-1">
            <Link to="/login" className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 transition-colors">
              <ArrowLeft className="w-4 h-4" /> Back to Login
            </Link>
          </div>
        </form>
      </Shell>
    );
  }

  // ────────────────────────────────────────────────────────────────────────────
  // STEP 2 — OTP Verification
  // ────────────────────────────────────────────────────────────────────────────
  if (step === STEP_OTP) {
    return (
      <Shell>
        <StepIndicator current={2} />
        <form className="space-y-5" onSubmit={handleVerifyOtp}>
          {/* Email hint */}
          <div className="rounded-lg bg-blue-500/10 border border-blue-500/20 p-3 text-center">
            <p className="text-xs text-blue-300 font-medium">OTP sent to</p>
            <p className="text-sm text-blue-100 font-semibold mt-0.5 break-all">{email}</p>
          </div>

          {/* Countdown */}
          <div className="flex flex-col items-center gap-1">
            <div
              className={`text-4xl font-mono font-bold tabular-nums tracking-widest
                ${otpExpired ? 'text-red-400' : countdown <= 30 ? 'text-amber-400' : 'text-emerald-400'}`}
            >
              {formatTime(countdown)}
            </div>
            <p className={`text-xs font-medium ${otpExpired ? 'text-red-400' : 'text-slate-400'}`}>
              {otpExpired ? '⚠ OTP has expired' : 'OTP valid for this duration'}
            </p>
          </div>

          <ErrorBanner message={otpError} />

          {/* OTP input */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              6-Digit Verification Code
            </label>
            <input
              id="otp-input"
              ref={otpInputRef}
              type="text"
              inputMode="numeric"
              pattern="\d{6}"
              maxLength={6}
              autoComplete="one-time-code"
              value={otp}
              disabled={otpExpired}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
              className="block w-full text-center text-3xl font-mono font-bold tracking-[0.5em] py-4 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              placeholder="······"
            />
            <p className="mt-1.5 text-xs text-slate-500 text-center">
              Check your email inbox (and spam folder)
            </p>
          </div>

          {/* Verify button */}
          <button
            id="verify-otp-btn"
            type="submit"
            disabled={loading || otpExpired || otp.length !== 6}
            className="w-full flex justify-center items-center gap-2 py-2.5 px-4 rounded-xl shadow-lg text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-600 focus:ring-offset-slate-900 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? <><Spinner /> Verifying…</> : <><ShieldCheck className="w-4 h-4" /> Verify OTP</>}
          </button>

          {/* Resend row */}
          <div className="flex items-center justify-between pt-1">
            <button
              id="resend-otp-btn"
              type="button"
              onClick={handleResendOtp}
              disabled={resendCooldown > 0 || resendLoading}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-400 hover:text-blue-300 transition-colors disabled:text-slate-500 disabled:cursor-not-allowed"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${resendLoading ? 'animate-spin' : ''}`} />
              {resendLoading
                ? 'Sending…'
                : resendCooldown > 0
                  ? `Resend OTP in ${resendCooldown}s`
                  : 'Resend OTP'}
            </button>

            <button
              type="button"
              onClick={() => { setStep(STEP_EMAIL); setError(''); setOtpError(''); setOtp(''); clearInterval(countdownRef.current); clearInterval(resendRef.current); }}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              Change email
            </button>
          </div>
        </form>
      </Shell>
    );
  }

  // ────────────────────────────────────────────────────────────────────────────
  // STEP 3 — New Password
  // ────────────────────────────────────────────────────────────────────────────
  if (step === STEP_PASSWORD) {
    return (
      <Shell>
        <StepIndicator current={3} />
        <form className="space-y-5" onSubmit={handleResetPassword}>
          <div className="text-center mb-2">
            <p className="text-sm text-slate-400">
              OTP verified. Set a new secure password for your account.
            </p>
          </div>

          <ErrorBanner message={passError} />

          {/* New Password */}
          <div>
            <label className="block text-sm font-medium text-slate-300">New Password</label>
            <div className="mt-1 relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Lock className="h-5 w-5 text-slate-500" />
              </div>
              <input
                id="new-password"
                type={showNew ? 'text' : 'password'}
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="block w-full pl-10 pr-10 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all sm:text-sm"
                placeholder="At least 6 characters"
              />
              <button
                type="button"
                onClick={() => setShowNew((v) => !v)}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-500 hover:text-slate-300 transition-colors"
              >
                {showNew ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {newPassword && newPassword.length < 6 && (
              <p className="mt-1 text-xs text-amber-400">At least 6 characters required</p>
            )}
          </div>

          {/* Confirm Password */}
          <div>
            <label className="block text-sm font-medium text-slate-300">Confirm New Password</label>
            <div className="mt-1 relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Lock className="h-5 w-5 text-slate-500" />
              </div>
              <input
                id="confirm-password"
                type={showConfirm ? 'text' : 'password'}
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="block w-full pl-10 pr-10 py-2.5 border border-slate-600 rounded-xl bg-slate-900/50 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all sm:text-sm"
                placeholder="Re-enter new password"
              />
              <button
                type="button"
                onClick={() => setShowConfirm((v) => !v)}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-500 hover:text-slate-300 transition-colors"
              >
                {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {confirmPassword && newPassword !== confirmPassword && (
              <p className="mt-1 text-xs text-red-400">Passwords do not match</p>
            )}
          </div>

          <button
            id="reset-password-btn"
            type="submit"
            disabled={loading}
            className="w-full flex justify-center items-center gap-2 py-2.5 px-4 rounded-xl shadow-lg text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-600 focus:ring-offset-slate-900 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? <><Spinner /> Resetting Password…</> : 'Reset Password'}
          </button>
        </form>
      </Shell>
    );
  }

  // ────────────────────────────────────────────────────────────────────────────
  // STEP 4 — Success
  // ────────────────────────────────────────────────────────────────────────────
  return (
    <Shell>
      <div className="text-center space-y-5">
        {/* Animated success icon */}
        <div className="flex justify-center">
          <div className="w-20 h-20 bg-emerald-500/10 border-2 border-emerald-500/30 rounded-full flex items-center justify-center animate-pulse">
            <CheckCircle2 className="w-10 h-10 text-emerald-400" />
          </div>
        </div>

        <div>
          <h3 className="text-xl font-bold text-white">Password Reset Successful!</h3>
          <p className="mt-2 text-sm text-slate-300">
            Your password has been updated. You can now sign in with your new credentials.
          </p>
        </div>

        <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3">
          <p className="text-xs text-emerald-300">
            Redirecting you to login in a few seconds…
          </p>
        </div>

        <button
          id="go-to-login-btn"
          onClick={() => navigate('/login')}
          className="w-full flex justify-center items-center gap-2 py-2.5 px-4 rounded-xl shadow-lg text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 transition-all"
        >
          Go to Login
        </button>
      </div>
    </Shell>
  );
}

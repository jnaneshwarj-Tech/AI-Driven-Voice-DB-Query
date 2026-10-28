import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import { Lock, User, AlertCircle, Mail, Eye, EyeOff, CheckCircle2 } from 'lucide-react';
import { useI18n } from '../context/LanguageContext';
import AuthShell from '../components/AuthShell';

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
  const [showPassword, setShowPassword] = useState(false);
  const navigate = useNavigate();
  const { t } = useI18n();

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
        setError(t('auth.invalid'));
      } else if (err.response?.status === 422) {
        setError(t('auth.needBoth'));
      } else if (err.response) {
        setError(getUserMessage(err, t('auth.loginFailed')));
      } else {
        setError(t('common.noServer'));
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
      setError(getUserMessage(err, t('auth.requestFailed')));
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
      setError(getUserMessage(err, t('auth.otpFailed')));
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
      setMessage(t('auth.resetSuccess'));
    } catch (err) {
      setError(getUserMessage(err, t('auth.resetFailed')));
    } finally {
      setLoading(false);
    }
  };

  const countdown = `${String(Math.floor(secondsLeft / 60)).padStart(2, '0')}:${String(secondsLeft % 60).padStart(2, '0')}`;

  const submitLabel = loading
    ? t('common.pleaseWait')
    : forgotStep === 'email'
      ? t('auth.sendOtp')
      : forgotStep === 'otp'
        ? t('auth.verifyOtp')
        : t('auth.resetPassword');

  return (
    <AuthShell
      heading={t('auth.signInHeading')}
      sub={t('auth.signInSub')}
      footnote={t('auth.footnote')}
    >
          {message && (
            <div
              role="status"
              className="mb-5 flex items-start gap-2.5 rounded-md border border-ok/25 bg-ok/10 p-3.5 text-ok"
            >
              <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
              <p className="text-[13.5px] font-medium leading-snug">{message}</p>
            </div>
          )}

          {forgotMode ? (
            <form
              className="space-y-5"
              onSubmit={forgotStep === 'email' ? handleForgotPassword : forgotStep === 'otp' ? handleVerifyOtp : handleResetPassword}
            >
              <div>
                <h2 className="t-section text-ink">{t('auth.resetHeading')}</h2>
                <p className="t-support mt-1 text-ink-mute">{t('auth.resetSub')}</p>
              </div>

              {error && (
                <div role="alert" className="flex items-start gap-2.5 rounded-md border border-err/25 bg-err/10 p-3.5 text-err">
                  <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
                  <p className="text-[13.5px] font-medium leading-snug">{error}</p>
                </div>
              )}

              {forgotStep === 'email' && (
                <>
                  <div>
                    <label className="field-label" htmlFor="fp-username">{t('auth.username')}</label>
                    <div className="relative">
                      <User className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-faint" aria-hidden="true" />
                      <input
                        id="fp-username"
                        type="text"
                        required
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        className="input pl-10"
                        placeholder={t('auth.usernamePlaceholder')}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="field-label" htmlFor="fp-email">{t('auth.registeredEmail')}</label>
                    <div className="relative">
                      <Mail className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-faint" aria-hidden="true" />
                      <input
                        id="fp-email"
                        type="email"
                        required
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="input pl-10"
                        placeholder={t('auth.emailPlaceholder')}
                      />
                    </div>
                    <p className="t-support mt-1.5 text-ink-mute">{t('auth.emailHelp')}</p>
                  </div>
                </>
              )}

              {forgotStep === 'otp' && (
                <div>
                  <label className="field-label" htmlFor="fp-otp">{t('auth.otpLabel')}</label>
                  <input
                    id="fp-otp"
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    maxLength="6"
                    required
                    value={otp}
                    onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                    className="input text-center text-lg tracking-[0.5em]"
                    placeholder="000000"
                  />
                  <p className="t-support mt-1.5 text-ink-mute">{t('auth.otpExpires', { time: countdown })}</p>
                </div>
              )}

              {forgotStep === 'password' && (
                <>
                  <div>
                    <label className="field-label" htmlFor="fp-new">{t('auth.newPassword')}</label>
                    <input
                      id="fp-new"
                      type={showPassword ? 'text' : 'password'}
                      minLength="6"
                      required
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      className="input"
                    />
                  </div>
                  <div>
                    <label className="field-label" htmlFor="fp-confirm">{t('auth.confirmPassword')}</label>
                    <input
                      id="fp-confirm"
                      type={showPassword ? 'text' : 'password'}
                      minLength="6"
                      required
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      className="input"
                    />
                  </div>
                </>
              )}

              <button type="submit" disabled={loading} className="btn btn-accent w-full btn-lg">
                {loading && <Spinner />}
                {submitLabel}
              </button>

              {forgotStep === 'otp' && (
                <button type="button" onClick={handleForgotPassword} disabled={loading} className="btn btn-ghost w-full btn-sm">
                  {t('auth.resendOtp')}
                </button>
              )}
              <button
                type="button"
                onClick={() => { setForgotMode(false); setError(''); setMessage(''); }}
                className="btn btn-ghost w-full btn-sm"
              >
                {t('auth.backToSignIn')}
              </button>
            </form>
          ) : (
            <form className="space-y-5" onSubmit={handleLogin}>
              {error && (
                <div role="alert" className="flex items-start gap-2.5 rounded-md border border-err/25 bg-err/10 p-3.5 text-err">
                  <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
                  <p className="text-[13.5px] font-medium leading-snug">{error}</p>
                </div>
              )}

              <div>
                <label className="field-label" htmlFor="login-username">{t('auth.username')}</label>
                <div className="relative">
                  <User className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-faint" aria-hidden="true" />
                  <input
                    id="login-username"
                    type="text"
                    required
                    autoComplete="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="input pl-10"
                    placeholder={t('auth.usernamePlaceholder')}
                  />
                </div>
              </div>

              <div>
                <div className="flex items-baseline justify-between gap-3">
                  <label className="field-label mb-0" htmlFor="login-password">{t('auth.password')}</label>
                  <button
                    type="button"
                    onClick={() => { setForgotMode(true); setError(''); setMessage(''); }}
                    className="text-[13px] font-medium text-brand-fg hover:text-brand-fg hover:underline dark:text-info"
                  >
                    {t('auth.forgot')}
                  </button>
                </div>
                <div className="relative mt-1.5">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-faint" aria-hidden="true" />
                  <input
                    id="login-password"
                    type={showPassword ? 'text' : 'password'}
                    required
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="input pl-10 pr-11"
                    placeholder="••••••••"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-ink-faint hover:text-ink-soft"
                    title={showPassword ? t('auth.hidePassword') : t('auth.showPassword')}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                    <span className="sr-only">{showPassword ? t('auth.hidePassword') : t('auth.showPassword')}</span>
                  </button>
                </div>
              </div>

              <button type="submit" disabled={loading} className="btn btn-primary w-full btn-lg">
                {loading ? <Spinner /> : null}
                {loading ? t('common.pleaseWait') : t('auth.signIn')}
              </button>

              {/* §8: registration sits below the sign-in action. */}
              <div className="border-t border-line pt-4 text-center">
                <span className="t-support text-ink-mute">{t('auth.noAccount')}&nbsp;</span>
                <Link to="/register" className="text-[14px] font-semibold text-brand-fg hover:underline dark:text-info">
                  {t('auth.registerLink')}
                </Link>
              </div>
            </form>
          )}
    </AuthShell>
  );
}

function Spinner() {
  return (
    <svg className="-ml-1 h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
    </svg>
  );
}

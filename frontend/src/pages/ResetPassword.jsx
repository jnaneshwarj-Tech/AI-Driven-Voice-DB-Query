import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Lock, AlertCircle } from 'lucide-react';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import { useI18n } from '../context/LanguageContext';
import AuthShell from '../components/AuthShell';

export default function ResetPassword() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { t } = useI18n();

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
      setError(getUserMessage(err, t('auth.resetFailed')));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell heading={t('reset.heading')} sub={t('reset.sub')} footnote={t('auth.footnote')}>
      {error && (
        <div role="alert" className="mb-5 flex items-start gap-2.5 rounded-md border border-err/25 bg-err/10 p-3.5 text-err">
          <AlertCircle className="mt-0.5 h-[18px] w-[18px] flex-shrink-0" aria-hidden="true" />
          <p className="text-[13.5px] font-medium leading-snug">{error}</p>
        </div>
      )}

      <form className="space-y-5" onSubmit={handleSubmit}>
        <div>
          <label className="field-label" htmlFor="reset-new">{t('auth.newPassword')}</label>
          <div className="relative">
            <Lock className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-faint" aria-hidden="true" />
            <input
              id="reset-new"
              type="password"
              required
              minLength="6"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input pl-10"
            />
          </div>
        </div>
        <div>
          <label className="field-label" htmlFor="reset-confirm">{t('auth.confirmPassword')}</label>
          <div className="relative">
            <Lock className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-faint" aria-hidden="true" />
            <input
              id="reset-confirm"
              type="password"
              required
              minLength="6"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="input pl-10"
            />
          </div>
          <p className="t-support mt-1.5 text-ink-mute">{t('reset.help')}</p>
        </div>

        <button type="submit" disabled={loading} className="btn btn-primary w-full btn-lg">
          {loading ? t('common.pleaseWait') : t('reset.submit')}
        </button>
      </form>

      <Link to="/login" className="mt-4 block text-center text-[14px] font-medium text-brand-fg hover:underline dark:text-info">
        {t('auth.backToSignIn')}
      </Link>
    </AuthShell>
  );
}

import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import { AlertCircle, User, Mail, Lock, ShieldCheck } from 'lucide-react';
import { useI18n } from '../context/LanguageContext';
import { useToast } from '../components/Toast';
import AuthShell from '../components/AuthShell';

export default function Register() {
  const [regUsername, setRegUsername] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regRole, setRegRole] = useState('Staff');
  const [regError, setRegError] = useState('');
  const [regLoading, setRegLoading] = useState(false);
  const navigate = useNavigate();
  const { t } = useI18n();
  const { showToast } = useToast();

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
      showToast({ type: 'success', title: t('register.successTitle'), message: t('register.success') });
      navigate('/login');
    } catch (err) {
      setRegError(err.response ? getUserMessage(err, t('register.failed')) : t('register.noServer'));
    } finally {
      setRegLoading(false);
    }
  };

  return (
    <AuthShell heading={t('register.heading')} sub={t('register.sub')} footnote={t('auth.footnote')}>
      {regError && (
        <div role="alert" className="mb-5 flex items-start gap-2.5 rounded-md border border-err/25 bg-err/10 p-3.5 text-err">
          <AlertCircle className="mt-0.5 h-[18px] w-[18px] flex-shrink-0" aria-hidden="true" />
          <p className="text-[13.5px] font-medium leading-snug">{regError}</p>
        </div>
      )}

      <form className="space-y-4" onSubmit={handleRegister}>
        <div>
          <label className="field-label" htmlFor="reg-username">{t('auth.username')}</label>
          <div className="relative">
            <User className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-faint" aria-hidden="true" />
            <input
              id="reg-username"
              type="text"
              required
              autoComplete="username"
              value={regUsername}
              onChange={(e) => setRegUsername(e.target.value)}
              className="input pl-10"
              placeholder={t('register.usernamePlaceholder')}
            />
          </div>
        </div>

        <div>
          <label className="field-label" htmlFor="reg-email">{t('register.email')}</label>
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-faint" aria-hidden="true" />
            <input
              id="reg-email"
              type="email"
              required
              autoComplete="email"
              value={regEmail}
              onChange={(e) => setRegEmail(e.target.value)}
              className="input pl-10"
              placeholder={t('register.emailPlaceholder')}
            />
          </div>
        </div>

        <div>
          <label className="field-label" htmlFor="reg-password">{t('auth.password')}</label>
          <div className="relative">
            <Lock className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-faint" aria-hidden="true" />
            <input
              id="reg-password"
              type="password"
              required
              minLength="6"
              autoComplete="new-password"
              value={regPassword}
              onChange={(e) => setRegPassword(e.target.value)}
              className="input pl-10"
              placeholder={t('register.passwordPlaceholder')}
            />
          </div>
        </div>

        <div>
          <label className="field-label" htmlFor="reg-role">{t('register.role')}</label>
          <div className="relative">
            <ShieldCheck className="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-ink-faint" aria-hidden="true" />
            <select
              id="reg-role"
              value={regRole}
              onChange={(e) => setRegRole(e.target.value)}
              className="input pl-10"
            >
              <option value="Staff">{t('register.roleStaff')}</option>
              <option value="Admin">{t('register.roleAdmin')}</option>
            </select>
          </div>
          <p className="t-support mt-1.5 text-ink-mute">{t('register.roleHelp')}</p>
        </div>

        <button type="submit" disabled={regLoading} className="btn btn-primary w-full btn-lg mt-2">
          {regLoading ? t('register.submitting') : t('register.submit')}
        </button>

        <div className="border-t border-line pt-4 text-center">
          <span className="t-support text-ink-mute">{t('register.haveAccount')}&nbsp;</span>
          <Link to="/login" className="text-[14px] font-semibold text-brand-fg hover:underline dark:text-info">
            {t('auth.signIn')}
          </Link>
        </div>
      </form>
    </AuthShell>
  );
}

/**
 * LanguageModeToggle — switches the language of the interface itself.
 *
 * Not to be confused with components/LanguageSelector.jsx, which chooses the
 * language of the *question sent to the query engine* and keeps its own
 * existing props contract. The two are independent on purpose: an English
 * interface can still ask the AI in Kannada.
 */
import { Languages } from 'lucide-react';
import { useI18n } from '../context/LanguageContext';

const MODES = [
  { id: 'en', text: 'EN' },
  { id: 'kn', text: 'ಕನ್ನಡ' },
];

export default function LanguageModeToggle({ variant = 'default', compact = false, className = '' }) {
  const { lang, setLang, t } = useI18n();

  // Collapsed sidebar: one button that swaps the interface language, so
  // shrinking the navigation never removes a control.
  if (compact) {
    const next = lang === 'en' ? 'kn' : 'en';
    return (
      <button
        type="button"
        onClick={() => setLang(next)}
        lang={next}
        title={next === 'kn' ? 'ಕನ್ನಡ' : 'English'}
        aria-label={t('lang.ariaGroup')}
        className="rounded-md p-1.5 leading-none text-nav-fg-mute hover:text-accent hover:bg-white/10 transition-colors"
      >
        <Languages className="h-4 w-4" aria-hidden="true" />
      </button>
    );
  }

  return (
    <div
      role="group"
      aria-label={t('lang.ariaGroup')}
      className={[
        'inline-flex items-center gap-0.5 rounded-md p-0.5 border',
        variant === 'onNav' ? 'bg-white/5 border-white/10' : 'bg-sunken border-line',
        className,
      ].filter(Boolean).join(' ')}
    >
      <Languages
        className={`h-3.5 w-3.5 ml-1 mr-0.5 ${variant === 'onNav' ? 'text-nav-fg-mute' : 'text-ink-mute'}`}
        aria-hidden="true"
      />
      {MODES.map(({ id, text }) => {
        const selected = lang === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => setLang(id)}
            aria-pressed={selected}
            lang={id}
            className={[
              'rounded-[6px] px-2 py-1 text-[13px] font-semibold leading-none transition-colors',
              id === 'kn' ? 'font-kannada' : '',
              selected
                ? (variant === 'onNav'
                    ? 'bg-white/15 text-accent'
                    : 'bg-surface text-accent-ink shadow-sm')
                : (variant === 'onNav'
                    ? 'text-nav-fg-mute hover:text-nav-fg hover:bg-white/10'
                    : 'text-ink-mute hover:text-ink hover:bg-line/60'),
            ].filter(Boolean).join(' ')}
          >
            {text}
          </button>
        );
      })}
    </div>
  );
}

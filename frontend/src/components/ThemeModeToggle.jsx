/**
 * ThemeModeToggle — the three modes ThemeContext already supports.
 *
 * The app previously exposed only a cycling button, so 'system' was reachable
 * but never labelled. This renders all three explicitly. It calls the existing
 * `setTheme`, which still persists to localStorage and POSTs /auth/theme — no
 * new backend behaviour.
 */
import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { useI18n } from '../context/LanguageContext';

const MODES = [
  { id: 'light', Icon: Sun },
  { id: 'dark', Icon: Moon },
  { id: 'system', Icon: Monitor },
];

export default function ThemeModeToggle({ variant = 'default', compact = false, className = '' }) {
  const { theme, setTheme } = useTheme();
  const { t } = useI18n();
  const active = MODES.find((m) => m.id === theme) ? theme : 'system';

  const label = {
    light: t('theme.light'),
    dark: t('theme.dark'),
    system: t('theme.system'),
  };

  // Collapsed sidebar: one button that steps through the same three modes, so
  // shrinking the navigation never removes a control.
  if (compact) {
    const order = ['light', 'dark', 'system'];
    const next = order[(order.indexOf(active) + 1) % order.length];
    const Icon = MODES.find((m) => m.id === active).Icon;
    return (
      <button
        type="button"
        onClick={() => setTheme(next)}
        title={`${label[active]} → ${label[next]}`}
        aria-label={t('theme.ariaGroup')}
        className="rounded-md p-1.5 leading-none text-nav-fg-mute hover:text-accent hover:bg-white/10 transition-colors"
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </button>
    );
  }

  return (
    <div
      role="group"
      aria-label={t('theme.ariaGroup')}
      className={[
        'inline-flex items-center gap-0.5 rounded-md p-0.5 border',
        variant === 'onNav'
          ? 'bg-white/5 border-white/10'
          : 'bg-sunken border-line',
        className,
      ].filter(Boolean).join(' ')}
    >
      {MODES.map(({ id, Icon }) => {
        const selected = active === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => setTheme(id)}
            aria-pressed={selected}
            title={label[id]}
            className={[
              'rounded-[6px] p-1.5 leading-none transition-colors',
              selected
                ? (variant === 'onNav'
                    ? 'bg-white/15 text-accent'
                    : 'bg-surface text-accent-ink shadow-sm')
                : (variant === 'onNav'
                    ? 'text-nav-fg-mute hover:text-nav-fg hover:bg-white/10'
                    : 'text-ink-mute hover:text-ink hover:bg-line/60'),
            ].join(' ')}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            <span className="sr-only">{label[id]}</span>
          </button>
        );
      })}
    </div>
  );
}

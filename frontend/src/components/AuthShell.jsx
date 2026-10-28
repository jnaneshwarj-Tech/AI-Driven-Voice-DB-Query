/**
 * AuthShell — the full-page auth wrapper shared by Login, Register, ResetPassword.
 *
 * One centred stage: the VTU emblem is the page ground (`.auth-bg` in index.css,
 * which paints the emblem, the brand lighting and the veil under the card), and
 * the identity block + glass form column sit in the middle of it. Nothing is a
 * framed picture and nothing is pushed to one side — the page reads as the
 * university's, and the eye lands on the card.
 *
 * Both artwork files are probed before use, so a missing file degrades to the
 * gradient ground and the monogram plate instead of a broken <img>.
 *
 * Zero state, zero API calls. The controls rendered here share ThemeContext and
 * LanguageContext with the dashboard, so preferences made here survive into the app.
 */
import { useEffect, useState } from 'react';
import { useI18n } from '../context/LanguageContext';
import LanguageModeToggle from './LanguageModeToggle';
import ThemeModeToggle from './ThemeModeToggle';

/** Probe once whether an image is present, to avoid a broken <img>. */
function useImageExists(src) {
  const [exists, setExists] = useState(false);
  useEffect(() => {
    if (!src) return;
    const img = new Image();
    img.onload  = () => setExists(true);
    img.onerror = () => setExists(false);
    img.src = src;
  }, [src]);
  return exists;
}

export default function AuthShell({ heading, sub, children, footnote }) {
  const { t } = useI18n();
  const hasEmblem = useImageExists('/vtu-emblem.png');

  return (
    <div className="relative min-h-screen bg-canvas">
      <div className="auth-bg" aria-hidden="true">
        <span className="auth-bg__ring" />
      </div>

      {/* Pinned to the viewport rather than the column: the theme and language
          you choose here are the ones the dashboard opens with. */}
      <div className="fixed right-4 top-4 z-20 flex items-center gap-2 sm:right-6 sm:top-5">
        <LanguageModeToggle variant="onNav" />
        <ThemeModeToggle variant="onNav" />
      </div>

      <div className="relative z-10 flex min-h-screen items-center justify-center px-4 py-12 sm:px-6">
        <div className="anim-page w-full max-w-[26rem]">
          {/* ── Identity block: emblem, college, then the action ─────────── */}
          <header className="mb-6 flex flex-col items-center text-center">
            {hasEmblem ? (
              <div className="flex h-[4.75rem] w-[8.5rem] items-center justify-center rounded-2xl bg-white p-2 shadow-lg ring-1 ring-line">
                <img
                  src="/vtu-emblem.png"
                  alt={t('brand.vtu')}
                  className="h-full w-full object-contain"
                />
              </div>
            ) : (
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl shadow-lg ring-1 ring-line"
                style={{ background: 'linear-gradient(135deg, rgb(var(--brand-mid-rgb)), rgb(var(--brand-rgb)))' }}>
                <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8 text-white" aria-hidden="true">
                  <path d="M4 7h16M4 12h16M4 17h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  <circle cx="19" cy="17" r="3" stroke="currentColor" strokeWidth="2"/>
                </svg>
              </div>
            )}

            <div className="mt-3.5 inline-flex items-center gap-2 rounded-full border border-line bg-surface/70 px-3 py-1 backdrop-blur-sm">
              <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-accent" />
              <span className="text-[11.5px] font-medium leading-none text-ink-soft">
                {t('brand.tagline')}
              </span>
            </div>

            <p className="mt-2 text-[13px] font-semibold leading-snug text-brand-fg dark:text-info">
              {t('brand.college')}
            </p>

            <h1 className="t-page mt-1.5 font-bold leading-tight tracking-tight text-ink">
              {heading}
            </h1>
            {sub && (
              <p className="mt-1.5 text-[14px] leading-snug text-ink-mute">{sub}</p>
            )}

            <p className="mt-2.5 text-[11.5px] leading-snug text-ink-mute">
              {t('brand.vtu')} · {t('brand.vtuAffiliated')}
            </p>
          </header>

          {/* ── Glass form card ─────────────────────────────────────────── */}
          <div className="glass p-6 sm:p-8">
            {children}
          </div>

          {footnote && (
            <p className="mt-5 text-center text-[11.5px] leading-relaxed text-ink-mute px-2">
              {footnote}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

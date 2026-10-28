/**
 * LanguageContext — UI chrome language (English / ಕನ್ನಡ).
 *
 * Deliberately separate from Dashboard's `queryLanguage`: that one selects the
 * language of the *question the user asks the AI* and is persisted as
 * 'queryLanguage'. This selects the language of every label the frontend owns
 * and is persisted as 'uiLanguage'. Changing one must never change the other.
 *
 * It never sends anything to the backend and never rewrites data values —
 * student names, USNs, branches and API field names are rendered as-is.
 */
import { createContext, useContext, useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { dictionaries } from '../i18n';

const DICTIONARIES = dictionaries;
export const UI_LANGUAGE_KEY = 'uiLanguage';

const LanguageContext = createContext({
  lang: 'en',
  setLang: () => {},
  toggleLang: () => {},
  t: (key) => key,
  isKn: false,
});

function readStoredLang() {
  try {
    const stored = localStorage.getItem(UI_LANGUAGE_KEY);
    if (stored === 'en' || stored === 'kn') return stored;
  } catch {
    /* storage disabled (private mode) — fall through to English */
  }
  return 'en';
}

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(readStoredLang);
  const firstLangRender = useRef(true);

  // <html lang> drives the Kannada font stack and line height in index.css.
  useEffect(() => {
    document.documentElement.lang = lang === 'kn' ? 'kn' : 'en';
    try {
      localStorage.setItem(UI_LANGUAGE_KEY, lang);
    } catch {
      /* non-fatal: the choice just won't survive a reload */
    }
    // Kannada and English have different metrics, so a switch reflows text.
    // A short opacity dip on the root masks that jump; it is cosmetic only and
    // is skipped on the first render (the page already fades in).
    if (firstLangRender.current) { firstLangRender.current = false; return; }
    const root = document.documentElement;
    root.classList.add('lang-shift');
    const id = setTimeout(() => root.classList.remove('lang-shift'), 260);
    return () => clearTimeout(id);
  }, [lang]);

  const setLang = useCallback((next) => {
    setLangState(next === 'kn' ? 'kn' : 'en');
  }, []);

  const toggleLang = useCallback(() => {
    setLangState((cur) => (cur === 'kn' ? 'en' : 'kn'));
  }, []);

  const t = useCallback((key, vars) => {
    const table = DICTIONARIES[lang] || DICTIONARIES.en;
    let out = table[key];
    // A missing Kannada string falls back to English, never to a raw key on screen.
    if (out === undefined) out = DICTIONARIES.en[key];
    if (out === undefined) return key;
    if (vars) {
      for (const [name, value] of Object.entries(vars)) {
        out = out.replace(new RegExp(`{${name}}`, 'g'), String(value));
      }
    }
    return out;
  }, [lang]);

  const value = useMemo(
    () => ({ lang, setLang, toggleLang, t, isKn: lang === 'kn' }),
    [lang, setLang, toggleLang, t]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useI18n() {
  return useContext(LanguageContext);
}

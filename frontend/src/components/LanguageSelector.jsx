import React from 'react';
import { Languages, ChevronDown } from 'lucide-react';
import { useI18n } from '../context/LanguageContext';

/**
 * LanguageSelector — chooses the language of the *question sent to the query
 * engine*. It has nothing to do with the interface language toggle
 * (components/ThemeModeToggle.jsx's sibling, LanguageModeToggle.jsx).
 *
 * Option labels stay endonyms ('English', 'ಕನ್ನಡ') on purpose: a language
 * picker names each language in that language, whatever the UI is set to.
 *
 * Props:
 *   - selectedLanguage: current language ('english' | 'kannada' | 'mixed')
 *   - onLanguageChange: callback when language changes
 *   - className: optional additional CSS classes
 */
export default function LanguageSelector({ selectedLanguage, onLanguageChange, className = '' }) {
  const { t } = useI18n();

  const languages = [
    { id: 'english', label: 'English', icon: '🇬🇧' },
    { id: 'kannada', label: 'ಕನ್ನಡ', icon: '🇮🇳' },
    { id: 'mixed', label: 'English + ಕನ್ನಡ', icon: '🌐' },
  ];

  return (
    <div className={`relative inline-block ${className}`}>
      <label className="sr-only" htmlFor="query-language-select">{t('query.selectLang')}</label>
      <select
        id="query-language-select"
        value={selectedLanguage}
        onChange={(e) => onLanguageChange(e.target.value)}
        className="input appearance-none w-auto max-w-full pl-9 pr-9 text-sm font-medium cursor-pointer"
        title={t('query.selectLang')}
      >
        {languages.map(lang => (
          <option key={lang.id} value={lang.id} lang={lang.id === 'english' ? 'en' : undefined}>
            {lang.icon} {lang.label}
          </option>
        ))}
      </select>

      <Languages className="w-4 h-4 text-ink-mute absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
      <ChevronDown className="w-4 h-4 text-ink-mute absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
    </div>
  );
}

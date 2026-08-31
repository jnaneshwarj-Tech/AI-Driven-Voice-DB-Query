import React from 'react';
import { Globe, Languages } from 'lucide-react';

/**
 * LanguageSelector Component
 * 
 * Provides a clean dropdown for selecting query language:
 * - English
 * - ಕನ್ನಡ (Kannada)
 * - English + ಕನ್ನಡ (Mixed)
 * 
 * Props:
 *   - selectedLanguage: current language ('english' | 'kannada' | 'mixed')
 *   - onLanguageChange: callback when language changes
 *   - className: optional additional CSS classes
 */
export default function LanguageSelector({ selectedLanguage, onLanguageChange, className = '' }) {
  const languages = [
    { id: 'english', label: 'English', icon: '🇬🇧' },
    { id: 'kannada', label: 'ಕನ್ನಡ', icon: '🇮🇳' },
    { id: 'mixed', label: 'English + ಕನ್ನಡ', icon: '🌐' },
  ];

  const currentLang = languages.find(l => l.id === selectedLanguage) || languages[0];

  return (
    <div className={`relative inline-block ${className}`}>
      <select
        value={selectedLanguage}
        onChange={(e) => onLanguageChange(e.target.value)}
        className="appearance-none pl-9 pr-8 py-2 text-sm font-medium bg-white border border-slate-200 rounded-lg hover:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent transition-all cursor-pointer text-slate-700"
        title="Select query language"
      >
        {languages.map(lang => (
          <option key={lang.id} value={lang.id}>
            {lang.icon} {lang.label}
          </option>
        ))}
      </select>
      
      {/* Icon */}
      <div className="absolute left-3 top-1/2 transform -translate-y-1/2 pointer-events-none">
        <Languages className="w-4 h-4 text-slate-400" />
      </div>

      {/* Dropdown arrow */}
      <div className="absolute right-2 top-1/2 transform -translate-y-1/2 pointer-events-none">
        <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>
  );
}

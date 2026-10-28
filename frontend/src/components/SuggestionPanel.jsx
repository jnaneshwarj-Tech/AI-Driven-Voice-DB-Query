/**
 * SuggestionPanel.jsx — Advanced AI Search Suggestion UI
 *
 * Handles 4 response types from the backend:
 *   1. "no_match"       → clean "No records" message
 *   2. "suggestion"     → "Did you mean X?" YES/NO  (confidence 75–90%)
 *   3. "possible_matches" → ranked list with SELECT buttons (confidence 50–74%)
 *   4. "multiple_match" → ambiguity table — user MUST pick by USN
 *
 * Auto-corrected (≥90%) is handled silently upstream in Dashboard.
 *
 * Data contract: `message`, `search_term` and every suggestion `name` / `usn`
 * come from the parser and are rendered verbatim; the object handed to `onYes`
 * is the untouched suggestion row. Only the surrounding chrome is translated.
 */
import { useState } from 'react';
import {
  Search, CheckCircle, XCircle, AlertCircle,
  Users, ChevronRight, AlertTriangle
} from 'lucide-react';
import { useI18n } from '../context/LanguageContext';

// ── Score badge ───────────────────────────────────────────────────────────────
// Thresholds (90 / 75 / 60) are the parser's confidence bands — unchanged.
// Only the colours they resolve to moved onto tokens.
function ConfBadge({ score }) {
  const { t } = useI18n();
  const pct = Math.round((score ?? 0) * 100);
  const tone =
    pct >= 90 ? 'badge-ok' :
    pct >= 75 ? 'badge-info' :
    pct >= 60 ? 'badge-warn' : 'badge-quiet';
  return (
    <span className={`badge tabular-nums ${tone}`}>
      {t('suggest.match', { pct })}
    </span>
  );
}

// ── No match ─────────────────────────────────────────────────────────────────
function NoMatch() {
  const { t } = useI18n();
  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-md border border-line bg-sunken p-3.5"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-ink-mute" aria-hidden="true" />
      <p className="t-support font-medium text-ink-mute">{t('suggest.noRecords')}</p>
    </div>
  );
}

// ── Avatar initial ────────────────────────────────────────────────────────────
function Avatar({ name }) {
  const initials = (name || '?')
    .split(' ').slice(0, 2).map(w => w[0]?.toUpperCase() || '').join('');
  return (
    <div
      aria-hidden="true"
      className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-mid to-brand text-xs font-bold text-white shadow-sm"
    >
      {initials}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function SuggestionPanel({ suggestion, onYes, onNo }) {
  const { t } = useI18n();
  const [answered, setAnswered] = useState(null); // null | 'yes' | 'no'

  if (!suggestion) return null;

  const { type, message, suggestions = [], auto_corrected, search_term, confidence } = suggestion;
  const top = suggestions[0];

  // ── 1. No match ───────────────────────────────────────────────────────────
  if (type === 'no_match' || !suggestions.length) {
    return <NoMatch />;
  }

  // ── After NO clicked ──────────────────────────────────────────────────────
  if (answered === 'no') {
    return <NoMatch />;
  }

  // ── After YES clicked (Did you mean?) ────────────────────────────────────
  if (answered === 'yes') {
    return (
      <div
        role="status"
        className="flex flex-wrap items-center gap-2.5 rounded-md border border-ok/40 bg-ok-soft p-3.5"
      >
        <CheckCircle className="h-4 w-4 flex-shrink-0 text-ok" aria-hidden="true" />
        <p className="t-support font-medium text-ink">
          {t('suggest.loadingBefore')} <strong className="font-bold">{top?.name}</strong> {t('suggest.loadingAfter')}
        </p>
      </div>
    );
  }

  // ── Auto-corrected notice (handled upstream, but defensive fallback) ───────
  // `message` is parser-authored — rendered exactly as received.
  if (auto_corrected) {
    return (
      <div className="flex flex-wrap items-center gap-2.5 rounded-md border border-info/40 bg-info-soft p-3">
        <Search className="h-3.5 w-3.5 flex-shrink-0 text-info" aria-hidden="true" />
        <p className="t-support font-medium text-info">{message}</p>
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ── 2. "Did you mean?" — single top match (score 75–90%) ─────────────────
  // ─────────────────────────────────────────────────────────────────────────
  if (type === 'suggestion') {
    const lines = message.split('\n');
    return (
      <section
        aria-label={t('suggest.regionLabel')}
        className="popover anim-scale-in overflow-hidden border-2 border-accent/50"
      >
        {/* Header */}
        <header className="flex items-start gap-2 bg-accent-soft px-4 py-2.5">
          <Search className="mt-0.5 h-4 w-4 flex-shrink-0 text-accent-ink" aria-hidden="true" />
          <div className="min-w-0">
            {lines.map((ln, i) => (
              <p
                key={i}
                className={`t-support break-words ${i === 0 ? 'font-semibold text-ink' : 'font-bold text-accent-ink'}`}
              >
                {ln}
              </p>
            ))}
          </div>
        </header>

        {/* Top match card */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <Avatar name={top.name} />
            <div className="min-w-0">
              <p className="t-body break-words font-semibold text-ink">{top.name}</p>
              <p className="break-all font-mono text-xs text-ink-mute">{top.usn}</p>
              <div className="mt-1">
                <ConfBadge score={top.score} />
              </div>
            </div>
          </div>

          {/* YES / NO buttons — gold marks this panel's single next action */}
          <div className="flex flex-shrink-0 flex-wrap gap-2">
            <button
              id="suggestion-yes-btn"
              type="button"
              onClick={() => { setAnswered('yes'); onYes && onYes(top); }}
              className="btn btn-sm btn-accent"
            >
              <CheckCircle className="h-4 w-4" aria-hidden="true" /> {t('common.yes')}
            </button>
            <button
              id="suggestion-no-btn"
              type="button"
              onClick={() => { setAnswered('no'); onNo && onNo(); }}
              className="btn btn-sm btn-ghost"
            >
              <XCircle className="h-4 w-4" aria-hidden="true" /> {t('common.no')}
            </button>
          </div>
        </div>

        {/* Other candidates */}
        {suggestions.length > 1 && (
          <div className="px-4 pb-3">
            <p className="mb-1.5 flex flex-wrap items-center gap-1 text-xs font-semibold uppercase tracking-wide text-ink-mute">
              {t('suggest.otherMatches')}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {suggestions.slice(1).map((s, i) => (
                <button
                  key={i}
                  type="button"
                  title={s.name}
                  onClick={() => { setAnswered('yes'); onYes && onYes(s); }}
                  className="btn btn-sm btn-ghost max-w-full gap-1.5"
                >
                  <span className="t-truncate max-w-[14rem]">{s.name}</span>
                  <ConfBadge score={s.score} />
                </button>
              ))}
            </div>
          </div>
        )}
      </section>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ── 3. "Possible matches" list (score 50–74%) — SELECT / CANCEL ───────────
  // ─────────────────────────────────────────────────────────────────────────
  if (type === 'possible_matches') {
    return (
      <section
        aria-label={t('suggest.regionLabel')}
        className="popover anim-scale-in overflow-hidden"
      >
        <header className="flex items-start gap-2 border-b border-line bg-info-soft px-4 py-2.5">
          <Search className="mt-0.5 h-4 w-4 flex-shrink-0 text-info" aria-hidden="true" />
          <div className="min-w-0">
            <p className="t-support break-words font-bold text-info">
              {t('suggest.noExactFor', { q: search_term })}
            </p>
            <p className="t-support break-words text-ink-soft">
              {t('suggest.possibleSelect')}
            </p>
          </div>
        </header>

        <div className="space-y-1.5 p-3">
          {suggestions.map((s, i) => (
            <div
              key={i}
              className="flex flex-wrap items-center justify-between gap-2.5 rounded-md border border-line bg-surface p-2.5 transition-colors hover:border-brand/40 hover:bg-brand/[0.03]"
            >
              <div className="flex min-w-0 items-center gap-2.5">
                <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-brand text-xs font-bold text-white tabular-nums">
                  {i + 1}
                </span>
                <div className="min-w-0">
                  <p className="t-body break-words font-semibold text-ink" title={s.name}>
                    {s.name}
                  </p>
                  <p className="break-all font-mono text-xs text-ink-mute">{s.usn}</p>
                </div>
              </div>
              <div className="flex flex-shrink-0 items-center gap-2">
                <ConfBadge score={s.score} />
                <button
                  type="button"
                  onClick={() => { onYes && onYes(s); }}
                  className="btn btn-sm btn-primary"
                >
                  <ChevronRight className="h-4 w-4" aria-hidden="true" /> {t('suggest.select')}
                </button>
              </div>
            </div>
          ))}

          <button
            type="button"
            onClick={() => { onNo && onNo(); }}
            className="btn btn-sm btn-ghost mt-1 w-full"
          >
            <XCircle className="h-4 w-4" aria-hidden="true" />
            {t('suggest.cancelNone')}
          </button>
        </div>
      </section>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ── 4. Multiple students with SAME name — must pick by USN ───────────────
  // ─────────────────────────────────────────────────────────────────────────
  if (type === 'multiple_match') {
    return (
      <section
        aria-label={t('suggest.regionLabel')}
        className="popover anim-scale-in overflow-hidden"
      >
        <header className="flex items-start gap-2 bg-err-soft px-4 py-2.5">
          <Users className="mt-0.5 h-4 w-4 flex-shrink-0 text-err" aria-hidden="true" />
          <div className="min-w-0">
            <p className="t-support break-words font-bold text-err">
              {t('suggest.multipleTitle')}
            </p>
            <p className="t-support break-words text-ink-soft">
              {t('suggest.multipleHint')}
            </p>
          </div>
        </header>

        <div className="table-scroll border-y border-line">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th scope="col" className="th">{t('suggest.colSelect')}</th>
                <th scope="col" className="th">{t('suggest.colUsn')}</th>
                <th scope="col" className="th">{t('suggest.colName')}</th>
                <th scope="col" className="th text-center">{t('suggest.colMatch')}</th>
              </tr>
            </thead>
            <tbody>
              {suggestions.map((s, i) => (
                <tr key={i} className="tr-hover">
                  <td className="td">
                    <button
                      type="button"
                      onClick={() => { onYes && onYes(s); }}
                      className="btn btn-sm btn-primary"
                    >
                      <ChevronRight className="h-4 w-4" aria-hidden="true" /> {t('suggest.view')}
                    </button>
                  </td>
                  <td className="td break-all font-mono font-semibold text-ink">{s.usn}</td>
                  <td className="td break-words font-semibold text-ink" title={s.name}>{s.name}</td>
                  <td className="td text-center">
                    <ConfBadge score={s.score} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="p-3">
          <button
            type="button"
            onClick={() => { onNo && onNo(); }}
            className="btn btn-sm btn-ghost w-full"
          >
            <XCircle className="h-4 w-4" aria-hidden="true" />
            {t('common.cancel')}
          </button>
        </div>
      </section>
    );
  }

  return <NoMatch />;
}

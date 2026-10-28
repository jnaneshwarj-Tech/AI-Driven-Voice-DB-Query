/**
 * GpaTable — renders SQL results AS-IS (preserves server sort order).
 * Only sorts within same student for trend arrows.
 * Never re-sorts the full result — SQL ORDER BY is the source of truth.
 */
import { useI18n } from '../context/LanguageContext';

export default function GpaTable({ data }) {
  const { t } = useI18n();
  if (!data?.length) return null;

  const hasSgpa    = data.some(r => r.sgpa != null);
  const hasCgpaCol = data.some(r => r.cgpa != null);
  const hasName    = data.some(r => r.name);
  const hasUsn     = data.some(r => r.usn);
  const hasSem     = data.some(r => r.semester != null);
  const hasSubject = data.some(r => r.subject != null && String(r.subject).trim() !== '');

  // Client-side cumulative CGPA fallback (only if SQL didn't return cgpa column)
  const cumulativeCgpa = {};
  if (hasSgpa && !hasCgpaCol) {
    // Build per-student sorted list to compute running average
    const groups = {};
    for (const r of data) {
      const key = r.usn || r.name || '';
      if (!key) continue;
      if (!groups[key]) groups[key] = [];
      groups[key].push({ sem: r.semester ?? 0, sgpa: parseFloat(r.sgpa) || 0 });
    }
    for (const [key, rows] of Object.entries(groups)) {
      rows.sort((a, b) => a.sem - b.sem);
      let sum = 0;
      cumulativeCgpa[key] = {};
      rows.forEach((r, i) => {
        sum += r.sgpa;
        cumulativeCgpa[key][r.sem] = (sum / (i + 1)).toFixed(2);
      });
    }
  }

  // ── DO NOT re-sort data — preserve SQL ORDER BY ──────────────────────────
  // Only build a per-student previous-row map for trend arrows
  const prevSgpaMap = {};  // key → last seen sgpa for that student
  const rows = data;       // use data directly, no sort

  const bestSgpa = hasSgpa
    ? Math.max(...rows.map(r => parseFloat(r.sgpa) || 0))
    : 0;

  return (
    <div className="table-wrap anim-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <span className="t-card text-ink">{t('gpa.title')}</span>
        {hasSgpa && (
          <span className="badge badge-brand tabular-nums">
            {t('gpa.bestSgpa', { v: bestSgpa.toFixed(2) })}
          </span>
        )}
      </div>
      <p className="sr-only">{t('gpa.caption')}</p>
      <div className="table-scroll">
        <table className="w-full t-table">
          <thead>
            <tr>
              <th className="th w-8">{t('gpa.row')}</th>
              {hasUsn  && <th className="th">{t('gpa.usn')}</th>}
              {hasName && <th className="th">{t('gpa.name')}</th>}
              {hasSubject && <th className="th">{t('gpa.backlogSubject')}</th>}
              {hasSem  && <th className="th">{t('gpa.sem')}</th>}
              {hasSgpa && <th className="th">{t('gpa.sgpa')}</th>}
              <th className="th">
                {t('gpa.cgpa')} <span className="t-support font-normal normal-case text-ink-mute">{t('gpa.cumulative')}</span>
              </th>
              {hasSgpa && <th className="th">{t('gpa.trend')}</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const studentKey = row.usn || row.name || '';
              const sem = row.semester ?? 0;

              // CGPA: prefer SQL-computed column, else client-side cumulative
              const cgpaVal = hasCgpaCol
                ? (row.cgpa != null ? parseFloat(row.cgpa).toFixed(2) : '—')
                : (cumulativeCgpa[studentKey]?.[sem] ?? '—');

              // Trend: compare to previous row of SAME student
              const prevSgpa = prevSgpaMap[studentKey] ?? null;
              const curSgpa  = parseFloat(row.sgpa) || 0;
              const trend = (prevSgpa === null || !hasSgpa) ? null
                : curSgpa > prevSgpa ? '↑'
                : curSgpa < prevSgpa ? '↓' : '→';
              const trendColor = trend === '↑' ? 'text-ok'
                : trend === '↓' ? 'text-err' : 'text-ink-faint';
              const trendLabel = trend === '↑' ? t('gpa.trendUp')
                : trend === '↓' ? t('gpa.trendDown') : t('gpa.trendFlat');

              // Update prev map
              if (hasSgpa) prevSgpaMap[studentKey] = curSgpa;

              return (
                <tr key={i} className="tr-hover">
                  <td className="td px-3 text-center text-xs tabular-nums text-ink-faint">{i + 1}</td>
                  {hasUsn  && <td className="td whitespace-nowrap font-mono text-xs text-ink-soft">{row.usn || '—'}</td>}
                  {hasName && <td className="td whitespace-nowrap font-medium text-ink">{row.name || '—'}</td>}
                  {hasSubject && <td className="td whitespace-normal max-w-[220px] text-xs font-medium text-err" title={row.subject || undefined}>{row.subject || '—'}</td>}
                  {hasSem  && <td className="td text-center font-medium text-ink-soft">{row.semester ?? '—'}</td>}
                  {hasSgpa && (
                    <td className="td">
                      <div className="flex items-center gap-2">
                        <span className="min-w-[36px] font-semibold tabular-nums text-brand-fg">
                          {row.sgpa != null ? parseFloat(row.sgpa).toFixed(2) : '—'}
                        </span>
                        {row.sgpa != null && (
                          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-sunken">
                            <div className="h-1.5 rounded-full bg-brand"
                              style={{ width: `${Math.min((parseFloat(row.sgpa)/10)*100, 100)}%` }} />
                          </div>
                        )}
                      </div>
                    </td>
                  )}
                  <td className="td">
                    <div className="flex items-center gap-2">
                      <span className="min-w-[36px] font-semibold tabular-nums text-ink">{cgpaVal}</span>
                      {cgpaVal !== '—' && (
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-sunken">
                          <div className="h-1.5 rounded-full bg-brand-soft"
                            style={{ width: `${Math.min((parseFloat(cgpaVal)/10)*100, 100)}%` }} />
                        </div>
                      )}
                    </div>
                  </td>
                  {hasSgpa && (
                    <td className={`td text-lg font-bold ${trendColor}`} title={trend ? trendLabel : undefined} aria-label={trend ? trendLabel : undefined}>
                      {trend || '—'}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * GpaTable — renders SQL results AS-IS (preserves server sort order).
 * Only sorts within same student for trend arrows.
 * Never re-sorts the full result — SQL ORDER BY is the source of truth.
 */
export default function GpaTable({ data }) {
  if (!data?.length) return null;

  const hasSgpa    = data.some(r => r.sgpa != null);
  const hasCgpaCol = data.some(r => r.cgpa != null);
  const hasName    = data.some(r => r.name);
  const hasUsn     = data.some(r => r.usn);
  const hasSem     = data.some(r => r.semester != null);

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
    <div className="rounded-xl overflow-hidden border border-slate-200">
      <div className="px-4 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 flex items-center justify-between">
        <span className="text-sm font-semibold text-white">Academic Performance</span>
        {hasSgpa && (
          <span className="text-xs text-blue-200">Best SGPA: {bestSgpa.toFixed(2)}</span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="px-3 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider w-8">#</th>
              {hasUsn  && <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">USN</th>}
              {hasName && <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Name</th>}
              {hasSem  && <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Sem</th>}
              {hasSgpa && <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">SGPA</th>}
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                CGPA <span className="text-[9px] font-normal text-slate-400 normal-case">(cumulative)</span>
              </th>
              {hasSgpa && <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Trend</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
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
              const trendColor = trend === '↑' ? 'text-green-500'
                : trend === '↓' ? 'text-red-500' : 'text-slate-400';

              // Update prev map
              if (hasSgpa) prevSgpaMap[studentKey] = curSgpa;

              return (
                <tr key={i} className="hover:bg-blue-50/30 transition-colors">
                  <td className="px-3 py-2.5 text-xs text-slate-400 text-center">{i + 1}</td>
                  {hasUsn  && <td className="px-4 py-2.5 text-xs font-mono text-slate-500 whitespace-nowrap">{row.usn || '—'}</td>}
                  {hasName && <td className="px-4 py-2.5 font-medium text-slate-800 whitespace-nowrap">{row.name || '—'}</td>}
                  {hasSem  && <td className="px-4 py-2.5 font-medium text-slate-600 text-center">{row.semester ?? '—'}</td>}
                  {hasSgpa && (
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-blue-700 min-w-[36px]">
                          {row.sgpa != null ? parseFloat(row.sgpa).toFixed(2) : '—'}
                        </span>
                        {row.sgpa != null && (
                          <div className="h-1.5 bg-slate-100 rounded-full w-16">
                            <div className="h-1.5 bg-blue-500 rounded-full"
                              style={{ width: `${Math.min((parseFloat(row.sgpa)/10)*100, 100)}%` }} />
                          </div>
                        )}
                      </div>
                    </td>
                  )}
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-indigo-700 min-w-[36px]">{cgpaVal}</span>
                      {cgpaVal !== '—' && (
                        <div className="h-1.5 bg-slate-100 rounded-full w-16">
                          <div className="h-1.5 bg-indigo-400 rounded-full"
                            style={{ width: `${Math.min((parseFloat(cgpaVal)/10)*100, 100)}%` }} />
                        </div>
                      )}
                    </div>
                  </td>
                  {hasSgpa && (
                    <td className={`px-4 py-2.5 font-bold text-lg ${trendColor}`}>{trend || '—'}</td>
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

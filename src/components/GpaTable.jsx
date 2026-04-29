/**
 * GpaTable — semester-wise SGPA table with dynamic CGPA (AVG of SGPA per student).
 * CGPA is computed client-side as AVG(sgpa) per student — never stored.
 */
export default function GpaTable({ data }) {
  if (!data?.length) return null;

  const hasSgpa = data.some(r => r.sgpa != null);
  const hasName = data.some(r => r.name);
  const hasUsn  = data.some(r => r.usn);

  // Compute dynamic CGPA per student = AVG(sgpa)
  const cgpaMap = {};
  if (hasSgpa) {
    const groups = {};
    for (const r of data) {
      const key = r.usn || r.name || '';
      if (!key) continue;
      if (!groups[key]) groups[key] = [];
      if (r.sgpa != null) groups[key].push(parseFloat(r.sgpa));
    }
    for (const [key, vals] of Object.entries(groups)) {
      if (vals.length) cgpaMap[key] = (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2);
    }
  }

  // If data already has cgpa column (from SQL AVG), use it directly
  const hasCgpaCol = data.some(r => r.cgpa != null);

  const sorted = [...data].sort((a, b) => {
    if ((a.usn || a.name || '') !== (b.usn || b.name || ''))
      return (a.usn || a.name || '').localeCompare(b.usn || b.name || '');
    return (a.semester || 0) - (b.semester || 0);
  });

  const bestSgpa = hasSgpa ? Math.max(...sorted.map(r => parseFloat(r.sgpa) || 0)) : 0;

  return (
    <div className="rounded-xl overflow-hidden border border-slate-200">
      <div className="px-4 py-2.5 bg-gradient-to-r from-blue-600 to-indigo-600 flex items-center justify-between">
        <span className="text-sm font-semibold text-white">Academic Performance</span>
        {hasSgpa && <span className="text-xs text-blue-200">Best SGPA: {bestSgpa.toFixed(2)}</span>}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              {hasUsn  && <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">USN</th>}
              {hasName && <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Name</th>}
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Sem</th>
              {hasSgpa && <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">SGPA</th>}
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                CGPA <span className="text-[9px] font-normal text-slate-400">(AVG)</span>
              </th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">Trend</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sorted.map((row, i) => {
              const studentKey = row.usn || row.name || '';
              const cgpa = hasCgpaCol
                ? (row.cgpa != null ? parseFloat(row.cgpa).toFixed(2) : '—')
                : (cgpaMap[studentKey] || '—');

              const cur  = parseFloat(row.sgpa) || 0;
              const prev = i > 0 && (sorted[i-1].usn === row.usn || sorted[i-1].name === row.name)
                ? parseFloat(sorted[i-1].sgpa) || 0 : null;
              const trend = prev === null ? null : cur > prev ? '↑' : cur < prev ? '↓' : '→';
              const trendColor = trend === '↑' ? 'text-green-500' : trend === '↓' ? 'text-red-500' : 'text-slate-400';

              return (
                <tr key={i} className="hover:bg-blue-50/30 transition-colors">
                  {hasUsn  && <td className="px-4 py-2.5 text-xs font-mono text-slate-500">{row.usn || '—'}</td>}
                  {hasName && <td className="px-4 py-2.5 font-medium text-slate-800">{row.name || '—'}</td>}
                  <td className="px-4 py-2.5 font-medium text-slate-600">{row.semester ?? '—'}</td>
                  {hasSgpa && (
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-blue-700 min-w-[36px]">
                          {row.sgpa != null ? parseFloat(row.sgpa).toFixed(2) : '—'}
                        </span>
                        {row.sgpa != null && (
                          <div className="h-1.5 bg-slate-100 rounded-full w-16">
                            <div className="h-1.5 bg-blue-500 rounded-full" style={{ width: `${(parseFloat(row.sgpa)/10)*100}%` }} />
                          </div>
                        )}
                      </div>
                    </td>
                  )}
                  <td className="px-4 py-2.5">
                    <span className="font-semibold text-indigo-700">{cgpa}</span>
                  </td>
                  <td className={`px-4 py-2.5 font-bold text-lg ${trendColor}`}>{trend || '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

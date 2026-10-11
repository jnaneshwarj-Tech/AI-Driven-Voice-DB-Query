/**
 * ReportModal.jsx — Simple "Generate Report" window for college staff.
 *
 * Reports are built from EXACTLY the records shown on the dashboard (current
 * page / selected students / all matching results, keeping the current search
 * filter and sorting) — never the whole database. The user picks a category,
 * a record scope and a format, previews the real table, then downloads or
 * prints it.
 */
import { useState, useEffect } from 'react';
import api from '../services/api';
import {
  X, Users, GraduationCap, User, Wallet, UserX, Contact,
  FileText, Table2, Sheet, Printer, Eye, Download, AlertCircle,
} from 'lucide-react';

const CATEGORIES = [
  { id: 'student_list', icon: Users, title: 'Student List', desc: 'USN, name, branch, semester and the other columns shown in the results.' },
  { id: 'academic', icon: GraduationCap, title: 'Academic', desc: 'Semester, SGPA, CGPA and branch for the shown students.' },
  { id: 'personal', icon: User, title: 'Personal Details', desc: 'Name, date of birth, address and personal fields you are allowed to see.' },
  { id: 'fees', icon: Wallet, title: 'Fees', desc: 'Total paid, pending amount and payment status, where available.' },
  { id: 'discontinued', icon: UserX, title: 'Discontinued Students', desc: 'Discontinuation date, reason and current status.' },
  { id: 'individual', icon: Contact, title: 'Individual Student', desc: 'Full details of one selected student (when exactly one is chosen).' },
];

const FORMATS = [
  { id: 'pdf', icon: FileText, label: 'PDF' },
  { id: 'excel', icon: Sheet, label: 'Excel' },
  { id: 'csv', icon: Table2, label: 'CSV' },
  { id: 'print', icon: Printer, label: 'Print' },
];

const EXT = { pdf: 'pdf', excel: 'xlsx', csv: 'csv' };

export default function ReportModal({ open, onClose, query = '', filteredRows = [], pageRows = [], selectedRows = [], hasPagedTable = false }) {
  const [category, setCategory] = useState('student_list');
  const [scope, setScope] = useState('all');
  const [format, setFormat] = useState('pdf');
  const [preview, setPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');

  const scopedRows =
    scope === 'selected' ? selectedRows :
    scope === 'page' ? pageRows : filteredRows;

  const studentsInScope = new Set(scopedRows.map(r => String(r.usn || r.name || '')).filter(Boolean)).size;
  const individualReady = studentsInScope === 1;

  useEffect(() => {
    if (!open) { setError(''); setWorking(false); }
  }, [open]);

  // Auto-preview whenever category/scope changes while the window is open.
  useEffect(() => {
    if (!open || scopedRows.length === 0) { setPreview(null); return; }
    let cancelled = false;
    setLoadingPreview(true);
    setPreview(null);
    api.post('/export/report/preview', { category, rows: scopedRows, subtitle: query })
      .then(res => { if (!cancelled) setPreview(res.data); })
      .catch(() => { if (!cancelled) setPreview(null); })
      .finally(() => { if (!cancelled) setLoadingPreview(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, category, scope, selectedRows.length, filteredRows.length]);

  if (!open) return null;

  const body = () => ({ category, rows: scopedRows, subtitle: query });

  const detailError = () => {
    if (scopedRows.length === 0) return 'There are no displayed records to report on.';
    if (category === 'individual' && !individualReady) {
      return 'Select exactly one student (tick one row) for an Individual Student Report.';
    }
    return '';
  };

  const download = async () => {
    const err = detailError();
    if (err) { setError(err); return; }
    setError(''); setWorking(true);
    try {
      if (format === 'print') {
        const res = await api.post('/export/report', { ...body(), format: 'print' });
        const win = window.open('', '_blank', 'width=900,height=700');
        if (!win) { setError('Please allow pop-ups to print the report.'); return; }
        win.document.write(typeof res.data === 'string' ? res.data : '');
        win.document.close(); win.focus();
        setTimeout(() => { win.print(); }, 400);
      } else {
        const res = await api.post('/export/report', { ...body(), format }, { responseType: 'blob' });
        const url = window.URL.createObjectURL(new Blob([res.data]));
        const a = document.createElement('a');
        a.href = url;
        a.download = `${category}_report.${EXT[format]}`;
        document.body.appendChild(a); a.click(); a.remove();
        window.URL.revokeObjectURL(url);
      }
    } catch (e) {
      setError(e?.response?.data?.detail
        ? (typeof e.response.data.detail === 'string' ? e.response.data.detail : 'Report generation failed.')
        : 'Report generation failed.');
    } finally { setWorking(false); }
  };

  const Opt = ({ active, onClick, disabled, icon: Icon, title, desc }) => (
    <button type="button" onClick={onClick} disabled={disabled}
      className={`flex items-start gap-2.5 w-full text-left px-3 py-2.5 rounded-xl border transition-colors
        ${active ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-300' : 'border-slate-200 hover:bg-slate-50'}
        ${disabled ? 'opacity-45 cursor-not-allowed' : 'cursor-pointer'}`}>
      <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${active ? 'text-indigo-600' : 'text-slate-400'}`} />
      <span className="min-w-0">
        <span className={`block text-sm font-semibold ${active ? 'text-indigo-800' : 'text-slate-700'}`}>{title}</span>
        {desc && <span className="block text-[11px] text-slate-500 leading-snug mt-0.5">{desc}</span>}
      </span>
    </button>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onMouseDown={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto"
           onMouseDown={e => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 sticky top-0 bg-white rounded-t-2xl z-10">
          <div>
            <h2 className="text-base font-bold text-slate-800">Generate Report</h2>
            {query && <p className="text-xs text-slate-500 truncate max-w-md">Search: “{query}”</p>}
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-5">
          {/* 1. Report type */}
          <section>
            <h3 className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">1. Report type</h3>
            <div className="grid sm:grid-cols-2 gap-2">
              {CATEGORIES.map(c => (
                <Opt key={c.id} icon={c.icon} title={c.title} desc={c.desc}
                     active={category === c.id} onClick={() => setCategory(c.id)} />
              ))}
            </div>
          </section>

          {/* 2. Which records */}
          <section>
            <h3 className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">2. Which records</h3>
            <div className="grid sm:grid-cols-3 gap-2">
              {hasPagedTable && (
                <Opt icon={FileText} title={`Current page (${pageRows.length})`}
                     desc="Only the rows on the page you are viewing."
                     active={scope === 'page'} onClick={() => setScope('page')} />
              )}
              <Opt icon={Users} title={`Selected students (${selectedRows.length})`}
                   desc="Rows ticked in the result table."
                   active={scope === 'selected'} onClick={() => setScope('selected')}
                   disabled={selectedRows.length === 0} />
              <Opt icon={Table2} title={`All matching results (${filteredRows.length})`}
                   desc="Every row shown by this search, with the same filter and sorting."
                   active={scope === 'all'} onClick={() => setScope('all')} />
            </div>
            {scope === 'selected' && selectedRows.length === 0 && (
              <p className="text-[11px] text-amber-600 mt-1.5">Tick rows in the table first, or choose another option.</p>
            )}
          </section>

          {/* 3. Format */}
          <section>
            <h3 className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-2">3. Format</h3>
            <div className="flex gap-2 flex-wrap">
              {FORMATS.map(f => (
                <button key={f.id} type="button" onClick={() => setFormat(f.id)}
                  className={`flex items-center gap-1.5 px-3.5 py-2 rounded-xl border text-sm font-semibold transition-colors
                    ${format === f.id ? 'border-indigo-500 bg-indigo-50 text-indigo-700 ring-1 ring-indigo-300'
                                       : 'border-slate-200 text-slate-600 hover:bg-slate-50'}`}>
                  <f.icon className="w-4 h-4" /> {f.label}
                </button>
              ))}
            </div>
          </section>

          {/* Preview */}
          <section>
            <h3 className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Eye className="w-3.5 h-3.5" /> Preview
            </h3>
            {loadingPreview ? (
              <div className="text-sm text-slate-400 py-6 text-center border border-dashed border-slate-200 rounded-xl">Preparing preview…</div>
            ) : preview ? (
              <div className="border border-slate-200 rounded-xl overflow-hidden">
                <div className="px-3 py-2 bg-slate-50 text-[11px] text-slate-600 flex flex-wrap gap-x-3 border-b border-slate-100">
                  <span className="font-semibold text-slate-700">{preview.title}</span>
                  <span>Records: {preview.record_count}</span>
                  <span>By: {preview.kind === 'detail' ? '' : `${preview.generated_by?.username} (${preview.generated_by?.role})`}</span>
                </div>
                {(preview.notes || []).map((n, i) => (
                  <p key={i} className="px-3 py-1.5 text-[11px] text-amber-700 bg-amber-50 border-b border-amber-100">Note: {n}</p>
                ))}
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-50">
                      <tr>{(preview.columns || []).map(c => (
                        <th key={c.key} className="px-2.5 py-1.5 text-left font-semibold text-slate-500 whitespace-nowrap">{c.label}</th>
                      ))}</tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {(preview.records || []).map((r, i) => (
                        <tr key={i}>{(preview.columns || []).map(c => (
                          <td key={c.key} className="px-2.5 py-1.5 text-slate-700 whitespace-nowrap max-w-[220px] truncate">
                            {r[c.key] === null || r[c.key] === undefined || r[c.key] === '' ? '' : String(r[c.key])}
                          </td>
                        ))}</tr>
                      ))}
                    </tbody>
                  </table>
                  {preview.records?.length === 0 && (
                    <p className="px-3 py-4 text-center text-slate-400 text-xs">No rows for this report with the selected students.</p>
                  )}
                </div>
                {preview.truncated_preview && (
                  <p className="px-3 py-1.5 text-[11px] text-slate-400 bg-slate-50 border-t border-slate-100">
                    Showing first 15 of {preview.record_count} rows — the downloaded report contains all of them.
                  </p>
                )}
                {preview.kind === 'detail' && (preview.sections || []).length > 0 && (
                  <p className="px-3 py-1.5 text-[11px] text-slate-500 bg-slate-50 border-t border-slate-100">
                    Also included: {preview.sections.join(' · ')}
                  </p>
                )}
              </div>
            ) : (
              <div className="text-sm text-slate-400 py-6 text-center border border-dashed border-slate-200 rounded-xl">Nothing to preview — choose records first.</div>
            )}
          </section>

          {error && (
            <div className="flex items-start gap-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded-xl px-3 py-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" /> {error}
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-slate-100 flex items-center justify-end gap-2 sticky bottom-0 bg-white rounded-b-2xl">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 rounded-xl border border-slate-200">
            Close
          </button>
          <button onClick={download} disabled={working || loadingPreview}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-xl">
            {format === 'print' ? <Printer className="w-4 h-4" /> : <Download className="w-4 h-4" />}
            {working ? 'Preparing…' : format === 'print' ? 'Print Report' : `Download ${format === 'excel' ? 'Excel' : format.toUpperCase()}`}
          </button>
        </div>
      </div>
    </div>
  );
}

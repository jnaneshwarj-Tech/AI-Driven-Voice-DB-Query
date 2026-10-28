/**
 * ReportModal.jsx — Simple "Generate Report" window for college staff.
 *
 * Reports are built from EXACTLY the records shown on the dashboard (current
 * page / selected students / all matching results, keeping the current search
 * filter and sorting) — never the whole database. The user picks a category,
 * a record scope and a format, previews the real table, then downloads or
 * prints it.
 *
 * Print path note: the popup receives the backend's own HTML document
 * (res.data is written verbatim into it). That HTML has no access to this
 * app's Tailwind bundle, so nothing here may inject class names into it.
 */
import { useState, useEffect } from 'react';
import api from '../services/api';
import { useI18n } from '../context/LanguageContext';
import {
  X, Users, GraduationCap, User, Wallet, UserX, Contact,
  FileText, Table2, Sheet, Printer, Eye, Download, AlertCircle,
} from 'lucide-react';

// ids are payload values sent to /export/report — they must never change.
// Display titles/descriptions live in i18n under report.cat.<id>.(title|desc).
const CATEGORIES = [
  { id: 'student_list', icon: Users },
  { id: 'academic', icon: GraduationCap },
  { id: 'personal', icon: User },
  { id: 'fees', icon: Wallet },
  { id: 'discontinued', icon: UserX },
  { id: 'individual', icon: Contact },
];

// ids are payload values ('pdf' | 'excel' | 'csv' | 'print'); labels are i18n
// keys report.fmt.<id> (PDF/CSV/Excel stay in Latin script).
const FORMATS = [
  { id: 'pdf', icon: FileText },
  { id: 'excel', icon: Sheet },
  { id: 'csv', icon: Table2 },
  { id: 'print', icon: Printer },
];

const EXT = { pdf: 'pdf', excel: 'xlsx', csv: 'csv' };

export default function ReportModal({ open, onClose, query = '', filteredRows = [], pageRows = [], selectedRows = [], hasPagedTable = false }) {
  const { t } = useI18n();
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
    if (scopedRows.length === 0) return t('report.noRecords');
    if (category === 'individual' && !individualReady) {
      return t('report.pickOne');
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
        if (!win) { setError(t('report.popups')); return; }
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
        ? (typeof e.response.data.detail === 'string' ? e.response.data.detail : t('report.failed'))
        : t('report.failed'));
    } finally { setWorking(false); }
  };

  const Opt = ({ active, onClick, disabled, icon: Icon, title, desc }) => (
    <button type="button" onClick={onClick} disabled={disabled}
      className={`flex items-start gap-2.5 w-full text-left px-3 py-2.5 rounded-md border transition-colors
        ${active ? 'border-brand bg-brand/10' : 'border-line hover:bg-sunken'}
        ${disabled ? 'opacity-45 cursor-not-allowed' : 'cursor-pointer'}`}>
      <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${active ? 'text-brand-fg' : 'text-ink-faint'}`} />
      <span className="min-w-0">
        <span className={`block text-sm font-semibold ${active ? 'text-ink' : 'text-ink-soft'}`}>{title}</span>
        {desc && <span className="block text-[11px] text-ink-mute leading-snug mt-0.5">{desc}</span>}
      </span>
    </button>
  );

  const sectionLabel = 'text-xs font-bold text-ink-mute uppercase tracking-wider mb-2';

  return (
    <div className="backdrop" onMouseDown={onClose}>
      <div className="modal-panel max-w-3xl anim-scale-in"
           onMouseDown={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="report-modal-title">
        <div className="flex items-center justify-between px-5 py-4 border-b border-line sticky top-0 bg-surface-elev rounded-t-lg z-10">
          <div>
            <h2 id="report-modal-title" className="t-card text-ink">{t('report.heading')}</h2>
            {query && <p className="t-support text-ink-mute truncate max-w-md">{t('report.searching', { query })}</p>}
          </div>
          <button onClick={onClose} aria-label={t('common.close')} className="p-1.5 rounded-md hover:bg-sunken text-ink-mute">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-5">
          {/* 1. Report type */}
          <section>
            <h3 className={sectionLabel}>{t('report.stepType')}</h3>
            <div className="grid sm:grid-cols-2 gap-2 stagger">
              {CATEGORIES.map(c => (
                <Opt key={c.id} icon={c.icon}
                     title={t(`report.cat.${c.id}.title`)} desc={t(`report.cat.${c.id}.desc`)}
                     active={category === c.id} onClick={() => setCategory(c.id)} />
              ))}
            </div>
          </section>

          {/* 2. Which records */}
          <section>
            <h3 className={sectionLabel}>{t('report.stepRecords')}</h3>
            <div className="grid sm:grid-cols-3 gap-2">
              {hasPagedTable && (
                <Opt icon={FileText} title={t('report.scopePage', { n: pageRows.length })}
                     desc={t('report.scopePage.desc')}
                     active={scope === 'page'} onClick={() => setScope('page')} />
              )}
              <Opt icon={Users} title={t('report.scopeSelected', { n: selectedRows.length })}
                   desc={t('report.scopeSelected.desc')}
                   active={scope === 'selected'} onClick={() => setScope('selected')}
                   disabled={selectedRows.length === 0} />
              <Opt icon={Table2} title={t('report.scopeAll', { n: filteredRows.length })}
                   desc={t('report.scopeAll.desc')}
                   active={scope === 'all'} onClick={() => setScope('all')} />
            </div>
            {scope === 'selected' && selectedRows.length === 0 && (
              <p className="text-[11px] text-warn mt-1.5">{t('report.tickFirst')}</p>
            )}
          </section>

          {/* 3. Format */}
          <section>
            <h3 className={sectionLabel}>{t('report.stepFormat')}</h3>
            <div className="flex gap-2 flex-wrap">
              {FORMATS.map(f => (
                <button key={f.id} type="button" onClick={() => setFormat(f.id)}
                  className={`flex items-center gap-1.5 px-3.5 py-2 rounded-md border text-sm font-semibold transition-colors
                    ${format === f.id ? 'border-brand bg-brand/10 text-brand-fg'
                                       : 'border-line text-ink-soft hover:bg-sunken'}`}>
                  <f.icon className="w-4 h-4" /> {t(`report.fmt.${f.id}`)}
                </button>
              ))}
            </div>
          </section>

          {/* Preview */}
          <section>
            <h3 className={`${sectionLabel} flex items-center gap-1.5`}>
              <Eye className="w-3.5 h-3.5" /> {t('report.preview')}
            </h3>
            {loadingPreview ? (
              <div className="t-body text-ink-faint py-6 text-center border border-dashed border-line rounded-md">{t('report.preparingPreview')}</div>
            ) : preview ? (
              <div className="border border-line rounded-md overflow-hidden bg-surface">
                <div className="px-3 py-2 bg-sunken text-[11px] text-ink-mute flex flex-wrap gap-x-3 border-b border-line">
                  {/* preview.* values are backend-authored — rendered as-is */}
                  <span className="font-semibold text-ink-soft">{preview.title}</span>
                  <span>{t('report.recordsCount', { n: preview.record_count })}</span>
                  <span>{t('report.by', { who: preview.kind === 'detail' ? '' : `${preview.generated_by?.username} (${preview.generated_by?.role})` })}</span>
                </div>
                {(preview.notes || []).map((n, i) => (
                  <p key={i} className="px-3 py-1.5 text-[11px] text-warn bg-warn-soft border-b border-line">{t('report.note', { text: n })}</p>
                ))}
                <div className="table-scroll">
                  <table className="w-full">
                    <thead>
                      <tr>{(preview.columns || []).map(c => (
                        <th key={c.key} className="th">{c.label}</th>
                      ))}</tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {(preview.records || []).map((r, i) => (
                        <tr key={i}>{(preview.columns || []).map(c => (
                          <td key={c.key} className="td max-w-[220px] truncate">
                            {r[c.key] === null || r[c.key] === undefined || r[c.key] === '' ? '' : String(r[c.key])}
                          </td>
                        ))}</tr>
                      ))}
                    </tbody>
                  </table>
                  {preview.records?.length === 0 && (
                    <p className="px-3 py-4 text-center text-ink-faint text-xs">{t('report.noRows')}</p>
                  )}
                </div>
                {preview.truncated_preview && (
                  <p className="px-3 py-1.5 text-[11px] text-ink-mute bg-sunken border-t border-line">
                    {t('report.truncated', { n: preview.record_count })}
                  </p>
                )}
                {preview.kind === 'detail' && (preview.sections || []).length > 0 && (
                  <p className="px-3 py-1.5 text-[11px] text-ink-mute bg-sunken border-t border-line">
                    {t('report.alsoIncluded', { sections: preview.sections.join(' · ') })}
                  </p>
                )}
              </div>
            ) : (
              <div className="t-body text-ink-faint py-6 text-center border border-dashed border-line rounded-md">{t('report.nothingPreview')}</div>
            )}
          </section>

          {error && (
            <div className="flex items-start gap-2 t-support text-err bg-err-soft border border-err/30 rounded-md px-3 py-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" /> {error}
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-line flex flex-wrap items-center justify-end gap-2 sticky bottom-0 bg-surface-elev rounded-b-lg">
          <button onClick={onClose} className="btn btn-ghost">
            {t('common.close')}
          </button>
          <button onClick={download} disabled={working || loadingPreview} className="btn btn-primary">
            {format === 'print' ? <Printer className="w-4 h-4" /> : <Download className="w-4 h-4" />}
            {working ? t('report.working') : format === 'print' ? t('report.printReport') : t('report.downloadFmt', { fmt: format === 'excel' ? 'Excel' : format.toUpperCase() })}
          </button>
        </div>
      </div>
    </div>
  );
}

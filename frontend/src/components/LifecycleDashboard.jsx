import { useState, useEffect, useMemo, useCallback } from 'react';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import { useToast } from './Toast';
import { useI18n } from '../context/LanguageContext';
import {
  Users, PlusCircle, RefreshCw, Search, History, CheckCircle, XCircle,
  AlertTriangle, ShieldCheck, Clock, FileText, ArrowRight, UserCheck,
  Sparkles, Download, Wand2,
} from 'lucide-react';

// ── Status → badge variants (mirrors the backend canonical list from /options) ─
// Values are design-system badge classes; the status strings themselves are
// backend data and are always rendered as-is.
const STATUS_COLORS = {
  'Active':                    'badge-ok',
  'Temporarily Discontinued':  'badge-warn',
  'Discontinued-Review Req':   'badge-err',
  'Dropout-College Recorded':  'badge-err',
  'Readmission Requested':     'badge-info',
  'Readmission Approved':      'badge-info',
  'Rejoined-Active':           'badge-ok',
  'Graduated':                 'badge-accent',
  'Transferred':               'badge-quiet',
  'Admission Cancelled':       'badge-quiet',
  'Other':                     'badge-quiet',
};

const fmtDate = (v) => {
  if (!v) return '—';
  const s = String(v);
  if (s.length >= 10 && /^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
  return s;
};

function StatusPill({ status }) {
  const cls = STATUS_COLORS[status] || 'badge-quiet';
  return (
    <span className={`badge ${cls}`}>
      {status || 'Active'}
    </span>
  );
}

// ── Small modal shell ─────────────────────────────────────────────────────────
function Modal({ title, subtitle, onClose, children, tone = 'blue' }) {
  const { t } = useI18n();
  const toneCls = { blue: 'border-brand', amber: 'border-warn', rose: 'border-err', emerald: 'border-ok' }[tone] || 'border-brand';
  return (
    <div className="backdrop" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : undefined}
           className={`modal-panel border-t-4 ${toneCls} anim-scale-in`}
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-3 p-4 sm:p-5 border-b border-line">
          <div className="min-w-0">
            <h3 className="t-card text-ink">{title}</h3>
            {subtitle && <p className="t-support text-ink-mute mt-0.5">{subtitle}</p>}
          </div>
          <button onClick={onClose} aria-label={t('common.close')}
                  className="btn btn-ghost btn-sm px-2 min-h-0 text-ink-mute hover:text-ink leading-none shrink-0">
            <span aria-hidden="true" className="text-lg leading-none">×</span>
          </button>
        </div>
        <div className="p-4 sm:p-5">{children}</div>
      </div>
    </div>
  );
}

const Empty = ({ icon: Icon, title, hint }) => (
  <div className="empty-state">
    {Icon && <div className="w-12 h-12 rounded-full bg-sunken border border-line flex items-center justify-center text-ink-mute"><Icon className="w-6 h-6" /></div>}
    <p className="t-card text-ink-soft">{title}</p>
    {hint && <p className="t-support text-ink-mute max-w-md">{hint}</p>}
  </div>
);

const Spinner = () => {
  const { t } = useI18n();
  return (
    <div className="flex items-center justify-center py-16 gap-3 text-ink-mute">
      <div className="w-8 h-8 border-4 border-line border-t-brand rounded-full animate-spin" />
      <p className="t-support">{t('lifecycle.loadingRecords')}</p>
    </div>
  );
};

export default function LifecycleDashboard({ role = 'Staff' }) {
  const { t } = useI18n();
  const isAdmin = String(role).toLowerCase() === 'admin';
  const showToast = useToast().showToast;

  const [options, setOptions] = useState({ statuses: [], event_types: [], active_statuses: [], discontinued_statuses: [], reason_categories: [] });
  const [filters, setFilters] = useState({
    status: '', scheme: '', admission_year: '', branch: '', last_semester: '',
    reason_category: '', date_from: '', date_to: '', search: '',
  });
  const [sort, setSort] = useState({ by: 'usn', dir: 'asc' });
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  // ── §1 natural-language recording (preview → authorized confirm) ────────────
  const [nlQuery, setNlQuery] = useState('');
  const [nlLang, setNlLang] = useState('english');
  const [nlLoading, setNlLoading] = useState(false);
  const [nlPreview, setNlPreview] = useState(null);   // {action_required, payload, confirmation_token, suggestions, message}
  const [exporting, setExporting] = useState('');

  const [detailUsn, setDetailUsn] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [statusTarget, setStatusTarget] = useState(null);       // student row for status change
  const [readmitTarget, setReadmitTarget] = useState(null);      // student row for new readmission request
  const [decisionTarget, setDecisionTarget] = useState(null);    // student row + eligibility snapshot

  // Load dropdown options once.
  useEffect(() => {
    api.get('/lifecycle/options')
      .then(r => setOptions(r.data))
      .catch(() => { /* options endpoint failure is non-fatal; keep defaults */ });
  }, []);

  const loadList = useCallback(async () => {
    setLoading(true); setErr('');
    try {
      const params = { sort_by: sort.by, sort_dir: sort.dir };
      Object.entries(filters).forEach(([k, v]) => { if (String(v).trim() !== '') params[k] = v; });
      const r = await api.get('/lifecycle/list', { params });
      setRows(r.data?.data || []);
      setTotal(r.data?.total_count ?? (r.data?.data || []).length);
    } catch (e) {
      const m = getUserMessage(e, t('lifecycle.errLoadList'));
      setErr(m);
      showToast({ type: 'error', message: m });
    } finally { setLoading(false); }
  }, [filters, sort, showToast]);

  useEffect(() => { loadList(); }, [loadList]);

  const openDetail = async (usn) => {
    setDetailUsn(usn); setDetail(null); setDetailLoading(true);
    try {
      const r = await api.get(`/lifecycle/students/${encodeURIComponent(usn)}`);
      setDetail(r.data);
    } catch (e) {
      showToast({ type: 'error', message: getUserMessage(e, t('lifecycle.errLoadHistory')) });
      setDetailUsn(null);
    } finally { setDetailLoading(false); }
  };

  const refreshDetail = (usn) => {
    return api.get(`/lifecycle/students/${encodeURIComponent(usn)}`).then(r => setDetail(r.data));
  };

  // After a status/readmission change the list must reflect the new derived cache.
  const afterChange = async (usn) => {
    await loadList();
    if (detailUsn === usn) { try { await refreshDetail(usn); } catch { /* ignore */ } }
  };

  // ── §1 NL record: parse + preview only (saves nothing) ──────────────────────
  const runNlPreview = async (usnOverride = '') => {
    if (!nlQuery.trim() && !usnOverride) return;
    setNlLoading(true);
    try {
      const r = await api.post('/lifecycle/nl/record', {
        natural_query: nlQuery, language: nlLang,
        ...(usnOverride ? { usn: usnOverride } : {}),
      });
      setNlPreview(r.data);
    } catch (e) {
      showToast({ type: 'error', message: getUserMessage(e, t('lifecycle.errNlRead')) });
    } finally { setNlLoading(false); }
  };

  // Resolve an ambiguous name by re-running with the chosen USN.
  const pickStudentForNl = (s) => runNlPreview(s.usn);

  // ── §1/§6 Commit only through /nl/confirm (Admin enforced on backend) ───────
  const confirmNlRecord = async () => {
    if (!nlPreview?.payload) return;
    setNlLoading(true);
    try {
      const r = await api.post('/lifecycle/nl/confirm', {
        payload: nlPreview.payload,
        confirmation_token: nlPreview.confirmation_token,
      });
      const d = r.data;
      showToast({
        type: 'success',
        message: d.deduplicated
          ? t('lifecycle.dedup')
          : t('lifecycle.recorded', { from: d.from_status, to: d.to_status }),
      });
      setNlPreview(null); setNlQuery('');
      await loadList();
    } catch (e) {
      showToast({ type: 'error', message: getUserMessage(e, t('lifecycle.errNlRecord')) });
    } finally { setNlLoading(false); }
  };

  const doExport = async (fmt) => {
    setExporting(fmt);
    try {
      const params = { fmt, sort_by: sort.by, sort_dir: sort.dir };
      Object.entries(filters).forEach(([k, v]) => { if (String(v).trim() !== '') params[k] = v; });
      const r = await api.get('/lifecycle/export', { params, responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url; a.download = `lifecycle_register.${fmt}`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      showToast({ type: 'success', message: t('lifecycle.exported', { fmt: fmt.toUpperCase() }) });
    } catch (e) {
      let msg = t('lifecycle.exportFailed');
      try { msg = JSON.parse(await e.response?.data?.text?.())?.detail || msg; } catch { /* blob error */ }
      showToast({ type: 'error', message: msg });
    } finally { setExporting(''); }
  };

  const clearFilters = () => setFilters({
    status: '', scheme: '', admission_year: '', branch: '', last_semester: '',
    reason_category: '', date_from: '', date_to: '', search: '',
  });

  return (
    <div className="space-y-6 anim-fade-up">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <h2 className="t-section text-ink flex items-center gap-2">
            <Users className="w-5 h-5 text-brand-fg" aria-hidden="true" /> {t('lifecycle.title')}
          </h2>
          <p className="t-support text-ink-mute mt-1 max-w-3xl">
            {t('lifecycle.subtitle')}
          </p>
        </div>
        <button onClick={loadList} disabled={loading}
                className="btn btn-ghost btn-sm">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" /> {t('common.refresh')}
        </button>
      </div>

      {err && (
        <div role="alert" className="flex items-center gap-2 p-3 bg-err-soft border border-err/30 text-err rounded-lg t-support">
          <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden="true" /> {err}
        </div>
      )}

      {/* §1 Record by natural language */}
      <section className="card p-4 sm:p-5" aria-labelledby="nl-heading">
        <div className="flex items-center gap-2 mb-2">
          <Wand2 className="w-4 h-4 text-brand-fg" aria-hidden="true" />
          <h3 id="nl-heading" className="t-card text-ink">{t('lifecycle.nlHeading')}</h3>
        </div>
        <p className="t-support text-ink-mute mb-3">
          {t('lifecycle.nlHelpBefore')} <strong className="text-ink-soft">{t('lifecycle.nlHelpStrong')}</strong>{t('lifecycle.nlHelpAfter')}
        </p>
        <div className="flex flex-wrap gap-2 items-stretch">
          <textarea value={nlQuery} onChange={e => setNlQuery(e.target.value)} rows={2}
                    aria-label={t('lifecycle.nlHeading')}
                    placeholder={t('lifecycle.nlPlaceholder')}
                    className="input flex-1 min-w-[220px]" />
          <select value={nlLang} onChange={e => setNlLang(e.target.value)}
                  aria-label={t('lifecycle.nlLangAria')}
                  className="input w-auto shrink-0">
            <option value="english">{t('lifecycle.langEnglish')}</option>
            <option value="kannada">{t('lifecycle.langKannada')}</option>
            <option value="mixed">{t('lifecycle.langMixed')}</option>
          </select>
          <button onClick={() => runNlPreview()} disabled={nlLoading || !nlQuery.trim()}
                  className="btn btn-primary">
            <Sparkles className="w-3.5 h-3.5" aria-hidden="true" /> {nlLoading ? t('lifecycle.reading') : t('lifecycle.detect')}
          </button>
        </div>
      </section>

      {/* Filters */}
      <section className="card p-4 sm:p-5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3" aria-label={t('lifecycle.filtersAria')}>
        <label className="flex flex-col gap-1">
          <span className="field-label">{t('common.status')}</span>
          <select value={filters.status} onChange={e => setFilters({ ...filters, status: e.target.value })}
                  className="input">
            <option value="">{t('lifecycle.any')}</option>
            {options.statuses.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="field-label">{t('lifecycle.reasonCategory')}</span>
          <select value={filters.reason_category} onChange={e => setFilters({ ...filters, reason_category: e.target.value })}
                  className="input">
            <option value="">{t('lifecycle.any')}</option>
            {(options.reason_categories || []).map(rc => <option key={rc} value={rc}>{rc}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="field-label">{t('lifecycle.scheme')}</span>
          <input value={filters.scheme} onChange={e => setFilters({ ...filters, scheme: e.target.value })}
                 placeholder={t('lifecycle.schemePlaceholder')}
                 className="input" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="field-label">{t('lifecycle.admissionYear')}</span>
          <input value={filters.admission_year} onChange={e => setFilters({ ...filters, admission_year: e.target.value })}
                 inputMode="numeric" placeholder={t('lifecycle.admissionYearPlaceholder')}
                 className="input" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="field-label">{t('lifecycle.branch')}</span>
          <input value={filters.branch} onChange={e => setFilters({ ...filters, branch: e.target.value })}
                 placeholder={t('lifecycle.branchPlaceholder')}
                 className="input" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="field-label">{t('lifecycle.lastSemester')}</span>
          <input value={filters.last_semester} onChange={e => setFilters({ ...filters, last_semester: e.target.value })}
                 inputMode="numeric" placeholder={t('lifecycle.lastSemesterPlaceholder')}
                 className="input" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="field-label">{t('lifecycle.effectiveFrom')}</span>
          <input type="date" value={filters.date_from} onChange={e => setFilters({ ...filters, date_from: e.target.value })}
                 className="input" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="field-label">{t('lifecycle.effectiveTo')}</span>
          <input type="date" value={filters.date_to} onChange={e => setFilters({ ...filters, date_to: e.target.value })}
                 className="input" />
        </label>
        <label className="flex flex-col gap-1 sm:col-span-2 lg:col-span-4">
          <span className="field-label">{t('lifecycle.searchLabel')}</span>
          <input value={filters.search} onChange={e => setFilters({ ...filters, search: e.target.value })}
                 placeholder={t('lifecycle.searchPlaceholder')}
                 className="input" />
        </label>
        <div className="sm:col-span-2 lg:col-span-4 flex items-center justify-between flex-wrap gap-2">
          <p className="t-support text-ink-mute" aria-live="polite">
            {t('lifecycle.showing', { shown: rows.length, total })} {t('lifecycle.liveRefresh')}
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <button onClick={clearFilters}
                    className="btn btn-ghost btn-sm">{t('lifecycle.clearFilters')}</button>
            {['csv', 'xlsx', 'pdf'].map(f => (
              <button key={f} onClick={() => doExport(f)} disabled={!!exporting || rows.length === 0}
                      className="btn btn-ghost btn-sm">
                <Download className="w-3 h-3" aria-hidden="true" /> {exporting === f ? '…' : f.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Table */}
      <div className="table-wrap">
        {loading ? <Spinner /> : rows.length === 0 ? (
          <Empty icon={Search} title={t('lifecycle.noRecords')}
                 hint={t('lifecycle.noRecordsHint')} />
        ) : (
          <div className="table-scroll">
            <table className="w-full">
              <thead>
                <tr>
                  <th scope="col"
                      aria-sort={sort.by === 'usn' ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      onClick={() => setSort({ by: 'usn', dir: sort.by === 'usn' && sort.dir === 'asc' ? 'desc' : 'asc' })}
                      className="th cursor-pointer select-none">USN{sort.by === 'usn' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th>
                  <th scope="col"
                      aria-sort={sort.by === 'name' ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      onClick={() => setSort({ by: 'name', dir: sort.by === 'name' && sort.dir === 'asc' ? 'desc' : 'asc' })}
                      className="th cursor-pointer select-none">{t('lifecycle.colName')}{sort.by === 'name' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th>
                  <th scope="col" className="th">{t('lifecycle.colBranchBatch')}</th>
                  <th scope="col" className="th">{t('common.status')}</th>
                  <th scope="col" className="th">{t('lifecycle.colLastSem')}</th>
                  <th scope="col" className="th">{t('lifecycle.colReason')}</th>
                  <th scope="col" className="th">{t('lifecycle.colCategory')}</th>
                  <th scope="col"
                      aria-sort={sort.by === 'effective_date' ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      onClick={() => setSort({ by: 'effective_date', dir: sort.by === 'effective_date' && sort.dir === 'asc' ? 'desc' : 'asc' })}
                      className="th cursor-pointer select-none">{t('lifecycle.colEffective')}{sort.by === 'effective_date' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th>
                  <th scope="col" className="th">{t('lifecycle.colLatestEvent')}</th>
                  <th scope="col" className="th text-right">{t('common.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.usn} className="tr-hover">
                    <td className="td font-mono whitespace-nowrap">{r.usn}</td>
                    <td className="td font-semibold text-ink">{r.name}</td>
                    <td className="td">{r.branch || '—'} / {r.admission_year ?? '—'}</td>
                    <td className="td"><StatusPill status={r.current_status} /></td>
                    <td className="td">{r.last_enrolled_semester ?? '—'}</td>
                    <td className="td t-truncate" title={r.reason || ''}>{r.reason || '—'}</td>
                    <td className="td"><span className="t-support text-ink-mute uppercase">{r.reason_category || '—'}</span></td>
                    <td className="td whitespace-nowrap">{fmtDate(r.effective_date)}</td>
                    <td className="td">{r.latest_event_type || '—'}</td>
                    <td className="td text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-2 flex-wrap justify-end">
                      <button onClick={() => openDetail(r.usn)}
                              className="btn btn-ghost btn-sm">
                        <History className="w-3 h-3" aria-hidden="true" /> {t('lifecycle.history')}
                      </button>
                      {isAdmin && (
                        <button onClick={() => setStatusTarget(r)}
                                className="btn btn-primary btn-sm">
                          <ArrowRight className="w-3 h-3" aria-hidden="true" /> {t('lifecycle.changeStatus')}
                        </button>
                      )}
                      {isAdmin && ['Temporarily Discontinued','Discontinued-Review Req','Dropout-College Recorded'].includes(r.current_status) && (
                        <button onClick={() => setReadmitTarget(r)}
                                className="btn btn-primary btn-sm">
                          <UserCheck className="w-3 h-3" aria-hidden="true" /> {t('lifecycle.readmissionRequest')}
                        </button>
                      )}
                      {isAdmin && r.current_status === 'Readmission Requested' && (
                        <button onClick={() => setDecisionTarget(r)}
                                className="btn btn-primary btn-sm">
                          <ShieldCheck className="w-3 h-3" aria-hidden="true" /> {t('lifecycle.approveReject')}
                        </button>
                      )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Non-admin hint */}
      {!isAdmin && (
        <p className="t-support text-ink-mute px-2">
          {t('lifecycle.staffHint')}
        </p>
      )}

      {/* Detail modal */}
      {detailUsn && (
        <Modal title={t('lifecycle.detailTitle', { usn: detailUsn })}
               subtitle={detail ? `${detail.name || ''}` : t('common.loading')}
               onClose={() => setDetailUsn(null)}>
          {detailLoading ? <Spinner /> : !detail ? <Empty title={t('lifecycle.noData')} /> : (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                <Field label={t('lifecycle.currentStatus')}><StatusPill status={detail.current_status} /></Field>
                <Field label={t('lifecycle.scheme')}>{detail.status?.scheme || '—'}</Field>
                <Field label={t('lifecycle.lastEnrolledSem')}>{detail.status?.last_enrolled_semester ?? '—'}</Field>
                <Field label={t('lifecycle.academicYear')}>{detail.status?.last_enrolled_academic_year || '—'}</Field>
                <Field label={t('lifecycle.effectiveDate')}>{fmtDate(detail.status?.effective_date)}</Field>
                <Field label={t('lifecycle.colReason')}>{detail.status?.reason || '—'}</Field>
                <Field label={t('lifecycle.documentRef')}>{detail.status?.document_ref || '—'}</Field>
                <Field label={t('lifecycle.updatedBy')}>{detail.status?.updated_by || '—'}</Field>
              </div>

              <Section title={t('lifecycle.statusHistory')} icon={History}>
                {detail.history?.length ? (
                  <ol className="space-y-2 text-sm">
                    {detail.history.map(ev => (
                      <li key={ev.id} className="sunken p-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full bg-brand" />
                        <span className="text-ink-faint font-mono t-support">{fmtDate(ev.created_at)}</span>
                        <span className="font-semibold text-ink-soft">{ev.event_type}</span>
                        <span className="text-ink-mute">{ev.from_status || '—'}</span>
                        <ArrowRight className="w-3 h-3 text-ink-faint inline" aria-hidden="true" />
                        <StatusPill status={ev.to_status} />
                        {ev.reason && <span className="text-ink-mute">· {ev.reason}</span>}
                        {ev.approval_ref && <span className="text-ink-mute">· {t('lifecycle.refLabel', { ref: ev.approval_ref })}</span>}
                        <span className="ml-auto text-ink-faint">{t('lifecycle.byWho', { who: ev.actor_username || '—' })}</span>
                      </li>
                    ))}
                  </ol>
                ) : <p className="t-support text-ink-faint">{t('lifecycle.historyEmpty')}</p>}
              </Section>

              <Section title={t('lifecycle.readmissionRequests')} icon={UserCheck}>
                {detail.readmission_requests?.length ? (
                  <div className="table-scroll">
                  <table className="w-full">
                    <thead><tr>
                      <th scope="col" className="th">{t('lifecycle.requestedSem')}</th><th scope="col" className="th">{t('lifecycle.colDate')}</th>
                      <th scope="col" className="th">{t('lifecycle.colOutcome')}</th><th scope="col" className="th">{t('common.status')}</th>
                      <th scope="col" className="th">{t('lifecycle.approvedSem')}</th><th scope="col" className="th">{t('lifecycle.colRef')}</th>
                    </tr></thead>
                    <tbody>
                      {detail.readmission_requests.map(q => (
                        <tr key={q.id} className="tr-hover">
                          <td className="td">{q.requested_semester ?? '—'}</td>
                          <td className="td">{fmtDate(q.request_date)}</td>
                          <td className="td"><code className="text-ink-mute">{q.eligibility_outcome || '—'}</code></td>
                          <td className="td font-semibold text-ink">{q.status}</td>
                          <td className="td">{q.approved_semester ?? '—'}</td>
                          <td className="td">{q.approval_ref || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  </div>
                ) : <p className="t-support text-ink-faint">{t('lifecycle.readmitEmpty')}</p>}
              </Section>

              {detail.identity_links?.length > 0 && (
                <Section title={t('lifecycle.relatedUsns')} icon={FileText}>
                  <ul className="text-sm space-y-1">
                    {detail.identity_links.map((lk, i) => (
                      <li key={i} className="flex gap-2 flex-wrap items-center">
                        <code className="text-brand-fg">{lk.relation_type}</code>
                        <span className="font-mono">{lk.related_usn}</span>
                        <span className="text-ink-mute">· {lk.note || ''}</span>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
            </div>
          )}
        </Modal>
      )}

      {/* Status change modal */}
      {isAdmin && statusTarget && (
        <StatusChangeModal student={statusTarget} options={options}
                           onClose={() => setStatusTarget(null)}
                           onDone={() => { const u = statusTarget.usn; setStatusTarget(null); afterChange(u); }} />
      )}

      {/* Readmission request modal (evaluates eligibility, never auto-approves) */}
      {isAdmin && readmitTarget && (
        <ReadmitRequestModal student={readmitTarget}
                             onClose={() => setReadmitTarget(null)}
                             onDone={() => { const u = readmitTarget.usn; setReadmitTarget(null); afterChange(u); }} />
      )}

      {/* Decision modal (approve / reject / record rejoining) */}
      {isAdmin && decisionTarget && (
        <DecisionModal student={decisionTarget}
                       onClose={() => setDecisionTarget(null)}
                       onDone={() => { const u = decisionTarget.usn; setDecisionTarget(null); afterChange(u); }} />
      )}

      {/* §1 NL preview: confirm / select-student / message */}
      {nlPreview && (
        <NlPreviewModal preview={nlPreview} isAdmin={isAdmin} loading={nlLoading}
                        onClose={() => setNlPreview(null)}
                        onPick={pickStudentForNl}
                        onConfirm={confirmNlRecord} />
      )}
    </div>
  );
}

// ── §1 natural-language preview / confirmation / student selection ────────────
function NlPreviewModal({ preview, isAdmin, loading, onClose, onPick, onConfirm }) {
  const { t } = useI18n();
  const action = preview?.action_required;
  const p = preview?.payload || {};

  if (action === 'select_student') {
    return (
      <Modal title={t('lifecycle.whichStudent')} subtitle={preview.message || t('lifecycle.selectUsnHint')}
             onClose={onClose} tone="amber">
        <ul className="space-y-2 text-sm">
          {(preview.suggestions || []).map(s => (
            <li key={s.usn}>
              <button onClick={() => onPick(s)}
                      className="w-full text-left btn btn-ghost justify-between">
                <span className="font-semibold text-ink">{s.name || s.usn}</span>
                <span className="font-mono text-ink-mute">{s.usn}{s.branch ? ` · ${s.branch}` : ''}</span>
              </button>
            </li>
          ))}
        </ul>
      </Modal>
    );
  }

  if (action !== 'confirm') {
    // clarify / no_record — informational, nothing was saved.
    return (
      <Modal title={t('lifecycle.noRecordCreated')} subtitle={preview.message || t('lifecycle.nothingToConfirm')}
             onClose={onClose} tone="rose">
        <p className="t-body text-ink-soft">
          {t('lifecycle.nothingWritten')}
        </p>
      </Modal>
    );
  }

  return (
    <Modal title={t('lifecycle.confirmHeading')}
           subtitle={t('lifecycle.confirmSub')}
           onClose={onClose} tone="emerald">
      <div className="space-y-3 text-sm">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <Field label={t('lifecycle.student')}>{p.name || '—'} <span className="font-mono text-ink-mute">({p.usn})</span></Field>
          <Field label={t('lifecycle.newStatus')}><StatusPill status={p.to_status} /></Field>
          <Field label={t('lifecycle.colReason')}>{p.reason || '—'}</Field>
          <Field label={t('lifecycle.reasonCategory')}>{p.reason_category || '—'}</Field>
          <Field label={t('lifecycle.effectiveDate')}>{fmtDate(p.effective_date)}</Field>
          <Field label={t('lifecycle.lastSemester')}>{p.last_enrolled_semester ?? '—'}</Field>
        </div>
        <div className="sunken p-2 t-support text-ink-mute">
          {t('lifecycle.originalInstruction')} <span className="italic">"{p.original_query}"</span>
        </div>
        {!isAdmin && (
          <div className="p-2 bg-warn-soft border border-warn/30 rounded text-warn t-support flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" /> {t('lifecycle.adminOnlyCommit')}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose} className="btn btn-ghost">{t('common.cancel')}</button>
          <button onClick={onConfirm} disabled={loading || !isAdmin}
                  className="btn btn-accent">
            <CheckCircle className="w-3.5 h-3.5" aria-hidden="true" /> {loading ? t('common.saving') : t('lifecycle.confirmSave')}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function Field({ label, children }) {
  return (
    <div className="sunken p-2">
      <p className="t-support text-ink-faint uppercase tracking-wide">{label}</p>
      <div className="text-ink mt-0.5">{children}</div>
    </div>
  );
}
function Section({ title, icon: Icon, children }) {
  return (
    <div>
      <h4 className="t-label text-ink-soft flex items-center gap-1.5 mb-1.5">
        {Icon && <Icon className="w-3.5 h-3.5 text-brand-fg" aria-hidden="true" />}{title}
      </h4>
      {children}
    </div>
  );
}

// ── Status change form ───────────────────────────────────────────────────────
function StatusChangeModal({ student, options, onClose, onDone }) {
  const { t } = useI18n();
  const showToast = useToast().showToast;
  const [form, setForm] = useState({
    to_status: '', event_type: 'STATUS_CHANGE', effective_date: '',
    last_enrolled_semester: '', last_enrolled_academic_year: '',
    scheme: '', reason: '', reason_category: '', document_ref: '', remarks: '',
  });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const needsReview = ['Discontinued-Review Req','Readmission Requested'].includes(form.to_status);

  const submit = async () => {
    if (!form.to_status) { showToast({ type: 'error', message: t('lifecycle.pickStatus') }); return; }
    setBusy(true);
    try {
      const payload = Object.fromEntries(Object.entries(form).filter(([_, v]) => String(v).trim() !== ''));
      payload.last_enrolled_semester = payload.last_enrolled_semester ? Number(payload.last_enrolled_semester) : undefined;
      const r = await api.post(`/lifecycle/students/${encodeURIComponent(student.usn)}/status`, payload);
      showToast(r.data.deduplicated
        ? { type: 'info', message: t('lifecycle.dedupAs', { status: r.data.to_status }) }
        : { type: 'success', message: t('lifecycle.statusUpdated', { from: r.data.from_status, to: r.data.to_status }) });
      onDone();
    } catch (e) {
      showToast({ type: 'error', message: getUserMessage(e, t('lifecycle.errStatusUpdate')) });
    } finally { setBusy(false); }
  };

  return (
    <Modal title={t('lifecycle.statusChangeTitle', { name: student.name || student.usn })}
           subtitle={t('lifecycle.statusChangeSub', { status: student.current_status || 'Active' })}
           onClose={onClose} tone="blue">
      <div className="space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.newStatus')} <span className="text-err" aria-hidden="true">*</span></span>
            <select value={form.to_status} onChange={set('to_status')} aria-required="true"
                    className="input">
              <option value="">{t('lifecycle.selectOption')}</option>
              {options.statuses.filter(s => s !== student.current_status).map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.eventType')}</span>
            <select value={form.event_type} onChange={set('event_type')}
                    className="input">
              {options.event_types.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.effectiveDate')}</span>
            <input type="date" value={form.effective_date} onChange={set('effective_date')}
                   className="input" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.lastEnrolledSemester')}</span>
            <input type="number" min="1" max="8" value={form.last_enrolled_semester} onChange={set('last_enrolled_semester')}
                   className="input" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.academicYearField')}</span>
            <input value={form.last_enrolled_academic_year} onChange={set('last_enrolled_academic_year')}
                   className="input" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.schemeField')}</span>
            <input value={form.scheme} onChange={set('scheme')}
                   className="input" />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="field-label">{t('lifecycle.reasonOptional')}</span>
            <input value={form.reason} onChange={set('reason')}
                   placeholder={t('lifecycle.reasonPlaceholder')}
                   className="input" />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="field-label">{t('lifecycle.reasonCategoryField')}</span>
            <select value={form.reason_category} onChange={set('reason_category')}
                    className="input">
              <option value="">{t('lifecycle.autoFromReason')}</option>
              {(options.reason_categories || []).map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="field-label">{t('lifecycle.documentReference')}</span>
            <input value={form.document_ref} onChange={set('document_ref')}
                   placeholder={t('lifecycle.documentRefPlaceholder')}
                   className="input" />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="field-label">{t('lifecycle.remarks')}</span>
            <textarea value={form.remarks} onChange={set('remarks')} rows={2}
                      className="input" />
          </label>
        </div>
        {needsReview && (
          <div className="p-2 bg-warn-soft border border-warn/30 rounded text-warn t-support flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" /> {t('lifecycle.reviewNote')}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="btn btn-ghost">{t('common.cancel')}</button>
          <button onClick={submit} disabled={busy}
                  className="btn btn-accent">
            <PlusCircle className="w-3.5 h-3.5" aria-hidden="true" /> {busy ? t('common.saving') : t('lifecycle.saveStatusChange')}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ── Readmission request modal (advisory eligibility, never auto-approves) ─────
function ReadmitRequestModal({ student, onClose, onDone }) {
  const { t } = useI18n();
  const showToast = useToast().showToast;
  const [form, setForm] = useState({ requested_semester: '', request_date: '', scheme: '', remarks: '' });
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const payload = Object.fromEntries(Object.entries(form).filter(([_, v]) => String(v).trim() !== ''));
      if (payload.requested_semester) payload.requested_semester = Number(payload.requested_semester);
      const r = await api.post(`/lifecycle/students/${encodeURIComponent(student.usn)}/readmission/request`, payload);
      showToast({ type: 'success', message: t('lifecycle.requestRecorded', { outcome: r.data.eligibility.outcome_text }) });
      onDone();
    } catch (e) {
      showToast({ type: 'error', message: getUserMessage(e, t('lifecycle.errReadmit')) });
    } finally { setBusy(false); }
  };

  return (
    <Modal title={t('lifecycle.readmitTitle', { name: student.name || student.usn })}
           subtitle={t('lifecycle.readmitSub')}
           onClose={onClose} tone="blue">
      <div className="space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.requestedSemester')}</span>
            <input type="number" min="1" max="8" value={form.requested_semester}
                   onChange={e => setForm({ ...form, requested_semester: e.target.value })}
                   className="input" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.requestDate')}</span>
            <input type="date" value={form.request_date}
                   onChange={e => setForm({ ...form, request_date: e.target.value })}
                   className="input" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.scheme')}</span>
            <input value={form.scheme} onChange={e => setForm({ ...form, scheme: e.target.value })}
                   placeholder={t('lifecycle.schemePlaceholder')}
                   className="input" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.remarks')}</span>
            <input value={form.remarks} onChange={e => setForm({ ...form, remarks: e.target.value })}
                   className="input" />
          </label>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="btn btn-ghost">{t('common.cancel')}</button>
          <button onClick={submit} disabled={busy}
                  className="btn btn-accent">
            {busy ? t('common.saving') : t('lifecycle.recordRequest')}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ── Approve / reject modal — fetches eligibility live, then records decision ──
function DecisionModal({ student, onClose, onDone }) {
  const { t } = useI18n();
  const showToast = useToast().showToast;
  const [elig, setElig] = useState(null);
  const [form, setForm] = useState({
    decision: 'approve', approved_semester: '', approval_date: '',
    approval_ref: '', rejoin: false, rejoin_date: '', remarks: '',
  });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/lifecycle/eligibility/${encodeURIComponent(student.usn)}`)
      .then(r => setElig(r.data))
      .catch(() => setElig(null));
  }, [student.usn]);

  const submit = async () => {
    setBusy(true);
    try {
      const payload = { decision: form.decision };
      if (form.approved_semester) payload.approved_semester = Number(form.approved_semester);
      if (form.approval_date) payload.approval_date = form.approval_date;
      if (form.approval_ref) payload.approval_ref = form.approval_ref;
      if (form.rejoin) { payload.rejoin = true; if (form.rejoin_date) payload.rejoin_date = form.rejoin_date; }
      if (form.remarks) payload.remarks = form.remarks;
      const r = await api.post(`/lifecycle/students/${encodeURIComponent(student.usn)}/readmission/decision`, payload);
      showToast({ type: 'success', message: form.decision === 'approve'
        ? t('lifecycle.approvedToast', { status: r.data.to_status })
        : t('lifecycle.rejectedToast', { status: r.data.to_status }) });
      onDone();
    } catch (e) {
      showToast({ type: 'error', message: getUserMessage(e, t('lifecycle.errDecision')) });
    } finally { setBusy(false); }
  };

  return (
    <Modal title={t('lifecycle.decisionTitle', { name: student.name || student.usn })}
           subtitle={t('lifecycle.decisionSub')}
           onClose={onClose} tone={form.decision === 'reject' ? 'rose' : 'emerald'}>
      <div className="space-y-3">
        {elig && (
          <div className="p-3 sunken">
            <p className="t-label text-ink-mute mb-1 flex items-center gap-1">
              <ShieldCheck className="w-3 h-3" aria-hidden="true" /> {t('lifecycle.advisoryHeading')}
            </p>
            <p className="text-ink-soft">{elig.outcome_text}</p>
            {elig.concerns?.length > 0 && (
              <ul className="mt-2 space-y-1">
                {elig.concerns.map((c, i) => (
                  <li key={i} className="t-support text-ink-soft flex gap-1">
                    <AlertTriangle className="w-3 h-3 mt-0.5 text-warn shrink-0" aria-hidden="true" /> {c}
                  </li>
                ))}
              </ul>
            )}
            {elig.rules_applied?.length > 0 && (
              <p className="mt-2 t-support text-ink-mute">{t('lifecycle.verifiedRules')} {elig.rules_applied.map(r => r.rule_key).join(', ')}</p>
            )}
            <p className="mt-2 t-support text-ink-mute italic">
              {t('lifecycle.decisionNote')}
            </p>
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.decision')}</span>
            <select value={form.decision} onChange={e => setForm({ ...form, decision: e.target.value })}
                    className="input">
              <option value="approve">{t('lifecycle.approve')}</option>
              <option value="reject">{t('lifecycle.rejectOption')}</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.approvedSemester')}</span>
            <input type="number" min="1" max="8" value={form.approved_semester}
                   onChange={e => setForm({ ...form, approved_semester: e.target.value })}
                   className="input" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.approvalDate')}</span>
            <input type="date" value={form.approval_date}
                   onChange={e => setForm({ ...form, approval_date: e.target.value })}
                   className="input" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="field-label">{t('lifecycle.approvalReference')}</span>
            <input value={form.approval_ref} onChange={e => setForm({ ...form, approval_ref: e.target.value })}
                   placeholder={t('lifecycle.approvalRefPlaceholder')}
                   className="input" />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="field-label">{t('lifecycle.remarks')}</span>
            <textarea rows={2} value={form.remarks} onChange={e => setForm({ ...form, remarks: e.target.value })}
                      className="input" />
          </label>
          {form.decision === 'approve' && (
            <label className="flex items-center gap-2 sm:col-span-2 cursor-pointer">
              <input type="checkbox" checked={form.rejoin}
                     onChange={e => setForm({ ...form, rejoin: e.target.checked })}
                     className="rounded border-line-strong text-brand-fg focus:ring-ring" />
              <span className="text-ink-soft">{t('lifecycle.alsoRejoin')}</span>
            </label>
          )}
          {form.decision === 'approve' && form.rejoin && (
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className="field-label">{t('lifecycle.rejoinDate')}</span>
              <input type="date" value={form.rejoin_date}
                     onChange={e => setForm({ ...form, rejoin_date: e.target.value })}
                     className="input" />
            </label>
          )}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="btn btn-ghost">{t('common.cancel')}</button>
          <button onClick={submit} disabled={busy}
                  className={`btn ${form.decision === 'approve' ? 'btn-accent' : 'btn-danger'}`}>
            {form.decision === 'approve' ? <CheckCircle className="w-3.5 h-3.5" aria-hidden="true" /> : <XCircle className="w-3.5 h-3.5" aria-hidden="true" />}
            {busy ? t('common.saving') : (form.decision === 'approve' ? t('lifecycle.recordApproval') : t('lifecycle.recordRejection'))}
          </button>
        </div>
      </div>
    </Modal>
  );
}

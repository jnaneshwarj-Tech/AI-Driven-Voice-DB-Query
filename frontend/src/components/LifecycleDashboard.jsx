import { useState, useEffect, useMemo, useCallback } from 'react';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import { useToast } from './Toast';
import {
  Users, PlusCircle, RefreshCw, Search, History, CheckCircle, XCircle,
  AlertTriangle, ShieldCheck, Clock, FileText, ArrowRight, UserCheck,
  Sparkles, Download, Wand2,
} from 'lucide-react';

// ── Status → colour hints (mirrors the backend canonical list from /options) ──
const STATUS_COLORS = {
  'Active':                    'bg-emerald-50 text-emerald-700 border-emerald-200',
  'Temporarily Discontinued':  'bg-amber-50 text-amber-700 border-amber-200',
  'Discontinued-Review Req':   'bg-rose-50 text-rose-700 border-rose-200',
  'Dropout-College Recorded':  'bg-rose-50 text-rose-700 border-rose-200',
  'Readmission Requested':     'bg-sky-50 text-sky-700 border-sky-200',
  'Readmission Approved':      'bg-blue-50 text-blue-700 border-blue-200',
  'Rejoined-Active':           'bg-teal-50 text-teal-700 border-teal-200',
  'Graduated':                 'bg-violet-50 text-violet-700 border-violet-200',
  'Transferred':               'bg-slate-100 text-slate-700 border-slate-200',
  'Admission Cancelled':       'bg-zinc-100 text-zinc-700 border-zinc-200',
  'Other':                     'bg-slate-50 text-slate-700 border-slate-200',
};

const fmtDate = (v) => {
  if (!v) return '—';
  const s = String(v);
  if (s.length >= 10 && /^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
  return s;
};

function StatusPill({ status }) {
  const cls = STATUS_COLORS[status] || 'bg-slate-50 text-slate-700 border-slate-200';
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border ${cls}`}>
      {status || 'Active'}
    </span>
  );
}

// ── Small modal shell ─────────────────────────────────────────────────────────
function Modal({ title, subtitle, onClose, children, tone = 'blue' }) {
  const toneCls = { blue: 'border-blue-500', amber: 'border-amber-500', rose: 'border-rose-500', emerald: 'border-emerald-500' }[tone] || 'border-blue-500';
  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className={`bg-white dark:bg-slate-900 rounded-2xl border-t-4 ${toneCls} shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto`}
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between p-5 border-b border-slate-100 dark:border-slate-800">
          <div>
            <h3 className="text-base font-bold text-slate-800 dark:text-slate-100">{title}</h3>
            {subtitle && <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">×</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

const Empty = ({ icon: Icon, title, hint }) => (
  <div className="flex flex-col items-center justify-center py-16 text-slate-400 gap-2">
    {Icon && <div className="w-12 h-12 rounded-full bg-slate-50 dark:bg-slate-800 flex items-center justify-center"><Icon className="w-6 h-6" /></div>}
    <p className="text-sm font-bold">{title}</p>
    {hint && <p className="text-xs text-slate-500 max-w-md text-center">{hint}</p>}
  </div>
);

const Spinner = () => (
  <div className="flex items-center justify-center py-16 gap-3 text-slate-400">
    <div className="w-8 h-8 border-4 border-slate-200 border-t-blue-500 rounded-full animate-spin" />
    <p className="text-xs">Loading lifecycle records…</p>
  </div>
);

export default function LifecycleDashboard({ role = 'Staff' }) {
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
      const m = getUserMessage(e, 'Could not load lifecycle list.');
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
      showToast({ type: 'error', message: getUserMessage(e, 'Could not load student lifecycle history.') });
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
      showToast({ type: 'error', message: getUserMessage(e, 'Could not read the lifecycle command.') });
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
          ? 'Already recorded — no duplicate created.'
          : `Recorded: ${d.from_status} → ${d.to_status}. Undo token saved.`,
      });
      setNlPreview(null); setNlQuery('');
      await loadList();
    } catch (e) {
      showToast({ type: 'error', message: getUserMessage(e, 'Could not record the lifecycle status.') });
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
      showToast({ type: 'success', message: `Exported lifecycle register as ${fmt.toUpperCase()}.` });
    } catch (e) {
      let msg = 'Export failed.';
      try { msg = JSON.parse(await e.response?.data?.text?.())?.detail || msg; } catch { /* blob error */ }
      showToast({ type: 'error', message: msg });
    } finally { setExporting(''); }
  };

  const clearFilters = () => setFilters({
    status: '', scheme: '', admission_year: '', branch: '', last_semester: '',
    reason_category: '', date_from: '', date_to: '', search: '',
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
            <Users className="w-5 h-5 text-blue-600" /> Student Lifecycle Management
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Audited status history for discontinuation, dropout, readmission and rejoining.
            Eligibility is advisory only — the software never auto-approves. Academic staff must record the decision.
          </p>
        </div>
        <button onClick={loadList} disabled={loading}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 text-xs font-semibold rounded-lg hover:bg-slate-50 disabled:opacity-60">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {err && (
        <div className="flex items-center gap-2 p-3 bg-rose-50 border border-rose-200 text-rose-700 rounded-lg text-xs">
          <AlertTriangle className="w-4 h-4" /> {err}
        </div>
      )}

      {/* §1 Record by natural language */}
      <div className="bg-white/80 dark:bg-slate-900/60 backdrop-blur border border-blue-200/70 dark:border-blue-800/50 rounded-2xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <Wand2 className="w-4 h-4 text-blue-600" />
          <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">Record by natural language</h3>
        </div>
        <p className="text-[11px] text-slate-500 mb-2">
          Type a plain instruction (English, broken English, Kannada or mixed). The system reads the action,
          finds the student in MySQL and shows a confirmation — it saves <strong>only after you confirm</strong>,
          and never invents a record for an unknown USN.
        </p>
        <div className="flex flex-wrap gap-2 items-stretch">
          <textarea value={nlQuery} onChange={e => setNlQuery(e.target.value)} rows={2}
                    placeholder="e.g. USN 4HG23CS032 discontinued due to financial problems on 12-05-2025"
                    className="flex-1 min-w-[220px] px-2 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs" />
          <select value={nlLang} onChange={e => setNlLang(e.target.value)}
                  className="px-2 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs">
            <option value="english">English</option>
            <option value="kannada">ಕನ್ನಡ (Kannada)</option>
            <option value="mixed">Mixed</option>
          </select>
          <button onClick={() => runNlPreview()} disabled={nlLoading || !nlQuery.trim()}
                  className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700 disabled:opacity-60 inline-flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5" /> {nlLoading ? 'Reading…' : 'Detect & preview'}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white/80 dark:bg-slate-900/60 backdrop-blur border border-slate-200/70 dark:border-slate-800/60 rounded-2xl p-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        <label className="flex flex-col gap-1">
          <span className="text-slate-500 font-semibold uppercase tracking-wide text-[10px]">Status</span>
          <select value={filters.status} onChange={e => setFilters({ ...filters, status: e.target.value })}
                  className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-100">
            <option value="">Any</option>
            {options.statuses.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500 font-semibold uppercase tracking-wide text-[10px]">Reason Category</span>
          <select value={filters.reason_category} onChange={e => setFilters({ ...filters, reason_category: e.target.value })}
                  className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-100">
            <option value="">Any</option>
            {(options.reason_categories || []).map(rc => <option key={rc} value={rc}>{rc}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500 font-semibold uppercase tracking-wide text-[10px]">Scheme</span>
          <input value={filters.scheme} onChange={e => setFilters({ ...filters, scheme: e.target.value })}
                 placeholder="e.g. 2022 / 2025"
                 className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-100" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500 font-semibold uppercase tracking-wide text-[10px]">Admission Year</span>
          <input value={filters.admission_year} onChange={e => setFilters({ ...filters, admission_year: e.target.value })}
                 inputMode="numeric" placeholder="e.g. 2024"
                 className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-100" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500 font-semibold uppercase tracking-wide text-[10px]">Branch</span>
          <input value={filters.branch} onChange={e => setFilters({ ...filters, branch: e.target.value })}
                 placeholder="e.g. CS"
                 className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-100" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500 font-semibold uppercase tracking-wide text-[10px]">Last Semester</span>
          <input value={filters.last_semester} onChange={e => setFilters({ ...filters, last_semester: e.target.value })}
                 inputMode="numeric" placeholder="1-8"
                 className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-100" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500 font-semibold uppercase tracking-wide text-[10px]">Effective From</span>
          <input type="date" value={filters.date_from} onChange={e => setFilters({ ...filters, date_from: e.target.value })}
                 className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-100" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500 font-semibold uppercase tracking-wide text-[10px]">Effective To</span>
          <input type="date" value={filters.date_to} onChange={e => setFilters({ ...filters, date_to: e.target.value })}
                 className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-100" />
        </label>
        <label className="flex flex-col gap-1 col-span-2 md:col-span-4">
          <span className="text-slate-500 font-semibold uppercase tracking-wide text-[10px]">Search (USN / name / reason)</span>
          <input value={filters.search} onChange={e => setFilters({ ...filters, search: e.target.value })}
                 placeholder="type to filter the register"
                 className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-100" />
        </label>
        <div className="col-span-2 md:col-span-4 flex items-center justify-between flex-wrap gap-2">
          <p className="text-[11px] text-slate-500">
            Showing <strong>{rows.length}</strong> of <strong>{total}</strong> student(s). Reports refresh from live MySQL after every change.
          </p>
          <div className="flex items-center gap-2">
            <button onClick={clearFilters}
                    className="text-[11px] text-blue-600 hover:underline">Clear filters</button>
            {['csv', 'xlsx', 'pdf'].map(f => (
              <button key={f} onClick={() => doExport(f)} disabled={!!exporting || rows.length === 0}
                      className="flex items-center gap-1 px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 text-[11px] font-semibold hover:bg-slate-50 disabled:opacity-50">
                <Download className="w-3 h-3" /> {exporting === f ? '…' : f.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white/80 dark:bg-slate-900/60 backdrop-blur border border-slate-200/70 dark:border-slate-800/60 rounded-2xl overflow-hidden">
        {loading ? <Spinner /> : rows.length === 0 ? (
          <Empty icon={Search} title="No matching lifecycle records"
                 hint="Try relaxing a filter, or record a status change from the Actions column of a student row." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 dark:bg-slate-950/40 text-slate-500 uppercase text-[10px]">
                <tr>
                  <th onClick={() => setSort({ by: 'usn', dir: sort.by === 'usn' && sort.dir === 'asc' ? 'desc' : 'asc' })}
                      className="text-left px-4 py-2 cursor-pointer select-none">USN{sort.by === 'usn' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th>
                  <th onClick={() => setSort({ by: 'name', dir: sort.by === 'name' && sort.dir === 'asc' ? 'desc' : 'asc' })}
                      className="text-left px-4 py-2 cursor-pointer select-none">Name{sort.by === 'name' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th>
                  <th className="text-left px-4 py-2">Branch / Batch</th>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-left px-4 py-2">Last Sem</th>
                  <th className="text-left px-4 py-2">Reason</th>
                  <th className="text-left px-4 py-2">Category</th>
                  <th onClick={() => setSort({ by: 'effective_date', dir: sort.by === 'effective_date' && sort.dir === 'asc' ? 'desc' : 'asc' })}
                      className="text-left px-4 py-2 cursor-pointer select-none">Effective{sort.by === 'effective_date' ? (sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th>
                  <th className="text-left px-4 py-2">Latest Event</th>
                  <th className="text-right px-4 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.usn} className="border-t border-slate-100 dark:border-slate-800/60 hover:bg-slate-50/60 dark:hover:bg-slate-800/30">
                    <td className="px-4 py-2 font-mono text-slate-600 dark:text-slate-300">{r.usn}</td>
                    <td className="px-4 py-2 font-semibold text-slate-800 dark:text-slate-100">{r.name}</td>
                    <td className="px-4 py-2 text-slate-600 dark:text-slate-300">{r.branch || '—'} / {r.admission_year ?? '—'}</td>
                    <td className="px-4 py-2"><StatusPill status={r.current_status} /></td>
                    <td className="px-4 py-2 text-slate-600 dark:text-slate-300">{r.last_enrolled_semester ?? '—'}</td>
                    <td className="px-4 py-2 text-slate-500 max-w-[180px] truncate" title={r.reason || ''}>{r.reason || '—'}</td>
                    <td className="px-4 py-2"><span className="text-[10px] uppercase font-bold text-slate-500">{r.reason_category || '—'}</span></td>
                    <td className="px-4 py-2 text-slate-500">{fmtDate(r.effective_date)}</td>
                    <td className="px-4 py-2 text-slate-500">{r.latest_event_type || '—'}</td>
                    <td className="px-4 py-2 text-right whitespace-nowrap space-x-2">
                      <button onClick={() => openDetail(r.usn)}
                              className="text-[10px] px-2 py-1 rounded border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-1 inline-flex">
                        <History className="w-3 h-3" /> History
                      </button>
                      {isAdmin && (
                        <button onClick={() => setStatusTarget(r)}
                                className="text-[10px] px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-700 inline-flex items-center gap-1">
                          <ArrowRight className="w-3 h-3" /> Change status
                        </button>
                      )}
                      {isAdmin && ['Temporarily Discontinued','Discontinued-Review Req','Dropout-College Recorded'].includes(r.current_status) && (
                        <button onClick={() => setReadmitTarget(r)}
                                className="text-[10px] px-2 py-1 rounded bg-sky-500 text-white hover:bg-sky-600 inline-flex items-center gap-1">
                          <UserCheck className="w-3 h-3" /> Readmission request
                        </button>
                      )}
                      {isAdmin && r.current_status === 'Readmission Requested' && (
                        <button onClick={() => setDecisionTarget(r)}
                                className="text-[10px] px-2 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700 inline-flex items-center gap-1">
                          <ShieldCheck className="w-3 h-3" /> Approve / reject
                        </button>
                      )}
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
        <p className="text-[11px] text-slate-500 px-2">
          Staff role: view + history only. Status changes, readmission requests and decisions require Admin.
        </p>
      )}

      {/* Detail modal */}
      {detailUsn && (
        <Modal title={`Lifecycle · ${detailUsn}`}
               subtitle={detail ? `${detail.name || ''}` : 'Loading…'}
               onClose={() => setDetailUsn(null)}>
          {detailLoading ? <Spinner /> : !detail ? <Empty title="No data" /> : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                <Field label="Current Status"><StatusPill status={detail.current_status} /></Field>
                <Field label="Scheme">{detail.status?.scheme || '—'}</Field>
                <Field label="Last Enrolled Sem">{detail.status?.last_enrolled_semester ?? '—'}</Field>
                <Field label="Academic Year">{detail.status?.last_enrolled_academic_year || '—'}</Field>
                <Field label="Effective Date">{fmtDate(detail.status?.effective_date)}</Field>
                <Field label="Reason">{detail.status?.reason || '—'}</Field>
                <Field label="Document Ref">{detail.status?.document_ref || '—'}</Field>
                <Field label="Updated By">{detail.status?.updated_by || '—'}</Field>
              </div>

              <Section title="Status history (append-only, audited)" icon={History}>
                {detail.history?.length ? (
                  <ol className="space-y-2 text-[11px]">
                    {detail.history.map(ev => (
                      <li key={ev.id} className="border border-slate-100 dark:border-slate-800 rounded-lg p-2 flex flex-wrap gap-x-3 gap-y-1">
                        <span className="text-slate-400 font-mono">{fmtDate(ev.created_at)}</span>
                        <span className="font-bold text-slate-600 dark:text-slate-300">{ev.event_type}</span>
                        <span className="text-slate-500">{ev.from_status || '—'}</span>
                        <ArrowRight className="w-3 h-3 text-slate-400 inline" />
                        <StatusPill status={ev.to_status} />
                        {ev.reason && <span className="text-slate-500">· {ev.reason}</span>}
                        {ev.approval_ref && <span className="text-slate-500">· Ref {ev.approval_ref}</span>}
                        <span className="ml-auto text-slate-400">by {ev.actor_username || '—'}</span>
                      </li>
                    ))}
                  </ol>
                ) : <p className="text-[11px] text-slate-400">No status events recorded yet.</p>}
              </Section>

              <Section title="Readmission requests" icon={UserCheck}>
                {detail.readmission_requests?.length ? (
                  <table className="w-full text-[11px]">
                    <thead className="text-slate-500 uppercase text-[10px]"><tr>
                      <th className="text-left py-1">Requested Sem</th><th className="text-left py-1">Date</th>
                      <th className="text-left py-1">Outcome</th><th className="text-left py-1">Status</th>
                      <th className="text-left py-1">Approved Sem</th><th className="text-left py-1">Ref</th>
                    </tr></thead>
                    <tbody>
                      {detail.readmission_requests.map(q => (
                        <tr key={q.id} className="border-t border-slate-100 dark:border-slate-800">
                          <td className="py-1">{q.requested_semester ?? '—'}</td>
                          <td className="py-1">{fmtDate(q.request_date)}</td>
                          <td className="py-1"><code className="text-slate-500">{q.eligibility_outcome || '—'}</code></td>
                          <td className="py-1 font-semibold">{q.status}</td>
                          <td className="py-1">{q.approved_semester ?? '—'}</td>
                          <td className="py-1">{q.approval_ref || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : <p className="text-[11px] text-slate-400">No readmission requests recorded.</p>}
              </Section>

              {detail.identity_links?.length > 0 && (
                <Section title="Related USNs (controlled identity links)" icon={FileText}>
                  <ul className="text-[11px] space-y-1">
                    {detail.identity_links.map((lk, i) => (
                      <li key={i} className="flex gap-2">
                        <code className="text-indigo-500">{lk.relation_type}</code>
                        <span className="font-mono">{lk.related_usn}</span>
                        <span className="text-slate-500">· {lk.note || ''}</span>
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
  const action = preview?.action_required;
  const p = preview?.payload || {};

  if (action === 'select_student') {
    return (
      <Modal title="Which student?" subtitle={preview.message || 'Please select the correct USN.'}
             onClose={onClose} tone="amber">
        <ul className="space-y-2 text-xs">
          {(preview.suggestions || []).map(s => (
            <li key={s.usn}>
              <button onClick={() => onPick(s)}
                      className="w-full text-left px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 flex items-center justify-between">
                <span className="font-semibold text-slate-800 dark:text-slate-100">{s.name || s.usn}</span>
                <span className="font-mono text-slate-500">{s.usn}{s.branch ? ` · ${s.branch}` : ''}</span>
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
      <Modal title="No record created" subtitle={preview.message || 'Nothing to confirm.'}
             onClose={onClose} tone="rose">
        <p className="text-xs text-slate-600 dark:text-slate-300">
          Nothing was written to the database. Adjust the instruction and try again.
        </p>
      </Modal>
    );
  }

  return (
    <Modal title="Confirm lifecycle record"
           subtitle="Review before saving. This appends an audited event and never alters academic, fee or backlog data."
           onClose={onClose} tone="emerald">
      <div className="space-y-3 text-xs">
        <div className="grid grid-cols-2 gap-2">
          <Field label="Student">{p.name || '—'} <span className="font-mono text-slate-500">({p.usn})</span></Field>
          <Field label="New Status"><StatusPill status={p.to_status} /></Field>
          <Field label="Reason">{p.reason || '—'}</Field>
          <Field label="Reason Category">{p.reason_category || '—'}</Field>
          <Field label="Effective Date">{fmtDate(p.effective_date)}</Field>
          <Field label="Last Semester">{p.last_enrolled_semester ?? '—'}</Field>
        </div>
        <div className="p-2 bg-slate-50 dark:bg-slate-950/30 rounded border border-slate-100 dark:border-slate-800 text-[11px] text-slate-500">
          Original instruction: <span className="italic">"{p.original_query}"</span>
        </div>
        {!isAdmin && (
          <div className="p-2 bg-amber-50 border border-amber-200 rounded text-amber-800 text-[11px] flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5" /> Only an Admin may commit a lifecycle change. Preview shown; ask an administrator to confirm.
          </div>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose} className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700">Cancel</button>
          <button onClick={onConfirm} disabled={loading || !isAdmin}
                  className="px-3 py-1.5 text-xs rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-60 inline-flex items-center gap-1">
            <CheckCircle className="w-3.5 h-3.5" /> {loading ? 'Saving…' : 'Confirm & save'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

function Field({ label, children }) {
  return (
    <div className="p-2 rounded-lg bg-slate-50 dark:bg-slate-950/30 border border-slate-100 dark:border-slate-800">
      <p className="text-[9px] uppercase font-bold text-slate-400 tracking-wide">{label}</p>
      <div className="text-slate-700 dark:text-slate-100 mt-0.5">{children}</div>
    </div>
  );
}
function Section({ title, icon: Icon, children }) {
  return (
    <div>
      <h4 className="text-xs font-bold text-slate-600 dark:text-slate-300 flex items-center gap-1.5 mb-1.5">
        {Icon && <Icon className="w-3.5 h-3.5 text-blue-500" />}{title}
      </h4>
      {children}
    </div>
  );
}

// ── Status change form ───────────────────────────────────────────────────────
function StatusChangeModal({ student, options, onClose, onDone }) {
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
    if (!form.to_status) { showToast({ type: 'error', message: 'Pick a lifecycle status.' }); return; }
    setBusy(true);
    try {
      const payload = Object.fromEntries(Object.entries(form).filter(([_, v]) => String(v).trim() !== ''));
      payload.last_enrolled_semester = payload.last_enrolled_semester ? Number(payload.last_enrolled_semester) : undefined;
      const r = await api.post(`/lifecycle/students/${encodeURIComponent(student.usn)}/status`, payload);
      showToast(r.data.deduplicated
        ? { type: 'info', message: `Already recorded as ${r.data.to_status} — nothing new was stored.` }
        : { type: 'success', message: `Status updated: ${r.data.from_status} → ${r.data.to_status}. Undo token recorded.` });
      onDone();
    } catch (e) {
      showToast({ type: 'error', message: getUserMessage(e, 'Could not update lifecycle status.') });
    } finally { setBusy(false); }
  };

  return (
    <Modal title={`Change status · ${student.name || student.usn}`}
           subtitle={`Current: ${student.current_status || 'Active'} — history is append-only, academic/fee/backlog data is preserved.`}
           onClose={onClose} tone="blue">
      <div className="space-y-3 text-xs">
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">New Status *</span>
            <select value={form.to_status} onChange={set('to_status')}
                    className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
              <option value="">— select —</option>
              {options.statuses.filter(s => s !== student.current_status).map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Event Type</span>
            <select value={form.event_type} onChange={set('event_type')}
                    className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
              {options.event_types.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Effective Date</span>
            <input type="date" value={form.effective_date} onChange={set('effective_date')}
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Last Enrolled Semester</span>
            <input type="number" min="1" max="8" value={form.last_enrolled_semester} onChange={set('last_enrolled_semester')}
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Academic Year (e.g. 2024-25)</span>
            <input value={form.last_enrolled_academic_year} onChange={set('last_enrolled_academic_year')}
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Scheme (2022 / 2025)</span>
            <input value={form.scheme} onChange={set('scheme')}
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          <label className="flex flex-col gap-1 col-span-2">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Reason (optional — never fabricate)</span>
            <input value={form.reason} onChange={set('reason')}
                   placeholder="Personal / medical / financial — leave blank if unknown"
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          <label className="flex flex-col gap-1 col-span-2">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Reason Category (drives the register filter and reports)</span>
            <select value={form.reason_category} onChange={set('reason_category')}
                    className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
              <option value="">Auto — worked out from the reason</option>
              {(options.reason_categories || []).map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 col-span-2">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Document Reference</span>
            <input value={form.document_ref} onChange={set('document_ref')}
                   placeholder="e.g. DEAN/2026/007 or upload filename"
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          <label className="flex flex-col gap-1 col-span-2">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Remarks</span>
            <textarea value={form.remarks} onChange={set('remarks')} rows={2}
                      className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
        </div>
        {needsReview && (
          <div className="p-2 bg-amber-50 border border-amber-200 rounded text-amber-800 text-[11px] flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5" /> This status flags the student for academic-section review — it does NOT change marks, fees, or backlogs.
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700">Cancel</button>
          <button onClick={submit} disabled={busy}
                  className="px-3 py-1.5 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 inline-flex items-center gap-1">
            <PlusCircle className="w-3.5 h-3.5" /> {busy ? 'Saving…' : 'Save status change'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ── Readmission request modal (advisory eligibility, never auto-approves) ─────
function ReadmitRequestModal({ student, onClose, onDone }) {
  const showToast = useToast().showToast;
  const [form, setForm] = useState({ requested_semester: '', request_date: '', scheme: '', remarks: '' });
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const payload = Object.fromEntries(Object.entries(form).filter(([_, v]) => String(v).trim() !== ''));
      if (payload.requested_semester) payload.requested_semester = Number(payload.requested_semester);
      const r = await api.post(`/lifecycle/students/${encodeURIComponent(student.usn)}/readmission/request`, payload);
      showToast({ type: 'success', message: `Request recorded. Outcome: ${r.data.eligibility.outcome_text}` });
      onDone();
    } catch (e) {
      showToast({ type: 'error', message: getUserMessage(e, 'Could not create readmission request.') });
    } finally { setBusy(false); }
  };

  return (
    <Modal title={`Readmission request · ${student.name || student.usn}`}
           subtitle="The eligibility check is advisory. The software never self-approves — an Admin records the official decision."
           onClose={onClose} tone="blue">
      <div className="space-y-3 text-xs">
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Requested Semester</span>
            <input type="number" min="1" max="8" value={form.requested_semester}
                   onChange={e => setForm({ ...form, requested_semester: e.target.value })}
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Request Date</span>
            <input type="date" value={form.request_date}
                   onChange={e => setForm({ ...form, request_date: e.target.value })}
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Scheme</span>
            <input value={form.scheme} onChange={e => setForm({ ...form, scheme: e.target.value })}
                   placeholder="e.g. 2022 / 2025"
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Remarks</span>
            <input value={form.remarks} onChange={e => setForm({ ...form, remarks: e.target.value })}
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700">Cancel</button>
          <button onClick={submit} disabled={busy}
                  className="px-3 py-1.5 text-xs rounded-lg bg-sky-500 text-white hover:bg-sky-600 disabled:opacity-60">
            {busy ? 'Saving…' : 'Record request'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ── Approve / reject modal — fetches eligibility live, then records decision ──
function DecisionModal({ student, onClose, onDone }) {
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
      showToast({ type: 'success', message: `${form.decision === 'approve' ? 'Approved' : 'Rejected'}. New status: ${r.data.to_status}. Undo token recorded.` });
      onDone();
    } catch (e) {
      showToast({ type: 'error', message: getUserMessage(e, 'Could not record the decision.') });
    } finally { setBusy(false); }
  };

  return (
    <Modal title={`Readmission decision · ${student.name || student.usn}`}
           subtitle="Only a designated authority may record this decision. An eligibility warning is advisory and does not permanently block the student."
           onClose={onClose} tone={form.decision === 'reject' ? 'rose' : 'emerald'}>
      <div className="space-y-3 text-xs">
        {elig && (
          <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-950/30 border border-slate-200 dark:border-slate-800">
            <p className="text-[10px] uppercase text-slate-400 font-bold mb-1 flex items-center gap-1">
              <ShieldCheck className="w-3 h-3" /> Advisory eligibility snapshot
            </p>
            <p className="text-slate-700 dark:text-slate-200">{elig.outcome_text}</p>
            {elig.concerns?.length > 0 && (
              <ul className="mt-2 space-y-1">
                {elig.concerns.map((c, i) => (
                  <li key={i} className="text-[11px] text-slate-600 dark:text-slate-300 flex gap-1">
                    <AlertTriangle className="w-3 h-3 mt-0.5 text-amber-500 shrink-0" /> {c}
                  </li>
                ))}
              </ul>
            )}
            {elig.rules_applied?.length > 0 && (
              <p className="mt-2 text-[10px] text-slate-500">Verified rules applied: {elig.rules_applied.map(r => r.rule_key).join(', ')}</p>
            )}
            <p className="mt-2 text-[10px] text-slate-500 italic">
              The application records and supports decision-making; authorised staff and VTU remain responsible for official approvals.
            </p>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Decision</span>
            <select value={form.decision} onChange={e => setForm({ ...form, decision: e.target.value })}
                    className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800">
              <option value="approve">Approve</option>
              <option value="reject">Reject (route to review)</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Approved Semester</span>
            <input type="number" min="1" max="8" value={form.approved_semester}
                   onChange={e => setForm({ ...form, approved_semester: e.target.value })}
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Approval Date</span>
            <input type="date" value={form.approval_date}
                   onChange={e => setForm({ ...form, approval_date: e.target.value })}
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Approval Reference</span>
            <input value={form.approval_ref} onChange={e => setForm({ ...form, approval_ref: e.target.value })}
                   placeholder="e.g. REG/2026/007"
                   className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          <label className="flex flex-col gap-1 col-span-2">
            <span className="text-slate-500 font-semibold uppercase text-[10px]">Remarks</span>
            <textarea rows={2} value={form.remarks} onChange={e => setForm({ ...form, remarks: e.target.value })}
                      className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
          </label>
          {form.decision === 'approve' && (
            <label className="flex items-center gap-2 col-span-2">
              <input type="checkbox" checked={form.rejoin}
                     onChange={e => setForm({ ...form, rejoin: e.target.checked })}
                     className="rounded border-slate-300" />
              <span className="text-slate-700 dark:text-slate-200">Also record actual rejoining / enrolment (mark Rejoined-Active)</span>
            </label>
          )}
          {form.decision === 'approve' && form.rejoin && (
            <label className="flex flex-col gap-1 col-span-2">
              <span className="text-slate-500 font-semibold uppercase text-[10px]">Rejoin Date</span>
              <input type="date" value={form.rejoin_date}
                     onChange={e => setForm({ ...form, rejoin_date: e.target.value })}
                     className="px-2 py-1.5 rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800" />
            </label>
          )}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700">Cancel</button>
          <button onClick={submit} disabled={busy}
                  className={`px-3 py-1.5 text-xs rounded-lg text-white disabled:opacity-60 inline-flex items-center gap-1 ${form.decision === 'approve' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-rose-600 hover:bg-rose-700'}`}>
            {form.decision === 'approve' ? <CheckCircle className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
            {busy ? 'Saving…' : (form.decision === 'approve' ? 'Record approval' : 'Record rejection')}
          </button>
        </div>
      </div>
    </Modal>
  );
}

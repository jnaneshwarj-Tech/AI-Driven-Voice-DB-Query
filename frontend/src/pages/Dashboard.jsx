import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import FileExplorer from '../components/FileExplorer';
import GpaTable from '../components/GpaTable';
import ResultChart from '../components/ResultChart';
import AnalyticsDashboard from '../components/AnalyticsDashboard';
import ValidationDashboard from '../components/ValidationDashboard';
import SuggestionPanel from '../components/SuggestionPanel';
import ReportHeader from '../components/ReportHeader';
import PrintReport from '../components/PrintReport';
import { useToast } from '../components/Toast';
import OperationResultModal from '../components/OperationResultModal';
import ActivityDashboard from '../components/ActivityDashboard';
import BackupRestore from '../components/BackupRestore';
import LifecycleDashboard from '../components/LifecycleDashboard';
import CombinedStudentView from '../components/CombinedStudentView';
import ReportModal from '../components/ReportModal';
import LanguageSelector from '../components/LanguageSelector';
import ThemeModeToggle from '../components/ThemeModeToggle';
import LanguageModeToggle from '../components/LanguageModeToggle';
import { useI18n } from '../context/LanguageContext';
import { getPlaceholderText, getExampleQueries } from '../utils/kannadaTransliteration';
import { DeshKannadaProcessor } from '../utils/simpleKannadaInput';
import {
  LogOut, History, Database, Mic, Send, AlertTriangle,
  Download, FileText, Table as TableIcon,
  CheckCircle, BarChart2, ShieldAlert, Printer, Search, User, GraduationCap,
  PlusCircle, Trash2, Clock, ChevronRight, RotateCcw, Activity,
  ChevronDown, ChevronUp,
  Zap, RefreshCw, Moon, Sun, Bell, HardDrive, Languages, MapPin, Upload, Menu, X,
  PanelLeftClose, PanelLeftOpen
} from 'lucide-react';

// ── Helpers ───────────────────────────────────────────────────────────────────
function getAllKeys(data) {
  const keys = new Set();
  for (let i = 0; i < Math.min(5, data.length); i++)
    Object.keys(data[i]).forEach(k => keys.add(k.toLowerCase()));
  return Array.from(keys);
}

function isGpaData(data) {
  if (!data?.length) return false;
  const keys = getAllKeys(data);
  return keys.includes('sgpa') || keys.includes('cgpa') || keys.includes('semester');
}

function flattenDoc(obj, prefix = '') {
  const flat = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v === null || v === undefined) flat[key] = '—';
    else if (Array.isArray(v)) flat[key] = v.length ? v.join(', ') : '—';
    else if (typeof v === 'object') Object.assign(flat, flattenDoc(v, key));
    else flat[key] = v;
  }
  return flat;
}

// Detect chart trigger words
function shouldShowChart(query) {
  return /\b(top|compare|trend|chart|graph|bar|pie|line|rank|best|worst|distribution)\b/i.test(query);
}

const QUERY_FIELD_LABELS = {
  student_type: 'Student type', branch: 'Branch', current_sem: 'Semester',
  blood_group: 'Blood group', rural_status: 'Residence',
  emergency_contact_number: 'Emergency contact', cgpa: 'CGPA', sgpa: 'SGPA',
  father_name: "Father's name", mother_name: "Mother's name", age: 'Age',
  gender: 'Gender', location: 'Location', status: 'Status', phone: 'Phone',
  address: 'Address', dob: 'Date of birth', year_of_joining: 'Year of joining',
};

function describeCondition(condition) {
  const label = QUERY_FIELD_LABELS[condition.field] || condition.field;
  const value = Array.isArray(condition.value) ? condition.value.join(', ') : condition.value;
  const operators = {
    MISSING: 'is missing', PRESENT: 'is present', CONTAINS: 'contains',
    IN: 'is', NOT_IN: 'is not', GREATER_THAN: '>', GREATER_EQUAL: '>=',
    LESS_THAN: '<', LESS_EQUAL: '<=', BETWEEN: 'between', NOT_EQUALS: 'is not',
  };
  const operator = operators[condition.operator] || '=';
  if (condition.operator === 'MISSING' || condition.operator === 'PRESENT') return `${label} ${operator}`;
  return `${label} ${operator} ${maskSensitive(String(value))}`;
}

// ── Debug output masking: never leak PII in the query-details panel ───────────
function maskSensitive(value) {
  if (value == null) return value;
  return String(value)
    .replace(/\b[\w.+-]+@[\w-]+\.[\w.-]+\b/g, (m) => m[0] + '***@***')
    .replace(/\b\d{12}\b/g, (m) => `${m.slice(0, 2)}**********`)
    .replace(/\b\d{10}\b/g, (m) => `${m.slice(0, 2)}********`);
}

function maskDebugParameters(params) {
  if (params == null) return params;
  if (Array.isArray(params)) return params.map(maskDebugParameters);
  if (typeof params === 'object') {
    return Object.fromEntries(Object.entries(params).map(([k, v]) => [k, maskDebugParameters(v)]));
  }
  if (typeof params === 'string') return maskSensitive(params);
  return params;
}

// ── Highlight matching letters in suggestion names ────────────────────────────
function HighlightMatch({ text, query }) {
  if (!query || !text) return <span>{text}</span>;
  // Try to find the query (or any token of it) in the text
  const q = query.toLowerCase().trim();
  const idx = text.toLowerCase().indexOf(q);
  if (idx !== -1 && q.length >= 2) {
    return (
      <span>
        {text.slice(0, idx)}
        <mark className="bg-accent-soft text-accent-ink rounded px-0.5 font-bold not-italic">
          {text.slice(idx, idx + q.length)}
        </mark>
        {text.slice(idx + q.length)}
      </span>
    );
  }
  // Try token-level highlight
  const tokens = q.split(/\s+/).filter(t => t.length >= 2);
  if (tokens.length > 0) {
    let result = text;
    let parts = [{ text, highlighted: false }];
    for (const token of tokens) {
      const newParts = [];
      for (const part of parts) {
        if (part.highlighted) { newParts.push(part); continue; }
        const i = part.text.toLowerCase().indexOf(token);
        if (i !== -1) {
          if (i > 0) newParts.push({ text: part.text.slice(0, i), highlighted: false });
          newParts.push({ text: part.text.slice(i, i + token.length), highlighted: true });
          if (i + token.length < part.text.length)
            newParts.push({ text: part.text.slice(i + token.length), highlighted: false });
        } else {
          newParts.push(part);
        }
      }
      parts = newParts;
    }
    return (
      <span>
        {parts.map((p, i) =>
          p.highlighted
            ? <mark key={i} className="bg-accent-soft text-accent-ink rounded px-0.5 font-bold not-italic">{p.text}</mark>
            : <span key={i}>{p.text}</span>
        )}
      </span>
    );
  }
  return <span>{text}</span>;
}

// Match type badge colors
const MATCH_BADGE = {
  exact:    { label: 'EXACT',    cls: 'bg-ok-soft text-ok' },
  prefix:   { label: 'PREFIX',   cls: 'bg-info-soft text-info' },
  fuzzy:    { label: 'FUZZY',    cls: 'bg-warn-soft text-warn' },
  phonetic: { label: 'PHONETIC', cls: 'bg-brand/10 text-brand-fg' },
};

// ── Generic Table ─────────────────────────────────────────────────────────────
export const rowSelectionKey = (r, i) => String(r.usn || r.name || `row-${i}`);

function GenericTable({ data, responseLanguage = 'english', onViewRows, selection, onToggleRow, onToggleAll }) {
  const { t } = useI18n();
  const [search, setSearch] = useState('');
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState('asc');
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;
  const kannadaHeaders = {
    usn: 'ವಿದ್ಯಾರ್ಥಿ ಸಂಖ್ಯೆ', name: 'ಹೆಸರು', current_sem: 'ಪ್ರಸ್ತುತ ಸೆಮಿಸ್ಟರ್',
    status: 'ಸ್ಥಿತಿ', father_name: 'ತಂದೆಯ ಹೆಸರು', mother_name: 'ತಾಯಿಯ ಹೆಸರು',
    blood_group: 'ರಕ್ತದ ಗುಂಪು', gender: 'ಲಿಂಗ', religion: 'ಧರ್ಮ', category: 'ವರ್ಗ',
    phone: 'ದೂರವಾಣಿ', email: 'ಇಮೇಲ್', address: 'ವಿಳಾಸ', branch: 'ಶಾಖೆ',
    semester: 'ಸೆಮಿಸ್ಟರ್', sgpa: 'SGPA', cgpa: 'CGPA', year: 'ವರ್ಷ',
  };

  if (!data?.length) return null;
  const flatRows = data.map(r => flattenDoc(r));
  let headers = [...new Set(flatRows.flatMap(r => Object.keys(r)))].filter(h =>
    h !== 'estimated_semester' &&
    flatRows.some(r => r[h] !== null && r[h] !== undefined && r[h] !== '—' && r[h] !== '')
  );

  let filtered = flatRows.filter(row =>
    !search || Object.values(row).some(v => String(v).toLowerCase().includes(search.toLowerCase()))
  );

  if (sortCol) {
    filtered = [...filtered].sort((a, b) => {
      const av = a[sortCol] ?? '', bv = b[sortCol] ?? '';
      const n = parseFloat(av), m = parseFloat(bv);
      const cmp = !isNaN(n) && !isNaN(m) ? n - m : String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const toggleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('asc'); }
    setPage(1);
  };

  // Publish the *displayed* rows (current search filter + sorting + page) so
  // Generate Report can scope to page / selected / all matching records.
  useEffect(() => {
    onViewRows?.({ pageRows: paged, filteredRows: filtered });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, search, sortCol, sortDir, page]);

  const selectable = !!onToggleRow;
  const pageKeys = paged.map((r, i) => rowSelectionKey(r, (page - 1) * PAGE_SIZE + i));
  const allPageChecked = pageKeys.length > 0 && pageKeys.every(k => selection?.[k]);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <label className="sr-only" htmlFor="generic-table-search">{t('table.searchLabel')}</label>
        <input
          id="generic-table-search"
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1); }}
          placeholder={t('table.search')}
          className="input flex-1 min-w-[10rem] max-w-md"
        />
        <span className="t-support text-ink-mute tabular-nums flex-shrink-0">{t('table.rows', { n: filtered.length })}</span>
      </div>
      <div className="table-wrap">
        <div className="table-scroll">
          <table className="w-full">
            <thead>
              <tr>
                {selectable && (
                  <th scope="col" className="th w-10 text-center">
                    <input type="checkbox" checked={allPageChecked}
                      onChange={e => onToggleAll(pageKeys, paged, e.target.checked)}
                      className="rounded border-line-strong accent-brand"
                      aria-label={t('table.selectAll')} title={t('table.selectAll')} />
                  </th>
                )}
                {headers.map(h => (
                  <th
                    key={h}
                    scope="col"
                    onClick={() => toggleSort(h)}
                    tabIndex={0}
                    role="columnheader"
                    aria-sort={sortCol === h ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleSort(h); }
                    }}
                    className="th cursor-pointer select-none hover:bg-line/70"
                    title={t('table.sortHint')}
                  >
                    {(responseLanguage === 'kannada' ? kannadaHeaders[h] : null) || h.replace(/_/g, ' ')}
                    <span className="ml-1 text-accent-ink" aria-hidden="true">
                      {sortCol === h ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            {/* Remounting the body on page/sort change replays the row cascade,
                so a reorder reads as a transition instead of an instant
                reshuffle. Rows are stateless (selection is prop-driven), so
                this is safe. */}
            <tbody key={`${page}|${sortCol}|${sortDir}`} className="rows-in">
              {paged.map((row, i) => {
                const key = rowSelectionKey(row, (page - 1) * PAGE_SIZE + i);
                return (
                <tr key={key} className={`tr-hover ${selection?.[key] ? 'bg-brand/[0.06]' : ''}`}>
                  {selectable && (
                    <td className="td text-center">
                      <input type="checkbox" checked={!!selection?.[key]}
                        onChange={() => onToggleRow(key, row)}
                        className="rounded border-line-strong accent-brand"
                        aria-label={t('table.selectRow', { key })} />
                    </td>
                  )}
                  {headers.map(h => (
                    <td key={h} className="td">
                      {row[h] !== null && row[h] !== undefined ? String(row[h]) : <span className="text-ink-faint">—</span>}
                    </td>
                  ))}
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      {totalPages > 1 && (
        <div className="flex flex-wrap items-center justify-center gap-2 mt-3">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
            className="btn btn-sm btn-ghost">{t('table.prev')}</button>
          <span className="t-support text-ink-mute tabular-nums">{t('table.pageOf', { page, total: totalPages })}</span>
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            className="btn btn-sm btn-ghost">{t('table.next')}</button>
        </div>
      )}
    </div>
  );
}

// ── Restore Panel ─────────────────────────────────────────────────────────────
function RestorePanel({ showToast, onRestored }) {
  const [deleted, setDeleted] = useState([]);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get('/undo/deleted');
      setDeleted(res.data || []);
    } catch {
      setDeleted([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleRestore = async (record) => {
    setRestoring(record.restore_token);
    try {
      await api.post(`/undo/restore/${record.restore_token}`);
      showToast({ type: 'success', message: `${record.student_name || record.usn} restored successfully!` });
      onRestored?.();
      load();
    } catch (e) {
      showToast({ type: 'error', message: getUserMessage(e, 'Restore failed.') });
    } finally {
      setRestoring(null);
    }
  };

  if (loading) return (
    <div role="status" aria-live="polite" className="flex items-center justify-center py-16 text-ink-mute gap-3">
      <div className="no-transition w-5 h-5 border-2 border-line border-t-brand rounded-full animate-spin" />
      <span className="t-body">{t('undo.loading')}</span>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="t-card text-ink">{t('undo.title')}</h2>
          <p className="t-support text-ink-mute mt-0.5">{t('undo.subtitle')}</p>
        </div>
        <button onClick={load} className="btn btn-sm btn-ghost flex-shrink-0" aria-label={t('undo.refresh')} title={t('undo.refresh')}>
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {deleted.length === 0 ? (
        <div className="card empty-state">
          <div className="w-12 h-12 rounded-full bg-ok-soft flex items-center justify-center">
            <CheckCircle className="w-6 h-6 text-ok" />
          </div>
          <p className="t-card text-ink">{t('undo.emptyTitle')}</p>
          <p className="t-support">{t('undo.emptyBody')}</p>
        </div>
      ) : (
        <div className="space-y-3 stagger">
          {deleted.map((rec) => {
            const isRestored = rec.restored === 1;
            const isRestoring = restoring === rec.restore_token;
            const secondsLeft = rec.undo_seconds_left || 0;
            const expired = secondsLeft <= 0;

            return (
              <div key={rec.id}
                className={`card p-4 flex items-center gap-4 flex-wrap
                  ${isRestored ? 'opacity-60' : expired ? 'opacity-70' : 'border-err/30'}`}
              >
                {/* Avatar */}
                <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm flex-shrink-0
                  ${isRestored ? 'bg-ok-soft text-ok' : 'bg-err-soft text-err'}`}>
                  {(rec.student_name || rec.usn || '?').charAt(0).toUpperCase()}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-[12rem]">
                  <p className="t-body font-semibold text-ink t-truncate" title={rec.student_name || ''}>{rec.student_name || '—'}</p>
                  <p className="t-support text-ink-mute font-mono t-truncate" title={rec.usn || ''}>{rec.usn}</p>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-[12px] text-ink-mute">
                    <span>{t('undo.deletedBy')} <span className="font-medium text-ink-soft">{rec.deleted_by}</span></span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date(rec.deleted_at).toLocaleTimeString()}
                    </span>
                  </div>
                  {/* Countdown */}
                  {!isRestored && !expired && (
                    <div
                      className="mt-2 h-1 bg-sunken rounded-full w-32 overflow-hidden"
                      role="progressbar"
                      aria-label={t('undo.window')}
                      aria-valuenow={secondsLeft}
                    >
                      <div
                        className="h-1 bg-warn rounded-full transition-all duration-1000"
                        style={{ width: `${Math.min(100, (secondsLeft / 30) * 100)}%` }}
                      />
                    </div>
                  )}
                </div>

                {/* Action */}
                <div className="flex-shrink-0">
                  {isRestored ? (
                    <span className="flex items-center gap-1.5 t-support text-ok font-semibold">
                      <CheckCircle className="w-4 h-4" /> {t('undo.restored')}
                    </span>
                  ) : expired ? (
                    <span className="t-support text-ink-mute">{t('undo.expired')}</span>
                  ) : (
                    <button
                      onClick={() => handleRestore(rec)}
                      disabled={isRestoring}
                      className="btn btn-sm btn-primary"
                    >
                      <RotateCcw className={`w-3.5 h-3.5 ${isRestoring ? 'animate-spin' : ''}`} />
                      {isRestoring ? t('undo.restoring') : t('undo.restore')}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function Dashboard() {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { t } = useI18n();
  const [navOpen, setNavOpen] = useState(false);
  // Desktop rail: the sidebar can collapse to icons. Local-only preference —
  // it changes nothing about which screens and actions each role can reach.
  const [navCollapsed, setNavCollapsed] = useState(() => localStorage.getItem('navCollapsed') === '1');
  useEffect(() => { localStorage.setItem('navCollapsed', navCollapsed ? '1' : '0'); }, [navCollapsed]);
  const [hasCampusPhoto, setHasCampusPhoto] = useState(false);
  const [role]     = useState(() => localStorage.getItem('role') || '');
  const [username] = useState(() => localStorage.getItem('username') || '');
  const [query, setQuery]           = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isLoading, setIsLoading]   = useState(false);
  const [queryDebugOpen, setQueryDebugOpen] = useState(false);
  const [queryComplete, setQueryComplete] = useState(false);
  const [results, setResults]       = useState(null);
  const [error, setError]           = useState('');
  const [suggestion, setSuggestion] = useState(null);
  const [noMatchMsg, setNoMatchMsg] = useState('');
  const [history, setHistory]       = useState([]);
  const [recentActivity, setRecentActivity] = useState({ additions: [], deletions: [] });
  const [confirmModal, setConfirmModal] = useState({ isOpen: false, data: null });
  const [secondConfirm, setSecondConfirm] = useState(false);
  const [uploadNotice, setUploadNotice] = useState(null);
  const [showHeader, setShowHeader] = useState(true);
  const [activeTab, setActiveTab]   = useState('query');
  const [liveSuggestions, setLiveSuggestions] = useState([]);
  const [showLiveDropdown, setShowLiveDropdown] = useState(false);
  const [activeSuggestion, setActiveSuggestion] = useState(-1);
  const [liveSearchTerm, setLiveSearchTerm] = useState('');
  const [opResult, setOpResult]     = useState(null);  // OperationResultModal data
  const [filesVersion, setFilesVersion] = useState(0); // bump to re-read the file list after an undo
  // ── Generate Report (category-scoped, from displayed dashboard results) ──
  const [reportOpen, setReportOpen] = useState(false);
  const [tableRowsView, setTableRowsView] = useState(null); // {pageRows, filteredRows}
  const [selectedRows, setSelectedRows] = useState({});     // key -> row
  const [kannadaSuggestions, setKannadaSuggestions] = useState([]);  // Desh Kannada-style suggestions
  
  // ── Language State ────────────────────────────────────────────────────────
  const [selectedLanguage, setSelectedLanguage] = useState(() => {
    // Restore from localStorage or default to English
    return localStorage.getItem('queryLanguage') || 'english';
  });
  const [voiceLanguage, setVoiceLanguage] = useState(() => {
    return localStorage.getItem('voiceLanguage') || 'en-US';
  });
  
  const recRef = useRef(null);
  const printRef = useRef(null);
  const dropdownRef = useRef(null);
  const selectionLocked = useRef(false);
  const confirmedEntity = useRef(null);
  const kannadaProcessor = useRef(null);
  const textareaRef = useRef(null);
  const searchRequestRef = useRef({ id: 0, controller: null, query: null });
  const queryCompleteTimerRef = useRef(null);

  useEffect(() => {
    if (!localStorage.getItem('token')) {
      navigate('/login');
      return;
    }
    fetchHistory();
  }, []);

  // §6 — the campus photograph is an operator-supplied asset
  // (frontend/public/college-photo.jpg). It is probed before use so a missing
  // file degrades to the CSS treatment instead of a broken background.
  useEffect(() => {
    const img = new Image();
    img.onload = () => setHasCampusPhoto(true);
    img.onerror = () => setHasCampusPhoto(false);
    img.src = '/college-photo.jpg';
    return () => {
      img.onload = null;
      img.onerror = null;
    };
  }, []);

  // The mobile drawer is a presentation layer: Escape dismisses it.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') setNavOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const fetchHistory = async () => {
    try {
      const r = await api.get('/query/history?limit=10'); 
      setHistory(r.data); 
    } catch {
      setHistory([]);
    }
    try {
      const act = await api.get('/query/recent_activity');
      setRecentActivity({ additions: [], deletions: [], recent_operations: [], ...act.data });
    } catch {
      // Keep the last persisted activity view visible if a refresh fails.
    }
  };

  // ── Live Suggestions Logic ──────────────────────────────────────────────────
  useEffect(() => {
    // If a suggestion was just selected, skip this one cycle and release the lock
    if (selectionLocked.current) {
      selectionLocked.current = false;
      return;
    }

    const term = query.trim();

    // If an entity is confirmed and the query still contains that confirmed name,
    // the user hasn't edited it yet — keep suggestions locked
    if (confirmedEntity.current) {
      const entityName = confirmedEntity.current.name.toLowerCase();
      if (term.toLowerCase().includes(entityName)) {
        setShowLiveDropdown(false);
        setLiveSuggestions([]);
        return;
      }
      // User edited the query and removed the confirmed name — release the lock
      confirmedEntity.current = null;
    }

    // Extract the last meaningful word being typed
    // e.g. "show marks of manja" → search term is "manja"
    const words = term.split(/\s+/);
    const lastWord = words[words.length - 1];
    const KEYWORDS = new Set(['show','give','me','display','list','get','find','fetch',
      'search','all','the','of','for','in','from','with','and','or','by','student',
      'students','marks','mark','gpa','cgpa','sgpa','details','data','record','records',
      'semester','sem','result','results','top','best','highest','lowest']);
    const searchTerm = (lastWord.length >= 2 && !KEYWORDS.has(lastWord.toLowerCase()))
      ? lastWord
      : term;

    if (searchTerm.length < 2) {
      setLiveSuggestions([]);
      setShowLiveDropdown(false);
      setActiveSuggestion(-1);
      return;
    }

    // Debounce: 200ms for short inputs, 300ms for longer
    const delay = searchTerm.length <= 3 ? 200 : 300;

    let alive = true;
    const timer = setTimeout(async () => {
      try {
        const res = await api.get(`/query/suggest?q=${encodeURIComponent(searchTerm)}`);
        // A response that lands after the query was submitted or rewritten must
        // not open a panel over results it no longer describes.
        if (!alive) return;
        const suggestions = res.data || [];
        const open = suggestions.length > 0 && !selectionLocked.current;
        setLiveSuggestions(suggestions);
        setLiveSearchTerm(searchTerm);
        setActiveSuggestion(-1);
        setShowLiveDropdown(open);
        if (open) {
          setNoMatchMsg('');
          setError('');
        }
      } catch (err) {
        console.error('Suggestion fetch failed', err);
      }
    }, delay);

    return () => { alive = false; clearTimeout(timer); };
  }, [query]);

  // ── Click-outside: close dropdown when clicking outside the query box ────────
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        // Only close if click is outside the entire query input area
        const queryBox = dropdownRef.current.closest('.relative');
        if (!queryBox || !queryBox.contains(e.target)) {
          setShowLiveDropdown(false);
          setActiveSuggestion(-1);
        }
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = () => {
    localStorage.clear(); navigate('/login');
  };

  // ── Language Handling ─────────────────────────────────────────────────────
  const handleLanguageChange = (lang) => {
    setSelectedLanguage(lang);
    localStorage.setItem('queryLanguage', lang);
    
    // Update voice language accordingly
    const voiceLangMap = {
      'english': 'en-US',
      'kannada': 'kn-IN',
      'mixed': 'kn-IN',
    };
    const newVoiceLang = voiceLangMap[lang] || 'en-US';
    setVoiceLanguage(newVoiceLang);
    localStorage.setItem('voiceLanguage', newVoiceLang);
    
    // Initialize Desh Kannada-style processor when Kannada mode selected
    if (lang === 'kannada' && !kannadaProcessor.current) {
      kannadaProcessor.current = new DeshKannadaProcessor(
        textareaRef,
        setQuery,
        setKannadaSuggestions
      );
    } else if (lang !== 'kannada') {
      if (kannadaProcessor.current) {
        kannadaProcessor.current.cleanup();
        kannadaProcessor.current = null;
      }
      setKannadaSuggestions([]);
    }
  };

  const handleQueryChange = (e) => {
    const value = typeof e === 'string' ? e : e.target.value;
    const cursorPos = typeof e === 'string' ? value.length : e.target.selectionStart;
    
    // Update query immediately
    setQuery(value);
    
    // If Kannada mode, process for suggestions
    if (selectedLanguage === 'kannada' && kannadaProcessor.current && textareaRef.current) {
      kannadaProcessor.current.handleInput(value, cursorPos);
    }
    
    // Clear errors
    if (error) setError('');
    if (noMatchMsg) setNoMatchMsg('');
  };
  
  const handleKeyDown = (e) => {
    // Handle space in Kannada mode
    if (e.key === ' ' && selectedLanguage === 'kannada' && kannadaProcessor.current) {
      e.preventDefault();
      const result = kannadaProcessor.current.handleSpace(query, e.target.selectionStart);
      setQuery(result.text);
      // Set cursor position
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.selectionStart = result.cursorPos;
          textareaRef.current.selectionEnd = result.cursorPos;
        }
      }, 0);
      return;
    }
    
    // Handle arrow keys for Kannada suggestions
    if (kannadaSuggestions.length > 0 && selectedLanguage === 'kannada') {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveSuggestion(i => (i + 1) % kannadaSuggestions.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveSuggestion(i => i <= 0 ? kannadaSuggestions.length - 1 : i - 1);
        return;
      }
      if (e.key === 'Enter' && activeSuggestion >= 0) {
        e.preventDefault();
        applySuggestion(activeSuggestion);
        return;
      }
    }
  };
  
  const applySuggestion = (index) => {
    if (!kannadaProcessor.current || index < 0 || index >= kannadaSuggestions.length) return;
    
    const result = kannadaProcessor.current.applySuggestion(
      query,
      textareaRef.current.selectionStart,
      kannadaSuggestions[index]
    );
    
    setQuery(result.text);
    setKannadaSuggestions([]);
    setActiveSuggestion(-1);
    
    // Set cursor position
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.selectionStart = result.cursorPos;
        textareaRef.current.selectionEnd = result.cursorPos;
      }
    }, 0);
  };
  
  // Cleanup on unmount
  useEffect(() => {
    return () => {
      searchRequestRef.current.controller?.abort();
      clearTimeout(queryCompleteTimerRef.current);
      if (kannadaProcessor.current) {
        kannadaProcessor.current.cleanup();
      }
    };
  }, []);

  const handleVoiceLanguageChange = (lang) => {
    setVoiceLanguage(lang);
    localStorage.setItem('voiceLanguage', lang);
  };


  // ── Voice input ─────────────────────────────────────────────────────────────
  const toggleListen = () => {
    if (isListening) { recRef.current?.stop(); setIsListening(false); return; }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { setError('Speech recognition not supported in this browser.'); return; }
    const rec = new SR();
    recRef.current = rec;
    rec.continuous = false; rec.interimResults = false; 
    rec.lang = voiceLanguage; // Use selected voice language
    rec.onstart  = () => setIsListening(true);
    rec.onresult = (e) => { setQuery(e.results[0][0].transcript); setIsListening(false); };
    rec.onerror  = (e) => { 
      setIsListening(false); 
      if (e.error === 'not-allowed') {
        setError('Microphone permission denied. Please allow microphone access.');
      } else {
        setError('Voice input failed. Please try again.');
      }
    };
    rec.onend    = () => setIsListening(false);
    rec.start();
  };

  // ── Generate Report scope helpers ───────────────────────────────────────────
  const toggleReportRow = useCallback((key, row) => {
    setSelectedRows(prev => {
      const next = { ...prev };
      if (next[key]) delete next[key]; else next[key] = row;
      return next;
    });
  }, []);

  const setAllReportRows = useCallback((keys, rows, checked) => {
    setSelectedRows(prev => {
      const next = { ...prev };
      keys.forEach((k, i) => { if (checked) next[k] = rows[i]; else delete next[k]; });
      return next;
    });
  }, []);

  const runQuerySearch = async (queryValue, languageAtSubmit = selectedLanguage) => {
    const submittedQuery = String(queryValue ?? '').trim();
    if (!submittedQuery) return;
    if (searchRequestRef.current.controller && searchRequestRef.current.query === submittedQuery) return;

    searchRequestRef.current.controller?.abort();
    const requestId = searchRequestRef.current.id + 1;
    const controller = new AbortController();
    searchRequestRef.current = { id: requestId, controller, query: submittedQuery };
    setIsLoading(true);
    setError('');
    setResults(null);
    setSuggestion(null);
    setNoMatchMsg('');
    setQueryDebugOpen(false);
    setQueryComplete(false);
    setSelectedRows({});
    setTableRowsView(null);
    clearTimeout(queryCompleteTimerRef.current);
    try {
      const payload = {
        natural_query: submittedQuery,
        language: languageAtSubmit,
        response_language: languageAtSubmit === 'kannada' ? 'kannada' : (languageAtSubmit === 'mixed' ? 'mixed' : 'english'),
        debug: import.meta.env.DEV,
      };
      const res = await api.post('/query/generate', payload, { signal: controller.signal });
      if (searchRequestRef.current.id !== requestId) return;

      if (res.data.action_required === 'confirm') {
        setConfirmModal({ isOpen: true, data: res.data });
        setSecondConfirm(false);
      } else if (res.data.action_required === 'select_student') {
        const picks = (res.data.suggestions || []).map((s) => ({
          usn: s.usn,
          name: s.name || s.usn,
          branch: s.branch,
          current_sem: s.current_sem ?? s.semester,
          score: s.score ?? 1,
        }));
        setSuggestion({
          type: picks.length > 1 ? 'multiple_match' : 'possible_matches',
          message: res.data.message || 'Please select the student.',
          suggestions: picks,
        });
        setNoMatchMsg(picks.length ? '' : (res.data.message || 'Please specify which student.'));
      } else {
        const rows = Array.isArray(res.data.data) ? res.data.data : [];
        setSuggestion(res.data.suggestion || null);
        setNoMatchMsg(res.data.no_match_message || '');
        setResults({ ...res.data, data: rows, _query: submittedQuery, intent: res.data.intent || 'full' });
        setQueryComplete(true);
        queryCompleteTimerRef.current = setTimeout(() => setQueryComplete(false), 900);
        void fetchHistory();
      }
    } catch (err) {
      const isCurrentRequest = searchRequestRef.current.id === requestId;
      const wasAborted = err.code === 'ERR_CANCELED' || err.name === 'CanceledError';
      if (isCurrentRequest && !wasAborted) setError(getUserMessage(err, 'Query failed.'));
    } finally {
      if (searchRequestRef.current.id === requestId) {
        searchRequestRef.current = { id: requestId, controller: null, query: null };
        setIsLoading(false);
      }
    }
  };

  // ── Query submit ─────────────────────────────────────────────────────────────
  const handleQuerySubmit = async (e) => {
    if (e) e.preventDefault();
    const submittedQuery = String(textareaRef.current?.value ?? query).trim();
    if (!submittedQuery) return;
    setShowLiveDropdown(false);
    setActiveSuggestion(-1);
    // Hold suggestions closed until the text changes again, so a suggestion
    // response still in flight can't pop up over the results it was typed for.
    selectionLocked.current = true;
    await runQuerySearch(submittedQuery, selectedLanguage);
  };

  // ── Select from live dropdown ─────────────────────────────────────────────────
  // Replaces the fuzzy token in the original query with the confirmed name,
  // rebuilds the full query, executes it immediately, and locks suggestions.
  // Example: "show academic details of manja" + select "MANJUNATH H"
  //       → "show academic details of MANJUNATH H" → execute
  const selectSuggestionAndRun = async (s) => {
    // 1. Lock the entity — suggestions will not reopen while this name is in the box
    selectionLocked.current = true;
    confirmedEntity.current = { usn: s.usn, name: s.name };

    // 2. Close dropdown immediately
    setShowLiveDropdown(false);
    setLiveSuggestions([]);
    setActiveSuggestion(-1);

    // 3. Rebuild the query: replace the fuzzy search token with the confirmed name
    const currentQuery = query.trim();
    const KEYWORDS = new Set(['show','give','me','display','list','get','find','fetch',
      'search','all','the','of','for','in','from','with','and','or','by','student',
      'students','marks','mark','gpa','cgpa','sgpa','details','data','record','records',
      'semester','sem','result','results','top','best','highest','lowest']);

    // Find the fuzzy token (last non-keyword word) and replace it with the confirmed name
    const words = currentQuery.split(/\s+/);
    let replaced = false;
    const rebuiltWords = [...words].reverse().map(w => {
      if (!replaced && w.length >= 2 && !KEYWORDS.has(w.toLowerCase())) {
        replaced = true;
        return s.name;
      }
      return w;
    }).reverse();

    const finalQuery = replaced ? rebuiltWords.join(' ') : `${currentQuery} ${s.name}`.trim();

    // 4. Update the textarea to show the rebuilt query (so user can see what ran)
    setQuery(finalQuery);

    await runQuerySearch(finalQuery, selectedLanguage);
  };

  // YES → load the suggested student's data directly
  const handleSuggestionYes = async (s) => {
    setSuggestion(null);
    setNoMatchMsg('');

    // Lock entity so suggestions don't reopen
    confirmedEntity.current = { usn: s.usn, name: s.name };
    selectionLocked.current = true;

    if (s.data?.length > 0) {
      // Pre-fetched data available — show it directly
      const profile = s.profile || {};
      const enriched = s.data.map(row => ({ ...profile, ...row }));
      setResults({
        action_required: 'none',
        data: enriched,
        query: `-- Data for ${s.name} (${s.usn})`,
        _query: query,
        _profile: profile,
      });
    } else {
      // No pre-fetched data — execute query for this student
      const naturalQuery = `Show details of ${s.name}`;
      setQuery(naturalQuery);
      await runQuerySearch(naturalQuery, selectedLanguage);
    }
  };

  // NO → clear and show "no records" message
  const handleSuggestionNo = () => {
    setSuggestion(null);
    setResults(null);
    setNoMatchMsg('No matching records available.');
  };

  const executeConfirmed = async () => {
    setIsLoading(true); setError('');
    const cd = confirmModal.data || {};

    // Natural-language fee / lifecycle previews carry an explicit confirm_endpoint
    // (no SQL query_dict). Route them to their dedicated commit endpoint.
    if (cd.confirm_endpoint) {
      try {
        const isLifecycle = String(cd.confirm_endpoint).includes('/lifecycle/');
        const body = isLifecycle
          ? { payload: cd.payload, confirmation_token: cd.confirmation_token }
          : { ...(cd.payload || {}), confirm: true };
        // The backend advertises absolute paths ("/api/update/fees") while this
        // axios client already has baseURL "/api" — posting the raw value asked
        // for /api/api/update/fees and failed with a bare "Not Found".
        const path = String(cd.confirm_endpoint).replace(/^\/?api\//, '/');
        const res = await api.post(path, body);
        setConfirmModal({ isOpen: false, data: null });
        setResults({ success: true, message: res.data.message || 'Operation executed.', data: [], _query: '' });
        showToast({
          type: 'success',
          title: isLifecycle ? 'Lifecycle updated' : 'Fees updated',
          message: res.data.message || (isLifecycle
            ? `${res.data.from_status || ''} → ${res.data.to_status || ''}`.trim()
            : 'Fee status saved.'),
          undoToken: res.data.undo_token,
          undoName: cd.payload?.usn,
          duration: 8000,
        });
        fetchHistory();
      } catch (err) {
        const message = getUserMessage(err, 'Could not complete the operation.');
        setError(message);
        setConfirmModal({ isOpen: false, data: null });
        showToast({ type: 'error', message });
      } finally {
        setIsLoading(false);
      }
      return;
    }

    try {
      const res = await api.post('/query/execute', {
        query_dict: confirmModal.data.query_dict,
        original_query: confirmModal.data.original_query,
        confirmed: true,
        confirmation_token: confirmModal.data.confirmation_token,
      });
      setConfirmModal({ isOpen: false, data: null });
      setResults({ success: true, message: 'Operation executed.', data: res.data.data || [], _query: '' });

      // Show detailed operation modal if details returned
      if (res.data.operation_details) {
        setOpResult({
          operation: res.data.operation_details.operation_type,
          affectedStudents: res.data.operation_details.students,
          rowsAffected: res.data.operation_details.affected_rows,
          performedBy: res.data.operation_details.performed_by,
          timestamp: res.data.operation_details.timestamp,
          restoreTokens: res.data.restore_tokens || [],
          message: res.data.message
        });
      }

      // Keep the immediate result aligned with the explicit backend operation.
      if (res.data.undo_available && res.data.restore_tokens?.length > 0) {
        res.data.restore_tokens.forEach(({ token, name, usn }) => {
          const operation = res.data.operation_details?.operation_type;
          const isDelete = operation === 'DELETE';
          showToast({
            type: isDelete ? 'warning' : 'success',
            title: operation === 'ADD' ? 'Student Added' : operation === 'UPDATE' ? 'Student Updated' : 'Student Deleted',
            message: isDelete ? `"${name || usn}" was deleted. Undo is available.` : res.data.message,
            undoToken: token,
            undoName: name || usn,
            duration: 8000,
          });
        });
      } else {
        showToast({
          type: 'success',
          message: res.data.message || 'Operation completed successfully.',
          duration: 3000,
        });
      }
      // The sidebar is backed by persistent activity records, so refresh it
      // after every completed database write as well as after query history.
      fetchHistory();
    } catch (err) {
      const message = getUserMessage(err, 'Could not save changes.');
      setError(message);
      setConfirmModal({ isOpen: false, data: null });
      showToast({ type: 'error', message });
    } finally {
      setIsLoading(false);
    }
  };

  // ── Export is handled by the ReportModal (category + scope + format) ───────

  const data = results?.data || [];
  const appliedConditions = results?.query_ast?.conditions || [];

  const keys = new Set();
  for (let i = 0; i < Math.min(5, data.length); i++) {
    Object.keys(data[i]).forEach(k => keys.add(k.toLowerCase()));
  }
  const hasAcademic = keys.has('sgpa') || keys.has('cgpa') || keys.has('semester');
  const hasPersonal = keys.has('father_name') || keys.has('dob') || keys.has('address')
    || keys.has('phone') || keys.has('email') || keys.has('blood_group') || keys.has('gender');

  const q = (results?._query || '').toLowerCase();

  // Sprint 2: Detect complete-profile intent (English + Kannada)
  const COMPLETE_PROFILE_RE = /\b(everything\s+about|complete\s+information|full\s+information|complete\s+details|full\s+details|entire\s+profile|all\s+information|all\s+about|show\s+everything|full\s+profile|complete\s+profile|student\s+profile|both\s+academic|academic\s+and\s+personal)\b/i;

  const isCompleteProfileIntent = (
    results?.intent === 'complete_profile' ||
    COMPLETE_PROFILE_RE.test(q) ||
    (results?._profile !== undefined)
  );

  // Single-student result detection
  const isSingleStudent = (() => {
    const usns = new Set(data.map(r => r.usn).filter(Boolean));
    return usns.size === 1;
  })();

  // Show CombinedStudentView when:
  // - complete_profile intent (user asked for full details)
  // - OR single student result with personal fields (even without academic)
  // Do NOT show for pure 'academic' intent — GpaTable handles that
  const showCombined = data.length > 0 && (
    results?.intent === 'complete_profile' ||
    (isCompleteProfileIntent && results?.intent !== 'academic') ||
    (isSingleStudent && hasPersonal && results?.intent !== 'academic' && results?.intent !== 'specific_field')
  );
  // Academic intent: pure marks query → GpaTable
  const showGpa     = !showCombined && isGpaData(data);
  const showGeneric = !showCombined && !showGpa && data.length > 0;
  const showChart   = data.length > 0 && shouldShowChart(results?._query || '');

  // Scalar number check (e.g. "How many students have 8+ CGPA?")
  const isScalarNumber = Boolean(
    results?.is_scalar_number ||
    results?.intent === 'count' ||
    (data.length === 1 && Object.keys(data[0]).length === 1 && typeof Object.values(data[0])[0] === 'number')
  );
  const scalarValue = results?.scalar_value ?? (data.length === 1 ? Object.values(data[0])[0] : null);


  // Girls names list check (e.g. "Give only girls names")
  const isGirlsNamesList = Boolean(
    results?.intent === 'girls_names' ||
    (data.length > 0 &&
      Object.keys(data[0]).length === 1 &&
      Object.keys(data[0])[0].toLowerCase() === 'name' &&
      /\b(girls?|female|women)\b/i.test(q))
  );

  // Track response language for Kannada label support
  const responseLanguage = results?.response_language || 'english';

  // §7 — department identity. The department is read from the rows the backend
  // already returned; nothing is hardcoded and no query changes. A stable hash
  // of the branch code selects one of six tints, so each department reads as a
  // distinct room without maintaining a branch→colour table. All six are muted,
  // low-chroma naturals drawn from the same family as the two themes (forest,
  // teal, slate, champagne, sage, clay) — they stay readable at 12% alpha over
  // both an ivory and a midnight ground instead of turning the app into a
  // different primary colour per screen.
  const deptName = (() => {
    const row = data?.[0];
    if (!row) return '';
    const key = Object.keys(row).find((k) => /^(branch|department|dept)$/i.test(k));
    return key ? String(row[key] ?? '').trim() : '';
  })();
  const DEPT_RAMPS = ['36 52 75', '216 189 138', '182 106 69', '60 84 118', '175 140 95', '140 85 60'];
  const deptRgb = deptName
    ? DEPT_RAMPS[[...deptName.toLowerCase()].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 997, 7) % DEPT_RAMPS.length]
    : null;
  const deptStyle = deptRgb ? { '--dept-a': deptRgb, '--dept-b': deptRgb } : undefined;

  return (
    <div className="flex h-screen bg-canvas overflow-hidden">
      {/* Hidden print area */}
      <div style={{ display: 'none' }} ref={printRef}>
        <PrintReport data={data} username={username} role={role} query={results?._query || ''} />
      </div>

      {/* ── Sidebar / mobile drawer ── */}
      {navOpen && (
        <div
          className="anim-fade-in fixed inset-0 z-30 bg-brand-deep/60 backdrop-blur-[2px] lg:hidden no-print"
          onClick={() => setNavOpen(false)}
          aria-hidden="true"
        />
      )}
      <aside
        aria-label={t('nav.ariaMain')}
        className={`nav-shell bg-nav text-nav-fg flex flex-col shadow-2xl flex-shrink-0
          fixed inset-y-0 left-0 z-40
          ${navCollapsed ? 'w-[4.5rem]' : 'w-64'}
          lg:static lg:translate-x-0 lg:z-20
          ${navOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        {/* Sidebar header */}
        <div className={`p-4 flex items-center gap-3 border-b border-nav-line ${navCollapsed ? 'justify-center gap-0' : ''}`}>
          <div className="w-9 h-9 rounded-xl bg-gradient-to-b from-brand-mid to-brand-deep ring-1 ring-white/10 flex items-center justify-center flex-shrink-0">
            <Database className="w-4 h-4 text-accent" />
          </div>
          <div className={`flex-1 min-w-0 ${navCollapsed ? 'hidden' : ''}`}>
            <h1 className="font-bold text-sm text-nav-fg t-truncate">{t('nav.brand')}</h1>
            <p className="text-[11px] text-nav-fg-mute t-truncate">{t('nav.brandSub')}</p>
          </div>
          <button
            type="button"
            onClick={() => setNavOpen(false)}
            className="lg:hidden p-1.5 rounded-md text-nav-fg-mute hover:text-nav-fg hover:bg-white/10 flex-shrink-0"
            aria-label={t('nav.close')}
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Appearance (§4) and interface language (§5) — available on every surface.
            In the icon rail they collapse to single cycling buttons so the rail
            never hides a control the expanded sidebar offers. */}
        <div className={`px-3 py-3 space-y-2 border-b border-nav-line ${navCollapsed ? 'px-2 flex flex-col items-center space-y-1.5' : ''}`}>
          <LanguageModeToggle variant="onNav" compact={navCollapsed} className="w-full justify-center" />
          <ThemeModeToggle variant="onNav" compact={navCollapsed} className="w-full justify-center" />
        </div>

        {/* Account: full card when there is room, an initial when there is not. */}
        <div className={`px-3 py-3 border-b border-nav-line bg-white/[0.04] ${navCollapsed ? 'flex justify-center px-2' : ''}`}>
          {navCollapsed ? (
            <span
              className="w-8 h-8 rounded-full bg-white/10 border border-white/10 flex items-center justify-center text-[12px] font-bold text-accent uppercase"
              title={`${username || 'User'} · ${String(role).toLowerCase() === 'admin' ? t('nav.roleAdmin') : String(role).toLowerCase() === 'staff' ? t('nav.roleStaff') : role}`}
            >
              {(username || 'U').slice(0, 1)}
            </span>
          ) : (
            <>
              <span className="text-[11px] text-nav-fg-mute uppercase tracking-wider font-semibold">{t('nav.loggedInAs')}</span>
              <p className="text-sm text-nav-fg font-medium t-truncate" title={username || 'User'}>{username || 'User'}</p>
              <span className="inline-flex items-center mt-1 px-2 py-0.5 rounded-md text-[11px] font-bold uppercase bg-white/10 text-accent border border-white/10">
                {String(role).toLowerCase() === 'admin' ? t('nav.roleAdmin')
                  : String(role).toLowerCase() === 'staff' ? t('nav.roleStaff')
                  : role}
              </span>
            </>
          )}
        </div>

        {/* Nav — grouped into a workspace, the record tools and the oversight
            screens, so the rail reads as a place rather than a list of seven
            identical buttons. Same destinations, same permissions, same order
            of access; only the grouping and the type size changed. */}
        <nav className={`py-2 border-b border-nav-line ${navCollapsed ? 'px-1.5' : 'px-2'}`}>
          {[
            ['nav.groupWorkspace', [
              ['query',     <Send className="w-[17px] h-[17px]" aria-hidden="true" />,              'nav.query'],
              ['analytics', <BarChart2 className="w-[17px] h-[17px]" aria-hidden="true" />,         'nav.analytics'],
            ]],
            ['nav.groupRecords', [
              ['files',     <Upload className="w-[17px] h-[17px]" aria-hidden="true" />,            'nav.files'],
              ['lifecycle', <GraduationCap className="w-[17px] h-[17px]" aria-hidden="true" />,     'nav.lifecycle'],
            ]],
            ['nav.groupOversight', [
              ['validation', <ShieldAlert className="w-[17px] h-[17px]" aria-hidden="true" />,      'nav.validation'],
              ['activity',   <Activity className="w-[17px] h-[17px]" aria-hidden="true" />,         'nav.activity'],
              ['backup',     <HardDrive className="w-[17px] h-[17px]" aria-hidden="true" />,        'nav.backup'],
            ]],
          ].map(([groupKey, items], gi) => (
            <div key={groupKey}>
              {navCollapsed
                ? (gi > 0 && <div className="mx-2 my-2 h-px bg-white/10" aria-hidden="true" />)
                : <p className="nav-group-label">{t(groupKey)}</p>}
              <div className="space-y-1">
                {items.map(([tab, icon, key]) => (
                  <button key={tab}
                    onClick={() => { setActiveTab(tab); setNavOpen(false); }}
                    aria-current={activeTab === tab ? 'page' : undefined}
                    aria-label={t(key)}
                    data-active={activeTab === tab}
                    title={t(key)}
                    className={`nav-item ${navCollapsed ? 'is-compact' : ''}`}>
                    <span className="nav-item__icon">{icon}</span>
                    <span className={`nav-item__label ${navCollapsed ? 'hidden' : ''}`}>{t(key)}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* History + recent activity. The icon rail keeps only primary
            navigation; an inert spacer holds the sign-out row at the bottom. */}
        <div aria-hidden="true" className={navCollapsed ? 'flex-1' : 'hidden'} />
        <div className={`flex-1 overflow-y-auto p-3 space-y-4 ${navCollapsed ? 'hidden' : ''}`}>
          <div>
            <div className="flex items-center gap-2 mb-2 text-nav-fg-mute px-1">
              <History className="w-3.5 h-3.5" />
              <span className="text-[11px] font-semibold uppercase tracking-wider">{t('nav.recentSearches')}</span>
            </div>
            <div className="space-y-1">
              {history.map((h, i) => (
                <button key={i} onClick={() => { setQuery(h.natural_query); setActiveTab('query'); setNavOpen(false); }}
                  title={h.natural_query}
                  className="w-full text-left p-2 rounded-md hover:bg-white/[0.07] transition-colors">
                  <p className="text-[13px] text-nav-fg/90 line-clamp-2">{h.natural_query}</p>
                </button>
              ))}
            </div>
          </div>

          {recentActivity.additions?.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2 text-ok px-1">
                <PlusCircle className="w-3.5 h-3.5" />
                <span className="text-[11px] font-semibold uppercase tracking-wider">{t('nav.recentlyAdded')}</span>
              </div>
              <div className="space-y-1.5">
                {recentActivity.additions.map((act, i) => (
                  <div key={i} className="p-2.5 rounded-md bg-white/[0.05] border border-white/[0.07]">
                    <p className="text-[13px] font-semibold text-nav-fg t-truncate" title={act.student_name}>{act.student_name}</p>
                    <p className="text-xs text-nav-fg-mute font-mono t-truncate" title={act.usn}>{act.usn}</p>
                    <div className="flex items-center justify-between mt-1 text-[11px] text-nav-fg-mute">
                      <span className="t-truncate">{t('nav.by')} {act.added_by}</span>
                      <span className="flex items-center gap-1 flex-shrink-0"><Clock className="w-3 h-3" /> {new Date(act.timestamp).toLocaleDateString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {recentActivity.deletions?.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2 text-err px-1">
                <Trash2 className="w-3.5 h-3.5" />
                <span className="text-[11px] font-semibold uppercase tracking-wider">{t('nav.recentlyDeleted')}</span>
              </div>
              <div className="space-y-1.5">
                {recentActivity.deletions.map((act, i) => (
                  <div key={i} className="p-2.5 rounded-md bg-white/[0.05] border border-white/[0.07]">
                    <p className="text-[13px] font-semibold text-nav-fg t-truncate" title={act.student_name}>{act.student_name}</p>
                    <p className="text-xs text-nav-fg-mute font-mono t-truncate" title={act.usn}>{act.usn}</p>
                    <div className="flex items-center justify-between mt-1 text-[11px] text-nav-fg-mute">
                      <span className="t-truncate">{t('nav.by')} {act.deleted_by}</span>
                      <span className="flex items-center gap-1 flex-shrink-0"><Clock className="w-3 h-3" /> {new Date(act.timestamp).toLocaleDateString()}</span>
                    </div>
                    {/* Quick restore button */}
                    {act.restore_token && (
                      <button
                        onClick={async () => {
                          try {
                            await api.post(`/undo/restore/${act.restore_token}`);
                            showToast({ type: 'success', message: `${act.student_name} restored!` });
                            fetchHistory();
                          } catch (e) {
                            showToast({ type: 'error', message: getUserMessage(e, 'Could not restore student.') });
                          }
                        }}
                        className="mt-2 w-full flex items-center justify-center gap-1.5 py-1.5 text-xs font-semibold text-ok bg-ok/10 hover:bg-ok/20 rounded-md transition-colors border border-ok/25"
                      >
                        <RotateCcw className="w-3 h-3" /> {t('nav.restore')}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="p-3 border-t border-nav-line">
          <button onClick={handleLogout}
            title={t('nav.signOut')}
            aria-label={t('nav.signOut')}
            className={`w-full flex items-center gap-2 py-2 rounded-md text-sm text-nav-fg-mute hover:text-white hover:bg-white/[0.07] transition-colors
              ${navCollapsed ? 'justify-center px-0' : 'justify-center'}`}>
            <LogOut className="w-4 h-4" /> <span className={navCollapsed ? 'hidden' : ''}>{t('nav.signOut')}</span>
          </button>
        </div>
      </aside>

      {/* ── Main ── */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden relative">
        {/* Background: the college photograph, full-bleed behind the whole
            working area and drifting very slowly. It is a ground, not a
            section — every card and table sits on top of it. Falls back to
            the campus gradient when public/college-photo.jpg is absent. */}
        <div
          className={`dash-bg absolute inset-0 pointer-events-none z-0 ${hasCampusPhoto ? 'has-photo' : ''}`}
          aria-hidden="true"
        />

        <header className="h-14 bg-surface/85 backdrop-blur border-b border-line flex items-center px-4 sm:px-6 shadow-sm z-10 shrink-0 gap-3">
          <button
            type="button"
            onClick={() => setNavOpen(true)}
            className="lg:hidden btn btn-ghost btn-sm"
            aria-label={t('nav.menu')}
          >
            <Menu className="w-4 h-4" />
          </button>
          {/* Rail toggle — the sidebar can shrink to icons so the working area
              gets the width back. Purely local, like the theme choice. */}
          <button
            type="button"
            onClick={() => setNavCollapsed((v) => !v)}
            className="btn btn-ghost btn-sm"
            aria-label={navCollapsed ? t('nav.expand') : t('nav.collapse')}
            aria-expanded={!navCollapsed}
            title={navCollapsed ? t('nav.expand') : t('nav.collapse')}
          >
            {navCollapsed
              ? <PanelLeftOpen className="w-4 h-4" aria-hidden="true" />
              : <PanelLeftClose className="w-4 h-4" aria-hidden="true" />}
          </button>
          <h2 className="text-[15px] sm:text-base font-semibold text-ink t-truncate">
            {t({
              query: 'nav.headerQuery',
              files: 'nav.headerFiles',
              backup: 'nav.headerBackup',
              analytics: 'nav.headerAnalytics',
              lifecycle: 'nav.headerLifecycle',
              activity: 'nav.headerActivity',
              validation: 'nav.headerValidation',
            }[activeTab] || 'nav.headerValidation')}
          </h2>
          <div className="ml-auto flex items-center gap-2 min-w-0">
            {deptName && (
              <span className="badge badge-quiet max-w-[14rem]" title={deptName}>
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ background: `rgb(${deptRgb})` }}
                  aria-hidden="true"
                />
                <span className="t-truncate">{deptName}</span>
              </span>
            )}
            <span className="badge badge-brand flex-shrink-0">{t('nav.badgeMysql')}</span>
            {results?.cached && <span className="badge badge-ok flex-shrink-0">{t('nav.badgeCached')}</span>}
          </div>
        </header>

        <main className="dept-tint flex-1 overflow-y-auto p-4 sm:p-5 relative z-10" style={deptStyle}>
          {/* key={activeTab} remounts the panel on tab change so the entrance
              animation replays; every value in here is parent state, so no
              query, selection or in-progress edit is lost. */}
          <div key={activeTab} className="anim-page max-w-5xl mx-auto space-y-4">
            {/* Institutional header */}
            {activeTab === 'query' && <ReportHeader showInDashboard={showHeader} />}

            {/* Upload notice */}
            {uploadNotice && (
              <div role="status" className="flex items-start gap-3 p-3 rounded-lg bg-ok-soft text-sm text-ok">
                <CheckCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <div className="min-w-0">
                  <p className="font-semibold break-words">{uploadNotice.filename} — {uploadNotice.message}</p>
                  <p className="text-[13px] mt-0.5 text-ink-soft">
                    {[
                      `${uploadNotice.rows_parsed} ${t('upload.parsed')}`,
                      `${t('upload.new')} ${uploadNotice.students_added ?? 0}`,
                      `${t('upload.updated')} ${uploadNotice.students_updated ?? 0}`,
                      `${t('upload.unchanged')} ${uploadNotice.students_unchanged ?? 0}`,
                      `${t('upload.dup')} ${uploadNotice.duplicate_rows ?? 0}`,
                      `${t('upload.invalid')} ${uploadNotice.invalid_rows ?? 0}`,
                      `${t('upload.saved')} ${uploadNotice.students_saved} ${t('upload.students')} / ${uploadNotice.marks_saved} ${t('upload.marks')}`,
                    ].join(' · ')}
                  </p>
                  {uploadNotice.column_mapping && Object.keys(uploadNotice.column_mapping).length > 0 && (
                    <p className="text-[13px] mt-0.5 text-ink-soft break-words">
                      {t('upload.columnsMapped')} {Object.entries(uploadNotice.column_mapping).map(([k,v]) => `${k}→${v}`).join(', ')}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* ── Backup & Reliability Tab ── */}
            {activeTab === 'backup' && <BackupRestore userRole={role} />}

            {/* ── Analytics Tab ── */}
            {activeTab === 'analytics' && <AnalyticsDashboard />}

            {/* ── Validation Tab ── */}
            {activeTab === 'validation' && <ValidationDashboard />}

            {/* ── Activity Tab ── */}
            {activeTab === 'activity' && <ActivityDashboard />}

            {/* ── Student Lifecycle Tab ── */}
            {activeTab === 'lifecycle' && <LifecycleDashboard role={role} />}

            {/* ── Files / Uploads Tab ── */}
            {activeTab === 'files' && (
              <FileExplorer canManageFiles={role === 'Admin'} refreshVersion={filesVersion} onDataLoaded={(info) => {
                  setUploadNotice(info); 
                  setTimeout(() => setUploadNotice(null), 8000); 
                  if (info.operation_details) {
                    setOpResult({
                      operation: 'UPLOAD',
                      affectedStudents: info.operation_details.students,
                      rowsAffected: info.operation_details.affected_rows,
                      performedBy: info.operation_details.performed_by,
                      timestamp: info.operation_details.timestamp,
                      restoreTokens: info.restore_tokens || [],
                      uploadStats: {
                        rows_parsed: info.rows_parsed,
                        students_added: info.students_added,
                        students_updated: info.students_updated,
                        students_unchanged: info.students_unchanged,
                        students_saved: info.students_saved,
                        marks_saved: info.marks_saved,
                        duplicate_rows: info.duplicate_rows,
                        invalid_rows: info.invalid_rows,
                        skipped_rows: info.skipped_rows,
                        total_accounted: info.total_accounted,
                        reconciled: info.reconciled,
                        column_mapping: info.column_mapping,
                        rejected_rows: info.rejected_rows,
                        duplicate_list: info.duplicate_list,
                        new_records: info.new_records,
                        updated_records: info.updated_records,
                      },
                    });
                  }
                  fetchHistory();
                }} />
            )}

            {/* ── Query Tab ── */}
            {activeTab === 'query' && (
              <>
                {/* Welcome hero — a copy card over the campus background. The
                    photograph itself is the page ground, so it is not repeated
                    in a frame here. */}
                {!results && (
                  <section className="welcome-hero anim-fade-up p-5 sm:p-7">
                    <div className="min-w-0 flex-1 flex flex-col justify-center">
                      <p className="eyebrow text-[11px] text-brand-fg">{t('brand.tagline')}</p>
                      <h3 className="t-section text-ink mt-1.5">{t('hero.title')}</h3>
                      <p className="t-body text-ink-soft mt-2 max-w-[48ch]">{t('hero.body')}</p>
                      <div className="mt-3.5 flex flex-wrap items-center gap-2">
                        <span className="badge badge-quiet max-w-full">
                          <Search className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
                          <span className="t-truncate">{t('hero.capType')}</span>
                        </span>
                        <span className="badge badge-quiet max-w-full">
                          <Mic className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
                          <span className="t-truncate">{t('hero.capVoice')}</span>
                        </span>
                        <span className="badge badge-quiet max-w-full">
                          <Database className="w-3 h-3 flex-shrink-0" aria-hidden="true" />
                          <span className="t-truncate">{t('hero.capDb')}</span>
                        </span>
                      </div>
                    </div>
                  </section>
                )}

                {/* Query input */}
                <div className="relative z-50">
                  {/* Language and Voice Selectors */}
                  <div className="flex flex-wrap items-center gap-3 mb-3">
                    {/* Language Selector */}
                    <LanguageSelector 
                      selectedLanguage={selectedLanguage}
                      onLanguageChange={handleLanguageChange}
                    />
                    
                    {/* Voice Language Selector */}
                    <div className="relative">
                      <label className="sr-only" htmlFor="voice-language-select">{t('query.voiceLabel')}</label>
                      <select
                        id="voice-language-select"
                        value={voiceLanguage}
                        onChange={(e) => handleVoiceLanguageChange(e.target.value)}
                        className="input appearance-none w-auto max-w-full pl-9 pr-9 text-sm font-medium cursor-pointer"
                        title={t('query.voiceLabel')}
                      >
                        <option value="en-US">🎤 {t('query.voiceEnglish')}</option>
                        <option value="kn-IN" lang="kn">🎤 {t('query.voiceKannada')}</option>
                        <option value="en-IN">🎤 {t('query.voiceIndia')}</option>
                      </select>
                      <Mic className="w-4 h-4 text-ink-mute absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
                      <ChevronDown className="w-4 h-4 text-ink-mute absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" aria-hidden="true" />
                    </div>

                    {/* Language indicator badge */}
                    {selectedLanguage !== 'english' && (
                      <div className="flex-1 flex items-center gap-2 min-w-0">
                        <span className="badge badge-accent max-w-full">
                          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse flex-shrink-0" aria-hidden="true" />
                          <span className="t-truncate">{selectedLanguage === 'kannada' ? t('query.kannadaMode') : t('query.mixedMode')}</span>
                        </span>
                      </div>
                    )}
                  </div>
                  
                  <div className="card rounded-xl p-2 focus-within:ring-2 focus-within:ring-ring/60">
                    <form onSubmit={handleQuerySubmit} className="relative flex items-end">
                      <textarea 
                        ref={textareaRef}
                        value={query} 
                        onChange={handleQueryChange}
                        aria-label={t('query.ariaInput')}
                        placeholder={getPlaceholderText(selectedLanguage)}
                        className="w-full resize-none p-4 pb-12 outline-none bg-transparent text-ink placeholder:text-ink-faint min-h-[90px] text-[15px] leading-relaxed"
                        onKeyDown={(e) => {
                          // Handle Kannada mode key events first
                          if (selectedLanguage === 'kannada') {
                            handleKeyDown(e);
                            if (e.defaultPrevented) return;
                          }
                          
                          // Live dropdown handling
                          if (showLiveDropdown && liveSuggestions.length > 0) {
                            if (e.key === 'ArrowDown') {
                              e.preventDefault();
                              setActiveSuggestion(i => Math.min(i + 1, liveSuggestions.length - 1));
                              return;
                            }
                            if (e.key === 'ArrowUp') {
                              e.preventDefault();
                              setActiveSuggestion(i => Math.max(i - 1, 0));
                              return;
                            }
                            if (e.key === 'Enter' && activeSuggestion >= 0) {
                              e.preventDefault();
                              const s = liveSuggestions[activeSuggestion];
                              selectSuggestionAndRun(s);
                              return;
                            }
                          }
                          if (e.key === 'Enter' && !e.shiftKey) { 
                            e.preventDefault(); 
                            setShowLiveDropdown(false);
                            handleQuerySubmit(); 
                          } 
                          if (e.key === 'Escape') {
                            setShowLiveDropdown(false);
                            setActiveSuggestion(-1);
                          }
                        }} 
                        onFocus={() => { if (liveSuggestions.length > 0) setShowLiveDropdown(true); }}
                      />
                      <div className="absolute bottom-3 left-3 flex flex-wrap items-center gap-2 max-w-[calc(100%-1.5rem)]">
                        <button type="button" onClick={toggleListen}
                          aria-pressed={isListening}
                          className={`btn btn-sm ${isListening ? 'btn-danger-soft animate-pulse' : 'btn-ghost'}`}
                          title={`${t('query.mic')} (${voiceLanguage === 'kn-IN' ? t('query.voiceKannada') : t('query.voiceEnglish')})`}
                          aria-label={t('query.mic')}>
                          <Mic className="w-4 h-4" />
                        </button>
                        {isListening && (
                          <span role="status" aria-live="polite" className="t-support text-err font-medium animate-pulse">
                            {t('query.listening')}
                          </span>
                        )}
                        {selectedLanguage === 'kannada' && !isListening && (
                          <div className="flex items-center gap-2 text-[13px] bg-ok-soft text-ok px-3 py-1.5 rounded-md border border-ok/20 font-medium min-w-0">
                            <Languages className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
                            <span className="t-truncate">{t('query.autoConvert')}</span>
                          </div>
                        )}
                      </div>
                      <div className="absolute bottom-3 right-3">
                        <button type="submit" disabled={isLoading || !query.trim()}
                          className="btn btn-accent">
                          {isLoading
                            ? <><div className="no-transition w-4 h-4 border-2 border-accent-fg/30 border-t-accent-fg rounded-full animate-spin" /> {t('query.searching')}</>
                            : queryComplete
                              ? <><CheckCircle className="w-4 h-4" /> {t('query.complete')}</>
                              : <><Send className="w-4 h-4" /> {t('query.run')}</>}
                        </button>
                      </div>
                    </form>
                    
                    {/* Kannada Transliteration Suggestions (Desh Kannada style) */}
                    {selectedLanguage === 'kannada' && kannadaSuggestions.length > 0 && (
                      <div
                        role="listbox"
                        aria-label={t('query.kaSuggestions')}
                        className="popover absolute top-full left-0 right-0 mt-1 rounded-xl overflow-hidden slide-down"
                      >
                        <div className="px-3 py-2 bg-sunken border-b border-line flex flex-wrap items-center justify-between gap-2">
                          <span className="flex items-center gap-2 t-support font-bold text-accent-ink min-w-0">
                            <Languages className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
                            <span className="t-truncate">{t('query.kaSuggestions')}</span>
                          </span>
                          <span className="t-support text-ink-mute">{t('query.kaNavigate')}</span>
                        </div>
                        <div className="max-h-48 overflow-y-auto">
                          {kannadaSuggestions.map((suggestion, idx) => (
                            <button
                              key={idx}
                              lang="kn"
                              role="option"
                              aria-selected={idx === activeSuggestion}
                              onClick={() => applySuggestion(idx)}
                              onMouseEnter={() => setActiveSuggestion(idx)}
                              className={`w-full text-left px-4 py-3 border-b border-line last:border-0 flex items-center gap-2
                                ${idx === activeSuggestion
                                  ? 'bg-brand/[0.07] border-l-4 border-l-brand font-semibold'
                                  : 'hover:bg-sunken'}`}
                            >
                              <span className="t-card text-ink">{suggestion}</span>
                              {idx === 0 && (
                                <span className="t-support text-accent-ink font-medium">{t('query.kaPressSpace')}</span>
                              )}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Language-aware example queries */}
                  {!query && !results && (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <span className="t-support text-ink-mute font-medium">{t('query.try')}</span>
                      {getExampleQueries(selectedLanguage).map((example, idx) => (
                        <button
                          key={idx}
                          onClick={() => setQuery(example)}
                          className="px-3 py-1.5 t-support bg-surface border border-line rounded-md text-ink-soft hover:bg-brand/[0.06] hover:border-brand/30 hover:text-ink transition-colors text-left min-w-0 max-w-full"
                        >
                          <span className="t-truncate block">{example}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Live Suggestions Dropdown */}
                  {showLiveDropdown && liveSuggestions.length > 0 && (
                    <div
                      ref={dropdownRef}
                      role="listbox"
                      aria-label={t('query.liveCount', { n: liveSuggestions.length, s: liveSuggestions.length !== 1 ? 's' : '', q: liveSearchTerm })}
                      className="popover absolute top-full left-0 right-0 mt-1 rounded-xl overflow-hidden slide-down"
                    >
                      {/* Header */}
                      <div className="px-3 py-2 bg-sunken border-b border-line flex flex-wrap items-center justify-between gap-2">
                        <span className="flex items-center gap-2 t-support font-bold text-brand-fg min-w-0">
                          <Search className="w-3.5 h-3.5 flex-shrink-0" aria-hidden="true" />
                          <span className="t-truncate">
                            {t('query.liveCount', { n: liveSuggestions.length, s: liveSuggestions.length !== 1 ? 's' : '', q: liveSearchTerm })}
                          </span>
                        </span>
                        <span className="t-support text-ink-mute">{t('query.liveHint')}</span>
                      </div>

                      {/* Suggestion rows */}
                      <div className="max-h-[280px] overflow-y-auto">
                        {liveSuggestions.map((s, idx) => {
                          const isActive = idx === activeSuggestion;
                          const badge = MATCH_BADGE[s.match_type] || MATCH_BADGE.fuzzy;
                          const pct = Math.round((s.score || 0) * 100);
                          return (
                            <button
                              key={s.usn}
                              role="option"
                              aria-selected={isActive}
                              onClick={() => {
                                selectSuggestionAndRun(s);
                              }}
                              onMouseEnter={() => setActiveSuggestion(idx)}
                              className={`w-full flex items-center justify-between gap-3 px-4 py-3 text-left border-b border-line last:border-0 group
                                ${isActive ? 'bg-brand/[0.07] border-l-4 border-l-brand' : 'hover:bg-sunken'}`}
                            >
                              {/* Avatar + name */}
                              <div className="flex items-center gap-3 min-w-0">
                                <div className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-sm flex-shrink-0
                                  ${isActive ? 'bg-brand text-white' : 'bg-brand/10 text-brand-fg group-hover:bg-brand/20'}`}>
                                  {(s.name || '?').charAt(0).toUpperCase()}
                                </div>
                                <div className="min-w-0">
                                  <p className="t-body font-semibold text-ink t-truncate" title={s.name || ''}>
                                    <HighlightMatch text={s.name || ''} query={liveSearchTerm} />
                                  </p>
                                  <p className="t-support text-ink-mute font-mono t-truncate" title={s.usn || ''}>{s.usn}</p>
                                  {s.suggested_phrases?.length > 1 && (
                                    <div className="flex flex-wrap gap-1 mt-1">
                                      {s.suggested_phrases.slice(1, 4).map((phrase, pIdx) => (
                                        <span
                                          key={pIdx}
                                          role="button"
                                          tabIndex={0}
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            setQuery(phrase);
                                            setShowLiveDropdown(false);
                                            handleQuerySubmit();
                                          }}
                                          onKeyDown={(e) => {
                                            if (e.key === 'Enter' || e.key === ' ') {
                                              e.preventDefault();
                                              e.stopPropagation();
                                              setQuery(phrase);
                                              setShowLiveDropdown(false);
                                              handleQuerySubmit();
                                            }
                                          }}
                                          className="text-[12px] bg-sunken hover:bg-brand/10 text-ink-soft px-1.5 py-0.5 rounded border border-line cursor-pointer"
                                        >
                                          {phrase}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </div>

                              {/* Right side: badge + score + arrow */}
                              <div className="flex items-center gap-2 flex-shrink-0">
                                <span className={`badge ${badge.cls}`}>{badge.label}</span>
                                <span className="t-support text-ink-mute font-mono w-10 text-right tabular-nums">{pct}%</span>
                                <ChevronRight className={`w-4 h-4 ${isActive ? 'text-brand-fg' : 'text-ink-faint'}`} />
                              </div>
                            </button>
                          );
                        })}
                      </div>

                      {/* Footer hint */}
                      <div className="px-3 py-2 bg-sunken border-t border-line text-center">
                        <span className="text-[12px] text-ink-mute">
                          {t('query.liveFooter', { key: t('query.kbdEnter') })}
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                {isLoading && (
                  <div role="status" aria-live="polite" className="card anim-fade-in overflow-hidden">
                    <div className="fetch-bar" aria-hidden="true" />
                    <div className="p-4 flex items-start gap-3">
                      <div className="no-transition w-5 h-5 rounded-full border-2 border-line border-t-brand animate-spin flex-shrink-0 mt-0.5" aria-hidden="true" />
                      <div className="min-w-0 flex-1">
                        <p className="t-label text-ink">{t('query.loadingTitle')}</p>
                        <p className="t-support text-ink-mute mt-0.5">{t('query.loadingBody')}</p>
                        {/* Shape preview only — no invented rows. */}
                        <div className="skeleton-list mt-3" aria-hidden="true">
                          <span className="skeleton w-full" />
                          <span className="skeleton w-11/12" />
                          <span className="skeleton w-4/5" />
                          <span className="skeleton w-2/3" />
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Error — suppress stale messages during a request or while typing */}
                {error && !isLoading && !showLiveDropdown && (
                  <div role="alert" className="p-4 rounded-lg flex items-start gap-3 bg-err-soft text-err">
                    <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <div className="min-w-0">
                      <p className="t-label">{t('query.failed')}</p>
                      <p className="t-body mt-0.5 break-words">{error}</p>
                    </div>
                  </div>
                )}

                {/* No-match message — only show when NOT typing (no live suggestions active) */}
                {noMatchMsg && !isLoading && !suggestion && !showLiveDropdown && (
                  <div className="card p-4 flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-ink-faint flex-shrink-0 mt-0.5" />
                    <p className="t-body font-medium text-ink-soft">{noMatchMsg}</p>
                  </div>
                )}

                {/* Suggestion panel — only when no result data yet */}
                {suggestion && !results?.auto_corrected && !(results?.data?.length > 0) && (
                  <SuggestionPanel
                    suggestion={suggestion}
                    onYes={handleSuggestionYes}
                    onNo={handleSuggestionNo}
                  />
                )}

                {/* Auto-correction notice */}
                {results?.auto_corrected && results?.correction_message && (
                  <div role="status" className="flex items-center gap-2 p-3 rounded-lg bg-info-soft text-sm text-info">
                    <Search className="w-4 h-4 flex-shrink-0" />
                    <span>{results.correction_message}</span>
                  </div>
                )}
                {/* Results */}
                {results && (
                  <div className="anim-reveal card overflow-hidden">
                    {appliedConditions.length > 1 && (
                      <section aria-label={t('results.ariaFilters')} className="px-4 sm:px-5 py-4 border-b border-line bg-surface">
                        <div className="flex items-center justify-between gap-3 mb-2">
                          <h4 className="text-[13px] font-bold uppercase tracking-wide text-ink-soft">{t('query.reportedFilters')}</h4>
                          <span className="text-[12px] text-ink-mute">{t('query.conditions', { n: appliedConditions.length })}</span>
                        </div>
                        <ul className="flex flex-wrap gap-2">
                          {appliedConditions.map((condition, index) => (
                            <li key={`${condition.field}-${index}`} className="badge badge-quiet">
                              <CheckCircle className="w-3 h-3 text-ok" />
                              {describeCondition(condition)}
                            </li>
                          ))}
                        </ul>
                        {!data.length && (
                          <p className="mt-3 text-[13px] text-ink-mute">
                            {t('query.conditionsChecked')} {appliedConditions.map(describeCondition).join(' · ')}
                          </p>
                        )}
                      </section>
                    )}
                    <div className="px-4 sm:px-5 py-3 border-b border-line flex items-center justify-between gap-3 bg-sunken/60">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="p-1.5 bg-ok-soft text-ok rounded-md flex-shrink-0">
                          <TableIcon className="w-4 h-4" />
                        </div>
                        <div className="min-w-0">
                          <h3 className="t-card t-truncate">
                            {isScalarNumber ? t('results.result') : isGirlsNamesList ? t('results.femaleStudents') : (data.length > 0 ? t('results.records', { n: data.length }) : (results.query_ast ? t('results.noMatching') : t('results.operationComplete')))}
                          </h3>
                          {results.execution_time != null && (
                            <p className="text-[12px] text-ink-mute tabular-nums">{(results.execution_time * 1000).toFixed(1)}ms{results.cached ? ` · ${t('query.fromCache')}` : ''}</p>
                          )}
                        </div>
                      </div>
                      {data.length > 0 && !isScalarNumber && (
                        <div className="flex items-center gap-1.5 flex-wrap justify-end">
                          {/* Intent badge */}
                          {results?.intent && results.intent !== 'full' && (
                            <span className={`badge ${
                              results.intent === 'personal'
                                ? 'bg-info-soft text-info'
                                : results.intent === 'complete_profile'
                                ? 'bg-brand/10 text-brand-fg'
                                : 'badge-brand'
                            }`}>
                              {results.intent === 'personal'
                                ? <><User className="w-3 h-3" /> {t('results.personalView')}</>
                                : results.intent === 'complete_profile'
                                ? <><GraduationCap className="w-3 h-3" /> {t('results.completeProfile')}</>
                                : <><GraduationCap className="w-3 h-3" /> {t('results.academicView')}</>}
                            </span>
                          )}
                          {/* Kannada indicator — the script marker itself stays untranslated */}
                          {responseLanguage !== 'english' && (
                            <span className="badge badge-accent font-kannada">ಕ•KN</span>
                          )}
                          <button onClick={() => setReportOpen(true)}
                            className="btn btn-primary btn-sm">
                            <FileText className="w-3.5 h-3.5" /> {t('results.generateReport')}
                          </button>
                        </div>
                      )}
                    </div>

                    <div className="p-4 sm:p-5 space-y-4">
                      {results.message && !isScalarNumber && (
                        <div className="flex items-start gap-2 p-3 rounded-lg bg-warn-soft text-sm text-warn">
                          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                          <span>{results.message}</span>
                        </div>
                      )}
                      {results.total_count != null && !isScalarNumber && (
                        <p className="t-label text-ink-soft">
                          {t('results.total', { n: results.total_count })}
                        </p>
                      )}
                      {isScalarNumber ? (
                        <div className="flex flex-col items-center justify-center py-16 px-4">
                          <span className="text-6xl sm:text-8xl font-black text-ink tracking-tight select-all tabular-nums break-all text-center">
                            {scalarValue}
                          </span>
                        </div>
                      ) : isGirlsNamesList ? (
                        <div className="card-elev max-w-md mx-auto p-5 sm:p-6 my-4">
                          <div className="text-[13px] font-bold text-ink-soft uppercase tracking-wider pb-3 border-b border-line flex items-center justify-between gap-3 mb-2">
                            <span className="flex items-center gap-1.5 min-w-0"><User className="w-4 h-4 text-info flex-shrink-0" /> <span className="t-truncate">{t('results.femaleNames')}</span></span>
                            <span className="badge badge-info flex-shrink-0">{t('results.studentsCount', { n: data.length })}</span>
                          </div>
                          <div className="divide-line max-h-[500px] overflow-y-auto pr-1">
                            {data.map((r, i) => (
                              <div key={i} className="py-2.5 px-3 flex items-center gap-3 hover:bg-brand/[0.045] rounded-md font-medium text-ink text-[14px]">
                                <span className="w-6 text-[13px] text-ink-faint font-mono tabular-nums flex-shrink-0">{i + 1}.</span>
                                <span className="font-semibold min-w-0 break-words">{r.name}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <>
                          {showCombined && <CombinedStudentView data={data} responseLanguage={responseLanguage} />}
                          {showGpa && <GpaTable data={data} />}
                          {showGeneric && <GenericTable data={data} responseLanguage={selectedLanguage}
                            onViewRows={setTableRowsView} selection={selectedRows}
                            onToggleRow={toggleReportRow} onToggleAll={setAllReportRows} />}
                          {showChart && <ResultChart data={data} query={results._query} />}
                        </>
                      )}
                      {data.length === 0 && !suggestion && !isScalarNumber && (
                        <div className="empty-state py-8">
                          {results.message || t('results.noRecords')}
                        </div>
                      )}
                    </div>

                    {import.meta.env.DEV && results.query_debug && (
                      <div className="border-t border-line bg-sunken">
                        <div className="flex items-center justify-between gap-3 px-4 sm:px-5 py-2.5 flex-wrap">
                          <button
                            type="button"
                            onClick={() => setQueryDebugOpen(value => !value)}
                            aria-expanded={queryDebugOpen}
                            className="inline-flex items-center gap-2 text-[13px] font-semibold text-ink-soft hover:text-brand-fg min-w-0"
                          >
                            {queryDebugOpen ? <ChevronUp className="w-3.5 h-3.5 shrink-0" /> : <ChevronDown className="w-3.5 h-3.5 shrink-0" />}
                            <span className="truncate">{t('debug.title')}</span>
                          </button>
                          <div className="flex items-center gap-2 text-[12px] text-ink-mute flex-wrap">
                            <span className="badge badge-quiet">
                              <Clock className="w-3 h-3" />
                              <span className="tabular-nums">{((results.execution_time ?? results.query_debug.execution_time ?? 0) * 1000).toFixed(0)} ms</span>
                            </span>
                            <span className="badge badge-quiet">
                              <TableIcon className="w-3 h-3" />
                              {t('debug.rows', { n: results.query_debug.returned_row_count ?? data.length })}
                            </span>
                          </div>
                        </div>
                        {queryDebugOpen && (
                          <div className="px-4 sm:px-5 pb-4 space-y-3 text-[13px] text-ink-soft max-w-full overflow-hidden">
                            <div className="flex justify-end">
                              <button type="button" onClick={() => setQueryDebugOpen(false)} className="text-[12px] font-medium text-ink-mute hover:text-ink">
                                {t('debug.close')}
                              </button>
                            </div>
                            {results.query_debug.normalized_query && (
                              <p className="break-words"><strong className="text-ink">{t('debug.normalized')}</strong> {maskSensitive(results.query_debug.normalized_query)}</p>
                            )}
                            <div className="flex flex-wrap gap-x-4 gap-y-1">
                              <p><strong className="text-ink">{t('debug.intent')}</strong> {results.query_debug.intent}</p>
                              <p><strong className="text-ink">{t('debug.validation')}</strong> {results.query_debug.validation}</p>
                            </div>
                            {results.query_debug.conditions?.length > 0 && (
                              <div>
                                <p className="font-semibold text-ink mb-1">{t('debug.filters')}</p>
                                <ul className="flex flex-wrap gap-1.5">
                                  {results.query_debug.conditions.map((condition, index) => (
                                    <li key={index} className="badge badge-quiet max-w-full">{describeCondition(condition)}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {results.query_debug.sql && (
                              <div>
                                <p className="font-semibold text-ink mb-1">{t('debug.sql')}</p>
                                <pre className="p-3 rounded-md bg-brand-deep text-ok text-[12px] font-mono overflow-x-auto max-w-full whitespace-pre-wrap break-words">{maskSensitive(results.query_debug.sql)}</pre>
                              </div>
                            )}
                            {results.query_debug.parameters != null && (
                              <div>
                                <p className="font-semibold text-ink mb-1">{t('debug.parameters')}</p>
                                <pre className="p-3 rounded-md bg-brand-deep text-ink-soft text-[12px] font-mono overflow-x-auto max-w-full whitespace-pre-wrap break-words">{JSON.stringify(maskDebugParameters(results.query_debug.parameters), null, 2)}</pre>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </main>
      </div>

      {/* ── Generate Report window ── */}
      <ReportModal
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        query={results?._query || ''}
        filteredRows={tableRowsView?.filteredRows || data}
        pageRows={tableRowsView?.pageRows || data}
        selectedRows={Object.values(selectedRows)}
        hasPagedTable={!!(tableRowsView && showGeneric)}
      />

      {/* ── Confirm Modal ── */}
      {confirmModal.isOpen && (
        <div className="backdrop" role="dialog" aria-modal="true" aria-labelledby="confirm-modal-title">
          <div className="modal-panel anim-scale-in max-w-md">
            <div className={`p-5 border-b border-line ${secondConfirm ? 'bg-err-soft' : 'bg-warn-soft'}`}>
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-full ${secondConfirm ? 'bg-err/15 text-err' : 'bg-warn/15 text-warn'}`}>
                  <AlertTriangle className="w-5 h-5" />
                </div>
                <h3 id="confirm-modal-title" className={`t-card ${secondConfirm ? 'text-err' : 'text-warn'}`}>
                  {secondConfirm ? t('confirm.finalTitle') : t('confirm.title', { action: confirmModal.data?.action_type })}
                </h3>
              </div>
            </div>
            <div className="p-5 space-y-3">
              <p className="t-body text-ink-soft">
                {secondConfirm
                  ? (confirmModal.data?.message
                      ? t('confirm.lastCheck', { message: confirmModal.data.message })
                      : t('confirm.confirmNow'))
                  : confirmModal.data?.message
                    || (confirmModal.data?.confirm_endpoint
                      ? (confirmModal.data?.action_type === 'FEE_UPDATE' ? t('confirm.updateFees') : t('confirm.lifecycleChange'))
                      : confirmModal.data?.action_type === 'DELETE'
                        ? t('confirm.deleteWarning')
                        : t('confirm.executePrefix', { action: confirmModal.data?.action_type }))}
              </p>
              {/* Admin-only commit gate for NL fee / lifecycle previews */}
              {confirmModal.data?.role_restricted === 'Admin' &&
                String(role).toLowerCase() !== 'admin' && (
                <div className="flex items-center gap-2 p-2.5 rounded-md bg-err-soft text-[13px] text-err">
                  <ShieldAlert className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>{t('confirm.adminOnly')}</span>
                </div>
              )}
              {/* UNDO notice for deletes */}
              {!secondConfirm && confirmModal.data?.action_type === 'DELETE' && (
                <div className="flex items-center gap-2 p-2.5 rounded-md bg-info-soft text-[13px] text-info">
                  <RotateCcw className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>{t('confirm.undoNote')}</span>
                </div>
              )}
              {confirmModal.data?.query && (
                <div className="bg-brand-deep p-3 rounded-md overflow-x-auto">
                  <code className="text-[12px] font-mono text-ok whitespace-pre-wrap break-words">
                    {confirmModal.data.query}
                  </code>
                </div>
              )}
            </div>
            <div className="p-4 border-t border-line bg-sunken flex justify-end gap-3">
              <button onClick={() => setConfirmModal({ isOpen: false, data: null })}
                className="btn btn-ghost btn-sm" disabled={isLoading}>
                {t('confirm.cancel')}
              </button>
              {!secondConfirm ? (
                <button onClick={() => setSecondConfirm(true)}
                  disabled={confirmModal.data?.role_restricted === 'Admin' && String(role).toLowerCase() !== 'admin'}
                  className="btn btn-accent btn-sm">
                  {t('confirm.proceed')}
                </button>
              ) : (
                <button onClick={executeConfirmed} disabled={isLoading}
                  className="btn btn-danger btn-sm">
                  {isLoading ? t('confirm.executing') : t('confirm.execute')}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Operation Result Modal ── */}
      {opResult && (
        <OperationResultModal 
          result={opResult} 
          onClose={() => setOpResult(null)} 
          onUndoDone={() => {
            fetchHistory();
            setFilesVersion(v => v + 1);
            showToast({ type: 'success', message: 'Operation successfully reverted!' });
          }}
        />
      )}
    </div>
  );
}

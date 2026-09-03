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
import CombinedStudentView from '../components/CombinedStudentView';
import LanguageSelector from '../components/LanguageSelector';
import { useTheme } from '../context/ThemeContext';
import { getPlaceholderText, getExampleQueries } from '../utils/kannadaTransliteration';
import { DeshKannadaProcessor } from '../utils/simpleKannadaInput';
import {
  LogOut, History, Database, Mic, Send, AlertTriangle,
  Download, FileText, Table as TableIcon,
  CheckCircle, BarChart2, ShieldAlert, Printer, Search, User, GraduationCap,
  PlusCircle, Trash2, Clock, ChevronRight, RotateCcw, Activity,
  Zap, RefreshCw, Moon, Sun, Bell, HardDrive, Languages
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
        <mark className="bg-yellow-200 text-yellow-900 rounded px-0.5 font-bold not-italic">
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
            ? <mark key={i} className="bg-yellow-200 text-yellow-900 rounded px-0.5 font-bold not-italic">{p.text}</mark>
            : <span key={i}>{p.text}</span>
        )}
      </span>
    );
  }
  return <span>{text}</span>;
}

// Match type badge colors
const MATCH_BADGE = {
  exact:    { label: 'EXACT',    cls: 'bg-green-100 text-green-700' },
  prefix:   { label: 'PREFIX',   cls: 'bg-blue-100 text-blue-700' },
  fuzzy:    { label: 'FUZZY',    cls: 'bg-amber-100 text-amber-700' },
  phonetic: { label: 'PHONETIC', cls: 'bg-purple-100 text-purple-700' },
};

// ── Generic Table ─────────────────────────────────────────────────────────────
function GenericTable({ data, responseLanguage = 'english' }) {
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

  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
          placeholder="Search results..." className="flex-1 px-3 py-1.5 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-blue-400" />
        <span className="text-xs text-slate-400">{filtered.length} rows</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              {headers.map(h => (
                <th key={h} onClick={() => toggleSort(h)}
                  className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer hover:bg-slate-100 whitespace-nowrap select-none">
                  {(responseLanguage === 'kannada' ? kannadaHeaders[h] : null) || h.replace(/_/g, ' ')} {sortCol === h ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {paged.map((row, i) => (
              <tr key={i} className="hover:bg-blue-50/30 transition-colors">
                {headers.map(h => (
                  <td key={h} className="px-4 py-2.5 text-slate-700 whitespace-nowrap">
                    {row[h] !== null && row[h] !== undefined ? String(row[h]) : <span className="text-slate-300">—</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-3">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
            className="px-3 py-1 text-xs rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-slate-50">Prev</button>
          <span className="text-xs text-slate-500">Page {page} of {totalPages}</span>
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            className="px-3 py-1 text-xs rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-slate-50">Next</button>
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
      showToast({ type: 'error', message: e.response?.data?.detail || 'Restore failed.' });
    } finally {
      setRestoring(null);
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center py-16 text-slate-400 gap-2">
      <div className="w-5 h-5 border-2 border-slate-300 border-t-blue-500 rounded-full animate-spin" />
      Loading deleted records...
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-slate-800">Restore Deleted Students</h2>
          <p className="text-xs text-slate-500 mt-0.5">Students deleted in the last 5 minutes can be restored.</p>
        </div>
        <button onClick={load} className="p-2 hover:bg-slate-100 rounded-lg transition-colors" title="Refresh">
          <RefreshCw className="w-4 h-4 text-slate-500" />
        </button>
      </div>

      {deleted.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-slate-400 gap-3">
          <div className="w-12 h-12 rounded-full bg-green-50 flex items-center justify-center">
            <CheckCircle className="w-6 h-6 text-green-400" />
          </div>
          <p className="text-sm font-medium">No recently deleted students</p>
          <p className="text-xs">Deleted students appear here for 5 minutes after deletion.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {deleted.map((rec) => {
            const isRestored = rec.restored === 1;
            const isRestoring = restoring === rec.restore_token;
            const secondsLeft = rec.undo_seconds_left || 0;
            const expired = secondsLeft <= 0;

            return (
              <div key={rec.id}
                className={`bg-white rounded-xl border p-4 flex items-center gap-4 transition-all
                  ${isRestored ? 'opacity-50 border-slate-200' : expired ? 'border-slate-200 opacity-60' : 'border-red-200 shadow-sm'}`}
              >
                {/* Avatar */}
                <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm flex-shrink-0
                  ${isRestored ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'}`}>
                  {(rec.student_name || rec.usn || '?').charAt(0).toUpperCase()}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-800 truncate">{rec.student_name || '—'}</p>
                  <p className="text-[11px] text-slate-400 font-mono">{rec.usn}</p>
                  <div className="flex items-center gap-3 mt-1 text-[10px] text-slate-400">
                    <span>Deleted by: <span className="font-medium text-slate-600">{rec.deleted_by}</span></span>
                    <span className="flex items-center gap-0.5">
                      <Clock className="w-2.5 h-2.5" />
                      {new Date(rec.deleted_at).toLocaleTimeString()}
                    </span>
                  </div>
                  {/* Countdown */}
                  {!isRestored && !expired && (
                    <div className="mt-1.5 h-1 bg-slate-100 rounded-full w-32">
                      <div
                        className="h-1 bg-amber-400 rounded-full transition-all duration-1000"
                        style={{ width: `${Math.min(100, (secondsLeft / 30) * 100)}%` }}
                      />
                    </div>
                  )}
                </div>

                {/* Action */}
                <div className="flex-shrink-0">
                  {isRestored ? (
                    <span className="flex items-center gap-1 text-xs text-green-600 font-semibold">
                      <CheckCircle className="w-3.5 h-3.5" /> Restored
                    </span>
                  ) : expired ? (
                    <span className="text-xs text-slate-400">Window expired</span>
                  ) : (
                    <button
                      onClick={() => handleRestore(rec)}
                      disabled={isRestoring}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white text-xs font-semibold rounded-lg transition-colors disabled:opacity-50"
                    >
                      <RotateCcw className={`w-3 h-3 ${isRestoring ? 'animate-spin' : ''}`} />
                      {isRestoring ? 'Restoring...' : 'Restore'}
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
  const { darkMode, toggleDark, theme, setTheme } = useTheme();
  const [role]     = useState(() => localStorage.getItem('role') || '');
  const [username] = useState(() => localStorage.getItem('username') || '');
  const [query, setQuery]           = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isLoading, setIsLoading]   = useState(false);
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

  useEffect(() => {
    if (!localStorage.getItem('token')) {
      navigate('/login');
      return;
    }
    fetchHistory();
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

    const timer = setTimeout(async () => {
      try {
        const res = await api.get(`/query/suggest?q=${encodeURIComponent(searchTerm)}`);
        const suggestions = res.data || [];
        setLiveSuggestions(suggestions);
        setLiveSearchTerm(searchTerm);
        setActiveSuggestion(-1);
        setShowLiveDropdown(suggestions.length > 0);
        if (suggestions.length > 0) {
          setNoMatchMsg('');
          setError('');
        }
      } catch (err) {
        console.error('Suggestion fetch failed', err);
      }
    }, delay);

    return () => clearTimeout(timer);
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

  // ── Print handler — compact, professional, no page breaks mid-section ────
  const handlePrint = () => {
    const content = document.getElementById('print-report-area');
    if (!content) return;
    const win = window.open('', '_blank', 'width=900,height=700');
    win.document.write(`<html><head><title>Student Report</title>
      <style>
        @page { margin: 12mm 14mm; size: A4 portrait; }
        * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; margin: 0; padding: 12px 16px; color: #111; font-size: 10pt; line-height: 1.35; }
        table { width: 100%; border-collapse: collapse; table-layout: fixed; page-break-inside: auto; }
        thead { display: table-header-group; }
        tr { page-break-inside: avoid; break-inside: avoid; }
        th { background: #1e3a5f; color: #fff; padding: 5px 7px; font-size: 9pt; border: 1px solid #2a5298; }
        td { padding: 4px 6px; font-size: 9pt; border: 1px solid #ddd; }
        .print-section { page-break-inside: avoid; break-inside: avoid; }
        .print-sig { page-break-inside: avoid; break-inside: avoid; }
        img { max-width: 56px; max-height: 56px; }
      </style>
      </head><body>${content.innerHTML}</body></html>`);
    win.document.close();
    win.focus();
    setTimeout(() => { win.print(); win.close(); }, 400);
  };

  // ── Query submit ─────────────────────────────────────────────────────────────
  const handleQuerySubmit = async (e) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;
    setShowLiveDropdown(false);
    setLiveSuggestions([]);
    setActiveSuggestion(-1);
    setIsLoading(true); setError(''); setResults(null); setSuggestion(null); setNoMatchMsg('');
    try {
      // Send original query + language context to backend
      // Backend will handle semantic translation if needed
      const payload = {
        natural_query: query.trim(),
        language: selectedLanguage,
        response_language: selectedLanguage === 'kannada' ? 'kannada' : (selectedLanguage === 'mixed' ? 'mixed' : 'english')
      };
      
      const res = await api.post('/query/generate', payload);
      
      if (res.data.action_required === 'confirm') {
        setConfirmModal({ isOpen: true, data: res.data });
        setSecondConfirm(false);
      } else {
        if (res.data.no_match_message) {
          setNoMatchMsg(res.data.no_match_message);
        }
        if (res.data.suggestion) {
          setSuggestion(res.data.suggestion);
        }
        if (res.data.auto_corrected) {
          setResults({ ...res.data, _query: query, intent: res.data.intent || 'full' });
        } else if (res.data.data?.length > 0) {
          setResults({ ...res.data, _query: query, intent: res.data.intent || 'full' });
        }
        fetchHistory();
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Query failed.');
    } finally {
      setIsLoading(false);
    }
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

    // 5. Execute immediately with language context
    setIsLoading(true);
    setError('');
    setResults(null);
    setSuggestion(null);
    setNoMatchMsg('');
    try {
      const payload = {
        natural_query: finalQuery,
        language: selectedLanguage,
        response_language: selectedLanguage === 'kannada' ? 'kannada' : (selectedLanguage === 'mixed' ? 'mixed' : 'english')
      };
      
      const res = await api.post('/query/generate', payload);
      if (res.data.action_required === 'confirm') {
        setConfirmModal({ isOpen: true, data: res.data });
        setSecondConfirm(false);
      } else {
        if (res.data.no_match_message) setNoMatchMsg(res.data.no_match_message);
        if (res.data.suggestion)       setSuggestion(res.data.suggestion);
        if (res.data.auto_corrected) {
          setResults({ ...res.data, _query: finalQuery, intent: res.data.intent || 'full' });
        } else if (res.data.data?.length > 0) {
          setResults({ ...res.data, _query: finalQuery, intent: res.data.intent || 'full' });
        }
        fetchHistory();
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Query failed.');
    } finally {
      setIsLoading(false);
    }
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
      setIsLoading(true); setError('');
      try {
        const payload = {
          natural_query: naturalQuery,
          language: selectedLanguage,
          response_language: selectedLanguage === 'kannada' ? 'kannada' : (selectedLanguage === 'mixed' ? 'mixed' : 'english')
        };
        const res = await api.post('/query/generate', payload);
        if (res.data.data?.length > 0) {
          setResults({ ...res.data, _query: naturalQuery, intent: res.data.intent || 'full' });
        }
        fetchHistory();
      } catch (err) {
        setError(getUserMessage(err, 'Something went wrong. Please try again.'));
      } finally {
        setIsLoading(false);
      }
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
    try {
      const res = await api.post('/query/execute', {
        query_dict: confirmModal.data.query_dict,
        original_query: confirmModal.data.original_query
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

  // ── Export ───────────────────────────────────────────────────────────────────
  const handleExport = async (format) => {
    if (!results?.data?.length) return;
    try {
      const res = await api.post(`/export/${format}`, results.data, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `results.${format === 'excel' ? 'xlsx' : format}`;
      document.body.appendChild(a); a.click(); a.remove();
    } catch { setError(`Export as ${format} failed.`); }
  };

  const data = results?.data || [];

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

  // Show CombinedStudentView when complete-profile intent OR single student with both data types
  const showCombined = data.length > 0 && (
    isCompleteProfileIntent ||
    (isSingleStudent && hasAcademic && hasPersonal)
  );
  const showGpa     = !showCombined && isGpaData(data);
  const showGeneric = !showCombined && !showGpa && data.length > 0;
  const showChart   = data.length > 0 && shouldShowChart(results?._query || '');

  // Sprint 2: Track response language for Kannada label support
  const responseLanguage = results?.response_language || 'english';


  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      {/* Hidden print area */}
      <div style={{ display: 'none' }} ref={printRef}>
        <PrintReport data={data} username={username} role={role} query={results?._query || ''} />
      </div>

      {/* ── Sidebar ── */}
      <div className="w-64 bg-slate-900 text-white flex flex-col shadow-2xl z-20 flex-shrink-0">
        {/* Sidebar header */}
        <div className="p-4 flex items-center gap-3 border-b border-slate-800">
          <div className="w-8 h-8 bg-blue-600 rounded-xl flex items-center justify-center flex-shrink-0">
            <Database className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="font-bold text-sm">AI Student DB</h1>
            <p className="text-[10px] text-slate-400">MySQL · v3.0</p>
          </div>
          <button
            onClick={toggleDark}
            className="p-1.5 rounded-lg hover:bg-slate-700 transition-colors flex-shrink-0"
            title={`Theme: ${theme ? theme.toUpperCase() : 'SYSTEM'} (Click to toggle)`}
          >
            {theme === 'light' && <Sun className="w-3.5 h-3.5 text-amber-400" />}
            {theme === 'dark' && <Moon className="w-3.5 h-3.5 text-blue-400" />}
            {theme === 'system' && <Zap className="w-3.5 h-3.5 text-purple-400" />}
          </button>
        </div>

        <div className="p-3 border-b border-slate-800 bg-slate-800/50">
          <span className="text-[10px] text-slate-500 uppercase font-semibold">Logged in as</span>
          <p className="text-sm text-slate-200 font-medium truncate">{username || 'User'}</p>
          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-blue-500/20 text-blue-400 border border-blue-500/20">{role}</span>
        </div>

        {/* Nav tabs */}
        <div className="p-2 border-b border-slate-800 space-y-1">
          {[
            ['query',      <Send className="w-3.5 h-3.5" />,      'Query Engine'],
            ['backup',     <HardDrive className="w-3.5 h-3.5" />, 'Database & Backup'],
            ['analytics',  <BarChart2 className="w-3.5 h-3.5" />, 'Analytics'],
            ['validation', <ShieldAlert className="w-3.5 h-3.5" />,'Validation'],
            ['activity',   <Activity className="w-3.5 h-3.5" />,   'Activity Logs'],
          ].map(([tab, icon, label]) => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors
                ${activeTab === tab
                  ? 'bg-blue-600 text-white shadow-sm shadow-blue-500/30'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}>
              {icon} {label}
            </button>
          ))}
        </div>

        {/* History */}
        <div className="flex-1 overflow-y-auto p-3 space-y-4">
          <div>
            <div className="flex items-center gap-2 mb-2 text-slate-400 px-1">
              <History className="w-3 h-3" />
              <span className="text-[10px] font-semibold uppercase tracking-wider">Recent Searches</span>
            </div>
            <div className="space-y-1">
              {history.map((h, i) => (
                <button key={i} onClick={() => { setQuery(h.natural_query); setActiveTab('query'); }}
                  className="w-full text-left p-2 rounded-lg hover:bg-slate-800 transition-colors">
                  <p className="text-xs text-slate-300 line-clamp-2">{h.natural_query}</p>
                </button>
              ))}
            </div>
          </div>

          {recentActivity.additions?.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2 text-green-400 px-1">
                <PlusCircle className="w-3 h-3" />
                <span className="text-[10px] font-semibold uppercase tracking-wider">Recently Added</span>
              </div>
              <div className="space-y-1">
                {recentActivity.additions.map((act, i) => (
                  <div key={i} className="p-2 rounded-lg bg-slate-800/50 border border-slate-700/50">
                    <p className="text-xs font-semibold text-slate-200">{act.student_name}</p>
                    <p className="text-[10px] text-slate-400 font-mono">{act.usn}</p>
                    <div className="flex items-center justify-between mt-1 text-[9px] text-slate-500">
                      <span>By: {act.added_by}</span>
                      <span className="flex items-center gap-0.5"><Clock className="w-2.5 h-2.5" /> {new Date(act.timestamp).toLocaleDateString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {recentActivity.deletions?.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2 text-red-400 px-1">
                <Trash2 className="w-3 h-3" />
                <span className="text-[10px] font-semibold uppercase tracking-wider">Recently Deleted</span>
              </div>
              <div className="space-y-1">
                {recentActivity.deletions.map((act, i) => (
                  <div key={i} className="p-2 rounded-lg bg-slate-800/50 border border-slate-700/50">
                    <p className="text-xs font-semibold text-slate-200">{act.student_name}</p>
                    <p className="text-[10px] text-slate-400 font-mono">{act.usn}</p>
                    <div className="flex items-center justify-between mt-1 text-[9px] text-slate-500">
                      <span>By: {act.deleted_by}</span>
                      <span className="flex items-center gap-0.5"><Clock className="w-2.5 h-2.5" /> {new Date(act.timestamp).toLocaleDateString()}</span>
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
                        className="mt-1.5 w-full flex items-center justify-center gap-1 py-1 text-[10px] font-semibold text-green-400 hover:text-green-300 hover:bg-green-900/30 rounded transition-colors border border-green-800/40"
                      >
                        <RotateCcw className="w-2.5 h-2.5" /> Restore
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="p-3 border-t border-slate-800">
          <button onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 py-2 text-xs text-slate-400 hover:text-white hover:bg-slate-800 rounded-xl transition-all">
            <LogOut className="w-3.5 h-3.5" /> Sign Out
          </button>
        </div>
      </div>

      {/* ── Main ── */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden relative">
        {/* Background */}
        <div className="absolute inset-0 pointer-events-none z-0">
          <div className="absolute inset-0 opacity-20 bg-no-repeat bg-center bg-cover"
            style={{ backgroundImage: "url('/college-bg.jpg')" }} />
          <div className="absolute inset-0 bg-white/70 dark:bg-slate-955/80 backdrop-blur-[2px]" />
        </div>

        <header className="h-12 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 flex items-center px-6 shadow-sm z-10 shrink-0 gap-3">
          <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
            {activeTab === 'query' ? 'Query Engine'
              : activeTab === 'backup' ? 'Database Reliability & Backup Center'
              : activeTab === 'analytics' ? 'Analytics Dashboard'
              : activeTab === 'activity' ? 'Audit & Activity Logs'
              : 'Data Validation'}
          </h2>
          <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded-full">MySQL</span>
          {results?.cached && <span className="px-2 py-0.5 text-xs bg-green-100 text-green-700 rounded-full">Cached</span>}
        </header>

        <main className="flex-1 overflow-y-auto p-5 relative z-10">
          <div className="max-w-5xl mx-auto space-y-4">
            {/* Institutional header */}
            {activeTab === 'query' && <ReportHeader showInDashboard={showHeader} />}

            {/* Upload notice */}
            {uploadNotice && (
              <div className="flex items-start gap-3 p-3 bg-green-50 border border-green-200 rounded-xl text-sm text-green-800">
                <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold">{uploadNotice.filename} — {uploadNotice.message}</p>
                  <p className="text-xs text-green-600 mt-0.5">
                    {uploadNotice.rows_parsed} parsed · New {uploadNotice.students_added ?? 0} · Updated {uploadNotice.students_updated ?? 0} · Unchanged {uploadNotice.students_unchanged ?? 0} · Dup {uploadNotice.duplicate_rows ?? 0} · Invalid {uploadNotice.invalid_rows ?? 0} · Saved {uploadNotice.students_saved} students / {uploadNotice.marks_saved} marks
                  </p>
                  {uploadNotice.column_mapping && Object.keys(uploadNotice.column_mapping).length > 0 && (
                    <p className="text-xs text-green-600 mt-0.5">
                      Columns mapped: {Object.entries(uploadNotice.column_mapping).map(([k,v]) => `${k}→${v}`).join(', ')}
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

            {/* ── Query Tab ── */}
            {activeTab === 'query' && (
              <>
                <FileExplorer onDataLoaded={(info) => { 
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
                      message: info.message
                    });
                  }
                }} />

                {/* Query input */}
                <div className="relative z-50">
                  {/* Language and Voice Selectors */}
                  <div className="flex items-center gap-3 mb-3">
                    {/* Language Selector */}
                    <LanguageSelector 
                      selectedLanguage={selectedLanguage}
                      onLanguageChange={handleLanguageChange}
                    />
                    
                    {/* Voice Language Selector */}
                    <div className="relative">
                      <select
                        value={voiceLanguage}
                        onChange={(e) => handleVoiceLanguageChange(e.target.value)}
                        className="appearance-none pl-9 pr-8 py-2 text-sm font-medium bg-white border border-slate-200 rounded-lg hover:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-all cursor-pointer text-slate-700"
                        title="Select voice input language"
                      >
                        <option value="en-US">🎤 English</option>
                        <option value="kn-IN">🎤 ಕನ್ನಡ</option>
                        <option value="en-IN">🎤 English (India)</option>
                      </select>
                      <div className="absolute left-3 top-1/2 transform -translate-y-1/2 pointer-events-none">
                        <Mic className="w-4 h-4 text-slate-400" />
                      </div>
                      <div className="absolute right-2 top-1/2 transform -translate-y-1/2 pointer-events-none">
                        <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>
                    </div>
                    
                    {/* Language indicator badge */}
                    {selectedLanguage !== 'english' && (
                      <div className="flex-1 flex items-center gap-2">
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-gradient-to-r from-orange-50 to-amber-50 text-orange-700 border border-orange-200">
                          <span className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-pulse"></span>
                          {selectedLanguage === 'kannada' ? 'ಕನ್ನಡ Mode' : 'Mixed Language Mode'}
                        </span>
                      </div>
                    )}
                  </div>
                  
                  <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-2 focus-within:ring-2 focus-within:ring-blue-500 transition-all">
                    <form onSubmit={handleQuerySubmit} className="relative flex items-end">
                      <textarea 
                        ref={textareaRef}
                        value={query} 
                        onChange={handleQueryChange}
                        placeholder={getPlaceholderText(selectedLanguage)}
                        className="w-full resize-none p-4 pb-12 outline-none text-slate-700 placeholder-slate-400 bg-transparent min-h-[90px] text-sm"
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
                      <div className="absolute bottom-3 left-3 flex items-center gap-2">
                        <button type="button" onClick={toggleListen}
                          className={`p-2 rounded-xl transition-all ${isListening ? 'bg-red-100 text-red-600 animate-pulse' : 'bg-slate-100 text-slate-500 hover:bg-blue-50 hover:text-blue-600'}`}
                          title={`Voice input (${voiceLanguage === 'kn-IN' ? 'Kannada' : 'English'})`}>
                          <Mic className="w-4 h-4" />
                        </button>
                        {isListening && (
                          <span className="text-xs text-red-500 animate-pulse font-medium">
                            {voiceLanguage === 'kn-IN' ? 'ಆಲಿಸುತ್ತಿದೆ...' : 'Listening...'}
                          </span>
                        )}
                        {selectedLanguage === 'kannada' && !isListening && (
                          <div className="text-xs bg-green-50 text-green-700 px-3 py-1.5 rounded-lg border border-green-200 font-medium flex items-center gap-2">
                            <Languages className="w-3.5 h-3.5" />
                            <span>✨ Auto-convert: Type English → Get Kannada instantly!</span>
                          </div>
                        )}
                      </div>
                      <div className="absolute bottom-3 right-3">
                        <button type="submit" disabled={isLoading || !query.trim()}
                          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-xl text-sm font-medium transition-all shadow-md shadow-blue-500/20 disabled:opacity-50">
                          {isLoading
                            ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            : <><Send className="w-3.5 h-3.5" /> Run Query</>}
                        </button>
                      </div>
                    </form>
                    
                    {/* Kannada Transliteration Suggestions (Desh Kannada style) */}
                    {selectedLanguage === 'kannada' && kannadaSuggestions.length > 0 && (
                      <div className="absolute top-full left-0 right-0 mt-1 bg-white border-2 border-orange-300 rounded-xl shadow-2xl z-[100] overflow-hidden">
                        <div className="px-3 py-2 bg-gradient-to-r from-orange-50 to-amber-50 border-b border-orange-100 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Languages className="w-3.5 h-3.5 text-orange-600" />
                            <span className="text-xs font-bold text-orange-700">
                              ಕನ್ನಡ Suggestions (Space or Click to select)
                            </span>
                          </div>
                          <span className="text-[10px] text-slate-500 italic">↑↓ navigate · Space/Enter select</span>
                        </div>
                        <div className="max-h-48 overflow-y-auto">
                          {kannadaSuggestions.map((suggestion, idx) => (
                            <button
                              key={idx}
                              onClick={() => applySuggestion(idx)}
                              onMouseEnter={() => setActiveSuggestion(idx)}
                              className={`w-full text-left px-4 py-3 transition-all border-b border-orange-50 last:border-0
                                ${idx === activeSuggestion 
                                  ? 'bg-orange-100 border-l-4 border-l-orange-500 font-semibold' 
                                  : 'hover:bg-orange-50'}`}
                            >
                              <span className="text-lg text-slate-800">{suggestion}</span>
                              {idx === 0 && (
                                <span className="ml-2 text-xs text-orange-600 font-medium">(Press Space)</span>
                              )}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Language-aware example queries */}
                  {!query && !results && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      <span className="text-xs text-slate-400 font-medium">Try:</span>
                      {getExampleQueries(selectedLanguage).map((example, idx) => (
                        <button
                          key={idx}
                          onClick={() => setQuery(example)}
                          className="px-3 py-1.5 text-xs bg-slate-50 hover:bg-blue-50 border border-slate-200 hover:border-blue-300 rounded-lg text-slate-600 hover:text-blue-700 transition-all"
                        >
                          {example}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Live Suggestions Dropdown */}
                  {showLiveDropdown && liveSuggestions.length > 0 && (
                    <div
                      ref={dropdownRef}
                      className="absolute top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-2xl z-[100] overflow-hidden"
                      style={{ animation: 'slideDown 0.15s ease-out' }}
                    >
                      {/* Header */}
                      <div className="px-3 py-2 bg-gradient-to-r from-blue-50 to-indigo-50 border-b border-slate-100 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Search className="w-3 h-3 text-blue-500" />
                          <span className="text-[10px] font-bold text-blue-600 uppercase tracking-wider">
                            {liveSuggestions.length} suggestion{liveSuggestions.length !== 1 ? 's' : ''} for &ldquo;{liveSearchTerm}&rdquo;
                          </span>
                        </div>
                        <span className="text-[10px] text-slate-400 italic">↑↓ navigate · Enter select · Esc close</span>
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
                              onClick={() => {
                                selectSuggestionAndRun(s);
                              }}
                              onMouseEnter={() => setActiveSuggestion(idx)}
                              className={`w-full flex items-center justify-between px-4 py-3 text-left transition-all border-b border-slate-50 last:border-0 group
                                ${isActive ? 'bg-blue-50 border-l-2 border-l-blue-500' : 'hover:bg-slate-50'}`}
                            >
                              {/* Avatar + name */}
                              <div className="flex items-center gap-3 min-w-0">
                                <div className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-sm flex-shrink-0 transition-colors
                                  ${isActive ? 'bg-blue-600 text-white' : 'bg-blue-100 text-blue-600 group-hover:bg-blue-200'}`}>
                                  {(s.name || '?').charAt(0).toUpperCase()}
                                </div>
                                <div className="min-w-0">
                                  <p className="text-sm font-semibold text-slate-800 truncate">
                                    <HighlightMatch text={s.name || ''} query={liveSearchTerm} />
                                  </p>
                                  <p className="text-[11px] text-slate-400 font-mono">{s.usn}</p>
                                </div>
                              </div>

                              {/* Right side: badge + score + arrow */}
                              <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ${badge.cls}`}>
                                  {badge.label}
                                </span>
                                <span className="text-[10px] text-slate-400 font-mono w-8 text-right">{pct}%</span>
                                <ChevronRight className={`w-4 h-4 transition-all ${isActive ? 'text-blue-500 translate-x-0.5' : 'text-slate-300'}`} />
                              </div>
                            </button>
                          );
                        })}
                      </div>

                      {/* Footer hint */}
                      <div className="px-3 py-1.5 bg-slate-50 border-t border-slate-100 text-center">
                        <span className="text-[9px] text-slate-400">
                          Press <kbd className="px-1 py-0.5 bg-white border border-slate-200 rounded text-[9px]">Enter</kbd> to search · Click to view student
                        </span>
                      </div>
                    </div>
                  )}
                  <style>{`@keyframes slideDown { from { opacity:0; transform:translateY(-6px); } to { opacity:1; transform:translateY(0); } }`}</style>
                </div>

                {/* Error — suppress while live suggestions are showing (user still typing) */}
                {error && !showLiveDropdown && (
                  <div className="bg-red-50 text-red-700 p-4 rounded-xl flex items-start gap-3 border border-red-100">
                    <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="font-semibold text-sm">Query Failed</p>
                      <p className="text-sm mt-0.5 text-red-600">{error}</p>
                    </div>
                  </div>
                )}

                {/* No-match message — only show when NOT typing (no live suggestions active) */}
                {noMatchMsg && !suggestion && !showLiveDropdown && (
                  <div className="flex items-start gap-3 p-4 bg-slate-50 border border-slate-200 rounded-2xl">
                    <AlertTriangle className="w-5 h-5 text-slate-400 flex-shrink-0 mt-0.5" />
                    <p className="text-sm text-slate-600 font-medium">{noMatchMsg}</p>
                  </div>
                )}

                {/* Suggestion panel — all types: suggestion | possible_matches | multiple_match */}
                {suggestion && !results?.auto_corrected && (
                  <SuggestionPanel
                    suggestion={suggestion}
                    onYes={handleSuggestionYes}
                    onNo={handleSuggestionNo}
                  />
                )}

                {/* Auto-correction notice */}
                {results?.auto_corrected && results?.correction_message && (
                  <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-200 rounded-xl text-sm text-blue-800">
                    <Search className="w-4 h-4 text-blue-500 flex-shrink-0" />
                    <span>{results.correction_message}</span>
                  </div>
                )}
                {/* Results */}
                {results && (
                  <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                    <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                      <div className="flex items-center gap-3">
                        <div className="p-1.5 bg-green-100 text-green-700 rounded-lg">
                          <TableIcon className="w-4 h-4" />
                        </div>
                        <div>
                          <h3 className="text-sm font-bold text-slate-800">
                            {data.length > 0 ? `${data.length} record(s)` : 'Operation Complete'}
                          </h3>
                          {results.execution_time != null && (
                            <p className="text-xs text-slate-400">{(results.execution_time * 1000).toFixed(1)}ms{results.cached ? ' · from cache' : ''}</p>
                          )}
                        </div>
                      </div>
                      {data.length > 0 && (
                        <div className="flex items-center gap-1.5 flex-wrap">
                          {/* Intent badge */}
                          {results?.intent && results.intent !== 'full' && (
                            <span className={`inline-flex items-center gap-1 px-2 py-1 text-[10px] font-bold rounded-full border ${
                              results.intent === 'personal'
                                ? 'bg-purple-50 text-purple-700 border-purple-200'
                                : results.intent === 'complete_profile'
                                ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                                : 'bg-blue-50 text-blue-700 border-blue-200'
                            }`}>
                              {results.intent === 'personal'
                                ? <><User className="w-3 h-3" /> Personal View</>
                                : results.intent === 'complete_profile'
                                ? <><GraduationCap className="w-3 h-3" /> Complete Profile</>
                                : <><GraduationCap className="w-3 h-3" /> Academic View</>}
                            </span>
                          )}
                          {/* Kannada indicator */}
                          {responseLanguage !== 'english' && (
                            <span className="inline-flex items-center gap-1 px-2 py-1 text-[10px] font-bold rounded-full border bg-orange-50 text-orange-700 border-orange-200">
                              ಕ•KN
                            </span>
                          )}
                          {[['csv',   <FileText className="w-3 h-3" />,    'CSV'],
                            ['excel', <TableIcon className="w-3 h-3" />,   'Excel'],
                            ['pdf',   <Download className="w-3 h-3" />,    'PDF'],
                          ].map(([fmt, icon, label]) => (
                            <button key={fmt} onClick={() => handleExport(fmt)}
                              className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors">
                              {icon} {label}
                            </button>
                          ))}
                          <button onClick={handlePrint}
                            className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50 rounded-lg border border-indigo-200 transition-colors">
                            <Printer className="w-3 h-3" /> Print Report
                          </button>
                        </div>
                      )}
                    </div>

                    {results.query && (
                      <div className="bg-slate-900 px-5 py-2 border-b border-slate-800">
                        <p className="text-xs font-mono text-green-400 break-all">{results.query}</p>
                      </div>
                    )}

                    <div className="p-5 space-y-4">
                      {showCombined && <CombinedStudentView data={data} responseLanguage={responseLanguage} />}
                      {showGpa && <GpaTable data={data} />}
                      {showGeneric && <GenericTable data={data} responseLanguage={selectedLanguage} />}
                      {showChart && <ResultChart data={data} query={results._query} />}
                      {data.length === 0 && !suggestion && (
                        <div className="flex items-center justify-center py-8 text-slate-400 text-sm">
                          {results.message || 'No records found.'}
                        </div>
                      )}
                      {/* Printable report (hidden, activated on print) */}
                      <div id="print-report-area" style={{ display: 'none' }}>
                        <PrintReport data={data} username={username} role={role} query={results._query || ''} />
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </main>
      </div>

      {/* ── Confirm Modal ── */}
      {confirmModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full overflow-hidden">
            <div className={`p-5 ${secondConfirm ? 'bg-red-50' : 'bg-amber-50'} border-b border-slate-100`}>
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-full ${secondConfirm ? 'bg-red-100 text-red-600' : 'bg-amber-100 text-amber-600'}`}>
                  <AlertTriangle className="w-5 h-5" />
                </div>
                <h3 className={`text-base font-bold ${secondConfirm ? 'text-red-800' : 'text-amber-800'}`}>
                  {secondConfirm ? 'Final Warning — Cannot Undo' : `Confirm ${confirmModal.data?.action_type}`}
                </h3>
              </div>
            </div>
            <div className="p-5 space-y-3">
              <p className="text-slate-600 text-sm">
                {secondConfirm
                  ? 'This action is permanent. Proceed?'
                  : `You are about to execute a ${confirmModal.data?.action_type} operation.`}
              </p>
              {/* UNDO notice for deletes */}
              {!secondConfirm && confirmModal.data?.action_type === 'DELETE' && (
                <div className="flex items-center gap-2 p-2.5 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-700">
                  <RotateCcw className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>An <strong>UNDO</strong> option will appear for 30 seconds after deletion.</span>
                </div>
              )}
              <div className="bg-slate-900 p-3 rounded-lg overflow-x-auto">
                <code className="text-xs font-mono text-green-400 whitespace-pre-wrap">
                  {confirmModal.data?.query}
                </code>
              </div>
            </div>
            <div className="p-4 border-t border-slate-100 bg-slate-50 flex justify-end gap-3">
              <button onClick={() => setConfirmModal({ isOpen: false, data: null })}
                className="px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200 rounded-lg transition-colors" disabled={isLoading}>
                Cancel
              </button>
              {!secondConfirm ? (
                <button onClick={() => setSecondConfirm(true)}
                  className="px-4 py-2 text-sm font-medium text-white bg-amber-600 hover:bg-amber-700 rounded-lg transition-colors">
                  Yes, proceed
                </button>
              ) : (
                <button onClick={executeConfirmed} disabled={isLoading}
                  className="px-4 py-2 text-sm font-bold text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors flex items-center gap-2">
                  {isLoading ? 'Executing...' : 'Confirm & Execute'}
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
            showToast({ type: 'success', message: 'Operation successfully reverted!' });
          }}
        />
      )}
    </div>
  );
}

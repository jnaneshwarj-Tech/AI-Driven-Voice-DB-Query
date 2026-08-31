import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import FileExplorer from '../components/FileExplorer';
import GpaTable from '../components/GpaTable';
import ResultChart from '../components/ResultChart';
import AnalyticsDashboard from '../components/AnalyticsDashboard';
import ValidationDashboard from '../components/ValidationDashboard';
import {
  LogOut, History, Database, Mic, Send, AlertTriangle,
  Download, FileText, Table as TableIcon, FileJson,
  CheckCircle, BarChart2, ShieldAlert, RefreshCw
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

// ── Generic Table ─────────────────────────────────────────────────────────────
function GenericTable({ data }) {
  const [search, setSearch] = useState('');
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState('asc');
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

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
                  {h.replace(/_/g, ' ')} {sortCol === h ? (sortDir === 'asc' ? '↑' : '↓') : ''}
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

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function Dashboard() {
  const navigate = useNavigate();
  const [role]     = useState(() => localStorage.getItem('role') || '');
  const [username] = useState(() => localStorage.getItem('username') || '');
  const [query, setQuery]           = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isLoading, setIsLoading]   = useState(false);
  const [results, setResults]       = useState(null);
  const [error, setError]           = useState('');
  const [history, setHistory]       = useState([]);
  const [confirmModal, setConfirmModal] = useState({ isOpen: false, data: null });
  const [secondConfirm, setSecondConfirm] = useState(false);
  const [uploadNotice, setUploadNotice] = useState(null);
  const [activeTab, setActiveTab]   = useState('query'); // query | analytics | validation
  const recRef = useRef(null);

  useEffect(() => {
    if (!localStorage.getItem('token')) navigate('/login');
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    try { const r = await api.get('/query/history?limit=10'); setHistory(r.data); } catch {}
  };

  const handleLogout = () => {
    localStorage.clear(); navigate('/login');
  };

  // ── Voice input ─────────────────────────────────────────────────────────────
  const toggleListen = () => {
    if (isListening) { recRef.current?.stop(); setIsListening(false); return; }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { setError('Speech recognition not supported in this browser.'); return; }
    const rec = new SR();
    recRef.current = rec;
    rec.continuous = false; rec.interimResults = false; rec.lang = 'en-US';
    rec.onstart  = () => setIsListening(true);
    rec.onresult = (e) => { setQuery(e.results[0][0].transcript); setIsListening(false); };
    rec.onerror  = (e) => { setIsListening(false); setError('Mic error: ' + e.error); };
    rec.onend    = () => setIsListening(false);
    rec.start();
  };

  // ── Query submit ─────────────────────────────────────────────────────────────
  const handleQuerySubmit = async (e) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;
    setIsLoading(true); setError(''); setResults(null);
    try {
      const res = await api.post('/query/generate', { natural_query: query });
      if (res.data.action_required === 'confirm') {
        setConfirmModal({ isOpen: true, data: res.data });
        setSecondConfirm(false);
      } else {
        setResults({ ...res.data, _query: query });
        fetchHistory();
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Query failed.');
    } finally {
      setIsLoading(false);
    }
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
      fetchHistory();
    } catch (err) {
      setError(err.response?.data?.detail || 'Execution failed.');
      setConfirmModal({ isOpen: false, data: null });
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
  const showGpa     = isGpaData(data);
  const showGeneric = !showGpa && data.length > 0;
  const showChart   = data.length > 0 && shouldShowChart(results?._query || '');

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      {/* ── Sidebar ── */}
      <div className="w-64 bg-slate-900 text-white flex flex-col shadow-2xl z-20 flex-shrink-0">
        <div className="p-4 flex items-center gap-3 border-b border-slate-800">
          <div className="w-8 h-8 bg-blue-600 rounded-xl flex items-center justify-center flex-shrink-0">
            <Database className="w-4 h-4 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-sm">AI Student DB</h1>
            <p className="text-[10px] text-slate-400">MySQL · v3.0</p>
          </div>
        </div>

        <div className="p-3 border-b border-slate-800 bg-slate-800/50">
          <span className="text-[10px] text-slate-500 uppercase font-semibold">Logged in as</span>
          <p className="text-sm text-slate-200 font-medium truncate">{username || 'User'}</p>
          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-blue-500/20 text-blue-400 border border-blue-500/20">{role}</span>
        </div>

        {/* Nav tabs */}
        <div className="p-2 border-b border-slate-800 space-y-1">
          {[
            ['query', <Send className="w-3.5 h-3.5" />, 'Query Engine'],
            ['analytics', <BarChart2 className="w-3.5 h-3.5" />, 'Analytics'],
            ['validation', <ShieldAlert className="w-3.5 h-3.5" />, 'Validation'],
          ].map(([tab, icon, label]) => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors
                ${activeTab === tab ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}>
              {icon} {label}
            </button>
          ))}
        </div>

        {/* History */}
        <div className="flex-1 overflow-y-auto p-3">
          <div className="flex items-center gap-2 mb-2 text-slate-400 px-1">
            <History className="w-3 h-3" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">Recent Queries</span>
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
          <div className="absolute inset-0 bg-white/70" />
        </div>

        <header className="h-12 bg-white border-b border-slate-200 flex items-center px-6 shadow-sm z-10 shrink-0 gap-3">
          <h2 className="text-sm font-semibold text-slate-800">
            {activeTab === 'query' ? 'Query Engine' : activeTab === 'analytics' ? 'Analytics Dashboard' : 'Data Validation'}
          </h2>
          <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded-full">MySQL</span>
          {results?.cached && <span className="px-2 py-0.5 text-xs bg-green-100 text-green-700 rounded-full">Cached</span>}
        </header>

        <main className="flex-1 overflow-y-auto p-5 relative z-10">
          <div className="max-w-5xl mx-auto space-y-4">

            {/* Upload notice */}
            {uploadNotice && (
              <div className="flex items-start gap-3 p-3 bg-green-50 border border-green-200 rounded-xl text-sm text-green-800">
                <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold">{uploadNotice.filename} — {uploadNotice.message}</p>
                  <p className="text-xs text-green-600 mt-0.5">
                    {uploadNotice.rows_parsed} rows · {uploadNotice.students_saved} students · {uploadNotice.marks_saved} marks
                  </p>
                  {uploadNotice.column_mapping && Object.keys(uploadNotice.column_mapping).length > 0 && (
                    <p className="text-xs text-green-600 mt-0.5">
                      Columns mapped: {Object.entries(uploadNotice.column_mapping).map(([k,v]) => `${k}→${v}`).join(', ')}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* ── Analytics Tab ── */}
            {activeTab === 'analytics' && <AnalyticsDashboard />}

            {/* ── Validation Tab ── */}
            {activeTab === 'validation' && <ValidationDashboard />}

            {/* ── Query Tab ── */}
            {activeTab === 'query' && (
              <>
                <FileExplorer onDataLoaded={(info) => { setUploadNotice(info); setTimeout(() => setUploadNotice(null), 8000); }} />

                {/* Query input */}
                <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-2 focus-within:ring-2 focus-within:ring-blue-500 transition-all">
                  <form onSubmit={handleQuerySubmit} className="relative flex items-end">
                    <textarea value={query} onChange={e => setQuery(e.target.value)}
                      placeholder='Ask anything... "Show marks of Manoj", "Top 10 students of sem 3", "CGPA of all students"'
                      className="w-full resize-none p-4 pb-12 outline-none text-slate-700 placeholder-slate-400 bg-transparent min-h-[90px] text-sm"
                      onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleQuerySubmit(); } }} />
                    <div className="absolute bottom-3 left-3 flex items-center gap-2">
                      <button type="button" onClick={toggleListen}
                        className={`p-2 rounded-xl transition-all ${isListening ? 'bg-red-100 text-red-600 animate-pulse' : 'bg-slate-100 text-slate-500 hover:bg-blue-50 hover:text-blue-600'}`}>
                        <Mic className="w-4 h-4" />
                      </button>
                      {isListening && <span className="text-xs text-red-500 animate-pulse font-medium">Listening...</span>}
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
                </div>

                {/* Error */}
                {error && (
                  <div className="bg-red-50 text-red-700 p-4 rounded-xl flex items-start gap-3 border border-red-100">
                    <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="font-semibold text-sm">Query Failed</p>
                      <p className="text-sm mt-0.5 text-red-600">{error}</p>
                    </div>
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
                        <div className="flex items-center gap-1.5">
                          {[['csv', <FileText className="w-3 h-3" />, 'CSV'],
                            ['excel', <TableIcon className="w-3 h-3" />, 'Excel'],
                            ['pdf', <Download className="w-3 h-3" />, 'PDF'],
                            ['json', <FileJson className="w-3 h-3" />, 'JSON']
                          ].map(([fmt, icon, label]) => (
                            <button key={fmt} onClick={() => handleExport(fmt)}
                              className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors">
                              {icon} {label}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    {results.query && (
                      <div className="bg-slate-900 px-5 py-2 border-b border-slate-800">
                        <p className="text-xs font-mono text-green-400 break-all">{results.query}</p>
                      </div>
                    )}

                    <div className="p-5 space-y-4">
                      {showGpa && <GpaTable data={data} />}
                      {showGeneric && <GenericTable data={data} />}
                      {showChart && <ResultChart data={data} query={results._query} />}
                      {data.length === 0 && (
                        <div className="flex items-center justify-center py-8 text-slate-400 text-sm">
                          {results.message || 'No records found.'}
                        </div>
                      )}
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
                {secondConfirm ? 'This action is permanent. Proceed?' : `You are about to execute a ${confirmModal.data?.action_type} operation.`}
              </p>
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
    </div>
  );
}

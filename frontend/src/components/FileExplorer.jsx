import { useState, useRef, useEffect } from 'react';
import api from '../services/api';
import {
  Upload, FileText, FileSpreadsheet, File, Image,
  Trash2, RefreshCw, ChevronDown, ChevronRight, Eye,
  Database, Clock, CheckCircle2, AlertCircle
} from 'lucide-react';

const FILE_ICONS = {
  csv: <FileSpreadsheet className="w-4 h-4 text-green-500" />,
  xlsx: <FileSpreadsheet className="w-4 h-4 text-emerald-600" />,
  xls: <FileSpreadsheet className="w-4 h-4 text-emerald-600" />,
  pdf: <FileText className="w-4 h-4 text-red-500" />,
  txt: <FileText className="w-4 h-4 text-slate-400" />,
  png: <Image className="w-4 h-4 text-purple-500" />,
  jpg: <Image className="w-4 h-4 text-purple-500" />,
  jpeg: <Image className="w-4 h-4 text-purple-500" />,
};

function getIcon(filename) {
  const ext = filename?.split('.').pop()?.toLowerCase();
  return FILE_ICONS[ext] || <File className="w-4 h-4 text-slate-400" />;
}

function formatBytes(b) {
  if (!b) return '—';
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

export default function FileExplorer({ onDataLoaded }) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [updatingDb, setUpdatingDb] = useState(null); // filename being updated
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(null);
  const [previewData, setPreviewData] = useState({});
  const [loadingPreview, setLoadingPreview] = useState(null);
  const [isOpen, setIsOpen] = useState(true);
  const [successMsg, setSuccessMsg] = useState('');
  const inputRef = useRef();

  const fetchFiles = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/files/list');
      setFiles(res.data);
    } catch {
      setError('Failed to load files.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchFiles(); }, []);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError('');
    setSuccessMsg('');
    const form = new FormData();
    form.append('file', file);
    try {
      await api.post('/files/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      await fetchFiles();
      setSuccessMsg(`"${file.name}" uploaded. Click "Update Database" to save data.`);
      setTimeout(() => setSuccessMsg(''), 6000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed.');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleUpdateDb = async (filename) => {
    setUpdatingDb(filename);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.post(`/files/update-db/${encodeURIComponent(filename)}`);
      await fetchFiles();
      setSuccessMsg(res.data.message || 'File successfully updated to database.');
      setTimeout(() => setSuccessMsg(''), 6000);
      if (onDataLoaded) onDataLoaded(res.data);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail && typeof detail === 'object') {
        const lines = [
          detail.message || 'Import rejected.',
          detail.invalid_row_count != null ? `Invalid rows: ${detail.invalid_row_count}` : null,
          detail.rows_parsed != null ? `Parsed: ${detail.rows_parsed}` : null,
        ].filter(Boolean);
        const sample = (detail.rejected_rows || detail.invalid_rows || []).slice(0, 3)
          .map(r => `Row ${r.row_number || r.row_index}: ${r.reason || (r.errors || []).join('; ')}`)
          .filter(Boolean);
        setError([...lines, ...sample].join(' | '));
      } else {
        setError(detail || 'Database update failed. Check file format.');
      }
    } finally {
      setUpdatingDb(null);
    }
  };

  const handlePreview = async (filename) => {
    if (expanded === filename) { setExpanded(null); return; }
    setExpanded(filename);
    if (previewData[filename]) return;
    setLoadingPreview(filename);
    try {
      const res = await api.get(`/files/parsed/${encodeURIComponent(filename)}`);
      setPreviewData(prev => ({ ...prev, [filename]: res.data }));
    } catch {
      setPreviewData(prev => ({ ...prev, [filename]: [] }));
    } finally {
      setLoadingPreview(null);
    }
  };

  const handleDelete = async (filename) => {
    if (!window.confirm(`Delete "${filename}" and all its data?`)) return;
    if (!window.confirm(`Are you sure? This cannot be undone.`)) return;
    try {
      await api.delete(`/files/delete/${encodeURIComponent(filename)}`);
      setFiles(f => f.filter(x => x.filename !== filename));
      setPreviewData(prev => { const n = { ...prev }; delete n[filename]; return n; });
      if (expanded === filename) setExpanded(null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Delete failed.');
    }
  };

  const renderPreviewTable = (data) => {
    if (!data || data.length === 0) return <p className="text-xs text-slate-400 p-3">No preview data.</p>;
    const first = data[0];
    if (first.type === 'text' || first.type === 'ocr_text') {
      return (
        <div className="p-3 text-xs text-slate-600 whitespace-pre-wrap max-h-40 overflow-y-auto bg-slate-50 rounded">
          {first.content}
        </div>
      );
    }
    const headers = Object.keys(first);
    return (
      <div className="overflow-x-auto max-h-48">
        <table className="w-full text-xs">
          <thead className="bg-slate-100 sticky top-0">
            <tr>{headers.map(h => <th key={h} className="px-3 py-1.5 text-left text-slate-500 font-semibold whitespace-nowrap">{h}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.slice(0, 20).map((row, i) => (
              <tr key={i} className="hover:bg-slate-50">
                {headers.map(h => {
                  const val = row[h];
                  const display = val === null || val === undefined
                    ? <span className="text-slate-300">—</span>
                    : typeof val === 'object'
                      ? <span className="text-blue-500 italic">[{Array.isArray(val) ? `${val.length} items` : 'object'}]</span>
                      : String(val);
                  return <td key={h} className="px-3 py-1.5 text-slate-700 whitespace-nowrap">{display}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {data.length > 20 && <p className="text-xs text-slate-400 p-2">Showing 20 of {data.length} rows</p>}
      </div>
    );
  };

  const pendingCount = files.filter(f => f.db_status === 'pending').length;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-3 bg-slate-50 border-b border-slate-200 cursor-pointer"
        onClick={() => setIsOpen(o => !o)}
      >
        <div className="flex items-center gap-2">
          {isOpen ? <ChevronDown className="w-4 h-4 text-slate-500" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
          <span className="text-sm font-semibold text-slate-700">File Explorer</span>
          <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-600 rounded-full">{files.length} files</span>
          {pendingCount > 0 && (
            <span className="px-2 py-0.5 text-xs bg-amber-100 text-amber-700 rounded-full">{pendingCount} pending</span>
          )}
        </div>
        <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
          <button onClick={fetchFiles} className="p-1.5 hover:bg-slate-200 rounded-lg transition-colors" title="Refresh">
            <RefreshCw className={`w-3.5 h-3.5 text-slate-500 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {pendingCount > 0 && (
            <button
              onClick={async () => {
                const pendings = files.filter(f => f.db_status === 'pending' && !f.cache_expired);
                for (const p of pendings) await handleUpdateDb(p.filename);
              }}
              disabled={!!updatingDb}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50"
            >
              <Database className="w-3.5 h-3.5" />
              {updatingDb ? 'Updating...' : `Update All (${pendingCount})`}
            </button>
          )}
          <button
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            <Upload className="w-3.5 h-3.5" />
            {uploading ? 'Uploading...' : 'Upload File'}
          </button>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept=".csv,.xlsx,.xls,.pdf,.txt,.png,.jpg,.jpeg"
            onChange={handleUpload}
          />
        </div>
      </div>

      {isOpen && (
        <div>
          {/* Success message */}
          {successMsg && (
            <div className="mx-4 mt-3 p-2.5 bg-green-50 text-green-700 text-xs rounded-lg border border-green-200 flex items-center gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
              {successMsg}
            </div>
          )}

          {/* Error message */}
          {error && (
            <div className="mx-4 mt-3 p-2.5 bg-red-50 text-red-600 text-xs rounded-lg border border-red-100 flex items-center gap-2">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
              {error}
            </div>
          )}

          {files.length === 0 && !loading ? (
            <div className="flex flex-col items-center justify-center py-10 text-slate-400">
              <Upload className="w-8 h-8 mb-2 opacity-40" />
              <p className="text-sm">No files uploaded yet</p>
              <p className="text-xs mt-1">Upload CSV, XLSX, PDF, TXT, or images</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {files.map((f) => {
                const isPending = f.db_status === 'pending';
                const isCacheExpired = isPending && f.cache_expired;
                const isSaved = f.db_status === 'saved';
                const isUpdating = updatingDb === f.filename;

                return (
                  <div key={f.filename}>
                    <div className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50 transition-colors">
                      <div className="flex-shrink-0">{getIcon(f.filename)}</div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-slate-700 truncate">{f.filename}</p>
                          {/* Status badge */}
                          {isPending && (
                            <span className="flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold bg-amber-100 text-amber-700 rounded-full whitespace-nowrap">
                              <Clock className="w-2.5 h-2.5" /> Pending
                            </span>
                          )}
                          {isSaved && (
                            <span className="flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold bg-green-100 text-green-700 rounded-full whitespace-nowrap">
                              <CheckCircle2 className="w-2.5 h-2.5" /> In Database
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {formatBytes(f.size_bytes)}
                          {f.row_count != null && ` · ${f.row_count} rows`}
                          {` · ${f.uploaded_by}`}
                        </p>
                        {/* Pending warning */}
                        {isPending && !isCacheExpired && (
                          <p className="text-[10px] text-amber-600 mt-0.5">
                            File uploaded but not yet added to database. Click Update Database.
                          </p>
                        )}
                        {isCacheExpired && (
                          <p className="text-[10px] text-red-500 mt-0.5">
                            Server was restarted. Please re-upload this file, then click Update Database.
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        {/* Update Database button — only for pending files with cached data */}
                        {isPending && !isCacheExpired && (
                          <button
                            onClick={() => handleUpdateDb(f.filename)}
                            disabled={isUpdating}
                            className="flex items-center gap-1 px-2.5 py-1.5 bg-green-600 hover:bg-green-700 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-60 whitespace-nowrap"
                            title="Parse and store in DB"
                          >
                            <Database className="w-3 h-3" />
                            {isUpdating ? 'Saving...' : 'Update Database'}
                          </button>
                        )}
                        {/* Preview — only for saved files */}
                        {isSaved && (
                          <button
                            onClick={() => handlePreview(f.filename)}
                            className="p-1.5 hover:bg-blue-50 text-slate-400 hover:text-blue-600 rounded-lg transition-colors"
                            title="Preview data"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(f.filename)}
                          className="p-1.5 hover:bg-red-50 text-slate-400 hover:text-red-500 rounded-lg transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    {/* Inline preview */}
                    {expanded === f.filename && (
                      <div className="border-t border-slate-100 bg-slate-50/50">
                        {loadingPreview === f.filename ? (
                          <div className="flex items-center gap-2 p-4 text-xs text-slate-400">
                            <div className="w-3 h-3 border border-slate-300 border-t-blue-500 rounded-full animate-spin" />
                            Loading preview...
                          </div>
                        ) : renderPreviewTable(previewData[f.filename])}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

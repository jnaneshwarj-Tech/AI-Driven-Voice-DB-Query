import { useState, useRef, useEffect } from 'react';
import api from '../services/api';
import {
  Upload, FileText, FileSpreadsheet, File, Image,
  RefreshCw, ChevronDown, ChevronRight,
  Database, Clock, CheckCircle2, AlertCircle, Trash2, RotateCcw
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

function formatErrorDetail(detail, fallback = 'Operation failed.') {
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object') {
    const lines = [
      detail.message || (detail.detail ? (typeof detail.detail === 'string' ? detail.detail : null) : null) || fallback,
      detail.invalid_row_count != null ? `Invalid rows: ${detail.invalid_row_count}` : null,
      detail.invalid_rows != null && typeof detail.invalid_rows === 'number' ? `Invalid rows: ${detail.invalid_rows}` : null,
      detail.rows_parsed != null ? `Parsed: ${detail.rows_parsed}` : null,
    ].filter(Boolean);
    const sample = (detail.rejected_rows || detail.invalid_rows || [])
      .filter(r => typeof r === 'object')
      .slice(0, 3)
      .map(r => `Row ${r.row_number || r.row_index || '?'}: ${r.reason || (r.errors || []).join('; ')}`)
      .filter(Boolean);
    if (sample.length > 0) {
      lines.push(sample.join('; '));
    }
    return lines.length > 0 ? lines.join(' | ') : JSON.stringify(detail);
  }
  return String(detail);
}

export default function FileExplorer({ onDataLoaded, canManageFiles = false }) {
  const [files, setFiles] = useState([]);
  const [trashFiles, setTrashFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [updatingDb, setUpdatingDb] = useState(null); // filename being updated
  const [deletingFile, setDeletingFile] = useState(null);
  const [restoringFile, setRestoringFile] = useState(null);
  const [permanentlyDeletingFile, setPermanentlyDeletingFile] = useState(null);
  const [error, setError] = useState('');
  const [isOpen, setIsOpen] = useState(true);
  const [showTrash, setShowTrash] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [uploadStats, setUploadStats] = useState(null); // last upload result details
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

  const fetchTrash = async () => {
    try {
      const res = await api.get('/files/trash');
      setTrashFiles(res.data);
    } catch {
      setError('Failed to load Trash.');
    }
  };

  useEffect(() => {
    fetchFiles();
    if (canManageFiles) fetchTrash();
  }, [canManageFiles]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError('');
    setSuccessMsg('');
    setUploadStats(null);
    const form = new FormData();
    form.append('file', file);
    try {
      await api.post('/files/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setSuccessMsg(`"${file.name}" uploaded. Updating database...`);
      try {
        const res = await api.post(`/files/update-db/${encodeURIComponent(file.name)}`);
        await fetchFiles();
        const d = res.data;
        // Build a detailed stats summary
        const parts = [
          d.students_added    > 0 ? `${d.students_added} new`       : null,
          d.students_updated  > 0 ? `${d.students_updated} updated`  : null,
          d.students_unchanged > 0 ? `${d.students_unchanged} unchanged` : null,
          d.duplicate_rows    > 0 ? `${d.duplicate_rows} duplicate`  : null,
          d.invalid_rows      > 0 ? `${d.invalid_rows} invalid`      : null,
        ].filter(Boolean);
        const marksParts = [
          d.marks_added   > 0 ? `${d.marks_added} marks added`   : null,
          d.marks_updated > 0 ? `${d.marks_updated} marks updated` : null,
        ].filter(Boolean);
        const statMsg = parts.length
          ? `Students: ${parts.join(', ')}.${marksParts.length ? ' ' + marksParts.join(', ') + '.' : ''}`
          : d.message;
        const provMsg = d.provisional_count > 0
          ? ` ${d.provisional_count} name-only student(s) given temporary USNs (in name order) — replace with real USNs later.`
          : '';
        setSuccessMsg(`"${file.name}" imported. ${statMsg}${provMsg}`);
        setUploadStats(d);
        setTimeout(() => setSuccessMsg(''), 9000);
        if (onDataLoaded) onDataLoaded(d);
      } catch (updateErr) {
        await fetchFiles();
        setError(formatErrorDetail(updateErr.response?.data?.detail, 'File uploaded, but database update failed. Check format.'));
      }
    } catch (err) {
      setError(formatErrorDetail(err.response?.data?.detail, 'Upload failed. Check file type and server connection.'));
    } finally {
      setUploading(false);
      if (e.target) e.target.value = '';
    }
  };

  const handleUpdateDb = async (filename) => {
    setUpdatingDb(filename);
    setError('');
    setSuccessMsg('');
    setUploadStats(null);
    try {
      const res = await api.post(`/files/update-db/${encodeURIComponent(filename)}`);
      await fetchFiles();
      const d = res.data;
      const parts = [
        d.students_added    > 0 ? `${d.students_added} new`        : null,
        d.students_updated  > 0 ? `${d.students_updated} updated`   : null,
        d.students_unchanged > 0 ? `${d.students_unchanged} unchanged` : null,
        d.invalid_rows      > 0 ? `${d.invalid_rows} invalid`       : null,
      ].filter(Boolean);
      setSuccessMsg(parts.length
        ? `"${filename}" saved. Students: ${parts.join(', ')}.`
        : (d.message || 'Database updated successfully.'));
      if (d.provisional_count > 0) {
        setSuccessMsg(s => `${s} ${d.provisional_count} name-only student(s) given temporary USNs — replace with real USNs later.`);
      }
      setUploadStats(d);
      setTimeout(() => setSuccessMsg(''), 7000);
      if (onDataLoaded) onDataLoaded(d);
    } catch (err) {
      setError(formatErrorDetail(err.response?.data?.detail, 'Database update failed. Check file format.'));
    } finally {
      setUpdatingDb(null);
    }
  };

  const handleDelete = async (filename) => {
    if (!window.confirm(
      `Move "${filename}" to Trash? Imported data owned only by this file will be removed. ` +
      'The file and its data can be restored for 30 days.'
    )) return;

    setDeletingFile(filename);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.delete(`/files/delete/${encodeURIComponent(filename)}`);
      setSuccessMsg(res.data.message || `"${filename}" moved to Trash for 30 days.`);
      await Promise.all([fetchFiles(), fetchTrash()]);
    } catch (err) {
      setError(formatErrorDetail(err.response?.data?.detail, 'Could not move file to Trash.'));
    } finally {
      setDeletingFile(null);
    }
  };

  const handleRestore = async (filename) => {
    setRestoringFile(filename);
    setError('');
    setSuccessMsg('');
    try {
      await api.post(`/files/trash/restore/${encodeURIComponent(filename)}`);
      setSuccessMsg(`"${filename}" and its imported data were restored.`);
      await Promise.all([fetchFiles(), fetchTrash()]);
    } catch (err) {
      setError(formatErrorDetail(err.response?.data?.detail, 'Could not restore file from Trash.'));
    } finally {
      setRestoringFile(null);
    }
  };

  const handlePermanentDelete = async (filename) => {
    const confirmed = window.confirm(
      '⚠️ Permanently delete this record?\n\n' +
      'This will permanently remove the selected student and its stored recovery data from Trash. This operation cannot be undone.\n\n' +
      'Are you sure?'
    );
    if (!confirmed) return;

    setPermanentlyDeletingFile(filename);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.delete(`/files/trash/permanent/${encodeURIComponent(filename)}`);
      setSuccessMsg(res.data.message || `"${filename}" was permanently deleted from Trash.`);
      await Promise.all([fetchFiles(), fetchTrash()]);
    } catch (err) {
      setError(formatErrorDetail(err.response?.data?.detail, 'Could not permanently delete this file from Trash.'));
    } finally {
      setPermanentlyDeletingFile(null);
    }
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
          {canManageFiles && (
            <button
              onClick={() => {
                setShowTrash(open => !open);
                fetchTrash();
              }}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg transition-colors ${showTrash ? 'bg-slate-200 text-slate-700' : 'hover:bg-slate-200 text-slate-600'}`}
              title="Open Trash"
              aria-expanded={showTrash}
            >
              <Trash2 className="w-3.5 h-3.5" />
              Trash ({trashFiles.length})
            </button>
          )}
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
            <div className="mx-4 mt-3 p-2.5 bg-green-50 text-green-700 text-xs rounded-lg border border-green-200 flex items-start gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span className="flex-1">{successMsg}</span>
            </div>
          )}

          {/* Error message */}
          {error && (
            <div className="mx-4 mt-3 p-2.5 bg-red-50 text-red-600 text-xs rounded-lg border border-red-100 flex items-center gap-2">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
              {error}
            </div>
          )}

          {canManageFiles && showTrash && (
            <section className="mx-4 mt-3 border border-slate-200 rounded-lg overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 bg-slate-50 border-b border-slate-200">
                <h3 className="text-xs font-semibold text-slate-700">Trash</h3>
                <span className="text-[11px] text-slate-500">Files can be restored for 30 days</span>
              </div>
              {trashFiles.length === 0 ? (
                <p className="px-4 py-5 text-xs text-slate-400">Trash is empty.</p>
              ) : (
                <div className="divide-y divide-slate-100">
                  {trashFiles.map(file => {
                    const expiresAt = new Date(file.restore_expires_at).getTime();
                    const daysRemaining = Math.max(0, Math.ceil((expiresAt - Date.now()) / (24 * 60 * 60 * 1000)));
                    const canRestore = Number.isFinite(expiresAt) && expiresAt > Date.now();
                    return (
                      <div key={file.filename} className="flex items-center gap-3 px-4 py-3">
                        <div className="flex-shrink-0">{getIcon(file.filename)}</div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-slate-700 truncate">{file.filename}</p>
                          <p className="mt-0.5 text-[11px] text-slate-500">
                            {formatBytes(file.size_bytes)}
                            {file.trashed_at && ` · Deleted ${new Date(file.trashed_at).toLocaleString()}`}
                            {canRestore ? ` · ${daysRemaining} days left to restore` : ' · Restore period expired'}
                          </p>
                        </div>
                        <button
                          onClick={() => handleRestore(file.filename)}
                          disabled={!canRestore || restoringFile === file.filename}
                          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50 rounded-md disabled:text-slate-400 disabled:hover:bg-transparent"
                          title={canRestore ? 'Restore file and imported data' : 'Restore period expired'}
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          {restoringFile === file.filename ? 'Restoring...' : 'Restore'}
                        </button>
                        <button
                          onClick={() => handlePermanentDelete(file.filename)}
                          disabled={permanentlyDeletingFile === file.filename}
                          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 rounded-md disabled:text-slate-400 disabled:hover:bg-transparent"
                          title="Delete Permanently"
                        >
                          {permanentlyDeletingFile === file.filename ? 'Deleting...' : 'Delete Permanently'}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
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

                return (
                  <div key={f.filename}>
                    <div className="flex items-start gap-3 px-5 py-3 hover:bg-slate-50 transition-colors">
                        <div className="flex-shrink-0 mt-0.5">{getIcon(f.filename)}</div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="text-sm font-medium text-slate-700 truncate">{f.filename}</p>
                            {isPending && (
                              <span className="flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold bg-amber-100 text-amber-700 rounded-full whitespace-nowrap">
                                <Clock className="w-2.5 h-2.5" /> Pending
                              </span>
                            )}
                            {isSaved && (
                              <span className="flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold bg-green-100 text-green-700 rounded-full whitespace-nowrap">
                                <CheckCircle2 className="w-2.5 h-2.5" /> Imported
                              </span>
                            )}
                          </div>

                          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
                            <span>{f.file_type || 'Unknown type'}</span>
                            <span>{formatBytes(f.size_bytes)}</span>
                            <span>{f.row_count != null ? `${f.row_count} rows` : 'Rows unavailable'}</span>
                            <span>{f.uploaded_at ? new Date(f.uploaded_at).toLocaleString() : 'Upload time unavailable'}</span>
                            <span>{f.uploaded_by || 'unknown uploader'}</span>
                          </div>

                          {isPending && !isCacheExpired && (
                            <p className="text-[10px] text-amber-600 mt-1">
                              File uploaded but not yet added to the database.
                            </p>
                          )}
                          {isCacheExpired && (
                            <p className="text-[10px] text-red-500 mt-1">
                              Server was restarted. Please re-upload this file and import it again.
                            </p>
                          )}
                        </div>
                        {canManageFiles && (
                          <button
                            onClick={() => handleDelete(f.filename)}
                            disabled={deletingFile === f.filename}
                            className="flex-shrink-0 p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-md disabled:opacity-50"
                            title="Move to Trash"
                            aria-label={`Move ${f.filename} to Trash`}
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
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

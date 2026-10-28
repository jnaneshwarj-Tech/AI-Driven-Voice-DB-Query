import { useState, useRef, useEffect } from 'react';
import api from '../services/api';
import { useI18n } from '../context/LanguageContext';
import {
  Upload, FileText, FileSpreadsheet, File, Image,
  RefreshCw, ChevronDown, ChevronRight,
  Database, Clock, CheckCircle2, AlertCircle, Trash2, RotateCcw
} from 'lucide-react';

const FILE_ICONS = {
  csv: <FileSpreadsheet className="w-4 h-4 text-ok" />,
  xlsx: <FileSpreadsheet className="w-4 h-4 text-ok" />,
  xls: <FileSpreadsheet className="w-4 h-4 text-ok" />,
  pdf: <FileText className="w-4 h-4 text-err" />,
  txt: <FileText className="w-4 h-4 text-ink-mute" />,
  png: <Image className="w-4 h-4 text-info" />,
  jpg: <Image className="w-4 h-4 text-info" />,
  jpeg: <Image className="w-4 h-4 text-info" />,
};

function getIcon(filename) {
  const ext = filename?.split('.').pop()?.toLowerCase();
  return FILE_ICONS[ext] || <File className="w-4 h-4 text-ink-faint" />;
}

function formatBytes(b) {
  if (!b) return '—';
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

// `t` is optional: when it is not passed the English literals below render,
// so the parse-and-join behaviour is identical to before the i18n pass.
function formatErrorDetail(detail, fallback = 'Operation failed.', t) {
  const L = (key, vars, english) => (typeof t === 'function' ? t(key, vars) : english);
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object') {
    const lines = [
      detail.message || (detail.detail ? (typeof detail.detail === 'string' ? detail.detail : null) : null) || fallback,
      detail.invalid_row_count != null ? L('files.invalidRows', { n: detail.invalid_row_count }, `Invalid rows: ${detail.invalid_row_count}`) : null,
      detail.invalid_rows != null && typeof detail.invalid_rows === 'number' ? L('files.invalidRows', { n: detail.invalid_rows }, `Invalid rows: ${detail.invalid_rows}`) : null,
      detail.rows_parsed != null ? L('files.rowsParsed', { n: detail.rows_parsed }, `Parsed: ${detail.rows_parsed}`) : null,
    ].filter(Boolean);
    const sample = (detail.rejected_rows || detail.invalid_rows || [])
      .filter(r => typeof r === 'object')
      .slice(0, 3)
      .map(r => L('files.rowReason', {
        row: r.row_number || r.row_index || '?',
        reason: r.reason || (r.errors || []).join('; '),
      }, `Row ${r.row_number || r.row_index || '?'}: ${r.reason || (r.errors || []).join('; ')}`))
      .filter(Boolean);
    if (sample.length > 0) {
      lines.push(sample.join('; '));
    }
    return lines.length > 0 ? lines.join(' | ') : JSON.stringify(detail);
  }
  return String(detail);
}

export default function FileExplorer({ onDataLoaded, canManageFiles = false, refreshVersion = 0 }) {
  const { t } = useI18n();
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
      setError(t('files.errLoad'));
    } finally {
      setLoading(false);
    }
  };

  const fetchTrash = async () => {
    try {
      const res = await api.get('/files/trash');
      setTrashFiles(res.data);
    } catch {
      setError(t('files.errTrashLoad'));
    }
  };

  useEffect(() => {
    fetchFiles();
    if (canManageFiles) fetchTrash();
    // An undo run from the operation modal changes a file's real state; the
    // card must not keep claiming 'Imported' until the tab is reopened.
  }, [canManageFiles, refreshVersion]);

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
      setSuccessMsg(t('files.uploadedStart', { name: file.name }));
      try {
        const res = await api.post(`/files/update-db/${encodeURIComponent(file.name)}`);
        await fetchFiles();
        const d = res.data;
        // Build a detailed stats summary
        const parts = [
          d.students_added    > 0 ? t('files.statNew', { n: d.students_added })             : null,
          d.students_updated  > 0 ? t('files.statUpdated', { n: d.students_updated })       : null,
          d.students_unchanged > 0 ? t('files.statUnchanged', { n: d.students_unchanged })  : null,
          d.duplicate_rows    > 0 ? t('files.statDuplicate', { n: d.duplicate_rows })       : null,
          d.invalid_rows      > 0 ? t('files.statInvalid', { n: d.invalid_rows })           : null,
        ].filter(Boolean);
        const marksParts = [
          d.marks_added   > 0 ? t('files.marksAdded', { n: d.marks_added })       : null,
          d.marks_updated > 0 ? t('files.marksUpdated', { n: d.marks_updated })   : null,
        ].filter(Boolean);
        const statMsg = parts.length
          ? t('files.studentsSummary', { list: parts.join(', ') }) + (marksParts.length ? ' ' + marksParts.join(', ') + '.' : '')
          : d.message;
        const provMsg = d.provisional_count > 0
          ? ' ' + t('files.provisional', { n: d.provisional_count })
          : '';
        setSuccessMsg(`${t('files.importedPrefix', { name: file.name })} ${statMsg}${provMsg}`);
        setUploadStats(d);
        setTimeout(() => setSuccessMsg(''), 9000);
        if (onDataLoaded) onDataLoaded(d);
      } catch (updateErr) {
        await fetchFiles();
        setError(formatErrorDetail(updateErr.response?.data?.detail, t('files.errUploadDb'), t));
      }
    } catch (err) {
      setError(formatErrorDetail(err.response?.data?.detail, t('files.errUpload'), t));
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
        d.students_added    > 0 ? t('files.statNew', { n: d.students_added })            : null,
        d.students_updated  > 0 ? t('files.statUpdated', { n: d.students_updated })      : null,
        d.students_unchanged > 0 ? t('files.statUnchanged', { n: d.students_unchanged }) : null,
        d.invalid_rows      > 0 ? t('files.statInvalid', { n: d.invalid_rows })          : null,
      ].filter(Boolean);
      setSuccessMsg(parts.length
        ? t('files.savedStats', { name: filename, list: parts.join(', ') })
        : (d.message || t('files.dbUpdatedOk')));
      if (d.provisional_count > 0) {
        setSuccessMsg(s => `${s} ${t('files.provisionalShort', { n: d.provisional_count })}`);
      }
      setUploadStats(d);
      setTimeout(() => setSuccessMsg(''), 7000);
      if (onDataLoaded) onDataLoaded(d);
    } catch (err) {
      setError(formatErrorDetail(err.response?.data?.detail, t('files.errDbUpdate'), t));
    } finally {
      setUpdatingDb(null);
    }
  };

  const handleDelete = async (filename) => {
    if (!window.confirm(t('files.toTrashConfirm', { name: filename }))) return;

    setDeletingFile(filename);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.delete(`/files/delete/${encodeURIComponent(filename)}`);
      setSuccessMsg(res.data.message || t('files.toTrashDone', { name: filename }));
      await Promise.all([fetchFiles(), fetchTrash()]);
    } catch (err) {
      setError(formatErrorDetail(err.response?.data?.detail, t('files.errToTrash'), t));
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
      setSuccessMsg(t('files.restored', { name: filename }));
      await Promise.all([fetchFiles(), fetchTrash()]);
    } catch (err) {
      setError(formatErrorDetail(err.response?.data?.detail, t('files.errRestore'), t));
    } finally {
      setRestoringFile(null);
    }
  };

  const handlePermanentDelete = async (filename) => {
    const confirmed = window.confirm(t('files.permConfirm'));
    if (!confirmed) return;

    setPermanentlyDeletingFile(filename);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.delete(`/files/trash/permanent/${encodeURIComponent(filename)}`);
      setSuccessMsg(res.data.message || t('files.permDeleted', { name: filename }));
      await Promise.all([fetchFiles(), fetchTrash()]);
    } catch (err) {
      setError(formatErrorDetail(err.response?.data?.detail, t('files.errPermanent'), t));
    } finally {
      setPermanentlyDeletingFile(null);
    }
  };

  const pendingCount = files.filter(f => f.db_status === 'pending').length;
  // Only a pending file whose parsed rows are still held by the server can be
  // imported; counting the rest would offer an "Update All (3)" that does nothing.
  const importableCount = files.filter(f => f.db_status === 'pending' && !f.cache_expired).length;

  return (
    <div className="card anim-fade-up overflow-hidden">
      {/* Header */}
      <div
        className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line bg-sunken px-4 py-3 cursor-pointer sm:px-5"
        onClick={() => setIsOpen(o => !o)}
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-2">
          {isOpen ? <ChevronDown className="w-4 h-4 text-ink-mute" /> : <ChevronRight className="w-4 h-4 text-ink-mute" />}
          <span className="t-card text-ink">{t('files.title')}</span>
          <span className="badge badge-brand">{t('files.count', { n: files.length })}</span>
          {pendingCount > 0 && (
            <span className="badge badge-warn">{t('files.pendingCount', { n: pendingCount })}</span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2" onClick={e => e.stopPropagation()}>
          {canManageFiles && (
            <button
              onClick={() => {
                setShowTrash(open => !open);
                fetchTrash();
              }}
              className={`btn btn-sm ${showTrash ? 'bg-surface-elev text-ink border-line-strong' : 'btn-ghost'}`}
              title={t('files.openTrash')}
              aria-expanded={showTrash}
            >
              <Trash2 className="w-3.5 h-3.5" />
              {t('files.trashCount', { n: trashFiles.length })}
            </button>
          )}
          <button
            onClick={fetchFiles}
            className="btn btn-sm btn-ghost px-2"
            title={t('common.refresh')}
            aria-label={t('common.refresh')}
          >
            <RefreshCw className={`w-3.5 h-3.5 text-ink-mute ${loading ? 'animate-spin' : ''}`} />
          </button>
          {importableCount > 0 && (
            <button
              onClick={async () => {
                const pendings = files.filter(f => f.db_status === 'pending' && !f.cache_expired);
                for (const p of pendings) await handleUpdateDb(p.filename);
              }}
              disabled={!!updatingDb}
              className="btn btn-sm btn-primary"
            >
              <Database className="w-3.5 h-3.5" />
              {updatingDb ? t('files.updating') : t('files.updateAll', { n: importableCount })}
            </button>
          )}
          <button
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="btn btn-sm btn-accent"
          >
            <Upload className="w-3.5 h-3.5" />
            {uploading ? t('files.uploading') : t('files.upload')}
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
        <div className="pb-1">
          {/* Success message */}
          {successMsg && (
            <div className="slide-down mx-4 mt-3 flex items-start gap-2 rounded-md border border-ok/25 bg-ok-soft p-2.5 text-ok t-support">
              <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span className="flex-1 min-w-0 break-words">{successMsg}</span>
            </div>
          )}

          {/* Error message */}
          {error && (
            <div className="slide-down mx-4 mt-3 flex items-start gap-2 rounded-md border border-err/25 bg-err-soft p-2.5 text-err t-support">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              <span className="flex-1 min-w-0 break-words">{error}</span>
            </div>
          )}

          {canManageFiles && showTrash && (
            <section className="mx-4 mt-3 overflow-hidden rounded-md border border-line">
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-line bg-sunken px-4 py-2">
                <h3 className="t-label flex items-center gap-1.5 text-ink">
                  <Trash2 className="w-3.5 h-3.5 text-ink-mute" />
                  {t('files.trash')}
                </h3>
                <span className="t-support text-ink-mute">{t('files.trashNote')}</span>
              </div>
              {trashFiles.length === 0 ? (
                <p className="t-support px-4 py-5 text-ink-faint">{t('files.trashEmpty')}</p>
              ) : (
                <div className="divide-line">
                  {trashFiles.map(file => {
                    const expiresAt = new Date(file.restore_expires_at).getTime();
                    const daysRemaining = Math.max(0, Math.ceil((expiresAt - Date.now()) / (24 * 60 * 60 * 1000)));
                    const canRestore = Number.isFinite(expiresAt) && expiresAt > Date.now();
                    return (
                      <div key={file.filename} className="tr-hover flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:gap-3">
                        <div className="flex-shrink-0">{getIcon(file.filename)}</div>
                        <div className="min-w-0 flex-1">
                          <p className="t-body t-truncate font-medium text-ink" title={file.filename}>{file.filename}</p>
                          <p className="t-support mt-0.5 text-ink-mute">
                            {formatBytes(file.size_bytes)}
                            {file.trashed_at && ` · ${t('files.deletedAt', { time: new Date(file.trashed_at).toLocaleString() })}`}
                            {canRestore ? ` · ${t('files.daysLeft', { n: daysRemaining })}` : ` · ${t('files.restoreExpired')}`}
                          </p>
                        </div>
                        <div className="flex flex-shrink-0 items-center gap-2">
                          <button
                            onClick={() => handleRestore(file.filename)}
                            disabled={!canRestore || restoringFile === file.filename}
                            className="btn btn-sm btn-ghost"
                            title={canRestore ? t('files.restoreTitle') : t('files.restoreExpired')}
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                            {restoringFile === file.filename ? t('files.restoring') : t('files.restore')}
                          </button>
                          <button
                            onClick={() => handlePermanentDelete(file.filename)}
                            disabled={permanentlyDeletingFile === file.filename}
                            className="btn btn-sm btn-danger-soft"
                            title={t('files.deletePermanent')}
                          >
                            {permanentlyDeletingFile === file.filename ? t('files.deleting') : t('files.deletePermanent')}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          )}

          {files.length === 0 && !loading ? (
            <div className="empty-state">
              <Upload className="w-8 h-8 text-ink-faint" />
              <p className="t-body text-ink-soft">{t('files.empty')}</p>
              <p className="t-support text-ink-mute">{t('files.emptyHint')}</p>
            </div>
          ) : (
            <div className="divide-line">
              {files.map((f) => {
                const isPending = f.db_status === 'pending';
                const isCacheExpired = isPending && f.cache_expired;
                const isSaved = f.db_status === 'saved';

                return (
                  <div key={f.filename}>
                    <div className="tr-hover flex items-start gap-3 px-4 py-3 sm:px-5">
                        <div className="mt-0.5 flex-shrink-0">{getIcon(f.filename)}</div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="t-body t-truncate max-w-full font-medium text-ink" title={f.filename}>{f.filename}</p>
                            {isPending && (
                              <span className="badge badge-warn">
                                <Clock className="w-2.5 h-2.5" /> {t('files.pending')}
                              </span>
                            )}
                            {isSaved && (
                              <span className="badge badge-ok">
                                <CheckCircle2 className="w-2.5 h-2.5" /> {t('files.badgeImported')}
                              </span>
                            )}
                          </div>

                          <div className="t-support mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-ink-mute">
                            <span>{f.file_type || t('files.unknownType')}</span>
                            <span>{formatBytes(f.size_bytes)}</span>
                            <span>{f.row_count != null ? t('files.rows', { n: f.row_count }) : t('files.rowsUnavailable')}</span>
                            <span>{f.uploaded_at ? new Date(f.uploaded_at).toLocaleString() : t('files.uploadTimeUnavailable')}</span>
                            <span>{f.uploaded_by || t('files.unknownUploader')}</span>
                          </div>

                          {isPending && !isCacheExpired && (
                            <p className="t-support mt-1 text-warn">
                              {t('files.pendingNote')}
                            </p>
                          )}
                          {isCacheExpired && (
                            <p className="t-support mt-1 text-err">
                              {t('files.expiredNote')}
                            </p>
                          )}
                        </div>
                        {canManageFiles && (
                          <button
                            onClick={() => handleDelete(f.filename)}
                            disabled={deletingFile === f.filename}
                            className="btn btn-sm btn-ghost mt-0.5 flex-shrink-0 px-2 text-ink-mute hover:text-err"
                            title={t('files.moveToTrash')}
                            aria-label={t('files.moveToTrashAria', { name: f.filename })}
                          >
                            <Trash2 className={`w-4 h-4 ${deletingFile === f.filename ? 'animate-pulse' : ''}`} />
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

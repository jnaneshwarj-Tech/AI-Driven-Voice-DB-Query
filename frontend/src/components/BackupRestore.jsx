import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { useToast } from './Toast';
import {
  Database, HardDrive, Download, RotateCcw, Trash2, Shield,
  AlertTriangle, CheckCircle, XCircle, Clock, RefreshCw,
  Activity, Server, Layers, FileText, ChevronDown, ChevronUp,
  AlertCircle, Info
} from 'lucide-react';

// ── Helper ────────────────────────────────────────────────────────────────────
function fmtBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`;
}

function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true
  });
}

function StatusBadge({ status }) {
  const cfg = {
    verified:  { color: 'bg-emerald-100 text-emerald-700 border-emerald-200', icon: <CheckCircle className="w-3 h-3" /> },
    success:   { color: 'bg-green-100 text-green-700 border-green-200',       icon: <CheckCircle className="w-3 h-3" /> },
    running:   { color: 'bg-blue-100 text-blue-700 border-blue-200',          icon: <RefreshCw className="w-3 h-3 animate-spin" /> },
    failed:    { color: 'bg-red-100 text-red-700 border-red-200',             icon: <XCircle className="w-3 h-3" /> },
  };
  const c = cfg[status] || cfg.failed;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border ${c.color}`}>
      {c.icon} {status?.toUpperCase()}
    </span>
  );
}

// ── Confirmation Modal ────────────────────────────────────────────────────────
function ConfirmModal({ backup, onConfirm, onCancel, loading }) {
  if (!backup) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white dark:bg-slate-900 border border-red-200 dark:border-red-800/50 rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-red-100 dark:bg-red-900/30 rounded-xl">
            <AlertTriangle className="w-6 h-6 text-red-600" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">Confirm Database Restore</h3>
            <p className="text-xs text-slate-500">This is a destructive operation</p>
          </div>
        </div>

        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/40 rounded-xl p-4 space-y-2 text-sm">
          <p className="font-semibold text-amber-800 dark:text-amber-300">What will happen:</p>
          <ul className="text-amber-700 dark:text-amber-400 space-y-1 text-xs list-disc list-inside">
            <li>A safety backup of the <strong>current database</strong> will be created first</li>
            <li>The selected backup will be restored</li>
            <li>All data added <strong>after</strong> the backup date will be lost</li>
            <li>This action cannot be undone with the normal undo button</li>
          </ul>
        </div>

        <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-3 text-xs space-y-1">
          <p><strong>Backup:</strong> {backup.backup_name}</p>
          <p><strong>Created:</strong> {fmtDate(backup.created_at)}</p>
          <p><strong>Size:</strong> {fmtBytes(backup.size_bytes)}</p>
          <p><strong>Records:</strong> {backup.record_count?.toLocaleString() || 'Unknown'} students</p>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={onCancel}
            disabled={loading}
            className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 text-sm font-semibold hover:bg-slate-50 dark:hover:bg-slate-800 transition-all disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex-1 px-4 py-2.5 rounded-xl bg-red-600 hover:bg-red-700 text-white text-sm font-bold transition-all disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
            {loading ? 'Restoring...' : 'Confirm Restore'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Storage Status Widget ─────────────────────────────────────────────────────
function StorageWidget({ storage }) {
  if (!storage) return null;
  const diskPct = storage.disk_used_pct || 0;
  const diskColor = diskPct > 90 ? 'bg-red-500' : diskPct > 75 ? 'bg-amber-500' : 'bg-emerald-500';

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {/* DB Size */}
      <div className="bg-white/70 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-800/40 rounded-2xl p-4 space-y-1">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Database Size</p>
        <p className="text-2xl font-black text-slate-800 dark:text-slate-100 font-mono">
          {storage.db_size_mb || 0} <span className="text-sm font-semibold text-slate-400">MB</span>
        </p>
        <p className="text-[10px] text-slate-400">Data: {storage.data_size_mb}MB · Index: {storage.index_size_mb}MB</p>
      </div>

      {/* Backup Storage */}
      <div className="bg-white/70 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-800/40 rounded-2xl p-4 space-y-1">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Backup Storage</p>
        <p className="text-2xl font-black text-slate-800 dark:text-slate-100 font-mono">
          {storage.backup_storage_mb || 0} <span className="text-sm font-semibold text-slate-400">MB</span>
        </p>
        <p className="text-[10px] text-slate-400">{storage.total_backups || 0} verified backup(s)</p>
      </div>

      {/* Disk Usage */}
      <div className="bg-white/70 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-800/40 rounded-2xl p-4 space-y-2 md:col-span-2">
        <div className="flex items-center justify-between">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Disk Usage</p>
          <span className={`text-xs font-bold ${diskPct > 90 ? 'text-red-600' : diskPct > 75 ? 'text-amber-600' : 'text-emerald-600'}`}>
            {diskPct}%
          </span>
        </div>
        <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all duration-700 ${diskColor}`}
            style={{ width: `${Math.min(diskPct, 100)}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-slate-400">
          <span>Used: {storage.disk_used_gb} GB</span>
          <span>Free: {storage.disk_free_gb} GB</span>
          <span>Total: {storage.disk_total_gb} GB</span>
        </div>
      </div>

      {/* Warnings */}
      {storage.warnings?.length > 0 && (
        <div className="md:col-span-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/40 rounded-xl p-3">
          {storage.warnings.map((w, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function BackupRestore({ userRole }) {
  const [backups, setBackups] = useState([]);
  const [storage, setStorage] = useState(null);
  const [uploadVersions, setUploadVersions] = useState([]);
  const [auditLog, setAuditLog] = useState([]);
  const [loadingBackups, setLoadingBackups] = useState(true);
  const [loadingStorage, setLoadingStorage] = useState(true);
  const [creatingBackup, setCreatingBackup] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState(null);
  const [restoring, setRestoring] = useState(false);
  const [activeTab, setActiveTab] = useState('backups');
  const [expandedBackup, setExpandedBackup] = useState(null);
  const { showToast } = useToast();

  const isAdmin = userRole === 'Admin';

  const fetchAll = useCallback(async () => {
    setLoadingBackups(true);
    setLoadingStorage(true);
    try {
      const [storRes, versRes, auditRes] = await Promise.all([
        api.get('/backup/storage-status'),
        api.get('/backup/upload-versions'),
        api.get('/backup/audit-log?limit=50'),
      ]);
      setStorage(storRes.data);
      setUploadVersions(versRes.data);
      setAuditLog(auditRes.data);

      if (isAdmin) {
        const backRes = await api.get('/backup/list');
        setBackups(backRes.data);
      }
    } catch (err) {
      console.error('Failed to load backup data:', err);
    } finally {
      setLoadingBackups(false);
      setLoadingStorage(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleCreateBackup = async () => {
    setCreatingBackup(true);
    try {
      const res = await api.post('/backup/create');
      showToast({ type: 'success', message: res.data.message || 'Backup created successfully!' });
      fetchAll();
    } catch (err) {
      showToast({
        type: 'error',
        message: err.response?.data?.detail || 'Backup creation failed.'
      });
    } finally {
      setCreatingBackup(false);
    }
  };

  const handleRestoreConfirm = async () => {
    if (!restoreTarget) return;
    setRestoring(true);
    try {
      const res = await api.post(`/backup/restore/${restoreTarget.id}`, { confirmed: true });
      showToast({
        type: 'success',
        message: res.data.message || 'Database restored successfully!'
      });
      setRestoreTarget(null);
      fetchAll();
    } catch (err) {
      showToast({
        type: 'error',
        message: err.response?.data?.detail || 'Restore failed. Check audit log for details.'
      });
    } finally {
      setRestoring(false);
    }
  };

  const handleDeleteBackup = async (backup) => {
    if (!window.confirm(`Delete backup "${backup.backup_name}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/backup/${backup.id}`);
      showToast({ type: 'success', message: 'Backup deleted.' });
      fetchAll();
    } catch (err) {
      showToast({
        type: 'error',
        message: err.response?.data?.detail || 'Delete failed.'
      });
    }
  };

  const tabs = [
    { id: 'backups', label: 'Backup History', icon: <HardDrive className="w-4 h-4" /> },
    { id: 'uploads', label: 'Upload Versions', icon: <Layers className="w-4 h-4" /> },
    { id: 'audit', label: 'Audit Log', icon: <Shield className="w-4 h-4" /> },
  ];

  return (
    <div className="space-y-6">
      {/* Restore Confirmation Modal */}
      <ConfirmModal
        backup={restoreTarget}
        onConfirm={handleRestoreConfirm}
        onCancel={() => setRestoreTarget(null)}
        loading={restoring}
      />

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
            <Database className="w-5 h-5 text-blue-600" />
            Database Reliability &amp; Backup Center
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Backup, restore, upload version history, and enterprise audit log.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchAll}
            disabled={loadingBackups}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 text-xs font-semibold rounded-lg hover:bg-slate-50 disabled:opacity-50 transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingBackups ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          {isAdmin && (
            <button
              onClick={handleCreateBackup}
              disabled={creatingBackup}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl transition-all disabled:opacity-50 shadow-sm shadow-blue-500/20"
            >
              {creatingBackup
                ? <RefreshCw className="w-4 h-4 animate-spin" />
                : <Download className="w-4 h-4" />}
              {creatingBackup ? 'Creating Backup...' : 'Create Backup Now'}
            </button>
          )}
        </div>
      </div>

      {/* Storage Status */}
      {loadingStorage
        ? <div className="h-24 bg-white/50 dark:bg-slate-900/30 rounded-2xl animate-pulse" />
        : <StorageWidget storage={storage} />}

      {/* Info bar for Staff */}
      {!isAdmin && (
        <div className="flex items-center gap-2 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800/40 rounded-xl text-sm text-blue-700 dark:text-blue-300">
          <Info className="w-4 h-4 flex-shrink-0" />
          Backup creation and restore require Admin access. You can view storage status and upload history.
        </div>
      )}

      {/* Tabs */}
      <div className="bg-white/80 dark:bg-slate-900/60 backdrop-blur-lg rounded-2xl border border-slate-200/80 dark:border-slate-800/60 shadow-md overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800/60 flex items-center gap-2 bg-slate-50/50 dark:bg-slate-950/20 flex-wrap">
          {tabs.filter(t => isAdmin || t.id !== 'backups' || t.id === 'uploads' || t.id === 'audit').map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all
                ${activeTab === tab.id
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'}`}
            >
              {tab.icon}{tab.label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {/* ── Backup History Tab ── */}
          {activeTab === 'backups' && isAdmin && (
            loadingBackups ? (
              <div className="flex items-center justify-center py-16 text-slate-400">
                <RefreshCw className="w-6 h-6 animate-spin mr-3" />
                Loading backup history...
              </div>
            ) : backups.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
                <HardDrive className="w-12 h-12 text-slate-200 dark:text-slate-700" />
                <p className="font-bold">No backups yet</p>
                <p className="text-sm">Click "Create Backup Now" to create the first backup.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {backups.map(b => (
                  <div
                    key={b.id}
                    className="border border-slate-100 dark:border-slate-800/80 rounded-xl overflow-hidden hover:border-slate-200 dark:hover:border-slate-700 transition-all"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-slate-50/40 dark:bg-slate-950/20">
                      {/* Left: info */}
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <StatusBadge status={b.status} />
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                            b.backup_type === 'pre_restore' ? 'bg-orange-100 text-orange-700' :
                            b.backup_type === 'manual' ? 'bg-purple-100 text-purple-700' :
                            b.backup_type === 'auto_daily' ? 'bg-sky-100 text-sky-700' :
                            'bg-teal-100 text-teal-700'
                          }`}>
                            {b.backup_type?.replace('_', ' ').toUpperCase()}
                          </span>
                          {!b.file_exists && (
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-100 text-red-600 font-bold">
                              FILE MISSING
                            </span>
                          )}
                        </div>
                        <p className="text-sm font-mono text-slate-700 dark:text-slate-200 truncate max-w-xs">
                          {b.backup_name}
                        </p>
                        <div className="flex items-center gap-4 text-[11px] text-slate-400 flex-wrap">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />{fmtDate(b.created_at)}
                          </span>
                          <span>{fmtBytes(b.size_bytes)}</span>
                          <span>{b.record_count?.toLocaleString() || 0} students</span>
                          <span>By: <strong className="text-slate-600 dark:text-slate-300">{b.created_by}</strong></span>
                        </div>
                      </div>

                      {/* Right: actions */}
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <button
                          onClick={() => setExpandedBackup(expandedBackup === b.id ? null : b.id)}
                          className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-all"
                        >
                          {expandedBackup === b.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </button>
                        {b.status !== 'failed' && b.file_exists && (
                          <button
                            onClick={() => setRestoreTarget(b)}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500/10 hover:bg-amber-500 hover:text-white border border-amber-200 dark:border-amber-800/40 text-amber-600 dark:text-amber-400 text-xs font-bold rounded-lg transition-all"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                            Restore
                          </button>
                        )}
                        {b.backup_type !== 'pre_restore' && (
                          <button
                            onClick={() => handleDeleteBackup(b)}
                            className="p-1.5 text-slate-400 hover:text-red-600 dark:hover:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Expanded row */}
                    {expandedBackup === b.id && (
                      <div className="px-4 py-3 border-t border-slate-100 dark:border-slate-800/60 text-xs text-slate-500 space-y-1 bg-white dark:bg-slate-900/40">
                        {b.error_message && (
                          <p className="text-red-500"><strong>Error:</strong> {b.error_message}</p>
                        )}
                        <p><strong>Verified:</strong> {b.verified ? 'Yes ✓' : 'Not verified'}</p>
                        <p><strong>Completed:</strong> {fmtDate(b.completed_at)}</p>
                        <p><strong>File:</strong> <span className="font-mono">{b.backup_name}</span></p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )
          )}

          {/* ── Upload Versions Tab ── */}
          {activeTab === 'uploads' && (
            uploadVersions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
                <Layers className="w-12 h-12 text-slate-200 dark:text-slate-700" />
                <p className="font-bold">No upload history yet</p>
                <p className="text-sm">Upload a file to see version history here.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400 border-b border-slate-100 dark:border-slate-800">
                      <th className="pb-2 pr-4">File</th>
                      <th className="pb-2 pr-4">Added</th>
                      <th className="pb-2 pr-4">Updated</th>
                      <th className="pb-2 pr-4">Unchanged</th>
                      <th className="pb-2 pr-4">Marks</th>
                      <th className="pb-2 pr-4">Skipped</th>
                      <th className="pb-2 pr-4">Status</th>
                      <th className="pb-2 pr-4">By</th>
                      <th className="pb-2">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50 dark:divide-slate-800/60">
                    {uploadVersions.map(v => (
                      <tr key={v.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-950/20 transition-colors">
                        <td className="py-2 pr-4 font-mono text-xs text-slate-700 dark:text-slate-300 truncate max-w-[180px]">{v.filename}</td>
                        <td className="py-2 pr-4 text-emerald-600 font-bold">{v.students_added}</td>
                        <td className="py-2 pr-4 text-amber-600 font-bold">{v.students_updated}</td>
                        <td className="py-2 pr-4 text-slate-400">{v.students_unchanged}</td>
                        <td className="py-2 pr-4 text-blue-600 font-bold">{(v.marks_added || 0) + (v.marks_updated || 0)}</td>
                        <td className="py-2 pr-4 text-slate-400">{v.skipped_rows}</td>
                        <td className="py-2 pr-4">
                          <StatusBadge status={v.status === 'success' ? 'verified' : v.status} />
                        </td>
                        <td className="py-2 pr-4 text-slate-500 text-xs">{v.performed_by}</td>
                        <td className="py-2 text-xs text-slate-400">{fmtDate(v.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}

          {/* ── Audit Log Tab ── */}
          {activeTab === 'audit' && (
            auditLog.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
                <Shield className="w-12 h-12 text-slate-200 dark:text-slate-700" />
                <p className="font-bold">No audit events yet</p>
                <p className="text-sm">Actions like login, upload, backup will appear here.</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {auditLog.map(log => (
                  <div
                    key={log.id}
                    className={`flex flex-wrap items-start justify-between gap-3 p-3 rounded-xl border text-xs
                      ${log.success
                        ? 'bg-slate-50/50 dark:bg-slate-950/20 border-slate-100 dark:border-slate-800/60'
                        : 'bg-red-50/50 dark:bg-red-900/10 border-red-100 dark:border-red-800/30'}`}
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        {log.success
                          ? <CheckCircle className="w-3 h-3 text-emerald-500" />
                          : <XCircle className="w-3 h-3 text-red-500" />}
                        <span className="font-bold text-slate-700 dark:text-slate-200 uppercase text-[10px] tracking-wider">
                          {log.action}
                        </span>
                        {log.target_table && (
                          <span className="text-[9px] px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-500 rounded font-mono">
                            {log.target_table}
                          </span>
                        )}
                      </div>
                      {log.summary && (
                        <p className="text-slate-600 dark:text-slate-300 text-[11px] leading-relaxed">
                          {log.summary}
                        </p>
                      )}
                      {log.error_info && (
                        <p className="text-red-500 text-[11px]">Error: {log.error_info}</p>
                      )}
                    </div>
                    <div className="text-right space-y-1 flex-shrink-0">
                      <p className="text-slate-500 font-semibold">{log.username} <span className="text-slate-400">({log.role})</span></p>
                      <p className="text-slate-400">{fmtDate(log.created_at)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}

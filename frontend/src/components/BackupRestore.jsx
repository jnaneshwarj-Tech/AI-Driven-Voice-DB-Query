import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import { useToast } from './Toast';
import { useI18n } from '../context/LanguageContext';
import CountUp from './CountUp';
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
    verified:  { variant: 'badge-ok',   icon: <CheckCircle className="w-3 h-3" aria-hidden="true" /> },
    success:   { variant: 'badge-ok',   icon: <CheckCircle className="w-3 h-3" aria-hidden="true" /> },
    running:   { variant: 'badge-info', icon: <RefreshCw className="w-3 h-3 animate-spin" aria-hidden="true" /> },
    failed:    { variant: 'badge-err',  icon: <XCircle className="w-3 h-3" aria-hidden="true" /> },
  };
  const c = cfg[status] || cfg.failed;
  return (
    <span className={`badge ${c.variant} font-bold`}>
      {c.icon} {status?.toUpperCase()}
    </span>
  );
}

// ── Confirmation Modal ────────────────────────────────────────────────────────
function ConfirmModal({ backup, onConfirm, onCancel, loading }) {
  const { t } = useI18n();
  if (!backup) return null;
  return (
    <div className="backdrop" role="dialog" aria-modal="true" aria-labelledby="restore-confirm-title">
      <div className="modal-panel max-w-md anim-scale-in p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-err-soft p-2.5">
            <AlertTriangle className="w-6 h-6 text-err" aria-hidden="true" />
          </div>
          <div>
            <h3 id="restore-confirm-title" className="t-card text-ink">{t('backup.modalHeading')}</h3>
            <p className="t-support mt-0.5 text-err">{t('backup.modalDanger')}</p>
          </div>
        </div>

        <div className="mt-4 space-y-1.5 rounded-md border border-warn/25 bg-warn-soft p-4">
          <p className="t-label font-semibold text-warn">{t('backup.modalWhat')}</p>
          <ul className="t-support list-disc space-y-1 pl-4 text-ink-soft">
            <li>
              {t('backup.modalPoint1Lead')} <strong>{t('backup.modalPoint1Bold')}</strong>{' '}
              {t('backup.modalPoint1Tail')}
            </li>
            <li>{t('backup.modalPoint2')}</li>
            <li>
              {t('backup.modalPoint3Lead')} <strong>{t('backup.modalPoint3Bold')}</strong>{' '}
              {t('backup.modalPoint3Tail')}
            </li>
            <li>{t('backup.modalPoint4')}</li>
          </ul>
        </div>

        <div className="sunken mt-3 space-y-1 p-3 text-[13px] text-ink-soft">
          <p><strong className="text-ink">{t('backup.modalBackup')}:</strong> <span className="font-mono">{backup.backup_name}</span></p>
          <p><strong className="text-ink">{t('backup.modalCreated')}:</strong> {fmtDate(backup.created_at)}</p>
          <p><strong className="text-ink">{t('backup.modalSize')}:</strong> {fmtBytes(backup.size_bytes)}</p>
          <p>
            <strong className="text-ink">{t('backup.modalRecords')}:</strong>{' '}
            {backup.record_count?.toLocaleString() || t('backup.unknown')} {t('backup.students')}
          </p>
        </div>

        <div className="mt-4 flex flex-wrap gap-3 pt-1">
          <button
            onClick={onCancel}
            disabled={loading}
            className="btn btn-ghost flex-1"
          >
            {t('common.cancel')}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="btn btn-danger flex-1"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" aria-hidden="true" /> : <RotateCcw className="w-4 h-4" aria-hidden="true" />}
            {loading ? t('backup.restoring') : t('backup.confirmRestore')}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Storage Status Widget ─────────────────────────────────────────────────────
function StorageWidget({ storage }) {
  const { t } = useI18n();
  if (!storage) return null;
  const diskPct = storage.disk_used_pct || 0;
  const diskColor = diskPct > 90 ? 'bg-err' : diskPct > 75 ? 'bg-warn' : 'bg-ok';

  return (
    <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 stagger">
      {/* DB Size */}
      <div className="card card-interactive lift relative space-y-1 p-4">
        <p className="t-support font-semibold uppercase tracking-wider text-ink-mute">{t('backup.dbSize')}</p>
        <p className="t-value text-ink">
          <CountUp value={storage.db_size_mb || 0} /> <span className="t-support font-semibold text-ink-mute">MB</span>
        </p>
        <p className="t-support text-ink-faint">
          {t('backup.dbBreakdown', { data: storage.data_size_mb, index: storage.index_size_mb })}
        </p>
        <span className="sheen" aria-hidden="true" />
      </div>

      {/* Backup Storage */}
      <div className="card card-interactive lift relative space-y-1 p-4">
        <p className="t-support font-semibold uppercase tracking-wider text-ink-mute">{t('backup.backupStorage')}</p>
        <p className="t-value text-ink">
          <CountUp value={storage.backup_storage_mb || 0} /> <span className="t-support font-semibold text-ink-mute">MB</span>
        </p>
        <p className="t-support text-ink-faint">
          {t('backup.verifiedBackups', { n: storage.total_backups || 0 })}
        </p>
        <span className="sheen" aria-hidden="true" />
      </div>

      {/* Disk Usage */}
      <div className="card space-y-2 p-4 sm:col-span-2">
        <div className="flex items-center justify-between">
          <p className="t-support font-semibold uppercase tracking-wider text-ink-mute">{t('backup.diskUsage')}</p>
          <span className={`t-support font-bold tabular-nums ${diskPct > 90 ? 'text-err' : diskPct > 75 ? 'text-warn' : 'text-ok'}`}>
            {diskPct}%
          </span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-sunken">
          <div
            className={`h-2 rounded-full transition-all duration-700 ${diskColor}`}
            style={{ width: `${Math.min(diskPct, 100)}%` }}
          />
        </div>
        <div className="t-support flex justify-between text-ink-faint">
          <span>{t('backup.diskUsed', { v: storage.disk_used_gb })}</span>
          <span>{t('backup.diskFree', { v: storage.disk_free_gb })}</span>
          <span>{t('backup.diskTotal', { v: storage.disk_total_gb })}</span>
        </div>
      </div>

      {/* Warnings */}
      {storage.warnings?.length > 0 && (
        <div className="space-y-1.5 rounded-md border border-warn/25 bg-warn-soft p-3 sm:col-span-2 lg:col-span-4">
          {storage.warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 text-sm text-warn">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
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
  const { t } = useI18n();

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
      showToast({ type: 'success', message: res.data.message || t('backup.createdToast') });
      fetchAll();
    } catch (err) {
      showToast({
        type: 'error',
        message: getUserMessage(err, t('backup.createFailed'))
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
        message: res.data.message || t('backup.restoredToast')
      });
      setRestoreTarget(null);
      fetchAll();
    } catch (err) {
      showToast({
        type: 'error',
        message: getUserMessage(err, t('backup.restoreFailed'))
      });
    } finally {
      setRestoring(false);
    }
  };

  const handleDeleteBackup = async (backup) => {
    if (!window.confirm(t('backup.deleteConfirm', { name: backup.backup_name }))) return;
    try {
      await api.delete(`/backup/${backup.id}`);
      showToast({ type: 'success', message: t('backup.deletedToast') });
      fetchAll();
    } catch (err) {
      showToast({
        type: 'error',
        message: getUserMessage(err, t('backup.deleteFailed'))
      });
    }
  };

  const tabs = [
    { id: 'backups', label: t('backup.tabHistory'), icon: <HardDrive className="w-4 h-4" aria-hidden="true" /> },
    { id: 'uploads', label: t('backup.tabUploads'), icon: <Layers className="w-4 h-4" aria-hidden="true" /> },
    { id: 'audit', label: t('backup.tabAudit'), icon: <Shield className="w-4 h-4" aria-hidden="true" /> },
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
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="t-section flex items-center gap-2 text-ink">
            <Database className="w-5 h-5 text-brand-fg" aria-hidden="true" />
            {t('backup.title')}
          </h2>
          <p className="t-support mt-1 text-ink-mute">{t('backup.subtitle')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={fetchAll}
            disabled={loadingBackups}
            className="btn btn-ghost btn-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingBackups ? 'animate-spin' : ''}`} aria-hidden="true" />
            {t('common.refresh')}
          </button>
          {isAdmin && (
            <button
              onClick={handleCreateBackup}
              disabled={creatingBackup}
              className="btn btn-accent"
            >
              {creatingBackup
                ? <RefreshCw className="w-4 h-4 animate-spin" aria-hidden="true" />
                : <Download className="w-4 h-4" aria-hidden="true" />}
              {creatingBackup ? t('backup.creating') : t('backup.create')}
            </button>
          )}
        </div>
      </div>

      {/* Storage Status */}
      {loadingStorage
        ? <div className="skeleton h-28 w-full" />
        : <StorageWidget storage={storage} />}

      {/* Info bar for Staff */}
      {!isAdmin && (
        <div className="flex items-start gap-2 rounded-md border border-info/25 bg-info-soft p-3 text-sm text-info">
          <Info className="w-4 h-4 flex-shrink-0 mt-0.5" aria-hidden="true" />
          {t('backup.staffNotice')}
        </div>
      )}

      {/* Tabs */}
      <div className="card overflow-hidden">
        <div
          role="tablist"
          className="flex flex-wrap items-center gap-2 border-b border-line bg-sunken px-4 py-2.5"
        >
          {tabs.filter(t => isAdmin || t.id !== 'backups' || t.id === 'uploads' || t.id === 'audit').map(tab => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-semibold transition-colors
                ${activeTab === tab.id
                  ? 'bg-brand text-white shadow-sm'
                  : 'text-ink-mute hover:bg-canvas hover:text-ink'}`}
            >
              {tab.icon}{tab.label}
            </button>
          ))}
        </div>

        <div className="p-4 sm:p-6">
          {/* ── Backup History Tab ── */}
          {activeTab === 'backups' && isAdmin && (
            loadingBackups ? (
              <div role="status" className="flex items-center justify-center py-16 text-ink-mute gap-3">
                <RefreshCw className="w-6 h-6 animate-spin" aria-hidden="true" />
                <span className="t-body">{t('backup.loadingHistory')}</span>
              </div>
            ) : backups.length === 0 ? (
              <div className="empty-state gap-3">
                <HardDrive className="h-12 w-12 text-ink-faint" aria-hidden="true" />
                <p className="t-card text-ink-soft">{t('backup.emptyHistory')}</p>
                <p className="t-support text-ink-mute">{t('backup.emptyHistoryHelp')}</p>
              </div>
            ) : (
              <div className="space-y-3">
                {backups.map(b => (
                  <div
                    key={b.id}
                    className="card overflow-hidden transition-colors hover:border-line-strong"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-4 p-4">
                      {/* Left: info */}
                      <div className="min-w-0 space-y-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusBadge status={b.status} />
                          <span className={`badge font-bold ${
                            b.backup_type === 'pre_restore' ? 'badge-warn' :
                            b.backup_type === 'manual' ? 'badge-brand' :
                            b.backup_type === 'auto_daily' ? 'badge-info' :
                            'badge-quiet'
                          }`}>
                            {b.backup_type?.replace('_', ' ').toUpperCase()}
                          </span>
                          {!b.file_exists && (
                            <span className="badge badge-err font-bold uppercase">
                              {t('backup.fileMissing')}
                            </span>
                          )}
                        </div>
                        <p className="text-sm font-mono text-ink-soft truncate max-w-xs" title={b.backup_name}>
                          {b.backup_name}
                        </p>
                        <div className="t-support flex flex-wrap items-center gap-x-4 gap-y-1 text-ink-mute">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" aria-hidden="true" />{fmtDate(b.created_at)}
                          </span>
                          <span className="tabular-nums">{fmtBytes(b.size_bytes)}</span>
                          <span className="tabular-nums">{b.record_count?.toLocaleString() || 0} {t('backup.students')}</span>
                          <span>{t('backup.by')}: <strong className="text-ink-soft">{b.created_by}</strong></span>
                        </div>
                      </div>

                      {/* Right: actions */}
                      <div className="flex flex-shrink-0 items-center gap-2">
                        <button
                          onClick={() => setExpandedBackup(expandedBackup === b.id ? null : b.id)}
                          aria-label={expandedBackup === b.id ? t('backup.hideDetails') : t('backup.showDetails')}
                          aria-expanded={expandedBackup === b.id}
                          className="rounded-md p-1.5 text-ink-faint transition-colors hover:bg-canvas hover:text-ink"
                        >
                          {expandedBackup === b.id ? <ChevronUp className="w-4 h-4" aria-hidden="true" /> : <ChevronDown className="w-4 h-4" aria-hidden="true" />}
                        </button>
                        {b.status !== 'failed' && b.file_exists && (
                          <button
                            onClick={() => setRestoreTarget(b)}
                            className="btn btn-danger-soft btn-sm"
                          >
                            <RotateCcw className="w-3.5 h-3.5" aria-hidden="true" />
                            {t('backup.restore')}
                          </button>
                        )}
                        {b.backup_type !== 'pre_restore' && (
                          <button
                            onClick={() => handleDeleteBackup(b)}
                            aria-label={t('backup.deleteAria')}
                            className="rounded-md p-1.5 text-ink-faint transition-colors hover:bg-err-soft hover:text-err"
                          >
                            <Trash2 className="w-4 h-4" aria-hidden="true" />
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Expanded row */}
                    {expandedBackup === b.id && (
                      <div className="slide-down space-y-1 border-t border-line bg-canvas px-4 py-3 text-[13px] text-ink-mute">
                        {b.error_message && (
                          <p className="text-err"><strong>{t('common.error')}:</strong> {b.error_message}</p>
                        )}
                        <p><strong className="text-ink-soft">{t('backup.verified')}:</strong> {b.verified ? t('backup.verifiedYes') : t('backup.notVerified')}</p>
                        <p><strong className="text-ink-soft">{t('backup.completed')}:</strong> {fmtDate(b.completed_at)}</p>
                        <p><strong className="text-ink-soft">{t('backup.fileLabel')}:</strong> <span className="font-mono">{b.backup_name}</span></p>
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
              <div className="empty-state gap-3">
                <Layers className="h-12 w-12 text-ink-faint" aria-hidden="true" />
                <p className="t-card text-ink-soft">{t('backup.emptyUploads')}</p>
                <p className="t-support text-ink-mute">{t('backup.emptyUploadsHelp')}</p>
              </div>
            ) : (
              <div className="table-scroll">
                <table className="w-full t-table">
                  <thead>
                    <tr>
                      <th className="th">{t('backup.colFile')}</th>
                      <th className="th">{t('backup.colAdded')}</th>
                      <th className="th">{t('backup.colUpdated')}</th>
                      <th className="th">{t('backup.colUnchanged')}</th>
                      <th className="th">{t('backup.colMarks')}</th>
                      <th className="th">{t('backup.colSkipped')}</th>
                      <th className="th">{t('common.status')}</th>
                      <th className="th">{t('backup.colBy')}</th>
                      <th className="th">{t('backup.colTime')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {uploadVersions.map(v => (
                      <tr key={v.id} className="tr-hover">
                        <td className="td font-mono text-xs text-ink-soft t-truncate" title={v.filename}>{v.filename}</td>
                        <td className="td font-semibold tabular-nums text-ok">{v.students_added}</td>
                        <td className="td font-semibold tabular-nums text-warn">{v.students_updated}</td>
                        <td className="td tabular-nums text-ink-mute">{v.students_unchanged}</td>
                        <td className="td font-semibold tabular-nums text-brand-fg">{(v.marks_added || 0) + (v.marks_updated || 0)}</td>
                        <td className="td tabular-nums text-ink-mute">{v.skipped_rows}</td>
                        <td className="td">
                          <StatusBadge status={v.status === 'success' ? 'verified' : v.status} />
                        </td>
                        <td className="td text-xs text-ink-soft">{v.performed_by}</td>
                        <td className="td whitespace-nowrap text-xs text-ink-mute">{fmtDate(v.created_at)}</td>
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
              <div className="empty-state gap-3">
                <Shield className="h-12 w-12 text-ink-faint" aria-hidden="true" />
                <p className="t-card text-ink-soft">{t('backup.emptyAudit')}</p>
                <p className="t-support text-ink-mute">{t('backup.emptyAuditHelp')}</p>
              </div>
            ) : (
              <div className="max-h-[600px] space-y-2 overflow-y-auto pr-1">
                {auditLog.map(log => (
                  <div
                    key={log.id}
                    className={`flex flex-wrap items-start justify-between gap-3 rounded-md border p-3 text-[13px]
                      ${log.success
                        ? 'border-line bg-canvas'
                        : 'border-err/30 bg-err-soft'}`}
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        {log.success
                          ? <CheckCircle className="w-3 h-3 text-ok" aria-hidden="true" />
                          : <XCircle className="w-3 h-3 text-err" aria-hidden="true" />}
                        <span className="text-[11px] font-bold uppercase tracking-wider text-ink">
                          {log.action}
                        </span>
                        {log.target_table && (
                          <span className="badge badge-quiet font-mono">
                            {log.target_table}
                          </span>
                        )}
                      </div>
                      {log.summary && (
                        <p className="text-ink-soft leading-relaxed">
                          {log.summary}
                        </p>
                      )}
                      {log.error_info && (
                        <p className="text-err">{t('common.error')}: {log.error_info}</p>
                      )}
                    </div>
                    <div className="space-y-1 text-right flex-shrink-0">
                      <p className="font-semibold text-ink-soft">{log.username} <span className="text-ink-faint">({log.role})</span></p>
                      <p className="text-ink-faint">{fmtDate(log.created_at)}</p>
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

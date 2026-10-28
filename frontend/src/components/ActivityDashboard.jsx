import { useState, useEffect } from 'react';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import { useToast } from './Toast';
import { useI18n } from '../context/LanguageContext';
import CountUp from './CountUp';
import {
  Search, PlusCircle, Trash2, Edit3, UploadCloud, Download, RotateCcw,
  Clock, User, RefreshCw, Layers, CheckCircle, HelpCircle, Activity
} from 'lucide-react';

export default function ActivityDashboard() {
  const { t } = useI18n();
  const [activities, setActivities] = useState({
    searches: [],
    additions: [],
    deletions: [],
    updates: [],
    uploads: [],
    exports: [],
    semester_updates: [],
    backups: []
  });
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState('all');
  const [revertingToken, setRevertingToken] = useState(null);
  const { showToast } = useToast();

  const fetchActivity = async () => {
    setLoading(true);
    try {
      const res = await api.get('/undo/activity');
      setActivities(res.data);
    } catch (err) {
      console.error('Failed to fetch activity logs:', err);
      showToast({ type: 'error', message: t('activity.errLoad') });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchActivity();
  }, []);

  const handleUndo = async (token, type) => {
    if (!token) return;
    setRevertingToken(token);
    try {
      const res = await api.post(`/undo/restore/${token}`);
      showToast({
        type: 'success',
        message: res.data.message || t('activity.revertedToast', { type })
      });
      fetchActivity();
    } catch (err) {
      showToast({
        type: 'error',
        message: getUserMessage(err, t('activity.restoreFailed'))
      });
    } finally {
      setRevertingToken(null);
    }
  };

  // Compile unified timeline
  const getUnifiedTimeline = () => {
    const timeline = [];

    activities.searches?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'search',
        icon: <Search className="w-4 h-4 text-info" />,
        color: 'badge-info',
        title: t('activity.tQuery'),
        desc: t('activity.dSearched', { query: item.natural_query }),
        tables: 'query_history'
      });
    });

    activities.additions?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'addition',
        icon: <PlusCircle className="w-4 h-4 text-ok" />,
        color: 'badge-ok',
        title: t('activity.tProfileAdded'),
        desc: item.description || t('activity.dInserted', { names: item.affected_students?.map(s => s.name).join(', ') }),
        tables: 'students table'
      });
    });

    activities.deletions?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'deletion',
        icon: <Trash2 className="w-4 h-4 text-err" />,
        color: 'badge-err',
        title: t('activity.tDeletion'),
        desc: item.description || t('activity.dDeletedStudents', { names: item.affected_students?.map(s => s.name).join(', ') }),
        tables: 'students, marks table'
      });
    });

    activities.updates?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'update',
        icon: <Edit3 className="w-4 h-4 text-warn" />,
        color: 'badge-warn',
        title: t('activity.tUpdated'),
        desc: item.description || t('activity.dUpdated', { names: item.affected_students?.map(s => s.name).join(', ') }),
        tables: 'students table'
      });
    });

    activities.uploads?.forEach(item => {
      const isFileDelete = (item.operation_type || '').toUpperCase() === 'FILE_DELETE';
      timeline.push({
        ...item,
        stream: isFileDelete ? 'upload' : 'upload',
        icon: isFileDelete
          ? <Trash2 className="w-4 h-4 text-err" />
          : <UploadCloud className="w-4 h-4 text-brand-fg" />,
        color: isFileDelete ? 'badge-err' : 'badge-brand',
        title: isFileDelete ? t('activity.tFileDeleted') : t('activity.tBulkImport'),
        desc: item.description || (isFileDelete
          ? t('activity.dDeletedFile', { name: item.filename || '' }).trim()
          : t('activity.dUploaded', { n: item.affected_students?.length })),
        tables: isFileDelete ? 'students, marks, uploaded_files' : 'students, uploaded_files'
      });
    });

    activities.exports?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'export',
        icon: <Download className="w-4 h-4 text-ink-soft" />,
        color: 'badge-quiet',
        title: t('activity.tReportExported'),
        desc: t('activity.dExported', { format: item.format.toUpperCase(), n: item.record_count }),
        tables: 'export_logs'
      });
    });

    activities.semester_updates?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'semester_update',
        icon: <RotateCcw className="w-4 h-4 text-ok" />,
        color: 'badge-ok',
        title: t('activity.tVtuSync'),
        desc: t('activity.dSemester', { n: item.affected_students?.length }),
        tables: 'students, marks'
      });
    });

    activities.undo_operations?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'undo',
        icon: <RotateCcw className="w-4 h-4 text-ok" />,
        color: 'badge-ok',
        title: t('activity.tUndoDone'),
        desc: item.description || t('activity.dUndone'),
        tables: 'students, marks',
        status: 'SUCCESS'
      });
    });

    activities.backups?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'backup',
        icon: <Layers className="w-4 h-4 text-info" />,
        color: 'badge-info',
        title: t('activity.tBackupCreated'),
        desc: t('activity.dBackup', { name: item.backup_name, type: item.backup_type, status: item.status }),
        tables: 'db_backups'
      });
    });

    activities.audit_events?.forEach(item => {
      const labels = { RESTORED: 'activity.aRestored', UNDO_SUCCESS: 'activity.aUndoSuccess', UPLOAD_FAILED: 'activity.aUploadFailed', UNDO_FAILED: 'activity.aUndoFailed', LOGIN_SUCCESS: 'activity.aLogin', LOGOUT: 'activity.aLogout' };
      if (!labels[item.action]) return;
      timeline.push({
        ...item,
        stream: 'audit',
        icon: <Activity className="w-4 h-4 text-brand-fg" />,
        color: 'badge-brand',
        title: t(labels[item.action]),
        desc: item.summary || t(labels[item.action]),
        tables: item.target_table || 'audit_log',
        status: item.success ? 'SUCCESS' : 'FAILED'
      });
    });

    // Sort by timestamp desc
    return timeline.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  };

  const timelineData = getUnifiedTimeline();
  const filteredData = activeFilter === 'all'
    ? timelineData
    : timelineData.filter(item => item.stream === activeFilter);

  // Compute status cards
  const statCards = [
    { label: t('activity.totalSearches'), count: activities.searches?.length || 0, icon: <Search className="w-5 h-5 text-info" /> },
    { label: t('activity.deletionsTracked'), count: activities.deletions?.length || 0, icon: <Trash2 className="w-5 h-5 text-err" /> },
    { label: t('activity.updatesDone'), count: activities.updates?.length || 0, icon: <Edit3 className="w-5 h-5 text-warn" /> },
    { label: t('activity.dbBackups'), count: activities.backups?.length || 0, icon: <Layers className="w-5 h-5 text-brand-fg" /> }
  ];

  return (
    <div className="anim-fade-up space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="t-section flex items-center gap-2 text-ink">
            <Activity className="w-5 h-5 text-brand-fg" aria-hidden="true" />
            {t('activity.title')}
          </h2>
          <p className="t-support mt-1 text-ink-mute">
            {t('activity.sub')}
          </p>
        </div>
        <button
          onClick={fetchActivity}
          disabled={loading}
          className="btn btn-sm btn-ghost flex-shrink-0"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          {loading ? t('activity.refreshing') : t('activity.refresh')}
        </button>
      </div>

      {/* Grid count cards */}
      <div className="stagger grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((c, i) => (
          <div key={i} className="card card-interactive lift relative flex items-center justify-between gap-3 p-4">
            <div className="min-w-0 space-y-1">
              <span className="t-support t-truncate block text-ink-mute">{c.label}</span>
              <p className="t-value text-ink"><CountUp value={c.count} /></p>
            </div>
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-brand/10">
              {c.icon}
            </div>
            <span className="sheen" aria-hidden="true" />
          </div>
        ))}
      </div>

      {/* Main interface card */}
      <div className="card-elev overflow-hidden">
        {/* Navigation tabs for streams */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-sunken px-3 py-2.5 sm:px-5">
          <div
            className="flex flex-wrap items-center gap-1.5"
            role="group"
            aria-label={t('activity.filterAria')}
          >
            {[
              { id: 'all', label: t('activity.tabAll'), icon: <Layers className="w-3 h-3" /> },
              { id: 'search', label: t('activity.tabQueries'), icon: <Search className="w-3 h-3" /> },
              { id: 'addition', label: t('activity.tabAdditions'), icon: <PlusCircle className="w-3 h-3" /> },
              { id: 'deletion', label: t('activity.tabDeletions'), icon: <Trash2 className="w-3 h-3" /> },
              { id: 'update', label: t('activity.tabUpdates'), icon: <Edit3 className="w-3 h-3" /> },
              { id: 'upload', label: t('activity.tabUploads'), icon: <UploadCloud className="w-3 h-3" /> },
              { id: 'backup', label: t('activity.tabBackups'), icon: <Layers className="w-3 h-3" /> },
              { id: 'export', label: t('activity.tabExports'), icon: <Download className="w-3 h-3" /> },
              { id: 'semester_update', label: t('activity.tabVtuSync'), icon: <RotateCcw className="w-3 h-3" /> }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveFilter(tab.id)}
                aria-pressed={activeFilter === tab.id}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors
                  ${activeFilter === tab.id
                    ? 'bg-brand text-white'
                    : 'text-ink-soft hover:bg-surface hover:text-ink'}`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>
          <span className="t-support text-ink-mute">{t('activity.recordCount', { n: filteredData.length })}</span>
        </div>

        {/* Timeline list */}
        <div className="p-4 sm:p-6">
          {loading ? (
            <div className="space-y-3" aria-busy="true" role="status">
              <span className="sr-only">{t('activity.loading')}</span>
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-20 w-full" />
              ))}
            </div>
          ) : filteredData.length === 0 ? (
            <div className="empty-state">
              <span className="flex h-12 w-12 items-center justify-center rounded-full bg-sunken">
                <HelpCircle className="w-6 h-6 text-ink-faint" />
              </span>
              <p className="t-card text-ink-soft">{t('activity.empty')}</p>
              <p className="t-support text-ink-mute">{t('activity.emptyHint')}</p>
            </div>
          ) : (
            <div className="relative ml-4 space-y-5 border-l border-line pl-5 sm:pl-6">
              {filteredData.map((item, index) => {
                const isUndone = item.undone === 1 || item.status === 'UNDONE';
                const isReverting = revertingToken === item.undo_token;

                return (
                  <div key={index} className="relative">
                    {/* Bullet marker */}
                    <div className="absolute -left-[27px] top-2 flex h-4 w-4 items-center justify-center rounded-full border border-line bg-surface">
                      <div className="h-2 w-2 rounded-full bg-brand" />
                    </div>

                    {/* Timeline card */}
                    <div className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4 transition-colors hover:bg-sunken/60 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                      <div className="min-w-0 space-y-2">
                        {/* Stream badge */}
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`badge ${item.color}`}>
                            {item.icon}
                            {item.title}
                          </span>
                          {isUndone && (
                            <span className="badge badge-quiet">
                              <CheckCircle className="w-2.5 h-2.5" /> {t('activity.undone')}
                            </span>
                          )}
                          {!isUndone && item.status && (
                            <span className={`badge ${item.status === 'SUCCESS' ? 'badge-ok' : item.status === 'FAILED' ? 'badge-err' : 'badge-quiet'}`}>
                              {item.status}
                            </span>
                          )}
                        </div>

                        {/* Description */}
                        <p className="t-body break-words font-medium text-ink">
                          {item.desc}
                        </p>

                        {/* Metadata row */}
                        <div className="t-support flex flex-wrap items-center gap-x-4 gap-y-1 text-ink-mute">
                          <span className="flex items-center gap-1">
                            <User className="w-3 h-3" />
                            {t('activity.operator')} <strong className="font-semibold text-ink-soft">{item.actor || t('activity.system')}</strong>
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {new Date(item.timestamp).toLocaleString('en-IN', {
                              day: '2-digit', month: 'short', year: 'numeric',
                              hour: '2-digit', minute: '2-digit', hour12: true
                            })}
                          </span>
                          <span className="flex items-center gap-1 font-mono text-[11px]">
                            {t('activity.dbTable')} <span className="text-brand-fg">{item.tables}</span>
                          </span>
                          {item.operation_id && <span className="font-mono text-[11px]">{t('activity.operation')} {item.operation_id}</span>}
                        </div>

                        {/* Affected records list */}
                        {item.affected_students?.length > 0 && (
                          <div className="sunken max-h-24 space-y-1 overflow-y-auto p-2">
                            <span className="t-support block px-1 text-ink-mute">{t('activity.affectedRecords', { n: item.affected_students.length })}</span>
                            {item.affected_students.map((st, sidx) => (
                              <div key={sidx} className="t-support flex items-center justify-between gap-3 rounded px-1 py-0.5 hover:bg-surface">
                                <span className="t-truncate min-w-0 font-medium text-ink-soft" title={st.name}>{st.name}</span>
                                <span className="flex-shrink-0 font-mono text-[11px] whitespace-nowrap text-ink-mute" title={st.usn}>{st.usn}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Undo action button */}
                      {item.undo_token && item.can_undo && !isUndone && (
                        <div className="flex-shrink-0 sm:self-center">
                          <button
                            onClick={() => handleUndo(item.undo_token, item.title)}
                            disabled={isReverting}
                            className="btn btn-sm btn-primary"
                          >
                            <RotateCcw className={`w-3.5 h-3.5 ${isReverting ? 'animate-spin' : ''}`} />
                            {isReverting ? t('activity.undoing') : t('activity.undo')}
                          </button>
                        </div>
                      )}
                      {item.undo_token && !item.can_undo && !isUndone && (
                        <span className="t-support max-w-36 text-ink-mute">{item.undo_unavailable_reason || t('activity.undoUnavailable')}</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

import { useState, useEffect } from 'react';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import { useToast } from './Toast';
import { 
  Search, PlusCircle, Trash2, Edit3, UploadCloud, Download, RotateCcw, 
  Clock, User, RefreshCw, Layers, CheckCircle, HelpCircle, Activity
} from 'lucide-react';

export default function ActivityDashboard() {
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
      showToast({ type: 'error', message: 'Failed to load activity logs.' });
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
        message: res.data.message || `Reverted ${type} successfully!`
      });
      fetchActivity();
    } catch (err) {
      showToast({
        type: 'error',
        message: getUserMessage(err, 'Could not restore student.')
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
        icon: <Search className="w-4 h-4 text-sky-500" />,
        color: 'from-sky-500/10 to-blue-500/10 text-sky-600 border-sky-200 dark:border-sky-800/40',
        title: 'NLP Data Query',
        desc: `Searched: "${item.natural_query}"`,
        tables: 'query_history'
      });
    });

    activities.additions?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'addition',
        icon: <PlusCircle className="w-4 h-4 text-green-500" />,
        color: 'from-green-500/10 to-emerald-500/10 text-green-600 border-green-200 dark:border-green-800/40',
        title: 'Student Profile Added',
        desc: item.description || `Inserted students: ${item.affected_students?.map(s => s.name).join(', ')}`,
        tables: 'students table'
      });
    });

    activities.deletions?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'deletion',
        icon: <Trash2 className="w-4 h-4 text-rose-500" />,
        color: 'from-rose-500/10 to-red-500/10 text-rose-600 border-rose-200 dark:border-rose-800/40',
        title: 'Student Deletion Executed',
        desc: item.description || `Deleted students: ${item.affected_students?.map(s => s.name).join(', ')}`,
        tables: 'students, marks table'
      });
    });

    activities.updates?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'update',
        icon: <Edit3 className="w-4 h-4 text-amber-500" />,
        color: 'from-amber-500/10 to-orange-500/10 text-amber-600 border-amber-200 dark:border-amber-800/40',
        title: 'Student Record Updated',
        desc: item.description || `Updated students: ${item.affected_students?.map(s => s.name).join(', ')}`,
        tables: 'students table'
      });
    });

    activities.uploads?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'upload',
        icon: <UploadCloud className="w-4 h-4 text-indigo-500" />,
        color: 'from-indigo-500/10 to-violet-500/10 text-indigo-600 border-indigo-200 dark:border-indigo-800/40',
        title: 'Bulk Database Import',
        desc: item.description || `Uploaded file data containing ${item.affected_students?.length} record(s)`,
        tables: 'students, uploaded_files'
      });
    });

    activities.exports?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'export',
        icon: <Download className="w-4 h-4 text-purple-500" />,
        color: 'from-purple-500/10 to-fuchsia-500/10 text-purple-600 border-purple-200 dark:border-purple-800/40',
        title: 'Academic Report Exported',
        desc: `Generated and downloaded ${item.format.toUpperCase()} sheet containing ${item.record_count} record(s)`,
        tables: 'export_logs'
      });
    });

    activities.semester_updates?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'semester_update',
        icon: <RotateCcw className="w-4 h-4 text-teal-500" />,
        color: 'from-teal-500/10 to-emerald-500/10 text-teal-600 border-teal-200 dark:border-teal-800/40',
        title: 'VTU Semester Synchronization',
        desc: `Completed academic semester mapping for ${item.affected_students?.length} student(s)`,
        tables: 'students, marks'
      });
    });

    activities.undo_operations?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'undo',
        icon: <RotateCcw className="w-4 h-4 text-teal-500" />,
        color: 'from-teal-500/10 to-cyan-500/10 text-teal-600 border-teal-200 dark:border-teal-800/40',
        title: 'Undo Completed',
        desc: item.description || 'Operation undone.',
        tables: 'students, marks',
        status: 'SUCCESS'
      });
    });

    activities.backups?.forEach(item => {
      timeline.push({
        ...item,
        stream: 'backup',
        icon: <Layers className="w-4 h-4 text-blue-500" />,
        color: 'from-blue-500/10 to-indigo-500/10 text-blue-600 border-blue-200 dark:border-blue-800/40',
        title: 'Database Backup Created',
        desc: `Backup ${item.backup_name} (${item.backup_type}) created. Status: ${item.status}`,
        tables: 'db_backups'
      });
    });

    activities.audit_events?.forEach(item => {
      const labels = { RESTORED: 'Student Restored', UNDO_SUCCESS: 'Undo Completed', UPLOAD_FAILED: 'Import Failed', UNDO_FAILED: 'Undo Failed', LOGIN_SUCCESS: 'User Login', LOGOUT: 'User Logout' };
      if (!labels[item.action]) return;
      timeline.push({
        ...item,
        stream: 'audit',
        icon: <Activity className="w-4 h-4 text-teal-500" />,
        color: 'from-teal-500/10 to-cyan-500/10 text-teal-600 border-teal-200 dark:border-teal-800/40',
        title: labels[item.action],
        desc: item.summary || labels[item.action],
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
    { label: 'Total Searches', count: activities.searches?.length || 0, icon: <Search className="w-5 h-5 text-sky-500" /> },
    { label: 'Deletions Tracked', count: activities.deletions?.length || 0, icon: <Trash2 className="w-5 h-5 text-rose-500" /> },
    { label: 'Updates Done', count: activities.updates?.length || 0, icon: <Edit3 className="w-5 h-5 text-amber-500" /> },
    { label: 'Database Backups', count: activities.backups?.length || 0, icon: <UploadCloud className="w-5 h-5 text-indigo-500" /> }
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
            <Activity className="w-5 h-5 text-blue-600" />
            Audit Activity & Operations Log
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Real-time track, snapshot timeline, and safe database reversion control.
          </p>
        </div>
        <button
          onClick={fetchActivity}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 text-xs font-semibold rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          {loading ? 'Refreshing...' : 'Refresh Logs'}
        </button>
      </div>

      {/* Grid count cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {statCards.map((c, i) => (
          <div key={i} className="p-4 bg-white/70 dark:bg-slate-900/50 backdrop-blur-md rounded-2xl border border-slate-200/60 dark:border-slate-800/40 flex items-center justify-between shadow-sm">
            <div className="space-y-1">
              <span className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wider font-bold">{c.label}</span>
              <p className="text-xl font-black text-slate-800 dark:text-slate-100 font-mono">{c.count}</p>
            </div>
            <div className="p-2.5 bg-slate-50 dark:bg-slate-800/60 rounded-xl">
              {c.icon}
            </div>
          </div>
        ))}
      </div>

      {/* Main interface card */}
      <div className="bg-white/80 dark:bg-slate-900/60 backdrop-blur-lg rounded-2xl border border-slate-200/80 dark:border-slate-800/60 shadow-md overflow-hidden">
        {/* Navigation tabs for streams */}
        <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800/60 flex items-center justify-between flex-wrap gap-2 bg-slate-50/50 dark:bg-slate-950/20">
          <div className="flex items-center gap-1 flex-wrap">
            {[
              { id: 'all', label: 'All Operations', icon: <Layers className="w-3 h-3" /> },
              { id: 'search', label: 'Queries', icon: <Search className="w-3 h-3" /> },
              { id: 'addition', label: 'Additions', icon: <PlusCircle className="w-3 h-3" /> },
              { id: 'deletion', label: 'Deletions', icon: <Trash2 className="w-3 h-3" /> },
              { id: 'update', label: 'Updates', icon: <Edit3 className="w-3 h-3" /> },
              { id: 'upload', label: 'Uploads', icon: <UploadCloud className="w-3 h-3" /> },
              { id: 'backup', label: 'Backups', icon: <Layers className="w-3 h-3" /> },
              { id: 'export', label: 'Exports', icon: <Download className="w-3 h-3" /> },
              { id: 'semester_update', label: 'VTU Sync', icon: <RotateCcw className="w-3 h-3" /> }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveFilter(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all
                  ${activeFilter === tab.id
                    ? 'bg-blue-600 text-white shadow-sm shadow-blue-500/20'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-800'}`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>
          <span className="text-[10px] text-slate-400 font-bold uppercase">{filteredData.length} records</span>
        </div>

        {/* Timeline list */}
        <div className="p-6">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
              <div className="w-8 h-8 border-4 border-slate-200 border-t-blue-500 rounded-full animate-spin" />
              <p className="text-xs font-medium">Fetching secure activity records...</p>
            </div>
          ) : filteredData.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-400 gap-3">
              <div className="w-12 h-12 bg-slate-50 dark:bg-slate-800 rounded-full flex items-center justify-center text-slate-300">
                <HelpCircle className="w-6 h-6" />
              </div>
              <p className="text-sm font-bold">No activity logs found</p>
              <p className="text-xs text-slate-500">Perform actions in the query dashboard to populate logs.</p>
            </div>
          ) : (
            <div className="relative border-l border-slate-100 dark:border-slate-800 ml-4 pl-6 space-y-6">
              {filteredData.map((item, index) => {
                const isUndone = item.undone === 1 || item.status === 'UNDONE';
                const isReverting = revertingToken === item.undo_token;
                
                return (
                  <div key={index} className="relative group">
                    {/* Bullet marker */}
                    <div className="absolute -left-[35px] top-1.5 w-4 h-4 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-center z-10 shadow-sm transition-all group-hover:scale-110">
                      <div className="w-2 h-2 rounded-full bg-blue-500" />
                    </div>

                    {/* Timeline card */}
                    <div className="bg-slate-50/50 dark:bg-slate-950/20 hover:bg-slate-50 dark:hover:bg-slate-950/40 border border-slate-100 dark:border-slate-800/80 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-all hover:shadow-sm">
                      <div className="space-y-2 min-w-0">
                        {/* Stream badge */}
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`inline-flex items-center gap-1 text-[9px] font-bold px-2 py-0.5 rounded-full border bg-gradient-to-r ${item.color}`}>
                            {item.icon}
                            {item.title}
                          </span>
                          {isUndone && (
                            <span className="inline-flex items-center gap-0.5 text-[9px] font-bold px-2 py-0.5 rounded-full border bg-slate-100 border-slate-300 text-slate-500 uppercase">
                              <CheckCircle className="w-2.5 h-2.5 text-slate-500" /> Undone / Rolled Back
                            </span>
                          )}
                          {!isUndone && item.status && (
                            <span className={`inline-flex items-center gap-0.5 text-[9px] font-bold px-2 py-0.5 rounded-full border uppercase ${item.status === 'SUCCESS' ? 'bg-emerald-50 border-emerald-200 text-emerald-600' : item.status === 'FAILED' ? 'bg-rose-50 border-rose-200 text-rose-600' : 'bg-slate-100 border-slate-300 text-slate-500'}`}>
                              {item.status}
                            </span>
                          )}
                        </div>

                        {/* Description */}
                        <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 break-words leading-relaxed">
                          {item.desc}
                        </p>

                        {/* Metadata row */}
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-400 font-medium">
                          <span className="flex items-center gap-1">
                            <User className="w-3 h-3 text-slate-400" />
                            Operator: <strong className="text-slate-600 dark:text-slate-300 font-semibold">{item.actor || 'System'}</strong>
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3 text-slate-400" />
                            {new Date(item.timestamp).toLocaleString('en-IN', {
                              day: '2-digit', month: 'short', year: 'numeric',
                              hour: '2-digit', minute: '2-digit', hour12: true
                            })}
                          </span>
                          <span className="flex items-center gap-1 font-mono text-[10px]">
                            Database Table: <span className="text-indigo-500">{item.tables}</span>
                          </span>
                          {item.operation_id && <span className="font-mono text-[10px]">Operation: {item.operation_id}</span>}
                        </div>

                        {/* Affected records list */}
                        {item.affected_students?.length > 0 && (
                          <div className="mt-2.5 p-2 bg-white/50 dark:bg-slate-900/60 border border-slate-100 dark:border-slate-800 rounded-xl max-h-24 overflow-y-auto space-y-1">
                            <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 block px-1">Affected Records ({item.affected_students.length}):</span>
                            {item.affected_students.map((st, sidx) => (
                              <div key={sidx} className="flex items-center justify-between text-[11px] px-1 hover:bg-slate-100/50 dark:hover:bg-slate-800/40 rounded py-0.5">
                                <span className="text-slate-600 dark:text-slate-300 font-semibold truncate max-w-[200px]">{st.name}</span>
                                <span className="text-slate-400 dark:text-slate-500 font-mono text-[10px]">{st.usn}</span>
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
                            className="flex items-center gap-1.5 px-4 py-2 border border-amber-200 dark:border-amber-800/40 bg-amber-500/10 hover:bg-amber-500 hover:text-white text-amber-600 dark:text-amber-400 text-xs font-bold rounded-xl transition-all disabled:opacity-50 active:scale-95"
                          >
                            <RotateCcw className={`w-3.5 h-3.5 ${isReverting ? 'animate-spin' : ''}`} />
                            {isReverting ? 'Undoing...' : 'UNDO'}
                          </button>
                        </div>
                      )}
                      {item.undo_token && !item.can_undo && !isUndone && (
                        <span className="text-[10px] text-slate-400 max-w-36">{item.undo_unavailable_reason || 'Undo unavailable'}</span>
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

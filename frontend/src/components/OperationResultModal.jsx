/**
 * OperationResultModal — Detailed popup after add/delete/upload operations.
 *
 * Upload stats come from backend result fields only (never frontend guesses).
 */
import { useState } from 'react';
import {
  CheckCircle, Trash2, Upload, Edit3, X,
  User, Database, Clock, RotateCcw, AlertTriangle, ChevronDown, ChevronRight
} from 'lucide-react';
import api from '../services/api';

const OP_CONFIG = {
  DELETE: {
    icon:    <Trash2 className="w-5 h-5" />,
    color:   'text-red-600',
    bg:      'bg-red-50 dark:bg-red-950/40',
    border:  'border-red-200 dark:border-red-800',
    badge:   'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300',
    title:   'Student Deleted',
    storage: 'soft_delete_records',
  },
  INSERT: {
    icon:    <CheckCircle className="w-5 h-5" />,
    color:   'text-green-600',
    bg:      'bg-green-50 dark:bg-green-950/40',
    border:  'border-green-200 dark:border-green-800',
    badge:   'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300',
    title:   'Student Added',
    storage: 'students table',
  },
  UPDATE: {
    icon:    <Edit3 className="w-5 h-5" />,
    color:   'text-blue-600',
    bg:      'bg-blue-50 dark:bg-blue-950/40',
    border:  'border-blue-200 dark:border-blue-800',
    badge:   'bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300',
    title:   'Record Updated',
    storage: 'students table + student_history',
  },
  UPLOAD: {
    icon:    <Upload className="w-5 h-5" />,
    color:   'text-indigo-600',
    bg:      'bg-indigo-50 dark:bg-indigo-950/40',
    border:  'border-indigo-200 dark:border-indigo-800',
    badge:   'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300',
    title:   'Upload Completed',
    storage: 'students table + marks table',
  },
};

function DetailList({ title, rows, emptyLabel }) {
  const [open, setOpen] = useState(false);
  if (!rows || rows.length === 0) return null;
  return (
    <div className="border border-slate-200 dark:border-slate-700 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800"
      >
        <span>{title} ({rows.length}{rows.length >= 50 ? '+' : ''})</span>
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
      </button>
      {open && (
        <div className="max-h-40 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
          {rows.map((r, i) => (
            <div key={i} className="px-3 py-2 text-[11px] text-slate-600 dark:text-slate-300">
              <div className="flex justify-between gap-2">
                <span className="font-mono text-slate-400">Row {r.row_number ?? r.row_index ?? '—'}</span>
                <span className="font-mono">{r.usn || '—'}</span>
              </div>
              <p className="font-medium truncate">{r.name || emptyLabel || '—'}</p>
              {r.reason && <p className="text-amber-700 dark:text-amber-400 mt-0.5">{r.reason}</p>}
              {r.problematic_fields?.length > 0 && (
                <p className="text-slate-400 mt-0.5">Fields: {r.problematic_fields.join(', ')}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function OperationResultModal({ result, onClose, onUndoDone }) {
  const [undoing, setUndoing] = useState(false);
  const [undone, setUndone]   = useState(false);

  if (!result) return null;

  const {
    operation = 'INSERT',
    affectedStudents = [],
    rowsAffected = 0,
    performedBy = '',
    timestamp = new Date().toISOString(),
    restoreTokens = [],
    uploadStats = null,
    message = '',
  } = result;

  const cfg = OP_CONFIG[operation] || OP_CONFIG.INSERT;

  const handleUndo = async () => {
    if (!restoreTokens.length || undoing || undone) return;
    setUndoing(true);
    try {
      for (const { token } of restoreTokens) {
        await api.post(`/undo/restore/${token}`);
      }
      setUndone(true);
      onUndoDone?.();
      setTimeout(onClose, 1500);
    } catch {
      // inline — keep modal open
    } finally {
      setUndoing(false);
    }
  };

  const ts = (() => {
    try { return new Date(timestamp).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }); }
    catch { return timestamp; }
  })();

  const uploadStatCells = uploadStats ? [
    ['Rows Parsed', uploadStats.rows_parsed ?? 0],
    ['New', uploadStats.students_added ?? 0],
    ['Updated', uploadStats.students_updated ?? 0],
    ['Unchanged', uploadStats.students_unchanged ?? 0],
    ['Duplicates', uploadStats.duplicate_rows ?? 0],
    ['Invalid', uploadStats.invalid_rows ?? 0],
    ['Students Saved', uploadStats.students_saved ?? 0],
    ['Marks Saved', uploadStats.marks_saved ?? 0],
  ] : [];

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
      <div className={`bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border ${cfg.border} w-full max-w-lg overflow-hidden`}
        style={{ animation: 'slideDown 0.2s ease-out' }}>

        <div className={`px-5 py-4 ${cfg.bg} border-b ${cfg.border} flex items-center justify-between`}>
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-xl bg-white/60 dark:bg-slate-800/60 ${cfg.color}`}>
              {cfg.icon}
            </div>
            <div>
              <h3 className={`text-sm font-bold ${cfg.color}`}>{cfg.title}</h3>
              {undone
                ? <p className="text-xs text-green-600 font-semibold">✓ Restored successfully</p>
                : <p className="text-xs text-slate-500 dark:text-slate-400">{message}</p>}
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 transition-colors">
            <X className="w-4 h-4 text-slate-400" />
          </button>
        </div>

        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          {uploadStats && (
            <>
              <div className="grid grid-cols-4 gap-2">
                {uploadStatCells.map(([label, val]) => (
                  <div key={label} className="bg-slate-50 dark:bg-slate-800 rounded-xl p-2.5 text-center border border-slate-200 dark:border-slate-700">
                    <p className="text-base font-bold text-slate-800 dark:text-slate-100">{val}</p>
                    <p className="text-[9px] text-slate-500 dark:text-slate-400 mt-0.5 leading-tight">{label}</p>
                  </div>
                ))}
              </div>
              {uploadStats.reconciled === false && (
                <div className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-xl p-2.5">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  <span>
                    Row accounting note: {uploadStats.total_accounted ?? '?'} of {uploadStats.rows_parsed ?? '?'} rows classified.
                  </span>
                </div>
              )}
              {uploadStats.column_mapping && Object.keys(uploadStats.column_mapping).length > 0 && (
                <p className="text-[10px] text-slate-500 break-words">
                  Mapping: {Object.entries(uploadStats.column_mapping).map(([k, v]) => `${k}→${v}`).join(', ')}
                </p>
              )}
              <DetailList title="New records" rows={uploadStats.new_records} />
              <DetailList title="Updated records" rows={uploadStats.updated_records} />
              <DetailList title="Duplicate rows" rows={uploadStats.duplicate_list} />
              <DetailList title="Invalid / rejected rows" rows={uploadStats.rejected_rows} emptyLabel="(no name)" />
            </>
          )}

          {!uploadStats && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-slate-500 dark:text-slate-400">Affected rows:</span>
              <span className={`font-bold text-base ${cfg.color}`}>{rowsAffected || affectedStudents.length}</span>
            </div>
          )}

          {affectedStudents.length > 0 && !uploadStats && (
            <div>
              <p className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
                {operation === 'DELETE' ? 'Moved to Recycle Bin' : 'Stored In Database'}
              </p>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {affectedStudents.map((s, i) => (
                  <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${cfg.badge}`}>
                      {(s.name || s.usn || '?').charAt(0).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">{s.name || '—'}</p>
                      <p className="text-[10px] text-slate-400 font-mono">{s.usn}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between text-[11px] text-slate-400 dark:text-slate-500 pt-1 border-t border-slate-100 dark:border-slate-800">
            <span className="flex items-center gap-1">
              <User className="w-3 h-3" /> {performedBy || 'System'}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" /> {ts}
            </span>
          </div>

          <div className="flex items-center gap-2 text-[11px] text-slate-400 dark:text-slate-500">
            <Database className="w-3 h-3 flex-shrink-0" />
            <span>Storage: <span className="font-mono text-slate-600 dark:text-slate-300">{cfg.storage}</span></span>
          </div>
        </div>

        <div className="px-5 pb-4 flex items-center justify-between gap-3">
          {restoreTokens.length > 0 && !undone && (
            <button
              onClick={handleUndo}
              disabled={undoing}
              className="flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold rounded-xl transition-colors disabled:opacity-50 shadow-sm"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${undoing ? 'animate-spin' : ''}`} />
              {undoing ? 'Restoring...' : 'UNDO — Restore'}
            </button>
          )}
          {undone && (
            <span className="flex items-center gap-1.5 text-xs text-green-600 font-semibold">
              <CheckCircle className="w-3.5 h-3.5" /> Restored!
            </span>
          )}
          <button
            onClick={onClose}
            className="ml-auto px-4 py-2 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

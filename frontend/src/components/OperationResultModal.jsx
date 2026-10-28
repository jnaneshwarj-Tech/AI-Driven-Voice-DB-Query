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
import { useI18n } from '../context/LanguageContext';

// Visual type tokens only — `storage` values are real table names and are
// rendered untranslated; `titleKey` resolves through i18n.
const OP_CONFIG = {
  DELETE: {
    icon:    <Trash2 className="w-5 h-5" />,
    color:   'text-err',
    bg:      'bg-err-soft',
    border:  'border-err/40',
    badge:   'bg-err/15 text-err',
    titleKey: 'results.deleted',
    storage: 'soft_delete_records',
  },
  INSERT: {
    icon:    <CheckCircle className="w-5 h-5" />,
    color:   'text-ok',
    bg:      'bg-ok-soft',
    border:  'border-ok/40',
    badge:   'bg-ok/15 text-ok',
    titleKey: 'results.added',
    storage: 'students table',
  },
  UPDATE: {
    icon:    <Edit3 className="w-5 h-5" />,
    color:   'text-info',
    bg:      'bg-info-soft',
    border:  'border-info/40',
    badge:   'bg-info/15 text-info',
    titleKey: 'results.updated',
    storage: 'students table + student_history',
  },
  UPLOAD: {
    icon:    <Upload className="w-5 h-5" />,
    color:   'text-brand-fg',
    bg:      'bg-brand/10',
    border:  'border-brand/30',
    badge:   'bg-brand/15 text-brand-fg',
    titleKey: 'results.uploadDone',
    storage: 'students table + marks table',
  },
};

function DetailList({ title, rows, emptyLabel }) {
  const [open, setOpen] = useState(false);
  const { t } = useI18n();
  if (!rows || rows.length === 0) return null;
  return (
    <div className="border border-line rounded-md overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-ink-soft bg-sunken"
      >
        <span>{title} ({rows.length}{rows.length >= 50 ? '+' : ''})</span>
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
      </button>
      {open && (
        <div className="max-h-40 overflow-y-auto divide-y divide-line">
          {rows.map((r, i) => (
            <div key={i} className="px-3 py-2 text-[11px] text-ink-soft">
              <div className="flex justify-between gap-2">
                <span className="font-mono text-ink-faint">{t('results.row', { n: r.row_number ?? r.row_index ?? '—' })}</span>
                {/* USN and name are data — never translated */}
                <span className="font-mono">{r.usn || '—'}</span>
              </div>
              <p className="font-medium truncate">{r.name || emptyLabel || '—'}</p>
              {r.reason && <p className="text-warn mt-0.5">{r.reason}</p>}
              {r.problematic_fields?.length > 0 && (
                <p className="text-ink-faint mt-0.5">{t('results.fields', { fields: r.problematic_fields.join(', ') })}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function OperationResultModal({ result, onClose, onUndoDone }) {
  const { t } = useI18n();
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
    [t('results.rowsParsed'), uploadStats.rows_parsed ?? 0],
    [t('results.new'), uploadStats.students_added ?? 0],
    [t('results.updatedShort'), uploadStats.students_updated ?? 0],
    [t('results.unchanged'), uploadStats.students_unchanged ?? 0],
    [t('results.duplicates'), uploadStats.duplicate_rows ?? 0],
    [t('results.invalid'), uploadStats.invalid_rows ?? 0],
    [t('results.studentsSaved'), uploadStats.students_saved ?? 0],
    [t('results.marksSaved'), uploadStats.marks_saved ?? 0],
  ] : [];

  return (
    <div className="backdrop">
      <div className={`bg-surface-elev rounded-lg shadow-lg border-2 ${cfg.border} w-full max-w-lg overflow-hidden anim-scale-in`}
        role="dialog" aria-modal="true" aria-labelledby="op-result-title">

        <div className={`px-5 py-4 ${cfg.bg} border-b ${cfg.border} flex items-center justify-between`}>
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-md bg-surface-elev/60 ${cfg.color}`}>
              {cfg.icon}
            </div>
            <div>
              <h3 id="op-result-title" className={`text-sm font-bold ${cfg.color}`}>{t(cfg.titleKey)}</h3>
              {undone
                ? <p className="text-xs text-ok font-semibold">{t('results.restored')}</p>
                : <p className="text-xs text-ink-mute">{message}</p>}
            </div>
          </div>
          <button onClick={onClose} aria-label={t('common.close')} className="p-1.5 rounded-md hover:bg-ink/10 transition-colors">
            <X className="w-4 h-4 text-ink-mute" />
          </button>
        </div>

        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          {uploadStats && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {uploadStatCells.map(([label, val]) => (
                  <div key={label} className="bg-sunken rounded-md p-2.5 text-center border border-line">
                    <p className="text-base font-bold text-ink">{val}</p>
                    <p className="text-[9px] text-ink-mute mt-0.5 leading-tight">{label}</p>
                  </div>
                ))}
              </div>
              {uploadStats.reconciled === false && (
                <div className="flex items-start gap-2 text-xs text-warn bg-warn-soft border border-warn/40 rounded-md p-2.5">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  <span>
                    {t('results.accounting', { accounted: uploadStats.total_accounted ?? '?', parsed: uploadStats.rows_parsed ?? '?' })}
                  </span>
                </div>
              )}
              {uploadStats.column_mapping && Object.keys(uploadStats.column_mapping).length > 0 && (
                <p className="text-[10px] text-ink-mute break-words">
                  {/* k→v pairs are API field names — rendered as-is */}
                  {t('results.mapping', { map: Object.entries(uploadStats.column_mapping).map(([k, v]) => `${k}→${v}`).join(', ') })}
                </p>
              )}
              <DetailList title={t('results.newRecords')} rows={uploadStats.new_records} />
              <DetailList title={t('results.updatedRecords')} rows={uploadStats.updated_records} />
              <DetailList title={t('results.duplicateRows')} rows={uploadStats.duplicate_list} />
              <DetailList title={t('results.invalidRows')} rows={uploadStats.rejected_rows} emptyLabel={t('results.noName')} />
            </>
          )}

          {!uploadStats && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-ink-mute">{t('results.affectedRows')}</span>
              <span className={`font-bold text-base ${cfg.color}`}>{rowsAffected || affectedStudents.length}</span>
            </div>
          )}

          {affectedStudents.length > 0 && !uploadStats && (
            <div>
              <p className="text-[10px] font-bold text-ink-faint uppercase tracking-wider mb-2">
                {operation === 'DELETE' ? t('results.recycleBin') : t('results.storedIn')}
              </p>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {affectedStudents.map((s, i) => (
                  <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-md bg-sunken border border-line">
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${cfg.badge}`}>
                      {(s.name || s.usn || '?').charAt(0).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      {/* Name and USN are student data — never translated */}
                      <p className="text-xs font-semibold text-ink truncate">{s.name || '—'}</p>
                      <p className="text-[10px] text-ink-faint font-mono">{s.usn}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between text-[11px] text-ink-mute pt-1 border-t border-line">
            <span className="flex items-center gap-1">
              <User className="w-3 h-3" /> {performedBy || t('results.system')}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" /> {ts}
            </span>
          </div>

          <div className="flex items-center gap-2 text-[11px] text-ink-mute">
            <Database className="w-3 h-3 flex-shrink-0" />
            {/* Storage value is a table name — rendered untranslated */}
            <span>{t('results.storage')} <span className="font-mono text-ink-soft">{cfg.storage}</span></span>
          </div>
        </div>

        <div className="px-5 pb-4 flex flex-wrap items-center justify-end gap-2">
          {restoreTokens.length > 0 && !undone && (
            <button
              onClick={handleUndo}
              disabled={undoing}
              className="btn btn-accent btn-sm"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${undoing ? 'animate-spin' : ''}`} />
              {undoing ? t('results.restoring') : t('results.undo')}
            </button>
          )}
          {undone && (
            <span className="flex items-center gap-1.5 text-xs text-ok font-semibold">
              <CheckCircle className="w-3.5 h-3.5" /> {t('results.restoredShort')}
            </span>
          )}
          <button
            onClick={onClose}
            className="btn btn-ghost btn-sm"
          >
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>
  );
}

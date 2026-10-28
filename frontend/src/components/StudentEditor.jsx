import React, { useState, useEffect, useMemo } from 'react';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import { useToast } from './Toast';
import { useI18n } from '../context/LanguageContext';
import {
  X, Save, Loader2, AlertCircle, Check, Search,
} from 'lucide-react';

// Shared modal shell
function Shell({ title, subtitle, onClose, children, footer }) {
  const { t } = useI18n();
  return (
    <div className="backdrop" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : undefined}
           className="modal-panel anim-scale-in max-w-3xl flex flex-col"
           onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 px-4 sm:px-5 py-4 border-b border-line">
          <div className="min-w-0">
            <h3 className="t-card text-ink t-truncate">{title}</h3>
            {subtitle && <p className="t-support text-ink-mute mt-0.5">{subtitle}</p>}
          </div>
          <button onClick={onClose} aria-label={t('common.close')}
                  className="btn btn-ghost btn-sm px-2 min-h-0 text-ink-mute hover:text-ink shrink-0">
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>
        <div className="px-4 sm:px-5 py-4 overflow-y-auto">{children}</div>
        <div className="px-4 sm:px-5 py-3 border-t border-line bg-sunken flex justify-end gap-3">{footer}</div>
      </div>
    </div>
  );
}

// ── Generic field editor — "fill any blank field" ─────────────────────────────
export function EditFieldModal({ usn, name, onClose, onSaved }) {
  const { t } = useI18n();
  const showToast = useToast().showToast;
  const [fields, setFields] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [values, setValues] = useState({});
  const [onlyBlanks, setOnlyBlanks] = useState(true);
  const [filter, setFilter] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.get(`/update/fields/${encodeURIComponent(usn)}`)
      .then((r) => {
        if (!alive) return;
        const list = r.data.editable_fields || [];
        setFields(list);
        const init = {};
        for (const f of list) init[f.column] = f.value == null ? '' : String(f.value);
        setValues(init);
      })
      .catch((e) => alive && setError(getUserMessage(e, t('editor.errLoadFields'))))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [usn]);

  const blankCount = useMemo(
    () => (fields || []).filter((f) => f.blank).length,
    [fields],
  );

  const visible = useMemo(() => {
    if (!fields) return [];
    const q = filter.trim().toLowerCase();
    return fields.filter((f) => {
      if (onlyBlanks && !f.blank) return false;
      if (q && !(f.label.toLowerCase().includes(q) || f.column.toLowerCase().includes(q))) return false;
      return true;
    });
  }, [fields, onlyBlanks, filter]);

  const dirtyCount = useMemo(() => {
    if (!fields) return 0;
    let n = 0;
    for (const f of fields) {
      const orig = f.value == null ? '' : String(f.value);
      const cur = values[f.column] ?? '';
      if (cur.trim() !== '' && cur !== orig) n += 1;
    }
    return n;
  }, [fields, values]);

  const save = async () => {
    // Only send boxes that are non-blank and changed; the backend also ignores blanks.
    const payloadFields = {};
    for (const f of fields || []) {
      const orig = f.value == null ? '' : String(f.value);
      const cur = (values[f.column] ?? '').trim();
      if (cur !== '' && cur !== orig) payloadFields[f.column] = cur;
    }
    if (!Object.keys(payloadFields).length) {
      showToast({ type: 'info', message: t('editor.nothingToSave') });
      return;
    }
    setSaving(true);
    setError('');
    try {
      const r = await api.post('/update/bulk', { usn, fields: payloadFields, confirm: true });
      showToast({
        type: 'success',
        title: t('editor.recordUpdated'),
        message: t('editor.fieldsSaved', { n: r.data.changed?.length || 0 }),
        undoToken: r.data.undo_token,
        undoName: name || usn,
      });
      onSaved?.(r.data);
      onClose();
    } catch (e) {
      setError(getUserMessage(e, t('editor.errSave')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Shell
      title={t('editor.editTitle', { name: name || usn })}
      subtitle={t('editor.editSub')}
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose} disabled={saving}
                  className="btn btn-ghost">
            {t('common.cancel')}
          </button>
          <button onClick={save} disabled={saving || dirtyCount === 0}
                  className="btn btn-accent">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> : <Save className="w-4 h-4" aria-hidden="true" />}
            {dirtyCount > 0 ? t('editor.saveN', { n: dirtyCount, s: dirtyCount > 1 ? 's' : '' }) : t('common.save')}
          </button>
        </>
      }
    >
      {loading && <p className="t-body text-ink-mute italic flex items-center gap-2" aria-live="polite"><Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />{t('editor.loadingFields')}</p>}
      {!loading && error && !fields && (
        <p role="alert" className="t-body text-err flex items-center gap-2"><AlertCircle className="w-4 h-4" aria-hidden="true" />{error}</p>
      )}
      {!loading && fields && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => setOnlyBlanks(v => !v)}
              className={`btn btn-sm ${onlyBlanks ? 'btn-primary' : 'btn-ghost'}`}
              aria-pressed={onlyBlanks}
            >
              {onlyBlanks ? t('editor.showingBlank', { n: blankCount }) : t('editor.showingAll')}
            </button>
            <div className="relative flex-1 min-w-[180px]">
              <Search className="w-3.5 h-3.5 text-ink-faint absolute left-2.5 top-1/2 -translate-y-1/2" aria-hidden="true" />
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                aria-label={t('common.search')}
                placeholder={t('editor.searchField')}
                className="input pl-8 py-1.5 text-sm min-h-0"
              />
            </div>
          </div>

          {error && <p role="alert" className="t-support text-err flex items-center gap-1.5"><AlertCircle className="w-3.5 h-3.5" aria-hidden="true" />{error}</p>}

          {visible.length === 0 ? (
            <p className="t-body text-ink-mute italic py-6 text-center">
              {onlyBlanks ? t('editor.noBlankFields') : t('editor.noMatches')}
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {visible.map((f) => {
                const cur = values[f.column] ?? '';
                const orig = f.value == null ? '' : String(f.value);
                const changed = cur.trim() !== '' && cur !== orig;
                return (
                  <label key={f.column} className="flex flex-col gap-1">
                    <span className="field-label flex items-center gap-1.5">
                      {f.label}
                      {f.blank && <span className="badge badge-warn">{t('editor.blank')}</span>}
                      {changed && <Check className="w-3 h-3 text-ok" aria-hidden="true" />}
                    </span>
                    <input
                      value={cur}
                      onChange={(e) => setValues((v) => ({ ...v, [f.column]: e.target.value }))}
                      placeholder={f.blank ? t('editor.enterValue') : ''}
                      className={`input py-1.5 text-sm min-h-0 ${changed ? 'border-ok bg-ok-soft/40' : ''}`}
                    />
                  </label>
                );
              })}
            </div>
          )}
        </div>
      )}
    </Shell>
  );
}

// ── Fee editor — Admin-only, verified status, undoable ────────────────────────
const FEE_STATUSES = ['Paid', 'Not Paid', 'Partially Paid'];
const FEE_ROWS_META = [
  { fee_type: 'VTU', label: 'VTU Fees', years: [1, 2, 3, 4] },
  { fee_type: 'PD', label: 'PD Fees', years: [1, 2, 3, 4] },
  { fee_type: 'IDP', label: 'IDP / Tuition Fees', years: [1, 2, 3, 4] },
  { fee_type: 'TUITION_PAID', label: 'Tuition Fees Paid', years: [0] },
  { fee_type: 'TUITION_REMAINING', label: 'Tuition Remaining', years: [0] },
];

export function EditFeesModal({ usn, name, onClose, onSaved }) {
  const { t } = useI18n();
  const showToast = useToast().showToast;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  // keyed by `${fee_type}::${year}` -> { status, amount_paid, remaining_amount, origStatus }
  const [rows, setRows] = useState({});

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.get(`/update/fees/${encodeURIComponent(usn)}`)
      .then((r) => {
        if (!alive) return;
        const map = {};
        for (const meta of FEE_ROWS_META) {
          for (const year of meta.years) map[`${meta.fee_type}::${year}`] = {
            fee_type: meta.fee_type, year, label: meta.label,
            status: '', amount_paid: '', remaining_amount: '',
            origStatus: '', origPaid: '', origRemaining: '',
          };
        }
        for (const f of (r.data.fees || [])) {
          const key = `${f.fee_type}::${f.year}`;
          if (!map[key]) map[key] = { fee_type: f.fee_type, year: f.year, label: f.fee_type, status: '', amount_paid: '', remaining_amount: '', origStatus: '', origPaid: '', origRemaining: '' };
          map[key].status = f.status || '';
          map[key].amount_paid = f.amount_paid == null ? '' : String(f.amount_paid);
          map[key].remaining_amount = f.remaining_amount == null ? '' : String(f.remaining_amount);
          map[key].origStatus = f.status || '';
          map[key].origPaid = map[key].amount_paid;
          map[key].origRemaining = map[key].remaining_amount;
        }
        setRows(map);
      })
      .catch((e) => alive && setError(getUserMessage(e, t('editor.errLoadFees'))))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [usn]);

  // A row counts as edited only when it differs from what the server sent.
  // Amounts arrive pre-filled, so "has a value" is not the same as "changed".
  const dirty = useMemo(() => Object.values(rows).filter((r) => (
    (r.status.trim() !== '' && r.status !== r.origStatus)
    || r.amount_paid.trim() !== r.origPaid.trim()
    || r.remaining_amount.trim() !== r.origRemaining.trim()
  )), [rows]);

  const setRow = (key, patch) => setRows((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));

  const save = async () => {
    if (!dirty.length) {
      showToast({ type: 'info', message: t('editor.nothingFee') });
      return;
    }
    setSaving(true); setError('');
    const fees = dirty.map((r) => ({
      fee_type: r.fee_type, year: r.year,
      status: r.status.trim() || undefined,
      amount_paid: r.amount_paid.trim() || undefined,
      remaining_amount: r.remaining_amount.trim() || undefined,
    }));
    try {
      const res = await api.post('/update/fees', { usn, fees, confirm: true });
      showToast({
        type: 'success', title: t('editor.feesUpdated'),
        message: t('editor.feeRowsSaved', { n: res.data.results?.length || 0 }),
        undoToken: res.data.undo_token, undoName: name || usn,
      });
      onSaved?.(res.data);
      onClose();
    } catch (e) {
      setError(getUserMessage(e, t('editor.errSaveFees')));
    } finally {
      setSaving(false);
    }
  };

  // group rows for display
  const grouped = useMemo(() => {
    const g = {};
    for (const r of Object.values(rows)) {
      const k = r.label || r.fee_type;
      (g[k] = g[k] || []).push(r);
    }
    return g;
  }, [rows]);

  return (
    <Shell
      title={t('editor.feesTitle', { who: name || usn })}
      subtitle={t('editor.feesSub')}
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose} disabled={saving} className="btn btn-ghost btn-sm">
            {t('common.cancel')}
          </button>
          <button onClick={save} disabled={saving || dirty.length === 0} className="btn btn-primary btn-sm">
            {saving ? <Loader2 className="no-transition w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {dirty.length > 0 ? t('editor.saveN', { n: dirty.length, s: dirty.length > 1 ? 's' : '' }) : t('common.save')}
          </button>
        </>
      }
    >
      {loading && (
        <p role="status" className="t-body text-ink-mute flex items-center gap-2">
          <Loader2 className="no-transition w-4 h-4 animate-spin" /> {t('editor.loadingFees')}
        </p>
      )}
      {!loading && error && !Object.keys(rows).length && (
        <p role="alert" className="t-body text-err flex items-center gap-2"><AlertCircle className="w-4 h-4" />{error}</p>
      )}
      {!loading && Object.keys(rows).length > 0 && (
        <div className="space-y-4">
          {error && <p role="alert" className="t-support text-err flex items-center gap-1.5"><AlertCircle className="w-3.5 h-3.5" />{error}</p>}
          {Object.entries(grouped).map(([label, list]) => (
            <div key={label}>
              <p className="text-[13px] font-semibold text-ink-soft uppercase tracking-wide mb-2">{label}</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {list
                  .sort((a, b) => a.year - b.year)
                  .map((r) => {
                    const key = `${r.fee_type}::${r.year}`;
                    return (
                      <div key={key} className="rounded-md border border-line bg-sunken/70 p-2.5">
                        <p className="text-[12px] text-ink-mute uppercase tracking-wide mb-1.5">
                          {r.year > 0 ? t('editor.year', { n: r.year }) : t('editor.total')}
                          {r.origStatus && <span className="ml-2 text-ink-soft normal-case">{t('editor.currentStatus')} {r.origStatus}</span>}
                        </p>
                        <div className="flex items-center gap-2">
                          <select
                            value={r.status}
                            onChange={(e) => setRow(key, { status: e.target.value })}
                            className="flex-1 min-w-0 px-2 py-1 text-[13px] rounded-md border border-line bg-surface text-ink hover:border-line-strong focus:outline-none focus:ring-2 focus:ring-ring/70">
                            <option value="">{t('editor.unchanged')}</option>
                            {FEE_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                          </select>
                        </div>
                        <div className="grid grid-cols-2 gap-2 mt-2">
                          <input
                            value={r.amount_paid}
                            onChange={(e) => setRow(key, { amount_paid: e.target.value })}
                            placeholder={t('editor.paidHint')}
                            aria-label={t('editor.paidHint')}
                            className="w-full min-w-0 px-2 py-1 text-[13px] rounded-md border border-line bg-surface text-ink placeholder:text-ink-faint tabular-nums hover:border-line-strong focus:outline-none focus:ring-2 focus:ring-ring/70" />
                          <input
                            value={r.remaining_amount}
                            onChange={(e) => setRow(key, { remaining_amount: e.target.value })}
                            placeholder={t('editor.remainingHint')}
                            aria-label={t('editor.remainingHint')}
                            className="w-full min-w-0 px-2 py-1 text-[13px] rounded-md border border-line bg-surface text-ink placeholder:text-ink-faint tabular-nums hover:border-line-strong focus:outline-none focus:ring-2 focus:ring-ring/70" />
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          ))}
        </div>
      )}
    </Shell>
  );
}

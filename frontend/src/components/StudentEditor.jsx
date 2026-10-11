import React, { useState, useEffect, useMemo } from 'react';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import { useToast } from './Toast';
import {
  X, Save, Loader2, AlertCircle, Check, Search,
} from 'lucide-react';

// Shared modal shell
function Shell({ title, subtitle, onClose, children, footer }) {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
         onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-3xl max-h-[88vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-slate-100">
          <div className="min-w-0">
            <h3 className="text-sm font-bold text-slate-800 truncate">{title}</h3>
            {subtitle && <p className="text-[11px] text-slate-500 mt-0.5">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-100 text-slate-400 flex-shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="px-5 py-4 overflow-y-auto">{children}</div>
        <div className="px-5 py-3 border-t border-slate-100 bg-slate-50 flex justify-end gap-3">{footer}</div>
      </div>
    </div>
  );
}

// ── Generic field editor — "fill any blank field" ─────────────────────────────
export function EditFieldModal({ usn, name, onClose, onSaved }) {
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
      .catch((e) => alive && setError(getUserMessage(e, 'Could not load this student’s editable fields.')))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
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
      showToast({ type: 'info', message: 'Nothing to save — no fields changed.' });
      return;
    }
    setSaving(true);
    setError('');
    try {
      const r = await api.post('/update/bulk', { usn, fields: payloadFields, confirm: true });
      showToast({
        type: 'success',
        title: 'Record updated',
        message: `${r.data.changed?.length || 0} field(s) saved.`,
        undoToken: r.data.undo_token,
        undoName: name || usn,
      });
      onSaved?.(r.data);
      onClose();
    } catch (e) {
      setError(getUserMessage(e, 'Could not save changes.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Shell
      title={`Edit details · ${name || usn}`}
      subtitle="Fill blank fields or correct values. Identity, timestamps and lifecycle status are managed elsewhere and can’t be edited here."
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose} disabled={saving}
                  className="px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200 rounded-lg">
            Cancel
          </button>
          <button onClick={save} disabled={saving || dirtyCount === 0}
                  className="px-4 py-2 text-sm font-bold text-white bg-blue-600 hover:bg-blue-700 rounded-lg flex items-center gap-2 disabled:opacity-50">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {dirtyCount > 0 ? `Save ${dirtyCount} change${dirtyCount > 1 ? 's' : ''}` : 'Save'}
          </button>
        </>
      }
    >
      {loading && <p className="text-sm text-slate-400 italic flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />Loading fields…</p>}
      {!loading && error && !fields && (
        <p className="text-sm text-red-600 flex items-center gap-2"><AlertCircle className="w-4 h-4" />{error}</p>
      )}
      {!loading && fields && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={() => setOnlyBlanks(v => !v)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors ${
                onlyBlanks ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}
            >
              {onlyBlanks ? `Showing ${blankCount} blank field(s)` : 'Showing all fields'}
            </button>
            <div className="relative flex-1 min-w-[180px]">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Search a field…"
                className="w-full pl-8 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
          </div>

          {error && <p className="text-xs text-red-600 flex items-center gap-1.5"><AlertCircle className="w-3.5 h-3.5" />{error}</p>}

          {visible.length === 0 ? (
            <p className="text-sm text-slate-400 italic py-6 text-center">
              {onlyBlanks ? 'No blank fields — every field already has a value. Toggle to edit any field.' : 'No fields match your search.'}
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {visible.map((f) => {
                const cur = values[f.column] ?? '';
                const orig = f.value == null ? '' : String(f.value);
                const changed = cur.trim() !== '' && cur !== orig;
                return (
                  <label key={f.column} className="flex flex-col gap-1">
                    <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1.5">
                      {f.label}
                      {f.blank && <span className="text-[9px] font-semibold text-amber-600 bg-amber-50 border border-amber-200 rounded px-1">blank</span>}
                      {changed && <Check className="w-3 h-3 text-green-600" />}
                    </span>
                    <input
                      value={cur}
                      onChange={(e) => setValues((v) => ({ ...v, [f.column]: e.target.value }))}
                      placeholder={f.blank ? 'Enter value…' : ''}
                      className={`px-2.5 py-1.5 text-xs rounded-lg border focus:outline-none focus:ring-2 focus:ring-blue-400 ${
                        changed ? 'border-green-300 bg-green-50/40' : 'border-slate-200 bg-white'}`}
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
            status: '', amount_paid: '', remaining_amount: '', origStatus: '',
          };
        }
        for (const f of (r.data.fees || [])) {
          const key = `${f.fee_type}::${f.year}`;
          if (!map[key]) map[key] = { fee_type: f.fee_type, year: f.year, label: f.fee_type, status: '', amount_paid: '', remaining_amount: '', origStatus: '' };
          map[key].status = f.status || '';
          map[key].amount_paid = f.amount_paid == null ? '' : String(f.amount_paid);
          map[key].remaining_amount = f.remaining_amount == null ? '' : String(f.remaining_amount);
          map[key].origStatus = f.status || '';
        }
        setRows(map);
      })
      .catch((e) => alive && setError(getUserMessage(e, 'Could not load fees.')))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [usn]);

  const dirty = useMemo(() => Object.values(rows).filter((r) => {
    const statusChanged = r.status.trim() !== '' && r.status !== r.origStatus;
    return statusChanged || r.amount_paid.trim() !== '' || r.remaining_amount.trim() !== '';
  }), [rows]);

  const setRow = (key, patch) => setRows((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));

  const save = async () => {
    if (!dirty.length) {
      showToast({ type: 'info', message: 'Nothing to save — no fee changes.' });
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
        type: 'success', title: 'Fees updated',
        message: `${res.data.results?.length || 0} fee row(s) saved.`,
        undoToken: res.data.undo_token, undoName: name || usn,
      });
      onSaved?.(res.data);
      onClose();
    } catch (e) {
      setError(getUserMessage(e, 'Could not save fee updates.'));
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
      title={`Fees · ${name || usn}`}
      subtitle="Admin-only. Status is verified against the canonical fee report before saving, and every change can be undone."
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose} disabled={saving}
                  className="px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200 rounded-lg">Cancel</button>
          <button onClick={save} disabled={saving || dirty.length === 0}
                  className="px-4 py-2 text-sm font-bold text-white bg-blue-600 hover:bg-blue-700 rounded-lg flex items-center gap-2 disabled:opacity-50">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {dirty.length > 0 ? `Save ${dirty.length} fee change${dirty.length > 1 ? 's' : ''}` : 'Save'}
          </button>
        </>
      }
    >
      {loading && <p className="text-sm text-slate-400 italic flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />Loading fees…</p>}
      {!loading && error && !Object.keys(rows).length && (
        <p className="text-sm text-red-600 flex items-center gap-2"><AlertCircle className="w-4 h-4" />{error}</p>
      )}
      {!loading && Object.keys(rows).length > 0 && (
        <div className="space-y-4">
          {error && <p className="text-xs text-red-600 flex items-center gap-1.5"><AlertCircle className="w-3.5 h-3.5" />{error}</p>}
          {Object.entries(grouped).map(([label, list]) => (
            <div key={label}>
              <p className="text-[10px] font-bold text-slate-500 uppercase mb-2">{label}</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {list
                  .sort((a, b) => a.year - b.year)
                  .map((r) => {
                    const key = `${r.fee_type}::${r.year}`;
                    return (
                      <div key={key} className="border border-slate-200 rounded-lg p-2.5 bg-slate-50/50">
                        <p className="text-[10px] text-slate-400 uppercase mb-1.5">
                          {r.year > 0 ? `Year ${r.year}` : 'Total'}
                          {r.origStatus && <span className="ml-2 text-slate-500">current: {r.origStatus}</span>}
                        </p>
                        <div className="flex items-center gap-2">
                          <select
                            value={r.status}
                            onChange={(e) => setRow(key, { status: e.target.value })}
                            className="flex-1 px-2 py-1 text-xs rounded border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-blue-400">
                            <option value="">— unchanged —</option>
                            {FEE_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                          </select>
                        </div>
                        <div className="grid grid-cols-2 gap-2 mt-2">
                          <input
                            value={r.amount_paid}
                            onChange={(e) => setRow(key, { amount_paid: e.target.value })}
                            placeholder="Paid ₹"
                            className="px-2 py-1 text-xs rounded border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-400" />
                          <input
                            value={r.remaining_amount}
                            onChange={(e) => setRow(key, { remaining_amount: e.target.value })}
                            placeholder="Remaining ₹"
                            className="px-2 py-1 text-xs rounded border border-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-400" />
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

/**
 * Toast.jsx — Animated toast notification system with UNDO support.
 *
 * Usage:
 *   const { showToast } = useToast();
 *   showToast({ type: 'success', message: 'Student deleted', undoToken: 'uuid', undoName: 'Manoj' });
 *
 * Types: 'success' | 'error' | 'warning' | 'info'
 */
import { useState, useCallback, useRef, createContext, useContext } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Info, X, RotateCcw } from 'lucide-react';
import api from '../services/api';

// ── Context ───────────────────────────────────────────────────────────────────
const ToastContext = createContext(null);

export function useToast() {
  return useContext(ToastContext);
}

// ── Individual Toast ──────────────────────────────────────────────────────────
function ToastItem({ toast, onDismiss, onUndoDone }) {
  const [undoing, setUndoing] = useState(false);
  const [undone, setUndone]   = useState(false);
  const timerRef = useRef(null);

  // Progress bar width (counts down from 100 to 0 over `duration` ms)
  const [progress, setProgress] = useState(100);
  const startRef = useRef(Date.now());
  const duration = toast.duration || (toast.undoToken ? 8000 : 4000);

  // Animate progress bar
  useState(() => {
    const tick = () => {
      const elapsed = Date.now() - startRef.current;
      const pct = Math.max(0, 100 - (elapsed / duration) * 100);
      setProgress(pct);
      if (pct > 0) timerRef.current = requestAnimationFrame(tick);
    };
    timerRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(timerRef.current);
  });

  const handleUndo = async () => {
    if (!toast.undoToken || undoing || undone) return;
    setUndoing(true);
    try {
      await api.post(`/undo/restore/${toast.undoToken}`);
      setUndone(true);
      onUndoDone?.(toast.undoToken);
      setTimeout(() => onDismiss(toast.id), 1200);
    } catch (err) {
      setUndoing(false);
      // Show error inline
    }
  };

  const STYLES = {
    success: {
      bar:  'bg-green-500',
      icon: <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0" />,
      ring: 'border-green-200 bg-green-55/95 dark:border-green-800/80 dark:bg-green-950/95',
      text: 'text-green-900 dark:text-green-200',
    },
    error: {
      bar:  'bg-red-500',
      icon: <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" />,
      ring: 'border-red-200 bg-red-55/95 dark:border-red-800/80 dark:bg-red-950/95',
      text: 'text-red-900 dark:text-red-200',
    },
    warning: {
      bar:  'bg-amber-500',
      icon: <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />,
      ring: 'border-amber-200 bg-amber-55/95 dark:border-amber-800/80 dark:bg-amber-950/95',
      text: 'text-amber-900 dark:text-amber-200',
    },
    info: {
      bar:  'bg-blue-500',
      icon: <Info className="w-4 h-4 text-blue-500 flex-shrink-0" />,
      ring: 'border-blue-200 bg-blue-55/95 dark:border-blue-800/80 dark:bg-blue-950/95',
      text: 'text-blue-900 dark:text-blue-200',
    },
  };

  const s = STYLES[toast.type] || STYLES.info;

  return (
    <div
      className={`relative flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg backdrop-blur-sm
        min-w-[280px] max-w-[380px] overflow-hidden
        ${s.ring} ${undone ? 'opacity-60' : 'opacity-100'}
        animate-in slide-in-from-right-4 fade-in duration-300`}
    >
      {/* Progress bar */}
      <div className="absolute bottom-0 left-0 h-0.5 bg-slate-200 w-full">
        <div
          className={`h-full transition-none ${s.bar}`}
          style={{ width: `${progress}%` }}
        />
      </div>

      {s.icon}

      <div className="flex-1 min-w-0">
        {toast.title && (
          <p className={`text-xs font-bold ${s.text} mb-0.5`}>{toast.title}</p>
        )}
        <p className={`text-xs ${s.text} leading-snug`}>
          {undone ? '✓ Restored successfully!' : toast.message}
        </p>

        {/* UNDO button */}
        {toast.undoToken && !undone && (
          <button
            onClick={handleUndo}
            disabled={undoing}
            className="mt-1.5 flex items-center gap-1 text-[11px] font-bold text-blue-700 hover:text-blue-900 transition-colors disabled:opacity-50"
          >
            <RotateCcw className={`w-3 h-3 ${undoing ? 'animate-spin' : ''}`} />
            {undoing ? 'Restoring...' : `UNDO — restore ${toast.undoName || 'student'}`}
          </button>
        )}
      </div>

      <button
        onClick={() => onDismiss(toast.id)}
        className="p-0.5 rounded hover:bg-black/10 transition-colors flex-shrink-0"
      >
        <X className="w-3.5 h-3.5 text-slate-400" />
      </button>
    </div>
  );
}

// ── Provider ──────────────────────────────────────────────────────────────────
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const counterRef = useRef(0);

  const showToast = useCallback((opts) => {
    const id = ++counterRef.current;
    const duration = opts.duration || (opts.undoToken ? 8000 : 4000);
    const toast = { id, type: 'info', ...opts, duration };
    setToasts(prev => [...prev, toast]);
    // Auto-dismiss
    setTimeout(() => dismissToast(id), duration);
    return id;
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const handleUndoDone = useCallback((token) => {
    // Optionally notify parent — handled via onUndoDone prop
  }, []);

  return (
    <ToastContext.Provider value={{ showToast, dismissToast }}>
      {children}
      {/* Toast container — bottom-right */}
      <div className="fixed bottom-5 right-5 z-[9999] flex flex-col gap-2 items-end pointer-events-none">
        {toasts.map(t => (
          <div key={t.id} className="pointer-events-auto">
            <ToastItem
              toast={t}
              onDismiss={dismissToast}
              onUndoDone={handleUndoDone}
            />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

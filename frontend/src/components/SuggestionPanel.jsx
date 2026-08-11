/**
 * SuggestionPanel.jsx — Advanced AI Search Suggestion UI
 *
 * Handles 4 response types from the backend:
 *   1. "no_match"       → clean "No records" message
 *   2. "suggestion"     → "Did you mean X?" YES/NO  (confidence 75–90%)
 *   3. "possible_matches" → ranked list with SELECT buttons (confidence 50–74%)
 *   4. "multiple_match" → ambiguity table — user MUST pick by USN
 *
 * Auto-corrected (≥90%) is handled silently upstream in Dashboard.
 */
import { useState } from 'react';
import {
  Search, CheckCircle, XCircle, AlertCircle,
  Users, ChevronRight, AlertTriangle
} from 'lucide-react';

// ── Score badge ───────────────────────────────────────────────────────────────
function ConfBadge({ score }) {
  const pct = Math.round((score ?? 0) * 100);
  const color =
    pct >= 90 ? '#16a34a' :
    pct >= 75 ? '#2563eb' :
    pct >= 60 ? '#d97706' : '#9ca3af';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      fontSize: 11, fontWeight: 700, color,
      background: color + '18', borderRadius: 6,
      padding: '1px 7px', border: `1px solid ${color}40`
    }}>
      {pct}% match
    </span>
  );
}

// ── No match ─────────────────────────────────────────────────────────────────
function NoMatch() {
  return (
    <div style={{
      display: 'flex', gap: 10, padding: '14px 16px',
      background: '#f8fafc', border: '1px solid #e2e8f0',
      borderRadius: 12, alignItems: 'flex-start'
    }}>
      <AlertCircle size={18} color="#94a3b8" style={{ flexShrink: 0, marginTop: 1 }} />
      <p style={{ margin: 0, fontSize: 13, color: '#64748b', fontWeight: 500 }}>
        No matching records available.
      </p>
    </div>
  );
}

// ── Avatar initial ────────────────────────────────────────────────────────────
function Avatar({ name }) {
  const initials = (name || '?')
    .split(' ').slice(0, 2).map(w => w[0]?.toUpperCase() || '').join('');
  return (
    <div style={{
      width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
      background: 'linear-gradient(135deg, #1d4ed8, #4f46e5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      color: '#fff', fontWeight: 700, fontSize: 12
    }}>
      {initials}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function SuggestionPanel({ suggestion, onYes, onNo }) {
  const [answered, setAnswered] = useState(null); // null | 'yes' | 'no'

  if (!suggestion) return null;

  const { type, message, suggestions = [], auto_corrected, search_term, confidence } = suggestion;
  const top = suggestions[0];

  // ── 1. No match ───────────────────────────────────────────────────────────
  if (type === 'no_match' || !suggestions.length) {
    return <NoMatch />;
  }

  // ── After NO clicked ──────────────────────────────────────────────────────
  if (answered === 'no') {
    return <NoMatch />;
  }

  // ── After YES clicked (Did you mean?) ────────────────────────────────────
  if (answered === 'yes') {
    return (
      <div style={{
        display: 'flex', gap: 10, padding: '12px 16px',
        background: '#f0fdf4', border: '1px solid #bbf7d0',
        borderRadius: 12, alignItems: 'center'
      }}>
        <CheckCircle size={16} color="#16a34a" style={{ flexShrink: 0 }} />
        <p style={{ margin: 0, fontSize: 13, color: '#15803d', fontWeight: 500 }}>
          Loading data for <strong>{top?.name}</strong>…
        </p>
      </div>
    );
  }

  // ── Auto-corrected notice (handled upstream, but defensive fallback) ───────
  if (auto_corrected) {
    return (
      <div style={{
        display: 'flex', gap: 10, padding: '10px 14px',
        background: '#eff6ff', border: '1px solid #bfdbfe',
        borderRadius: 12, alignItems: 'center'
      }}>
        <Search size={14} color="#3b82f6" style={{ flexShrink: 0 }} />
        <p style={{ margin: 0, fontSize: 13, color: '#1e40af', fontWeight: 500 }}>{message}</p>
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ── 2. "Did you mean?" — single top match (score 75–90%) ─────────────────
  // ─────────────────────────────────────────────────────────────────────────
  if (type === 'suggestion') {
    const lines = message.split('\n');
    return (
      <div style={{
        borderRadius: 14, border: '2px solid #fbbf24',
        background: '#fffbeb', overflow: 'hidden', boxShadow: '0 1px 4px #0001'
      }}>
        {/* Header */}
        <div style={{
          padding: '10px 16px', background: '#fef3c7',
          display: 'flex', alignItems: 'center', gap: 8
        }}>
          <Search size={14} color="#d97706" />
          <div>
            {lines.map((ln, i) => (
              <p key={i} style={{
                margin: 0, fontSize: i === 0 ? 13 : 13,
                fontWeight: i === 0 ? 600 : 700,
                color: i === 0 ? '#92400e' : '#78350f'
              }}>
                {ln}
              </p>
            ))}
          </div>
        </div>

        {/* Top match card */}
        <div style={{
          padding: '12px 16px', display: 'flex',
          alignItems: 'center', justifyContent: 'space-between', gap: 12
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Avatar name={top.name} />
            <div>
              <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: '#1e293b' }}>
                {top.name}
              </p>
              <p style={{ margin: '2px 0 0', fontSize: 11, color: '#64748b', fontFamily: 'monospace' }}>
                {top.usn}
              </p>
              <div style={{ marginTop: 4 }}>
                <ConfBadge score={top.score} />
              </div>
            </div>
          </div>

          {/* YES / NO buttons */}
          <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
            <button
              id="suggestion-yes-btn"
              onClick={() => { setAnswered('yes'); onYes && onYes(top); }}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '8px 18px', background: '#16a34a', color: '#fff',
                border: 'none', borderRadius: 10, fontWeight: 700, fontSize: 13,
                cursor: 'pointer', boxShadow: '0 2px 6px #16a34a30',
                transition: 'transform .1s'
              }}
              onMouseOver={e => e.currentTarget.style.transform = 'scale(1.04)'}
              onMouseOut={e => e.currentTarget.style.transform = 'scale(1)'}
            >
              <CheckCircle size={15} /> YES
            </button>
            <button
              id="suggestion-no-btn"
              onClick={() => { setAnswered('no'); onNo && onNo(); }}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '8px 18px', background: '#f1f5f9', color: '#475569',
                border: '1px solid #e2e8f0', borderRadius: 10,
                fontWeight: 700, fontSize: 13, cursor: 'pointer',
                transition: 'transform .1s'
              }}
              onMouseOver={e => e.currentTarget.style.transform = 'scale(1.04)'}
              onMouseOut={e => e.currentTarget.style.transform = 'scale(1)'}
            >
              <XCircle size={15} /> NO
            </button>
          </div>
        </div>

        {/* Other candidates */}
        {suggestions.length > 1 && (
          <div style={{ padding: '0 16px 12px' }}>
            <p style={{
              margin: '0 0 6px', fontSize: 10, color: '#94a3b8',
              fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1
            }}>
              Other possible matches
            </p>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {suggestions.slice(1).map((s, i) => (
                <button
                  key={i}
                  onClick={() => { setAnswered('yes'); onYes && onYes(s); }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '5px 12px', background: '#fff',
                    border: '1px solid #e2e8f0', borderRadius: 8,
                    fontSize: 12, color: '#374151', fontWeight: 500,
                    cursor: 'pointer', transition: 'border-color .15s'
                  }}
                  onMouseOver={e => e.currentTarget.style.borderColor = '#3b82f6'}
                  onMouseOut={e => e.currentTarget.style.borderColor = '#e2e8f0'}
                >
                  {s.name}
                  <ConfBadge score={s.score} />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ── 3. "Possible matches" list (score 50–74%) — SELECT / CANCEL ───────────
  // ─────────────────────────────────────────────────────────────────────────
  if (type === 'possible_matches') {
    return (
      <div style={{
        borderRadius: 14, border: '2px solid #e0e7ff',
        background: '#f5f3ff', overflow: 'hidden'
      }}>
        <div style={{
          padding: '10px 16px', background: '#ede9fe',
          display: 'flex', alignItems: 'center', gap: 8
        }}>
          <Search size={14} color="#7c3aed" />
          <div>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: '#4c1d95' }}>
              No exact record found for &ldquo;{search_term}&rdquo;
            </p>
            <p style={{ margin: '2px 0 0', fontSize: 12, color: '#6d28d9' }}>
              Possible matches found. Please select:
            </p>
          </div>
        </div>

        <div style={{ padding: '8px 12px 12px' }}>
          {suggestions.map((s, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 12px', margin: '4px 0',
              background: '#fff', borderRadius: 10,
              border: '1px solid #ddd6fe', gap: 10
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{
                  width: 22, height: 22, borderRadius: '50%',
                  background: '#7c3aed', color: '#fff', fontSize: 11,
                  fontWeight: 700, display: 'flex', alignItems: 'center',
                  justifyContent: 'center', flexShrink: 0
                }}>{i + 1}</span>
                <div>
                  <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: '#1e293b' }}>
                    {s.name}
                  </p>
                  <p style={{ margin: '1px 0 0', fontSize: 11, color: '#94a3b8', fontFamily: 'monospace' }}>
                    {s.usn}
                  </p>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                <ConfBadge score={s.score} />
                <button
                  onClick={() => { onYes && onYes(s); }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 5,
                    padding: '6px 14px', background: '#7c3aed', color: '#fff',
                    border: 'none', borderRadius: 8, fontSize: 12,
                    fontWeight: 700, cursor: 'pointer'
                  }}
                >
                  <ChevronRight size={13} /> SELECT
                </button>
              </div>
            </div>
          ))}

          <button
            onClick={() => { onNo && onNo(); }}
            style={{
              marginTop: 8, width: '100%', padding: '8px',
              background: 'transparent', border: '1px solid #c4b5fd',
              borderRadius: 8, fontSize: 12, color: '#6d28d9',
              fontWeight: 600, cursor: 'pointer'
            }}
          >
            <XCircle size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
            CANCEL — None of these
          </button>
        </div>
      </div>
    );
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ── 4. Multiple students with SAME name — must pick by USN ───────────────
  // ─────────────────────────────────────────────────────────────────────────
  if (type === 'multiple_match') {
    return (
      <div style={{
        borderRadius: 14, border: '2px solid #fecdd3',
        background: '#fff1f2', overflow: 'hidden'
      }}>
        <div style={{
          padding: '10px 16px', background: '#ffe4e6',
          display: 'flex', alignItems: 'center', gap: 8
        }}>
          <Users size={16} color="#be123c" />
          <div>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 700, color: '#881337' }}>
              Multiple students found with similar name
            </p>
            <p style={{ margin: '2px 0 0', fontSize: 12, color: '#be123c' }}>
              USN is the unique identity. Please choose:
            </p>
          </div>
        </div>

        <div style={{ padding: '8px 12px 12px', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#881337', color: '#fff' }}>
                <th style={thS}>Select</th>
                <th style={thS}>USN</th>
                <th style={thS}>Name</th>
                <th style={thS}>Match</th>
              </tr>
            </thead>
            <tbody>
              {suggestions.map((s, i) => (
                <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#fff1f2' }}>
                  <td style={{ ...tdS, textAlign: 'center' }}>
                    <button
                      onClick={() => { onYes && onYes(s); }}
                      style={{
                        display: 'inline-flex', alignItems: 'center', gap: 5,
                        padding: '5px 14px', background: '#be123c', color: '#fff',
                        border: 'none', borderRadius: 7, fontSize: 12,
                        fontWeight: 700, cursor: 'pointer'
                      }}
                    >
                      <ChevronRight size={13} /> View
                    </button>
                  </td>
                  <td style={{ ...tdS, fontFamily: 'monospace', fontWeight: 600, color: '#374151' }}>
                    {s.usn}
                  </td>
                  <td style={{ ...tdS, fontWeight: 600, color: '#1e293b' }}>
                    {s.name}
                  </td>
                  <td style={{ ...tdS, textAlign: 'center' }}>
                    <ConfBadge score={s.score} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <button
            onClick={() => { onNo && onNo(); }}
            style={{
              marginTop: 10, width: '100%', padding: '8px',
              background: 'transparent', border: '1px solid #fecdd3',
              borderRadius: 8, fontSize: 12, color: '#be123c',
              fontWeight: 600, cursor: 'pointer'
            }}
          >
            <XCircle size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
            CANCEL
          </button>
        </div>
      </div>
    );
  }

  return <NoMatch />;
}

const thS = {
  padding: '8px 12px', textAlign: 'left',
  fontSize: 11, fontWeight: 700, letterSpacing: 0.5,
  border: '1px solid #fecdd3'
};
const tdS = {
  padding: '7px 12px', border: '1px solid #fecdd3', fontSize: 12
};

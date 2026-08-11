import React, { useState, useRef } from 'react';
import { runQuery, exportPDF } from '../api';
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, ArcElement,
  Title, Tooltip, Legend, PointElement, LineElement
} from 'chart.js';
import { Bar, Pie, Line } from 'react-chartjs-2';

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Title, Tooltip, Legend, PointElement, LineElement);

const SUGGESTIONS = [
  'Show all students',
  'Top 10 students by CGPA',
  'Show graduated students',
  'Students with CGPA below 5',
  'Average CGPA by branch',
  'Show semester wise SGPA',
  'Compare CGPA distribution',
  'Students in CSE branch',
];

export default function AIQuery({ role = 'staff' }) {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [listening, setListening] = useState(false);
  const [sortCol, setSortCol] = useState('');
  const [sortDir, setSortDir] = useState('asc');
  const [filterText, setFilterText] = useState('');
  const [page, setPage] = useState(1);
  const [confirmPending, setConfirmPending] = useState(null);
  const PAGE_SIZE = 20;
  const recognitionRef = useRef(null);

  const submit = async (q, confirmed = false) => {
    const text = q || query;
    if (!text.trim()) return;

    // Admin block on destructive keywords
    const destructiveKw = ['delete', 'insert', 'update', 'drop', 'truncate'];
    const isDestructive = destructiveKw.some(k => text.toLowerCase().includes(k));
    if (isDestructive && role === 'admin') {
      setError('❌ You do not have permission to perform this operation. Admins are view-only.');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);
    setConfirmPending(null);
    setPage(1);
    setFilterText('');
    try {
      const r = await runQuery(text, confirmed);
      if (r.data.requires_confirmation) {
        setConfirmPending(r.data);
        setLoading(false);
        return;
      }
      setResult(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  const startVoice = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { alert('Speech recognition not supported in this browser.'); return; }
    const rec = new SR();
    rec.lang = 'en-US';
    rec.interimResults = false;
    rec.onstart = () => setListening(true);
    rec.onend = () => setListening(false);
    rec.onresult = (e) => {
      const text = e.results[0][0].transcript;
      setQuery(text);
      submit(text, false);
    };
    rec.onerror = () => setListening(false);
    recognitionRef.current = rec;
    rec.start();
  };

  const stopVoice = () => {
    recognitionRef.current?.stop();
    setListening(false);
  };

  // Table processing
  const rawData = result?.data || [];
  const columns = rawData.length > 0 ? Object.keys(rawData[0]) : [];

  const filtered = filterText
    ? rawData.filter(row => columns.some(c => String(row[c] || '').toLowerCase().includes(filterText.toLowerCase())))
    : rawData;

  const sorted = sortCol
    ? [...filtered].sort((a, b) => {
        const av = a[sortCol], bv = b[sortCol];
        const an = parseFloat(av), bn = parseFloat(bv);
        if (!isNaN(an) && !isNaN(bn)) return sortDir === 'asc' ? an - bn : bn - an;
        return sortDir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
      })
    : filtered;

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const pageData = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const handleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('asc'); }
  };

  // Chart
  const cd = result?.chart_data;
  const chartColors = ['#1a73e8','#34a853','#fbbc04','#ea4335','#9c27b0','#00bcd4','#ff5722','#607d8b'];
  const chartDataset = cd ? {
    labels: cd.labels,
    datasets: [{
      label: cd.value_col,
      data: cd.values,
      backgroundColor: chartColors,
      borderColor: '#1a73e8',
      borderWidth: cd.type === 'line' ? 2 : 0,
      fill: false,
      tension: 0.3,
    }],
  } : null;

  const handlePDF = () => {
    if (!result) return;
    exportPDF(query, result.data, result.sql).catch(e => alert('PDF error: ' + e.message));
  };

  return (
    <div>
      <div className="card">
        <h2>🤖 AI Natural Language Query</h2>
        <div className="query-box">
          <input
            className="query-input"
            placeholder="Ask anything... e.g. 'Show top 10 students by CGPA'"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
          />
          <button className={`mic-btn ${listening ? 'listening' : ''}`}
            onClick={listening ? stopVoice : startVoice}
            title={listening ? 'Stop listening' : 'Voice input'}>
            {listening ? '🔴' : '🎤'}
          </button>
          <button className="btn btn-primary" onClick={() => submit()} disabled={loading}>
            {loading ? <span className="spinner" /> : '🔍 Ask'}
          </button>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {SUGGESTIONS.map(s => (
            <button key={s} className="btn btn-outline" style={{ fontSize: '0.8rem', padding: '5px 10px' }}
              onClick={() => { setQuery(s); submit(s, false); }}>
              {s}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {/* Confirmation dialog for destructive operations */}
      {confirmPending && (
        <div style={{
          background: '#fff8e1', border: '2px solid #ffb300', borderRadius: 12,
          padding: 20, marginBottom: 16
        }}>
          <p style={{ fontWeight: 700, color: '#e65100', marginBottom: 8, fontSize: '1rem' }}>
            ⚠️ Critical Operation Warning
          </p>
          <p style={{ color: '#555', marginBottom: 16, fontSize: '0.9rem' }}>
            {confirmPending.message}
          </p>
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="btn btn-danger" onClick={() => submit(confirmPending.query, true)}>
              ✅ YES — Proceed
            </button>
            <button className="btn btn-outline" onClick={() => setConfirmPending(null)}>
              ❌ CANCEL
            </button>
          </div>
        </div>
      )}

      {result && (
        <>
          {result.sql && <div className="sql-box">SQL: {result.sql}</div>}
          {result.from_cache && <div className="alert alert-info">⚡ Result from cache</div>}

          {chartDataset && (
            <div className="card">
              <h2>📈 Chart</h2>
              <div style={{ maxHeight: 350 }}>
                {cd.type === 'bar' && <Bar data={chartDataset} options={{ responsive: true, maintainAspectRatio: true }} />}
                {cd.type === 'line' && <Line data={chartDataset} options={{ responsive: true, maintainAspectRatio: true }} />}
                {cd.type === 'pie' && <Pie data={chartDataset} options={{ responsive: true, maintainAspectRatio: true }} />}
              </div>
            </div>
          )}

          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
              <h2>📋 Results ({filtered.length} rows)</h2>
              <div className="export-row">
                <input className="search-input" style={{ width: 200 }} placeholder="Filter results..."
                  value={filterText} onChange={e => { setFilterText(e.target.value); setPage(1); }} />
                <button className="btn btn-success" onClick={handlePDF}>📄 PDF</button>
              </div>
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {columns.map(col => (
                      <th key={col} onClick={() => handleSort(col)}>
                        {col.replace(/_/g, ' ').toUpperCase()}
                        {sortCol === col ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pageData.length === 0 ? (
                    <tr><td colSpan={columns.length} style={{ textAlign: 'center', padding: 30, color: '#999' }}>No results</td></tr>
                  ) : pageData.map((row, i) => (
                    <tr key={i}>
                      {columns.map(col => <td key={col}>{row[col] ?? '-'}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="pagination">
                <button onClick={() => setPage(1)} disabled={page === 1}>«</button>
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>‹</button>
                <span>Page {page} of {totalPages}</span>
                <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>›</button>
                <button onClick={() => setPage(totalPages)} disabled={page === totalPages}>»</button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

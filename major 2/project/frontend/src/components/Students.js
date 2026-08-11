import React, { useEffect, useState, useCallback } from 'react';
import { getStudents, exportCSV, exportExcel } from '../api';

export default function Students() {
  const [data, setData] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('usn');
  const [sortDir, setSortDir] = useState('asc');
  const [loading, setLoading] = useState(false);
  const [columns, setColumns] = useState([]);

  const load = useCallback(() => {
    setLoading(true);
    getStudents({ page, page_size: pageSize, search, sort_by: sortBy, sort_dir: sortDir })
      .then(r => {
        setData(r.data.data || []);
        setTotal(r.data.total || 0);
        if (r.data.data?.length > 0) {
          setColumns(Object.keys(r.data.data[0]).filter(c => c !== 'id'));
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [page, pageSize, search, sortBy, sortDir]);

  useEffect(() => { load(); }, [load]);

  const handleSort = (col) => {
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortBy(col); setSortDir('asc'); }
    setPage(1);
  };

  const totalPages = Math.ceil(total / pageSize);

  const renderCell = (col, val) => {
    if (col === 'status') {
      const cls = val === 'GRADUATED' ? 'graduated' : val === 'ACTIVE' ? 'active' : '';
      return <span className={`badge ${cls}`}>{val || '-'}</span>;
    }
    if (col === 'cgpa' && val) {
      const f = parseFloat(val);
      return <span style={{ color: f < 5 ? '#e53935' : f >= 8 ? '#2e7d32' : '#1a1a2e', fontWeight: 600 }}>{val}</span>;
    }
    return val || '-';
  };

  return (
    <div>
      <div className="controls">
        <input className="search-input" placeholder="Search by name, USN, branch, email..."
          value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} />
        <button className="btn btn-outline" onClick={exportCSV}>⬇ CSV</button>
        <button className="btn btn-outline" onClick={exportExcel}>⬇ Excel</button>
        <button className="btn btn-primary" onClick={load}>🔄 Refresh</button>
      </div>

      <div className="card" style={{ padding: 0 }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.9rem', color: '#666' }}>
            {loading ? 'Loading...' : `${total} students found`}
          </span>
        </div>

        {loading ? (
          <div className="loading-overlay"><div className="spinner" /><span>Loading...</span></div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {columns.map(col => (
                    <th key={col} onClick={() => handleSort(col)}>
                      {col.replace(/_/g, ' ').toUpperCase()}
                      {sortBy === col ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.length === 0 ? (
                  <tr><td colSpan={columns.length} style={{ textAlign: 'center', padding: 40, color: '#999' }}>
                    No students found. Upload a file to get started.
                  </td></tr>
                ) : data.map((row, i) => (
                  <tr key={row.usn || i}>
                    {columns.map(col => <td key={col}>{renderCell(col, row[col])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {totalPages > 1 && (
          <div className="pagination" style={{ padding: '12px 16px' }}>
            <button onClick={() => setPage(1)} disabled={page === 1}>«</button>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>‹</button>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const p = Math.max(1, Math.min(page - 2, totalPages - 4)) + i;
              return p <= totalPages ? (
                <button key={p} className={page === p ? 'active' : ''} onClick={() => setPage(p)}>{p}</button>
              ) : null;
            })}
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>›</button>
            <button onClick={() => setPage(totalPages)} disabled={page === totalPages}>»</button>
            <span>Page {page} of {totalPages}</span>
          </div>
        )}
      </div>
    </div>
  );
}

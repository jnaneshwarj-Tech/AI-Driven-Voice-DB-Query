import React, { useEffect, useState } from 'react';
import { getValidation } from '../api';

export default function Validation() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('issues');

  useEffect(() => {
    getValidation()
      .then(r => setData(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading-overlay"><div className="spinner" /><span>Loading...</span></div>;

  const issues = data?.issues || [];
  const duplicates = data?.duplicates || [];

  return (
    <div>
      <div className="stats-grid">
        <div className={`stat-card ${issues.length > 0 ? 'warn' : 'success'}`}>
          <div className="value">{issues.length}</div>
          <div className="label">Validation Issues</div>
        </div>
        <div className={`stat-card ${duplicates.length > 0 ? 'warn' : 'success'}`}>
          <div className="value">{duplicates.length}</div>
          <div className="label">Duplicate USNs</div>
        </div>
      </div>

      <div className="tabs">
        <button className={`tab ${tab === 'issues' ? 'active' : ''}`} onClick={() => setTab('issues')}>
          ⚠️ Validation Issues ({issues.length})
        </button>
        <button className={`tab ${tab === 'duplicates' ? 'active' : ''}`} onClick={() => setTab('duplicates')}>
          🔁 Duplicates ({duplicates.length})
        </button>
      </div>

      {tab === 'issues' && (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>USN</th><th>Field</th><th>Issue</th><th>Raw Value</th><th>Logged At</th>
                </tr>
              </thead>
              <tbody>
                {issues.length === 0 ? (
                  <tr><td colSpan={5} style={{ textAlign: 'center', padding: 30, color: '#2e7d32' }}>
                    ✅ No validation issues found
                  </td></tr>
                ) : issues.map((issue, i) => (
                  <tr key={i} className="issue-row">
                    <td>{issue.usn || '-'}</td>
                    <td>{issue.field_name}</td>
                    <td>{issue.issue}</td>
                    <td><code>{issue.raw_value}</code></td>
                    <td style={{ fontSize: '0.8rem', color: '#999' }}>{issue.logged_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'duplicates' && (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>USN</th><th>Count</th><th>Status</th></tr>
              </thead>
              <tbody>
                {duplicates.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', padding: 30, color: '#2e7d32' }}>
                    ✅ No duplicate USNs found
                  </td></tr>
                ) : duplicates.map((d, i) => (
                  <tr key={i} className="issue-row">
                    <td>{d.usn}</td>
                    <td>{d.cnt}</td>
                    <td><span className="badge low">Duplicate</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

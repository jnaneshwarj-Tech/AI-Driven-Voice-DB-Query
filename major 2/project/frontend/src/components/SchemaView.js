import React, { useEffect, useState } from 'react';
import { getSchema, clearCache } from '../api';

export default function SchemaView() {
  const [schema, setSchema] = useState({});
  const [loading, setLoading] = useState(true);
  const [cacheMsg, setCacheMsg] = useState('');

  useEffect(() => {
    getSchema()
      .then(r => setSchema(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleClearCache = () => {
    clearCache()
      .then(() => { setCacheMsg('✅ Cache cleared successfully'); setTimeout(() => setCacheMsg(''), 3000); })
      .catch(e => setCacheMsg('❌ ' + e.message));
  };

  if (loading) return <div className="loading-overlay"><div className="spinner" /><span>Loading schema...</span></div>;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ fontSize: '1.1rem' }}>🗄️ Database Schema</h2>
        <button className="btn btn-danger" onClick={handleClearCache}>🗑️ Clear Query Cache</button>
      </div>

      {cacheMsg && <div className={`alert ${cacheMsg.startsWith('✅') ? 'alert-success' : 'alert-error'}`}>{cacheMsg}</div>}

      {Object.keys(schema).length === 0 ? (
        <div className="alert alert-info">No schema data yet. Upload a file to create tables.</div>
      ) : Object.entries(schema).map(([table, cols]) => (
        <div className="card" key={table}>
          <h2>📋 {table}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>#</th><th>Column Name</th><th>Data Type</th></tr>
              </thead>
              <tbody>
                {cols.map((col, i) => (
                  <tr key={col.column}>
                    <td style={{ color: '#999', width: 40 }}>{i + 1}</td>
                    <td><code style={{ color: '#1a73e8' }}>{col.column}</code></td>
                    <td><span style={{ background: '#f0f4ff', padding: '2px 8px', borderRadius: 4, fontSize: '0.8rem' }}>{col.type}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

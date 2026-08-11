import React, { useState, useRef } from 'react';
import { uploadFile } from '../api';

export default function Upload({ role = 'staff' }) {
  const [dragging, setDragging] = useState(false);
  const [files, setFiles] = useState([]);
  const [results, setResults] = useState([]);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef();

  const handleFiles = (fileList) => {
    const arr = Array.from(fileList);
    const allowed = ['.csv', '.xlsx', '.xls', '.json', '.pdf'];
    const valid = arr.filter(f => allowed.some(ext => f.name.toLowerCase().endsWith(ext)));
    if (valid.length !== arr.length) alert('Some files were skipped (unsupported format).');
    setFiles(valid);
    setResults([]);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const handleUpload = async () => {
    if (!files.length) return;
    setUploading(true);
    setResults([]);
    const res = [];
    for (const file of files) {
      try {
        const r = await uploadFile(file);
        res.push({ file: file.name, status: 'success', ...r.data });
      } catch (e) {
        res.push({ file: file.name, status: 'error', error: e.response?.data?.detail || e.message });
      }
    }
    setResults(res);
    setUploading(false);
    setFiles([]);
  };

  return (
    <div>
      <div className="card">
        <h2>📁 Upload Student Data</h2>
        <p style={{ color: '#666', marginBottom: 16, fontSize: '0.9rem' }}>
          Supported formats: CSV, Excel (.xlsx/.xls), JSON, PDF. Data is automatically merged by USN.
        </p>

        <div
          className={`upload-zone ${dragging ? 'drag' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current.click()}
        >
          <div className="upload-icon">📂</div>
          <p><strong>Drag & drop files here</strong> or click to browse</p>
          <p>CSV · Excel · JSON · PDF</p>
          <input ref={inputRef} type="file" multiple accept=".csv,.xlsx,.xls,.json,.pdf"
            style={{ display: 'none' }} onChange={e => handleFiles(e.target.files)} />
        </div>

        {files.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <p style={{ marginBottom: 8, fontWeight: 600 }}>Selected files:</p>
            {files.map(f => (
              <div key={f.name} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid #eee' }}>
                <span>📄</span>
                <span style={{ flex: 1 }}>{f.name}</span>
                <span style={{ color: '#666', fontSize: '0.8rem' }}>{(f.size / 1024).toFixed(1)} KB</span>
              </div>
            ))}
            <div style={{ marginTop: 16, display: 'flex', gap: 10 }}>
              <button className="btn btn-primary" onClick={handleUpload} disabled={uploading}>
                {uploading ? <><span className="spinner" /> Uploading...</> : '⬆ Upload & Process'}
              </button>
              <button className="btn btn-outline" onClick={() => setFiles([])}>Clear</button>
            </div>
          </div>
        )}
      </div>

      {results.length > 0 && (
        <div className="card">
          <h2>Upload Results</h2>
          {results.map((r, i) => (
            <div key={i} className={`alert ${r.status === 'success' ? 'alert-success' : 'alert-error'}`} style={{ marginBottom: 8 }}>
              <strong>{r.file}</strong>
              {r.status === 'success' ? (
                <span> — ✅ {r.total_rows} rows processed | {r.inserted} inserted | {r.updated} updated
                  {r.validation_issues > 0 && <span style={{ color: '#e65100' }}> | ⚠️ {r.validation_issues} validation issues</span>}
                  {r.errors?.length > 0 && <span style={{ color: '#c62828' }}> | ❌ {r.errors.length} errors</span>}
                </span>
              ) : (
                <span> — ❌ {r.error}</span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h2>📋 Upload Guidelines</h2>
        <ul style={{ paddingLeft: 20, lineHeight: 2, color: '#555', fontSize: '0.9rem' }}>
          <li>Files must contain a <strong>USN</strong> column as the primary key</li>
          <li>Column names are auto-normalized (lowercase, underscores)</li>
          <li>New columns are automatically added to the database</li>
          <li>Existing records are updated; new records are inserted</li>
          <li>NULL values never overwrite existing data</li>
          <li>Students with semester ≥ 8 are auto-marked as GRADUATED</li>
          <li>CGPA/SGPA must be between 0 and 10</li>
        </ul>
      </div>
    </div>
  );
}

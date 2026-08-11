/**
 * ValidationDashboard — Data quality checks: missing values, invalid SGPA, duplicates.
 */
import { useState, useEffect } from 'react';
import api from '../services/api';
import { AlertTriangle, CheckCircle, RefreshCw, Users } from 'lucide-react';

const ISSUE_COLORS = {
  missing_name:       'bg-yellow-50 border-yellow-200 text-yellow-800',
  invalid_sgpa:       'bg-red-50 border-red-200 text-red-800',
  invalid_semester:   'bg-orange-50 border-orange-200 text-orange-800',
  too_many_semesters: 'bg-purple-50 border-purple-200 text-purple-800',
};

export default function ValidationDashboard() {
  const [data, setData]         = useState(null);
  const [dupes, setDupes]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState('');

  const load = async () => {
    setLoading(true); setError('');
    try {
      const [v, d] = await Promise.all([
        api.get('/files/validation'),
        api.get('/files/duplicates'),
      ]);
      setData(v.data);
      setDupes(d.data);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to load validation data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) return (
    <div className="flex items-center justify-center py-16 text-slate-400 gap-2">
      <div className="w-5 h-5 border-2 border-slate-300 border-t-blue-500 rounded-full animate-spin" />
      Running validation checks...
    </div>
  );

  if (error) return (
    <div className="p-4 bg-red-50 text-red-600 rounded-xl border border-red-100 text-sm">{error}</div>
  );

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-bold text-slate-800">Data Validation Dashboard</h2>
        <button onClick={load} className="p-2 hover:bg-slate-100 rounded-lg transition-colors">
          <RefreshCw className="w-4 h-4 text-slate-500" />
        </button>
      </div>

      {/* Summary */}
      {data && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-white rounded-xl border border-slate-200 p-4 text-center">
            <p className="text-2xl font-bold text-slate-800">{data.total_students}</p>
            <p className="text-xs text-slate-500 mt-1">Total Students</p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-4 text-center">
            <p className="text-2xl font-bold text-slate-800">{data.total_marks}</p>
            <p className="text-xs text-slate-500 mt-1">Mark Records</p>
          </div>
          <div className={`rounded-xl border p-4 text-center ${data.issue_count === 0 ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
            <p className={`text-2xl font-bold ${data.issue_count === 0 ? 'text-green-700' : 'text-red-700'}`}>{data.issue_count}</p>
            <p className={`text-xs mt-1 ${data.issue_count === 0 ? 'text-green-600' : 'text-red-600'}`}>Issues Found</p>
          </div>
        </div>
      )}

      {/* All clear */}
      {data?.issue_count === 0 && (
        <div className="flex items-center gap-3 p-4 bg-green-50 border border-green-200 rounded-xl text-green-800">
          <CheckCircle className="w-5 h-5 text-green-500" />
          <span className="text-sm font-medium">All data looks clean. No issues detected.</span>
        </div>
      )}

      {/* Issues list */}
      {data?.issues?.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-4 py-3 bg-red-50 border-b border-red-100 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-500" />
            <span className="text-sm font-semibold text-red-800">{data.issues.length} Issue(s) Found</span>
          </div>
          <div className="divide-y divide-slate-100 max-h-64 overflow-y-auto">
            {data.issues.map((issue, i) => (
              <div key={i} className={`flex items-start gap-3 p-3 m-2 rounded-lg border text-xs ${ISSUE_COLORS[issue.type] || 'bg-slate-50 border-slate-200 text-slate-700'}`}>
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold uppercase tracking-wide">{issue.type.replace(/_/g, ' ')}</span>
                  {issue.usn && <span className="ml-2 font-mono">{issue.usn}</span>}
                  {issue.semester && <span className="ml-1">Sem {issue.semester}</span>}
                  <p className="mt-0.5 opacity-80">{issue.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Duplicates */}
      {dupes.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-4 py-3 bg-purple-50 border-b border-purple-100 flex items-center gap-2">
            <Users className="w-4 h-4 text-purple-500" />
            <span className="text-sm font-semibold text-purple-800">Potential Duplicate Students ({dupes.length})</span>
          </div>
          <div className="divide-y divide-slate-100">
            {dupes.map((d, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-3 text-sm">
                <span className="font-medium text-slate-800">{d.name}</span>
                <div className="text-right">
                  <span className="text-xs text-purple-600 font-semibold">{d.cnt} records</span>
                  <p className="text-xs text-slate-400 font-mono">{d.usns}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

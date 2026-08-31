/**
 * AnalyticsDashboard — Admin analytics: totals, top students, semester stats.
 */
import { useState, useEffect } from 'react';
import api from '../services/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { Users, BookOpen, Upload, Search, RefreshCw } from 'lucide-react';

function StatCard({ icon, label, value, color }) {
  return (
    <div className={`bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-4`}>
      <div className={`p-3 rounded-xl ${color}`}>{icon}</div>
      <div>
        <p className="text-xs text-slate-500 font-medium">{label}</p>
        <p className="text-2xl font-bold text-slate-800">{value ?? '—'}</p>
      </div>
    </div>
  );
}

export default function AnalyticsDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true); setError('');
    try {
      const res = await api.get('/query/analytics');
      setData(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to load analytics.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) return (
    <div className="flex items-center justify-center py-16 text-slate-400 gap-2">
      <div className="w-5 h-5 border-2 border-slate-300 border-t-blue-500 rounded-full animate-spin" />
      Loading analytics...
    </div>
  );

  if (error) return (
    <div className="p-4 bg-red-50 text-red-600 rounded-xl border border-red-100 text-sm">{error}</div>
  );

  if (!data) return null;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-bold text-slate-800">Analytics Dashboard</h2>
        <button onClick={load} className="p-2 hover:bg-slate-100 rounded-lg transition-colors">
          <RefreshCw className="w-4 h-4 text-slate-500" />
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard icon={<Users className="w-5 h-5 text-blue-600" />} label="Total Students" value={data.total_students} color="bg-blue-50" />
        <StatCard icon={<BookOpen className="w-5 h-5 text-indigo-600" />} label="Mark Records" value={data.total_marks} color="bg-indigo-50" />
        <StatCard icon={<Upload className="w-5 h-5 text-green-600" />} label="Files Uploaded" value={data.total_files} color="bg-green-50" />
        <StatCard icon={<Search className="w-5 h-5 text-purple-600" />} label="Queries Run" value={data.total_queries} color="bg-purple-50" />
      </div>

      {/* Semester avg SGPA chart */}
      {data.semester_stats?.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Average SGPA by Semester</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.semester_stats} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="semester" tick={{ fontSize: 11 }} label={{ value: 'Semester', position: 'insideBottom', offset: -2, fontSize: 11 }} />
              <YAxis domain={[0, 10]} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => [parseFloat(v).toFixed(2), 'Avg SGPA']} />
              <Bar dataKey="avg_sgpa" fill="#3b82f6" radius={[4,4,0,0]} name="Avg SGPA" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Top students */}
      {data.top_students?.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-4 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 flex items-center justify-between">
            <span className="text-sm font-semibold text-white">Top 10 Students by CGPA</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase">#</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase">USN</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase">Name</th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 uppercase">CGPA (Avg SGPA)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.top_students.map((s, i) => (
                  <tr key={i} className="hover:bg-blue-50/30">
                    <td className="px-4 py-2.5 text-slate-500 font-medium">{i + 1}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-slate-500">{s.usn}</td>
                    <td className="px-4 py-2.5 font-medium text-slate-800">{s.name}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-blue-700">{parseFloat(s.cgpa).toFixed(2)}</span>
                        <div className="h-1.5 bg-slate-100 rounded-full w-20">
                          <div className="h-1.5 bg-blue-500 rounded-full" style={{ width: `${(s.cgpa / 10) * 100}%` }} />
                        </div>
                      </div>
                    </td>
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

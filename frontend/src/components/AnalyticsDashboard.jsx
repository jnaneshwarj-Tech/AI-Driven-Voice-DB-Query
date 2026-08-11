/**
 * AnalyticsDashboard — Admin analytics: totals, top students, semester stats, graduation analytics.
 */
import { useState, useEffect } from 'react';
import api from '../services/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell } from 'recharts';
import { Users, BookOpen, Upload, Search, RefreshCw, GraduationCap, UserCheck, Calendar, TrendingUp } from 'lucide-react';

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

  const gradAnalytics = data.graduation_analytics || {};
  const COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899'];

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

      {/* Graduation Analytics Section */}
      {gradAnalytics && Object.keys(gradAnalytics).length > 0 && (
        <>
          <div className="mt-6">
            <h3 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
              <GraduationCap className="w-5 h-5 text-indigo-600" />
              Graduation Management System
            </h3>
          </div>

          {/* Graduation stat cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard 
              icon={<UserCheck className="w-5 h-5 text-green-600" />} 
              label="Active Students" 
              value={gradAnalytics.total_active || 0} 
              color="bg-green-50" 
            />
            <StatCard 
              icon={<GraduationCap className="w-5 h-5 text-blue-600" />} 
              label="Graduated Students" 
              value={gradAnalytics.total_graduated || 0} 
              color="bg-blue-50" 
            />
            <StatCard 
              icon={<Calendar className="w-5 h-5 text-purple-600" />} 
              label="Graduated This Year" 
              value={gradAnalytics.graduated_this_year || 0} 
              color="bg-purple-50" 
            />
            <StatCard 
              icon={<TrendingUp className="w-5 h-5 text-amber-600" />} 
              label="Next Graduation Batch" 
              value={gradAnalytics.next_graduation_batch || '—'} 
              color="bg-amber-50" 
            />
          </div>

          {/* Student Type Distribution */}
          {gradAnalytics.student_type_distribution && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-white rounded-xl border border-slate-200 p-4">
                <h3 className="text-sm font-semibold text-slate-700 mb-3">Student Type Distribution</h3>
                <div className="space-y-2">
                  <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg">
                    <span className="text-sm font-medium text-slate-700">Regular Students</span>
                    <span className="text-lg font-bold text-blue-700">
                      {gradAnalytics.student_type_distribution.Regular || 0}
                    </span>
                  </div>
                  <div className="flex items-center justify-between p-3 bg-purple-50 rounded-lg">
                    <span className="text-sm font-medium text-slate-700">Lateral Entry</span>
                    <span className="text-lg font-bold text-purple-700">
                      {gradAnalytics.student_type_distribution['Lateral Entry'] || 0}
                    </span>
                  </div>
                </div>
              </div>

              {/* Graduation by Branch */}
              {gradAnalytics.graduation_by_branch && Object.keys(gradAnalytics.graduation_by_branch).length > 0 && (
                <div className="bg-white rounded-xl border border-slate-200 p-4">
                  <h3 className="text-sm font-semibold text-slate-700 mb-3">Graduation Status by Branch</h3>
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {Object.entries(gradAnalytics.graduation_by_branch).map(([branch, stats], idx) => (
                      <div key={branch} className="flex items-center justify-between p-2 hover:bg-slate-50 rounded">
                        <span className="text-sm font-medium text-slate-700">{branch}</span>
                        <div className="flex items-center gap-3 text-xs">
                          <span className="text-green-600 font-semibold">
                            Active: {stats.active || 0}
                          </span>
                          <span className="text-blue-600 font-semibold">
                            Graduated: {stats.graduated || 0}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Graduation by Year Chart */}
          {gradAnalytics.graduation_by_year && Object.keys(gradAnalytics.graduation_by_year).length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="text-sm font-semibold text-slate-700 mb-3">Graduation Distribution by Year</h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart 
                  data={Object.entries(gradAnalytics.graduation_by_year)
                    .map(([year, count]) => ({ year: parseInt(year), count }))
                    .sort((a, b) => a.year - b.year)
                  } 
                  margin={{ top: 5, right: 10, left: 0, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="year" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => [v, 'Students']} />
                  <Bar dataKey="count" fill="#8b5cf6" radius={[4,4,0,0]} name="Students" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Admission Batch Distribution */}
          {gradAnalytics.admission_batch_distribution && Object.keys(gradAnalytics.admission_batch_distribution).length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="text-sm font-semibold text-slate-700 mb-3">Students by Admission Batch</h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart 
                  data={Object.entries(gradAnalytics.admission_batch_distribution)
                    .map(([batch, count]) => ({ batch: parseInt(batch), count }))
                    .sort((a, b) => a.batch - b.batch)
                  } 
                  margin={{ top: 5, right: 10, left: 0, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="batch" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => [v, 'Students']} />
                  <Bar dataKey="count" fill="#10b981" radius={[4,4,0,0]} name="Students" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}

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

/**
 * AnalyticsDashboard — Admin analytics: totals, top students, semester stats, graduation analytics.
 *
 * Colour only: every chart reads its palette from the CSS custom properties
 * defined in src/index.css, so a chart is correct in light and dark without a
 * single `dark:` variant. Data, aggregation, axes keys and series names are
 * untouched.
 */
import { useState, useEffect } from 'react';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import CountUp from './CountUp';
import { prefersReducedMotion } from '../utils/motionPref';
import { useI18n } from '../context/LanguageContext';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell } from 'recharts';
import { Users, BookOpen, Upload, Search, RefreshCw, GraduationCap, UserCheck, Calendar, TrendingUp } from 'lucide-react';

// Chart palette comes from the token layer, never from a hex literal.
const GRID_STROKE = 'rgb(var(--line-rgb))';
const TICK = { fontSize: 11, fill: 'rgb(var(--ink-mute-rgb))' };
const AXIS_LINE = { stroke: 'rgb(var(--line-strong-rgb))' };
const TOOLTIP_STYLE = {
  background: 'rgb(var(--surface-elev-rgb))',
  border: '1px solid rgb(var(--line-rgb))',
  borderRadius: 'var(--r-sm)',
  color: 'rgb(var(--ink-rgb))',
  fontSize: 12,
};
const TOOLTIP_LABEL = { color: 'rgb(var(--ink-rgb))', fontWeight: 600 };
const TOOLTIP_ITEM = { color: 'rgb(var(--ink-soft-rgb))' };
const BAR_CURSOR = { fill: 'rgb(var(--brand-rgb) / 0.06)' };

function StatCard({ icon, label, value, color }) {
  const n = Number(value);
  const numeric = value !== null && value !== undefined && value !== '' && Number.isFinite(n);
  return (
    <div className="card card-interactive lift relative flex items-center gap-4 p-4">
      <div className={`rounded-md p-3 ${color}`} aria-hidden="true">{icon}</div>
      <div className="min-w-0">
        <p className="t-support text-ink-mute">{label}</p>
        <p className="t-value text-ink">{numeric ? <CountUp value={n} /> : (value ?? '—')}</p>
      </div>
      <span className="sheen" aria-hidden="true" />
    </div>
  );
}

export default function AnalyticsDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const { t } = useI18n();
  // recharts animates in JS, so the CSS reduced-motion block cannot reach it.
  const animate = !prefersReducedMotion();

  const load = async () => {
    setLoading(true); setError('');
    try {
      const res = await api.get('/query/analytics');
      setData(res.data);
    } catch (e) {
      setError(getUserMessage(e, t('analytics.loadFailed')));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) return (
    <div role="status" className="card overflow-hidden">
      <div className="fetch-bar" aria-hidden="true" />
      <div className="flex items-center justify-center gap-2 py-12 text-ink-mute">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-line border-t-brand" aria-hidden="true" />
        <span className="t-body">{t('analytics.loading')}</span>
      </div>
      {/* Shape of the panels to come, never invented numbers. */}
      <div className="skeleton-list px-5 pb-5" aria-hidden="true">
        <span className="skeleton w-full" />
        <span className="skeleton w-11/12" />
        <span className="skeleton w-3/4" />
      </div>
    </div>
  );

  if (error) return (
    <div role="alert" className="card flex flex-wrap items-center justify-between gap-3 border-err/30 bg-err-soft p-4 text-err">
      <span className="t-body">{error}</span>
      <button onClick={load} className="btn btn-ghost btn-sm">{t('common.retry')}</button>
    </div>
  );

  if (!data) return null;

  const gradAnalytics = data.graduation_analytics || {};

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="t-section text-ink">{t('analytics.title')}</h2>
        <button onClick={load} aria-label={t('analytics.refreshAria')} className="btn btn-ghost btn-sm">
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 stagger">
        <StatCard icon={<Users className="h-5 w-5 text-brand-fg" />} label={t('analytics.totalStudents')} value={data.total_students} color="bg-brand/10" />
        <StatCard icon={<BookOpen className="h-5 w-5 text-info" />} label={t('analytics.markRecords')} value={data.total_marks} color="bg-info-soft" />
        <StatCard icon={<Upload className="h-5 w-5 text-ok" />} label={t('analytics.filesUploaded')} value={data.total_files} color="bg-ok-soft" />
        <StatCard icon={<Search className="h-5 w-5 text-warn" />} label={t('analytics.queriesRun')} value={data.total_queries} color="bg-warn-soft" />
      </div>

      {/* Graduation Analytics Section */}
      {gradAnalytics && Object.keys(gradAnalytics).length > 0 && (
        <>
          <div className="mt-6">
            <h3 className="t-section flex items-center gap-2 text-ink">
              <GraduationCap className="h-5 w-5 text-brand-fg" aria-hidden="true" />
              {t('analytics.graduationSystem')}
            </h3>
          </div>

          {/* Graduation stat cards */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 stagger">
            <StatCard
              icon={<UserCheck className="h-5 w-5 text-ok" />}
              label={t('analytics.activeStudents')}
              value={gradAnalytics.total_active || 0}
              color="bg-ok-soft"
            />
            <StatCard
              icon={<GraduationCap className="h-5 w-5 text-brand-fg" />}
              label={t('analytics.graduatedStudents')}
              value={gradAnalytics.total_graduated || 0}
              color="bg-brand/10"
            />
            <StatCard
              icon={<Calendar className="h-5 w-5 text-info" />}
              label={t('analytics.graduatedThisYear')}
              value={gradAnalytics.graduated_this_year || 0}
              color="bg-info-soft"
            />
            <StatCard
              icon={<TrendingUp className="h-5 w-5 text-warn" />}
              label={t('analytics.nextGraduationBatch')}
              value={gradAnalytics.next_graduation_batch || '—'}
              color="bg-warn-soft"
            />
          </div>

          {/* Student Type Distribution */}
          {gradAnalytics.student_type_distribution && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="card p-4 sm:p-5">
                <h3 className="t-card mb-3 text-ink">{t('analytics.studentTypeDist')}</h3>
                <div className="space-y-2">
                  <div className="sunken flex items-center justify-between p-3">
                    <span className="t-body text-ink-soft">{t('analytics.regularStudents')}</span>
                    <span className="t-section tabular-nums text-brand-fg">
                      {gradAnalytics.student_type_distribution.Regular || 0}
                    </span>
                  </div>
                  <div className="sunken flex items-center justify-between p-3">
                    <span className="t-body text-ink-soft">{t('analytics.lateralEntry')}</span>
                    <span className="t-section tabular-nums text-brand-fg">
                      {gradAnalytics.student_type_distribution['Lateral Entry'] || 0}
                    </span>
                  </div>
                </div>
              </div>

              {/* Graduation by Branch */}
              {gradAnalytics.graduation_by_branch && Object.keys(gradAnalytics.graduation_by_branch).length > 0 && (
                <div className="card p-4 sm:p-5">
                  <h3 className="t-card mb-3 text-ink">{t('analytics.gradByBranch')}</h3>
                  <div className="max-h-48 space-y-1 overflow-y-auto pr-1">
                    {Object.entries(gradAnalytics.graduation_by_branch).map(([branch, stats]) => (
                      <div key={branch} className="tr-hover flex items-center justify-between gap-3 rounded-md px-2 py-2">
                        <span className="t-body t-truncate text-ink-soft" title={branch}>{branch}</span>
                        <div className="flex flex-shrink-0 items-center gap-2 text-xs">
                          <span className="badge badge-ok tabular-nums">
                            {t('analytics.active')}: {stats.active || 0}
                          </span>
                          <span className="badge badge-brand tabular-nums">
                            {t('analytics.graduated')}: {stats.graduated || 0}
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
            <div className="card p-4 sm:p-5">
              <h3 className="t-card mb-1 text-ink">{t('analytics.gradByYearChart')}</h3>
              <p className="t-support mb-3 text-ink-mute">{t('analytics.gradByYearAlt')}</p>
              <div className="h-60 w-full sm:h-64" role="img" aria-label={t('analytics.gradByYearAlt')}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={Object.entries(gradAnalytics.graduation_by_year)
                      .map(([year, count]) => ({ year: parseInt(year), count }))
                      .sort((a, b) => a.year - b.year)
                    }
                    margin={{ top: 5, right: 10, left: 0, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
                    <XAxis dataKey="year" tick={TICK} tickLine={false} axisLine={AXIS_LINE} />
                    <YAxis tick={TICK} tickLine={false} axisLine={AXIS_LINE} width={36} />
                    <Tooltip formatter={(v) => [v, t('analytics.students')]} contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} cursor={BAR_CURSOR} />
                    <Bar dataKey="count" fill="rgb(var(--chart-1-rgb))" radius={[4,4,0,0]} name="Students" isAnimationActive={animate} animationDuration={620} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Admission Batch Distribution */}
          {gradAnalytics.admission_batch_distribution && Object.keys(gradAnalytics.admission_batch_distribution).length > 0 && (
            <div className="card p-4 sm:p-5">
              <h3 className="t-card mb-1 text-ink">{t('analytics.admissionBatchChart')}</h3>
              <p className="t-support mb-3 text-ink-mute">{t('analytics.batchAlt')}</p>
              <div className="h-60 w-full sm:h-64" role="img" aria-label={t('analytics.batchAlt')}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={Object.entries(gradAnalytics.admission_batch_distribution)
                      .map(([batch, count]) => ({ batch: parseInt(batch), count }))
                      .sort((a, b) => a.batch - b.batch)
                    }
                    margin={{ top: 5, right: 10, left: 0, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
                    <XAxis dataKey="batch" tick={TICK} tickLine={false} axisLine={AXIS_LINE} />
                    <YAxis tick={TICK} tickLine={false} axisLine={AXIS_LINE} width={36} />
                    <Tooltip formatter={(v) => [v, t('analytics.students')]} contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} cursor={BAR_CURSOR} />
                    <Bar dataKey="count" fill="rgb(var(--chart-4-rgb))" radius={[4,4,0,0]} name="Students" isAnimationActive={animate} animationDuration={620} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </>
      )}

      {/* Semester avg SGPA chart */}
      {data.semester_stats?.length > 0 && (
        <div className="card p-4 sm:p-5">
          <h3 className="t-card mb-1 text-ink">{t('analytics.avgSgpaBySem')}</h3>
          <p className="t-support mb-3 text-ink-mute">{t('analytics.sgpaAlt')}</p>
          <div className="h-56 w-full sm:h-60" role="img" aria-label={t('analytics.sgpaAlt')}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.semester_stats} margin={{ top: 5, right: 10, left: 0, bottom: 18 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
                <XAxis
                  dataKey="semester"
                  tick={TICK}
                  tickLine={false}
                  axisLine={AXIS_LINE}
                  label={{ value: t('analytics.semester'), position: 'insideBottom', offset: -2, fontSize: 11, fill: 'rgb(var(--ink-mute-rgb))' }}
                />
                <YAxis domain={[0, 10]} tick={TICK} tickLine={false} axisLine={AXIS_LINE} width={30} />
                <Tooltip formatter={(v) => [parseFloat(v).toFixed(2), t('analytics.avgSgpa')]} contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} cursor={BAR_CURSOR} />
                <Bar dataKey="avg_sgpa" fill="rgb(var(--chart-3-rgb))" radius={[4,4,0,0]} name="Avg SGPA" isAnimationActive={animate} animationDuration={620} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Top students */}
      {data.top_students?.length > 0 && (
        <div className="card overflow-hidden">
          <div className="border-b border-line px-4 py-3">
            <h3 className="t-card text-ink">{t('analytics.topStudents')}</h3>
          </div>
          <div className="table-scroll">
            <table className="w-full t-table">
              <thead>
                <tr>
                  <th className="th w-8">{t('analytics.rank')}</th>
                  <th className="th">{t('analytics.usn')}</th>
                  <th className="th">{t('analytics.name')}</th>
                  <th className="th">{t('analytics.cgpaCol')}</th>
                </tr>
              </thead>
              <tbody>
                {data.top_students.map((s, i) => (
                  <tr key={i} className="tr-hover">
                    <td className="td tabular-nums text-ink-mute">{i + 1}</td>
                    <td className="td whitespace-nowrap font-mono text-xs text-ink-soft">{s.usn}</td>
                    <td className="td whitespace-nowrap font-medium text-ink">{s.name}</td>
                    <td className="td">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold tabular-nums text-brand-fg">{parseFloat(s.cgpa).toFixed(2)}</span>
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-sunken">
                          <div className="h-1.5 rounded-full bg-brand" style={{ width: `${(s.cgpa / 10) * 100}%` }} />
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

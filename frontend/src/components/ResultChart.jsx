/**
 * ResultChart — auto-renders bar/line/pie based on query trigger words.
 * Triggered by: top, compare, trend, chart, graph, rank, distribution
 *
 * Palette is read from the design tokens in src/index.css (`--chart-N-rgb`),
 * so the chart follows light/dark without any `dark:` variant. Chart type
 * detection and the data shaping below are unchanged.
 */
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import { useI18n } from '../context/LanguageContext';
import { prefersReducedMotion } from '../utils/motionPref';

// Token-driven chart palette — no hex literals, theme-correct in dark mode.
const COLORS = [
  'rgb(var(--chart-3-rgb))',
  'rgb(var(--chart-1-rgb))',
  'rgb(var(--chart-2-rgb))',
  'rgb(var(--chart-4-rgb))',
  'rgb(var(--chart-5-rgb))',
  'rgb(var(--chart-6-rgb))',
  'rgb(var(--chart-1-rgb))',
  'rgb(var(--chart-3-rgb))',
];
const SGPA_SERIES = 'rgb(var(--chart-3-rgb))';
const CGPA_SERIES = 'rgb(var(--chart-1-rgb))';
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
const LEGEND_STYLE = { color: 'rgb(var(--ink-soft-rgb))', fontSize: 12 };
const BAR_CURSOR = { fill: 'rgb(var(--brand-rgb) / 0.06)' };

function detectChartType(query = '') {
  const q = query.toLowerCase();
  if (/trend|over time|progress|semester/.test(q)) return 'line';
  if (/pie|distribution|breakdown|share/.test(q)) return 'pie';
  return 'bar';
}

function prepareChartData(data) {
  if (!data?.length) return [];
  // Use name or usn as label, sgpa/cgpa as value
  return data.slice(0, 20).map(row => ({
    label: row.name || row.usn || row.filename || String(Object.values(row)[0]),
    sgpa:  row.sgpa  != null ? parseFloat(row.sgpa)  : undefined,
    cgpa:  row.cgpa  != null ? parseFloat(row.cgpa)  : undefined,
    value: row.sgpa  != null ? parseFloat(row.sgpa)
         : row.cgpa  != null ? parseFloat(row.cgpa)
         : row.avg_sgpa != null ? parseFloat(row.avg_sgpa)
         : parseFloat(Object.values(row).find(v => !isNaN(parseFloat(v)))) || 0,
    semester: row.semester,
  }));
}

export default function ResultChart({ data, query }) {
  const { t } = useI18n();
  if (!data?.length) return null;
  const chartType = detectChartType(query);
  const chartData = prepareChartData(data);
  const hasSgpa = data.some(r => r.sgpa != null);
  const hasCgpa = data.some(r => r.cgpa != null);
  // recharts animates in JS, so the CSS reduced-motion block cannot reach it.
  const animate = !prefersReducedMotion();

  const altText = chartType === 'line'
    ? t('analytics.resultLineAlt')
    : chartType === 'pie'
      ? t('analytics.resultPieAlt')
      : t('analytics.resultBarAlt');

  return (
    <div className="anim-fade-up mt-4 card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="t-card text-ink">
          {chartType === 'line' ? t('analytics.chartTrend') : chartType === 'pie' ? t('analytics.chartDistribution') : t('analytics.chartBar')}
        </span>
        <span className="t-support tabular-nums text-ink-mute">{t('analytics.dataPoints', { n: chartData.length })}</span>
      </div>
      <p className="sr-only">{altText}</p>
      <div className="h-72 w-full" role="img" aria-label={altText}>
        <ResponsiveContainer width="100%" height="100%">
          {chartType === 'pie' ? (
            <PieChart>
              <Pie data={chartData} dataKey="value" nameKey="label" cx="50%" cy="50%" outerRadius={100} isAnimationActive={animate} animationDuration={620} label={({label, value}) => `${label}: ${value}`} stroke="rgb(var(--surface-rgb))">
                {chartData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} />
              <Legend wrapperStyle={LEGEND_STYLE} />
            </PieChart>
          ) : chartType === 'line' ? (
            <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
              <XAxis dataKey="label" tick={TICK} angle={-35} textAnchor="end" interval={0} tickLine={false} axisLine={AXIS_LINE} />
              <YAxis domain={[0, 10]} tick={TICK} tickLine={false} axisLine={AXIS_LINE} />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} />
              <Legend wrapperStyle={LEGEND_STYLE} />
              {hasSgpa && <Line type="monotone" dataKey="sgpa" stroke={SGPA_SERIES} strokeWidth={2} dot={{ r: 4, fill: SGPA_SERIES }} name="SGPA" isAnimationActive={animate} animationDuration={620} />}
              {hasCgpa && <Line type="monotone" dataKey="cgpa" stroke={CGPA_SERIES} strokeWidth={2} dot={{ r: 4, fill: CGPA_SERIES }} name="CGPA" isAnimationActive={animate} animationDuration={620} />}
              {!hasSgpa && !hasCgpa && <Line type="monotone" dataKey="value" stroke={SGPA_SERIES} strokeWidth={2} dot={{ r: 4, fill: SGPA_SERIES }} isAnimationActive={animate} animationDuration={620} />}
            </LineChart>
          ) : (
            <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="label" tick={TICK} angle={-35} textAnchor="end" interval={0} tickLine={false} axisLine={AXIS_LINE} />
              <YAxis domain={[0, 10]} tick={TICK} tickLine={false} axisLine={AXIS_LINE} />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL} itemStyle={TOOLTIP_ITEM} cursor={BAR_CURSOR} />
              <Legend wrapperStyle={LEGEND_STYLE} />
              {hasSgpa && <Bar dataKey="sgpa" fill={SGPA_SERIES} name="SGPA" radius={[4,4,0,0]} isAnimationActive={animate} animationDuration={620} />}
              {hasCgpa && <Bar dataKey="cgpa" fill={CGPA_SERIES} name="CGPA" radius={[4,4,0,0]} isAnimationActive={animate} animationDuration={620} />}
              {!hasSgpa && !hasCgpa && <Bar dataKey="value" fill={SGPA_SERIES} radius={[4,4,0,0]} isAnimationActive={animate} animationDuration={620} />}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

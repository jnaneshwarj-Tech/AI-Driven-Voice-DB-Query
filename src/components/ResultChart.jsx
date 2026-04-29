/**
 * ResultChart — auto-renders bar/line/pie based on query trigger words.
 * Triggered by: top, compare, trend, chart, graph, rank, distribution
 */
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';

const COLORS = ['#3b82f6','#6366f1','#8b5cf6','#ec4899','#f59e0b','#10b981','#ef4444','#06b6d4'];

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
  if (!data?.length) return null;
  const chartType = detectChartType(query);
  const chartData = prepareChartData(data);
  const hasSgpa = data.some(r => r.sgpa != null);
  const hasCgpa = data.some(r => r.cgpa != null);

  return (
    <div className="mt-4 p-4 bg-slate-50 rounded-xl border border-slate-200">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold text-slate-700">
          {chartType === 'line' ? 'Trend Chart' : chartType === 'pie' ? 'Distribution' : 'Bar Chart'}
        </span>
        <span className="text-xs text-slate-400">{chartData.length} data points</span>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        {chartType === 'pie' ? (
          <PieChart>
            <Pie data={chartData} dataKey="value" nameKey="label" cx="50%" cy="50%" outerRadius={100} label={({label, value}) => `${label}: ${value}`}>
              {chartData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        ) : chartType === 'line' ? (
          <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} angle={-35} textAnchor="end" interval={0} />
            <YAxis domain={[0, 10]} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            {hasSgpa && <Line type="monotone" dataKey="sgpa" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} name="SGPA" />}
            {hasCgpa && <Line type="monotone" dataKey="cgpa" stroke="#6366f1" strokeWidth={2} dot={{ r: 4 }} name="CGPA" />}
            {!hasSgpa && !hasCgpa && <Line type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} />}
          </LineChart>
        ) : (
          <BarChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} angle={-35} textAnchor="end" interval={0} />
            <YAxis domain={[0, 10]} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            {hasSgpa && <Bar dataKey="sgpa" fill="#3b82f6" name="SGPA" radius={[4,4,0,0]} />}
            {hasCgpa && <Bar dataKey="cgpa" fill="#6366f1" name="CGPA" radius={[4,4,0,0]} />}
            {!hasSgpa && !hasCgpa && <Bar dataKey="value" fill="#3b82f6" radius={[4,4,0,0]} />}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

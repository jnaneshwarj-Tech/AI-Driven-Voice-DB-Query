import React, { useEffect, useState } from 'react';
import { getDashboard } from '../api';
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, ArcElement,
  Title, Tooltip, Legend, PointElement, LineElement
} from 'chart.js';
import { Bar, Pie } from 'react-chartjs-2';

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Title, Tooltip, Legend, PointElement, LineElement);

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getDashboard()
      .then(r => setStats(r.data))
      .catch(e => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading-overlay"><div className="spinner" /><span>Loading dashboard...</span></div>;
  if (error) return <div className="alert alert-error">{error}</div>;
  if (!stats) return null;

  const branchChart = {
    labels: (stats.branch_distribution || []).map(r => r.branch || 'Unknown'),
    datasets: [{
      label: 'Students',
      data: (stats.branch_distribution || []).map(r => r.count),
      backgroundColor: ['#1a73e8','#34a853','#fbbc04','#ea4335','#9c27b0','#00bcd4','#ff5722','#607d8b','#795548','#e91e63'],
    }],
  };

  const cgpaChart = {
    labels: (stats.cgpa_distribution || []).map(r => r.range_label),
    datasets: [{
      data: (stats.cgpa_distribution || []).map(r => r.count),
      backgroundColor: ['#1a73e8','#34a853','#fbbc04','#ea4335','#9c27b0','#00bcd4'],
    }],
  };

  return (
    <div>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="value">{stats.total_students}</div>
          <div className="label">Total Students</div>
        </div>
        <div className="stat-card">
          <div className="value">{stats.avg_cgpa}</div>
          <div className="label">Average CGPA</div>
        </div>
        <div className="stat-card success">
          <div className="value">{stats.graduated}</div>
          <div className="label">Graduated</div>
        </div>
        <div className="stat-card warn">
          <div className="value">{stats.low_performers}</div>
          <div className="label">Low Performers (CGPA &lt; 5)</div>
        </div>
      </div>

      <div className="charts-grid">
        {(stats.branch_distribution || []).length > 0 && (
          <div className="chart-card">
            <h3>Students by Branch</h3>
            <Bar data={branchChart} options={{ responsive: true, plugins: { legend: { display: false } } }} />
          </div>
        )}
        {(stats.cgpa_distribution || []).length > 0 && (
          <div className="chart-card">
            <h3>CGPA Distribution</h3>
            <Pie data={cgpaChart} options={{ responsive: true }} />
          </div>
        )}
      </div>

      {(stats.top_students || []).length > 0 && (
        <div className="card">
          <h2>🏆 Top 5 Students by CGPA</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th>Name</th><th>USN</th><th>CGPA</th><th>Branch</th></tr></thead>
              <tbody>
                {stats.top_students.map((s, i) => (
                  <tr key={s.usn}>
                    <td>{i + 1}</td>
                    <td>{s.name}</td>
                    <td>{s.usn}</td>
                    <td><strong>{s.cgpa}</strong></td>
                    <td>{s.branch}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(stats.low_performer_list || []).length > 0 && (
        <div className="card">
          <h2>⚠️ Low Performers (CGPA &lt; 5)</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Name</th><th>USN</th><th>CGPA</th><th>Branch</th></tr></thead>
              <tbody>
                {stats.low_performer_list.map(s => (
                  <tr key={s.usn} className="issue-row">
                    <td>{s.name}</td><td>{s.usn}</td><td>{s.cgpa}</td><td>{s.branch}</td>
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

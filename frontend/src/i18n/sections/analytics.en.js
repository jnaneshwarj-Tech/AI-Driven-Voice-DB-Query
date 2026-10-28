/**
 * Analytics dashboard + query result chart strings (English).
 *
 * Chart series names (Students / Avg SGPA / SGPA / CGPA) and every data value
 * stay exactly as the charts render them today; only headings, captions and
 * axis titles live here.
 */
export default {
  'analytics.title': 'Analytics Dashboard',
  'analytics.loading': 'Loading analytics...',
  'analytics.loadFailed': 'Failed to load analytics.',
  'analytics.refreshAria': 'Reload analytics',

  // ── KPI captions ──────────────────────────────────────────────────────
  'analytics.totalStudents': 'Total Students',
  'analytics.markRecords': 'Mark Records',
  'analytics.filesUploaded': 'Files Uploaded',
  'analytics.queriesRun': 'Queries Run',

  // ── Graduation section ────────────────────────────────────────────────
  'analytics.graduationSystem': 'Graduation Management System',
  'analytics.activeStudents': 'Active Students',
  'analytics.graduatedStudents': 'Graduated Students',
  'analytics.graduatedThisYear': 'Graduated This Year',
  'analytics.nextGraduationBatch': 'Next Graduation Batch',
  'analytics.studentTypeDist': 'Student Type Distribution',
  'analytics.regularStudents': 'Regular Students',
  'analytics.lateralEntry': 'Lateral Entry',
  'analytics.gradByBranch': 'Graduation Status by Branch',
  'analytics.active': 'Active',
  'analytics.graduated': 'Graduated',
  'analytics.gradByYearChart': 'Graduation Distribution by Year',
  'analytics.admissionBatchChart': 'Students by Admission Batch',

  // ── SGPA chart / top performers ───────────────────────────────────────
  'analytics.avgSgpaBySem': 'Average SGPA by Semester',
  'analytics.semester': 'Semester',
  'analytics.students': 'Students',
  'analytics.avgSgpa': 'Avg SGPA',
  'analytics.topStudents': 'Top 10 Students by CGPA',
  'analytics.rank': '#',
  'analytics.usn': 'USN',
  'analytics.name': 'Name',
  'analytics.cgpaCol': 'CGPA (Avg SGPA)',

  // ── ResultChart (query results) ───────────────────────────────────────
  'analytics.chartTrend': 'Trend Chart',
  'analytics.chartDistribution': 'Distribution',
  'analytics.chartBar': 'Bar Chart',
  'analytics.dataPoints': '{n} data points',

  // ── Text alternatives so charts are not colour-only ───────────────────
  'analytics.gradByYearAlt': 'Bar chart of graduates counted by graduation year.',
  'analytics.batchAlt': 'Bar chart of students counted by admission batch year.',
  'analytics.sgpaAlt': 'Bar chart of the average SGPA for each semester.',
  'analytics.resultLineAlt': 'Line chart of scores for each student in the query result.',
  'analytics.resultBarAlt': 'Bar chart of scores for each student in the query result.',
  'analytics.resultPieAlt': 'Pie chart of the share contributed by each entry in the query result.',
};

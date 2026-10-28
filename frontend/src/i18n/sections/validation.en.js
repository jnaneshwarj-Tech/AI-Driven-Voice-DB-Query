/**
 * ValidationDashboard — English chrome strings.
 * Issue-type values (`missing_name`, …), USNs, names and the backend
 * `issue.detail` text are rendered raw; only the labels around them live here.
 * Values mirror the pre-redesign on-screen wording.
 */
export default {
  'validation.title': 'Data Validation Dashboard',
  'validation.loading': 'Running validation checks…',
  'validation.errLoad': 'Failed to load validation data.',

  // Summary cards
  'validation.totalStudents': 'Total Students',
  'validation.markRecords': 'Mark Records',
  'validation.issuesFound': 'Issues Found',
  'validation.allClean': 'All data looks clean. No issues detected.',

  // Issues table
  'validation.issueCount': '{n} Issue(s) Found',
  'validation.colIssue': 'Issue',
  'validation.colUsn': 'USN',
  'validation.colSemester': 'Semester',
  'validation.colDetail': 'Detail',
  'validation.semester': 'Sem {n}',

  // Issue labels (keyed by the backend value, which is never translated)
  'validation.typeMissingName': 'Missing name',
  'validation.typeInvalidSgpa': 'Invalid SGPA',
  'validation.typeInvalidSemester': 'Invalid semester',
  'validation.typeTooManySemesters': 'Too many semesters',

  // Duplicates table
  'validation.duplicatesTitle': 'Potential Duplicate Students ({n})',
  'validation.colName': 'Name',
  'validation.colRecords': 'Records',
  'validation.colUsns': 'USN(s)',
  'validation.recordCount': '{n} records',
};

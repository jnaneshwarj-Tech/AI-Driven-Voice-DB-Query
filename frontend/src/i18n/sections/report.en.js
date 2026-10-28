/**
 * Report section — English strings for ReportModal.jsx (Generate Report).
 *
 * Scope: on-screen chrome only. Preview titles, notes, column values, USNs,
 * usernames/roles and generated filenames are backend data and never routed
 * through here.
 */
export default {
  'report.heading': 'Generate Report',
  'report.searching': 'Search: “{query}”',
  'report.stepType': '1. Report type',
  'report.stepRecords': '2. Which records',
  'report.stepFormat': '3. Format',
  'report.preview': 'Preview',

  // Categories — ids match the payload sent to /export/report and never change
  'report.cat.student_list.title': 'Student List',
  'report.cat.student_list.desc': 'USN, name, branch, semester and the other columns shown in the results.',
  'report.cat.academic.title': 'Academic',
  'report.cat.academic.desc': 'Semester, SGPA, CGPA and branch for the shown students.',
  'report.cat.personal.title': 'Personal Details',
  'report.cat.personal.desc': 'Name, date of birth, address and personal fields you are allowed to see.',
  'report.cat.fees.title': 'Fees',
  'report.cat.fees.desc': 'Total paid, pending amount and payment status, where available.',
  'report.cat.discontinued.title': 'Discontinued Students',
  'report.cat.discontinued.desc': 'Discontinuation date, reason and current status.',
  'report.cat.individual.title': 'Individual Student',
  'report.cat.individual.desc': 'Full details of one selected student (when exactly one is chosen).',

  // Formats — PDF/CSV/Excel stay in Latin script
  'report.fmt.pdf': 'PDF',
  'report.fmt.excel': 'Excel',
  'report.fmt.csv': 'CSV',
  'report.fmt.print': 'Print',

  // Record scope
  'report.scopePage': 'Current page ({n})',
  'report.scopePage.desc': 'Only the rows on the page you are viewing.',
  'report.scopeSelected': 'Selected students ({n})',
  'report.scopeSelected.desc': 'Rows ticked in the result table.',
  'report.scopeAll': 'All matching results ({n})',
  'report.scopeAll.desc': 'Every row shown by this search, with the same filter and sorting.',
  'report.tickFirst': 'Tick rows in the table first, or choose another option.',

  // Validation / error messages owned by the frontend
  'report.noRecords': 'There are no displayed records to report on.',
  'report.pickOne': 'Select exactly one student (tick one row) for an Individual Student Report.',
  'report.popups': 'Please allow pop-ups to print the report.',
  'report.failed': 'Report generation failed.',

  // Preview meta — the {value} slots carry backend data verbatim
  'report.preparingPreview': 'Preparing preview…',
  'report.nothingPreview': 'Nothing to preview — choose records first.',
  'report.recordsCount': 'Records: {n}',
  'report.by': 'By: {who}',
  'report.note': 'Note: {text}',
  'report.noRows': 'No rows for this report with the selected students.',
  'report.truncated': 'Showing first 15 of {n} rows — the downloaded report contains all of them.',
  'report.alsoIncluded': 'Also included: {sections}',

  // Footer actions
  'report.working': 'Preparing…',
  'report.printReport': 'Print Report',
  'report.downloadFmt': 'Download {fmt}',
};

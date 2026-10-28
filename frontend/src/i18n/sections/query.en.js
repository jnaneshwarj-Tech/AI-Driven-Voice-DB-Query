/**
 * Query tab, results area, data tables and the undo panel.
 * These keys belong to Dashboard.jsx — the components in src/components use
 * their own section files.
 */
export default {
  // ── Welcome hero (query tab, shown until the first result) ───────────────
  'hero.title': 'Ask about students in your own words',
  'hero.body': 'Type or speak in English, Kannada or a mix of both. Marks, fees, semesters and arrears come straight from the college database.',
  'hero.photoAlt': 'The college campus',
  'hero.capType': 'Plain language',
  'hero.capVoice': 'Voice input',
  'hero.capDb': 'Live records',

  // ── Query input ──────────────────────────────────────────────────────────
  'query.voiceLabel': 'Select voice input language',
  'query.selectLang': 'Select the language of your question',
  'query.voiceEnglish': 'English',
  'query.voiceKannada': 'Kannada',
  'query.voiceIndia': 'English (India)',
  'query.kannadaMode': 'ಕನ್ನಡ Mode',
  'query.mixedMode': 'Mixed Language Mode',
  'query.mic': 'Voice input',
  'query.listening': 'Listening...',
  'query.autoConvert': 'Auto-convert: Type English → Get Kannada instantly!',
  'query.run': 'Run Query',
  'query.searching': 'Searching...',
  'query.complete': 'Query Complete',
  'query.try': 'Try:',
  'query.ariaInput': 'Ask about students in plain language',

  // ── ಕನ್ನಡ transliteration suggestions ───────────────────────────────────
  'query.kaSuggestions': 'ಕನ್ನಡ Suggestions (Space or Click to select)',
  'query.kaNavigate': '↑↓ navigate · Space/Enter select',
  'query.kaPressSpace': '(Press Space)',

  // ── Live suggestions dropdown ────────────────────────────────────────────
  'query.liveCount': '{n} suggestion{s} for “{q}”',
  'query.liveHint': '↑↓ navigate · Enter select · Esc close',
  'query.kbdEnter': 'Enter',
  'query.liveFooter': 'Press {key} to search · Click to view student',

  // ── Notices ──────────────────────────────────────────────────────────────
  'query.loadingTitle': 'Searching students...',
  'query.loadingBody': 'Applying the submitted filters and validating matching records.',
  'query.failed': 'Query Failed',
  'query.reportedFilters': 'Applied filters',
  'query.conditions': '{n} conditions',
  'query.conditionsChecked': 'Conditions checked:',
  'query.fromCache': 'from cache',

  // ── Results ──────────────────────────────────────────────────────────────
  'results.result': 'Result',
  'results.femaleStudents': 'Female Students',
  'results.records': '{n} record(s)',
  'results.noMatching': 'No matching students',
  'results.operationComplete': 'Operation Complete',
  'results.personalView': 'Personal View',
  'results.completeProfile': 'Complete Profile',
  'results.academicView': 'Academic View',
  'results.generateReport': 'Generate Report',
  'results.total': 'Total: {n}',
  'results.femaleNames': 'Female Student Names',
  'results.studentsCount': '{n} students',
  'results.noRecords': 'No records found.',
  'results.ariaFilters': 'Applied filters',

  // ── Query execution details (dev only) ───────────────────────────────────
  'debug.title': 'Query Execution Details',
  'debug.close': 'Close',
  'debug.normalized': 'Normalized:',
  'debug.intent': 'Intent:',
  'debug.validation': 'Validation:',
  'debug.filters': 'Resolved filters',
  'debug.sql': 'SQL (masked)',
  'debug.parameters': 'Parameters (masked)',
  'debug.rows': '{n} row(s)',

  // ── Data table ───────────────────────────────────────────────────────────
  'table.search': 'Search results...',
  'table.searchLabel': 'Search within these results',
  'table.rows': '{n} rows',
  'table.selectAll': 'Select all rows on this page',
  'table.selectRow': 'Select row {key}',
  'table.sortHint': 'Click to sort',
  'table.prev': 'Prev',
  'table.next': 'Next',
  'table.pageOf': 'Page {page} of {total}',

  // ── Undo / restore panel ─────────────────────────────────────────────────
  'undo.loading': 'Loading deleted records...',
  'undo.title': 'Restore Deleted Students',
  'undo.subtitle': 'Students deleted in the last 5 minutes can be restored.',
  'undo.refresh': 'Refresh',
  'undo.emptyTitle': 'No recently deleted students',
  'undo.emptyBody': 'Deleted students appear here for 5 minutes after deletion.',
  'undo.deletedBy': 'Deleted by:',
  'undo.window': 'Restore window remaining',
  'undo.restored': 'Restored',
  'undo.expired': 'Window expired',
  'undo.restore': 'Restore',
  'undo.restoring': 'Restoring...',

  // ── Confirm modal ────────────────────────────────────────────────────────
  'confirm.finalTitle': 'Final Confirmation',
  'confirm.title': 'Confirm {action}',
  'confirm.lastCheck': 'Last check before writing: {message}',
  'confirm.confirmNow': 'Confirm this operation now.',
  'confirm.updateFees': 'You are about to update this student’s fees.',
  'confirm.lifecycleChange': 'You are about to record a lifecycle change.',
  'confirm.deleteWarning': 'Warning: This will permanently remove the selected student data. Do you want to continue?',
  'confirm.executePrefix': 'You are about to execute a {action} operation.',
  'confirm.adminOnly': 'This change is Admin-only. You do not have permission to execute it.',
  'confirm.undoNote': 'An UNDO option will appear for 30 seconds after deletion.',
  'confirm.cancel': 'Cancel',
  'confirm.proceed': 'Yes, proceed',
  'confirm.executing': 'Executing...',
  'confirm.execute': 'Confirm & Execute',

  // ── Upload notice ────────────────────────────────────────────────────────
  'upload.parsed': 'parsed',
  'upload.new': 'New',
  'upload.updated': 'Updated',
  'upload.unchanged': 'Unchanged',
  'upload.dup': 'Dup',
  'upload.invalid': 'Invalid',
  'upload.saved': 'Saved',
  'upload.students': 'students',
  'upload.marks': 'marks',
  'upload.columnsMapped': 'Columns mapped:',
};

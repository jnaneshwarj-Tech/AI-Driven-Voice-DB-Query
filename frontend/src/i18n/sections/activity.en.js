/**
 * ActivityDashboard — English chrome strings.
 *
 * Backend-owned values (status codes SUCCESS/FAILED/UNDONE, actor ids, table
 * names, file names, `description`/`summary` text, formats such as PDF/CSV) are
 * rendered raw and are never routed through here; only the labels the frontend
 * writes around them are keys.
 */
export default {
  // Header
  'activity.title': 'Audit Activity & Operations Log',
  'activity.sub': 'Real-time track, snapshot timeline, and safe database reversion control.',
  'activity.refresh': 'Refresh Logs',
  'activity.refreshing': 'Refreshing…',
  'activity.errLoad': 'Failed to load activity logs.',
  'activity.revertedToast': 'Reverted {type} successfully!',
  'activity.restoreFailed': 'Could not restore student.',

  // Stat cards
  'activity.totalSearches': 'Total Searches',
  'activity.deletionsTracked': 'Deletions Tracked',
  'activity.updatesDone': 'Updates Done',
  'activity.dbBackups': 'Database Backups',

  // Filter tabs
  'activity.filterAria': 'Filter activity log by operation type',
  'activity.tabAll': 'All Operations',
  'activity.tabQueries': 'Queries',
  'activity.tabAdditions': 'Additions',
  'activity.tabDeletions': 'Deletions',
  'activity.tabUpdates': 'Updates',
  'activity.tabUploads': 'Uploads',
  'activity.tabBackups': 'Backups',
  'activity.tabExports': 'Exports',
  'activity.tabVtuSync': 'VTU Sync',
  'activity.recordCount': '{n} records',

  // States
  'activity.loading': 'Fetching secure activity records…',
  'activity.empty': 'No activity logs found',
  'activity.emptyHint': 'Perform actions in the query dashboard to populate logs.',

  // Stream titles
  'activity.tQuery': 'NLP Data Query',
  'activity.tProfileAdded': 'Student Profile Added',
  'activity.tDeletion': 'Student Deletion Executed',
  'activity.tUpdated': 'Student Record Updated',
  'activity.tFileDeleted': 'Uploaded File Deleted',
  'activity.tBulkImport': 'Bulk Database Import',
  'activity.tReportExported': 'Academic Report Exported',
  'activity.tVtuSync': 'VTU Semester Synchronization',
  'activity.tUndoDone': 'Undo Completed',
  'activity.tBackupCreated': 'Database Backup Created',

  // Audit event titles (keyed by the backend action value)
  'activity.aRestored': 'Student Restored',
  'activity.aUndoSuccess': 'Undo Completed',
  'activity.aUploadFailed': 'Import Failed',
  'activity.aUndoFailed': 'Undo Failed',
  'activity.aLogin': 'User Login',
  'activity.aLogout': 'User Logout',

  // Descriptions the frontend builds (backend `description`/`summary` wins when present)
  'activity.dSearched': 'Searched: "{query}"',
  'activity.dInserted': 'Inserted students: {names}',
  'activity.dDeletedStudents': 'Deleted students: {names}',
  'activity.dUpdated': 'Updated students: {names}',
  'activity.dDeletedFile': 'Deleted file {name}',
  'activity.dUploaded': 'Uploaded file data containing {n} record(s)',
  'activity.dSemester': 'Completed academic semester mapping for {n} student(s)',
  'activity.dExported': 'Generated and downloaded {format} sheet containing {n} record(s)',
  'activity.dUndone': 'Operation undone.',
  'activity.dBackup': 'Backup {name} ({type}) created. Status: {status}',

  // Row metadata
  'activity.undone': 'Undone / Rolled Back',
  'activity.operator': 'Operator:',
  'activity.system': 'System',
  'activity.dbTable': 'Database Table:',
  'activity.operation': 'Operation:',
  'activity.affectedRecords': 'Affected Records ({n}):',
  'activity.undo': 'Undo',
  'activity.undoing': 'Undoing…',
  'activity.undoUnavailable': 'Undo unavailable',
};

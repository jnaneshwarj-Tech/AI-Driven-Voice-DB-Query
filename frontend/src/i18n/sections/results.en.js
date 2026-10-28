/**
 * Results section — English strings for OperationResultModal.jsx.
 *
 * Backend-authored fields (operation messages, USNs, names, row numbers,
 * storage identifiers, column mappings, field names) are rendered as-is;
 * only the labels the frontend owns live here.
 */
export default {
  'results.deleted': 'Student Deleted',
  'results.added': 'Student Added',
  'results.updated': 'Record Updated',
  'results.uploadDone': 'Upload Completed',

  'results.restored': '✓ Restored successfully',
  'results.restoredShort': 'Restored!',
  'results.restoring': 'Restoring...',
  'results.undo': 'UNDO — Restore',

  // DetailList (collapsible per-row lists)
  'results.newRecords': 'New records',
  'results.updatedRecords': 'Updated records',
  'results.duplicateRows': 'Duplicate rows',
  'results.invalidRows': 'Invalid / rejected rows',
  'results.noName': '(no name)',
  'results.row': 'Row {n}',
  'results.fields': 'Fields: {fields}',

  // Upload stat cells — labels only; every value comes from backend stats
  'results.rowsParsed': 'Rows Parsed',
  'results.new': 'New',
  'results.updatedShort': 'Updated',
  'results.unchanged': 'Unchanged',
  'results.duplicates': 'Duplicates',
  'results.invalid': 'Invalid',
  'results.studentsSaved': 'Students Saved',
  'results.marksSaved': 'Marks Saved',
  'results.accounting': 'Row accounting note: {accounted} of {parsed} rows classified.',
  'results.mapping': 'Mapping: {map}',

  'results.affectedRows': 'Affected rows:',
  'results.recycleBin': 'Moved to Recycle Bin',
  'results.storedIn': 'Stored In Database',
  'results.system': 'System',
  'results.storage': 'Storage:',
};

/**
 * FileExplorer — English chrome strings.
 * Merged automatically by src/i18n/index.js (import.meta.glob).
 *
 * Values mirror the wording that was on screen before the redesign, so English
 * users see no change. File names, USNs, backend `message`/`detail` payloads and
 * table names are never routed through here.
 */
export default {
  'files.title': 'File Explorer',
  'files.count': '{n} files',
  'files.pendingCount': '{n} pending',

  // Actions
  'files.upload': 'Upload File',
  'files.uploading': 'Uploading…',
  'files.updateAll': 'Update All ({n})',
  'files.updating': 'Updating…',
  'files.moveToTrash': 'Move to Trash',
  'files.moveToTrashAria': 'Move {name} to Trash',

  // Trash
  'files.trash': 'Trash',
  'files.trashCount': 'Trash ({n})',
  'files.openTrash': 'Open Trash',
  'files.trashNote': 'Files can be restored for 30 days',
  'files.trashEmpty': 'Trash is empty.',
  'files.deletedAt': 'Deleted {time}',
  'files.daysLeft': '{n} days left to restore',
  'files.restoreExpired': 'Restore period expired',
  'files.restore': 'Restore',
  'files.restoring': 'Restoring…',
  'files.restoreTitle': 'Restore file and imported data',
  'files.deletePermanent': 'Delete Permanently',
  'files.deleting': 'Deleting…',

  // Upload / import result
  'files.uploadedStart': '"{name}" uploaded. Updating database…',
  'files.importedPrefix': '"{name}" imported.',
  'files.statNew': '{n} new',
  'files.statUpdated': '{n} updated',
  'files.statUnchanged': '{n} unchanged',
  'files.statDuplicate': '{n} duplicate',
  'files.statInvalid': '{n} invalid',
  'files.studentsSummary': 'Students: {list}.',
  'files.marksAdded': '{n} marks added',
  'files.marksUpdated': '{n} marks updated',
  'files.savedStats': '"{name}" saved. Students: {list}.',
  'files.dbUpdatedOk': 'Database updated successfully.',
  'files.provisional': '{n} name-only student(s) given temporary USNs (in name order) — replace with real USNs later.',
  'files.provisionalShort': '{n} name-only student(s) given temporary USNs — replace with real USNs later.',

  // Confirmation dialogs
  'files.toTrashConfirm': 'Move "{name}" to Trash? Imported data owned only by this file will be removed. The file and its data can be restored for 30 days.',
  'files.toTrashDone': '"{name}" moved to Trash for 30 days.',
  'files.permConfirm': '⚠️ Permanently delete this record?\n\nThis will permanently remove the selected student and its stored recovery data from Trash. This operation cannot be undone.\n\nAre you sure?',
  'files.permDeleted': '"{name}" was permanently deleted from Trash.',
  'files.restored': '"{name}" and its imported data were restored.',

  // Error-detail line labels (the reason text itself comes from the backend)
  'files.invalidRows': 'Invalid rows: {n}',
  'files.rowsParsed': 'Parsed: {n}',
  'files.rowReason': 'Row {row}: {reason}',

  // Row metadata and states
  'files.pending': 'Pending',
  'files.badgeImported': 'Imported',
  'files.unknownType': 'Unknown type',
  'files.rows': '{n} rows',
  'files.rowsUnavailable': 'Rows unavailable',
  'files.uploadTimeUnavailable': 'Upload time unavailable',
  'files.unknownUploader': 'unknown uploader',
  'files.pendingNote': 'File uploaded but not yet added to the database.',
  'files.expiredNote': 'This file\'s data is no longer in the database. Please re-upload it and import it again.',
  'files.empty': 'No files uploaded yet',
  'files.emptyHint': 'Upload CSV, XLSX, PDF, TXT, or images',

  // Failures
  'files.errLoad': 'Failed to load files.',
  'files.errTrashLoad': 'Failed to load Trash.',
  'files.errUpload': 'Upload failed. Check file type and server connection.',
  'files.errUploadDb': 'File uploaded, but database update failed. Check format.',
  'files.errDbUpdate': 'Database update failed. Check file format.',
  'files.errToTrash': 'Could not move file to Trash.',
  'files.errRestore': 'Could not restore file from Trash.',
  'files.errPermanent': 'Could not permanently delete this file from Trash.',
};

/**
 * Backup & Restore panel strings (English).
 *
 * Values mirror the wording already on screen so the English UI does not move
 * a single word. Backend-authored text (`err.response.data.detail`, the
 * `message` returned by the API, status/backup_type enum values, filenames and
 * usernames) is deliberately NOT routed through here.
 */
export default {
  // ── Header / actions ──────────────────────────────────────────────────
  'backup.title': 'Database Reliability & Backup Center',
  'backup.subtitle': 'Backup, restore, upload version history, and enterprise audit log.',
  'backup.create': 'Create Backup Now',
  'backup.creating': 'Creating Backup...',
  'backup.restoring': 'Restoring...',
  'backup.confirmRestore': 'Confirm Restore',
  'backup.restore': 'Restore',

  // ── Storage widget ────────────────────────────────────────────────────
  'backup.dbSize': 'Database Size',
  'backup.dbBreakdown': 'Data: {data}MB · Index: {index}MB',
  'backup.backupStorage': 'Backup Storage',
  'backup.verifiedBackups': '{n} verified backup(s)',
  'backup.diskUsage': 'Disk Usage',
  'backup.diskUsed': 'Used: {v} GB',
  'backup.diskFree': 'Free: {v} GB',
  'backup.diskTotal': 'Total: {v} GB',

  // ── Tabs ──────────────────────────────────────────────────────────────
  'backup.tabHistory': 'Backup History',
  'backup.tabUploads': 'Upload Versions',
  'backup.tabAudit': 'Audit Log',

  // ── Staff notice ──────────────────────────────────────────────────────
  'backup.staffNotice':
    'Backup creation and restore require Admin access. You can view storage status and upload history.',

  // ── Empty / loading states ────────────────────────────────────────────
  'backup.loadingHistory': 'Loading backup history...',
  'backup.emptyHistory': 'No backups yet',
  'backup.emptyHistoryHelp': 'Click “Create Backup Now” to create the first backup.',
  'backup.emptyUploads': 'No upload history yet',
  'backup.emptyUploadsHelp': 'Upload a file to see version history here.',
  'backup.emptyAudit': 'No audit events yet',
  'backup.emptyAuditHelp': 'Actions like login, upload, backup will appear here.',

  // ── Backup rows ───────────────────────────────────────────────────────
  'backup.fileMissing': 'File missing',
  'backup.by': 'By',
  'backup.students': 'students',
  'backup.unknown': 'Unknown',
  'backup.verified': 'Verified',
  'backup.verifiedYes': 'Yes ✓',
  'backup.notVerified': 'Not verified',
  'backup.completed': 'Completed',
  'backup.fileLabel': 'File',
  'backup.showDetails': 'Show backup details',
  'backup.hideDetails': 'Hide backup details',
  'backup.deleteAria': 'Delete this backup',

  // ── Restore confirmation modal ────────────────────────────────────────
  'backup.modalHeading': 'Confirm Database Restore',
  'backup.modalDanger': 'This is a destructive operation',
  'backup.modalWhat': 'What will happen:',
  'backup.modalPoint1Lead': 'A safety backup of the',
  'backup.modalPoint1Bold': 'current database',
  'backup.modalPoint1Tail': 'will be created first',
  'backup.modalPoint2': 'The selected backup will be restored',
  'backup.modalPoint3Lead': 'All data added',
  'backup.modalPoint3Bold': 'after',
  'backup.modalPoint3Tail': 'the backup date will be lost',
  'backup.modalPoint4': 'This action cannot be undone with the normal undo button',
  'backup.modalBackup': 'Backup',
  'backup.modalCreated': 'Created',
  'backup.modalSize': 'Size',
  'backup.modalRecords': 'Records',

  // ── Delete confirmation (native dialog) ───────────────────────────────
  'backup.deleteConfirm': 'Delete backup “{name}”? This cannot be undone.',

  // ── Toast fallbacks (only used when the API sends no message) ─────────
  'backup.createdToast': 'Backup created successfully!',
  'backup.createFailed': 'Backup creation failed.',
  'backup.restoredToast': 'Database restored successfully!',
  'backup.restoreFailed': 'Restore failed. Check audit log for details.',
  'backup.deletedToast': 'Backup deleted.',
  'backup.deleteFailed': 'Delete failed.',

  // ── Upload version table ──────────────────────────────────────────────
  'backup.colFile': 'File',
  'backup.colAdded': 'Added',
  'backup.colUpdated': 'Updated',
  'backup.colUnchanged': 'Unchanged',
  'backup.colMarks': 'Marks',
  'backup.colSkipped': 'Skipped',
  'backup.colBy': 'By',
  'backup.colTime': 'Time',
};

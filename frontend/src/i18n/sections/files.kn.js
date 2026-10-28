/**
 * FileExplorer — Kannada chrome strings (ಅಧಿಕೃತ ಪ್ರಶಾಸನ ನೋಂದಣಿ).
 *
 * ಫೈಲ್ ಹೆಸರು, USN, ಬ್ಯಾಕೆಂಡ್‌ನಿಂದ ಬರುವ `message`/`detail` ಸಂದೇಶಗಳು ಮತ್ತು
 * ಕೋಷ್ಟಕ (table) ಹೆಸರುಗಳು ಇಲ್ಲಿ ಬರುವುದಿಲ್ಲ — ಅವುಗಳನ್ನು ಯಥಾವತ್ತಾಗಿ ತೋರಿಸುತ್ತದೆ.
 * CSV/XLSX/PDF/TXT, USN, OTP ನಂತರದ ಸಂಕ್ಷಿಪ್ತನಾಮಗಳು ಲ್ಯಾಟಿನ್‌ನಲ್ಲೇ ಉಳಿಯುತ್ತವೆ.
 */
export default {
  'files.title': 'ಫೈಲ್ ಎಕ್ಸ್‌ಪ್ಲೋರರ್',
  'files.count': '{n} ಫೈಲ್‌ಗಳು',
  'files.pendingCount': '{n} ಬಾಕಿ',

  // Actions
  'files.upload': 'ಫೈಲ್ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ',
  'files.uploading': 'ಅಪ್‌ಲೋಡ್ ಆಗುತ್ತಿದೆ…',
  'files.updateAll': 'ಎಲ್ಲವನ್ನೂ ಪರಿಷಕರಿಸಿ ({n})',
  'files.updating': 'ಪರಿಷಕರಿಸುತ್ತಿದೆ…',
  'files.moveToTrash': 'ಕಸದ ಪೆಟ್ಟಿಗೆಗೆ ಸೇರಿಸಿ',
  'files.moveToTrashAria': '{name} ಅನ್ನು ಕಸದ ಪೆಟ್ಟಿಗೆಗೆ ಸೇರಿಸಿ',

  // Trash
  'files.trash': 'ಕಸದ ಪೆಟ್ಟಿಗೆ',
  'files.trashCount': 'ಕಸದ ಪೆಟ್ಟಿಗೆ ({n})',
  'files.openTrash': 'ಕಸದ ಪೆಟ್ಟಿಗೆ ತೆರೆಯಿರಿ',
  'files.trashNote': 'ಫೈಲ್‌ಗಳನ್ನು 30 ದಿನಗಳವರೆಗೆ ಮರುಪಡೆಯಬಹುದು',
  'files.trashEmpty': 'ಕಸದ ಪೆಟ್ಟಿಗೆ ಖಾಲಿಯಾಗಿದೆ.',
  'files.deletedAt': 'ಅಳಿಸಿದ್ದು: {time}',
  'files.daysLeft': 'ಮರುಪಡೆಯಲು {n} ದಿನಗಳು ಉಳಿದಿವೆ',
  'files.restoreExpired': 'ಮರುಪಡೆಯುವ ಅವಧಿ ಮುಗಿದಿದೆ',
  'files.restore': 'ಮರುಪಡೆಯಿರಿ',
  'files.restoring': 'ಮರುಪಡೆಯುತ್ತಿದೆ…',
  'files.restoreTitle': 'ಫೈಲ್ ಮತ್ತು ಆಮದು ದತ್ತಾಂಶ ಮರುಪಡೆಯಿರಿ',
  'files.deletePermanent': 'ಶಾಶ್ವತವಾಗಿ ಅಳಿಸಿ',
  'files.deleting': 'ಅಳಿಸುತ್ತಿದೆ…',

  // Upload / import result
  'files.uploadedStart': '"{name}" ಅಪ್‌ಲೋಡ್ ಆಗಿದೆ. ದತ್ತಾಂಶ ಸಂಗ್ರಹ ಪರಿಷ್ಕರಣೆ ನಡೆಯುತ್ತಿದೆ…',
  'files.importedPrefix': '"{name}" ದಾಖಲಿಸಲಾಗಿದೆ.',
  'files.statNew': '{n} ಹೊಸ',
  'files.statUpdated': '{n} ಪರಿಷಕರಿಸಿದ್ದು',
  'files.statUnchanged': '{n} ಬದಲಾಗಿಲ್ಲ',
  'files.statDuplicate': '{n} ನಕಲು',
  'files.statInvalid': '{n} ತಪ್ಪು',
  'files.studentsSummary': 'ವಿದ್ಯಾರ್ಥಿಗಳು: {list}.',
  'files.marksAdded': '{n} ಅಂಕ ಸೇರಿಸಿದ್ದು',
  'files.marksUpdated': '{n} ಅಂಕ ಪರಿಷಕರಿಸಿದ್ದು',
  'files.savedStats': '"{name}" ಉಳಿಸಲಾಗಿದೆ. ವಿದ್ಯಾರ್ಥಿಗಳು: {list}.',
  'files.dbUpdatedOk': 'ದತ್ತಾಂಶ ಸಂಗ್ರಹ ಯಶಸ್ವಿಯಾಗಿ ಪರಿಷಕರಿಸಲಾಗಿದೆ.',
  'files.provisional': '{n} ಹೆಸರು ಮಾತ್ರ ಇರುವ ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ತಾತ್ಕಾಲಿಕ USN ನೀಡಲಾಗಿದೆ (ಹೆಸರಿನ ಕ್ರಮದಲ್ಲಿ) — ನಂತರ ನಿಜವಾದ USN ಅನ್ನು ಆದೇಶಿಸಿ.',
  'files.provisionalShort': '{n} ಹೆಸರು ಮಾತ್ರ ಇರುವ ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ತಾತ್ಕಾಲಿಕ USN ನೀಡಲಾಗಿದೆ — ನಂತರ ನಿಜವಾದ USN ಅನ್ನು ಆದೇಶಿಸಿ.',

  // Confirmation dialogs
  'files.toTrashConfirm': '"{name}" ಅನ್ನು ಕಸದ ಪೆಟ್ಟಿಗೆಗೆ ಸೇರಿಸಬೇಕೇ? ಈ ಫೈಲ್‌ಗೆ ಮಾತ್ರ ಸೇರಿದ ಆಮದು ದತ್ತಾಂಶವನ್ನು ತೆಗೆದುಹಾಕಲಾಗುವುದು. ಫೈಲ್ ಮತ್ತು ದತ್ತಾಂಶವನ್ನು 30 ದಿನಗಳವರೆಗೆ ಮರುಪಡೆಯಬಹುದು.',
  'files.toTrashDone': '"{name}" ಅನ್ನು 30 ದಿನಗಳಿಗೆ ಕಸದ ಪೆಟ್ಟಿಗೆಗೆ ಸೇರಿಸಲಾಗಿದೆ.',
  'files.permConfirm': '⚠️ ಈ ದಾಖಲೆಯನ್ನು ಶಾಶ್ವತವಾಗಿ ಅಳಿಸಬೇಕೇ?\n\nಆಯ್ಕೆಮಾಡಿದ ವಿದ್ಯಾರ್ಥಿ ಮತ್ತು ಕಸದ ಪೆಟ್ಟಿಗೆಯಲ್ಲಿ ಸಂಗ್ರಹಿಸಿರುವ ಮರುಪಡೆಯುವಿಕೆಯ ದತ್ತಾಂಶ ಶಾಶ್ವತವಾಗಿ ತೆಗೆದುಹಾಕಲಾಗುವುದು. ಈ ಕ್ರಿಯೆಯನ್ನು ಹಿಂತಿರುಗಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ.\n\nನೀವು ಖಚಿತವಾಗಿ ಬಯಸುತ್ತೀರಾ?',
  'files.permDeleted': '"{name}" ಅನ್ನು ಕಸದ ಪೆಟ್ಟಿಗೆಯಿಂದ ಶಾಶ್ವತವಾಗಿ ಅಳಿಸಲಾಗಿದೆ.',
  'files.restored': '"{name}" ಮತ್ತು ಅದರ ಆಮದು ದತ್ತಾಂಶ ಮರುಪಡೆಯಲಾಗಿದೆ.',

  // Error-detail line labels (ಕಾರಣದ ಸಂದೇಶ ಬ್ಯಾಕೆಂಡ್‌ನಿಂದ ಬರುತ್ತದೆ)
  'files.invalidRows': 'ತಪ್ಪಾದ ಸಾಲುಗಳು: {n}',
  'files.rowsParsed': 'ವಿಶ್ಲೇಷಿಸಿದ ಸಾಲುಗಳು: {n}',
  'files.rowReason': 'ಸಾಲು {row}: {reason}',

  // Row metadata and states
  'files.pending': 'ಬಾಕಿ',
  'files.badgeImported': 'ದಾಖಲಿಸಲಾಗಿದೆ',
  'files.unknownType': 'ಅಜ್ಞಾತ ಪ್ರಕಾರ',
  'files.rows': '{n} ಸಾಲುಗಳು',
  'files.rowsUnavailable': 'ಸಾಲುಗಳ ಸಂಖ್ಯೆ ಲಭ್ಯವಿಲ್ಲ',
  'files.uploadTimeUnavailable': 'ಅಪ್‌ಲೋಡ್ ಸಮಯ ಲಭ್ಯವಿಲ್ಲ',
  'files.unknownUploader': 'ಅಪ್‌ಲೋಡ್ ಮಾಡಿದವರು ಅಜ್ಞಾತ',
  'files.pendingNote': 'ಫೈಲ್ ಅಪ್‌ಲೋಡ್ ಆಗಿದೆ, ಆದರೆ ಇನ್ನೂ ದತ್ತಾಂಶ ಸಂಗ್ರಹಕ್ಕೆ ಸೇರಿಸಿಲ್ಲ.',
  'files.expiredNote': 'ಈ ಫೈಲ್‌ನ ದತ್ತಾಂಶ ಇನ್ನು ದತ್ತಾಂಶ ಸಂಗ್ರಹದಲ್ಲಿ ಇಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಅಪ್‌ಲೋಡ್ ಮಾಡಿ ದಾಖಲಿಸಿ.',
  'files.empty': 'ಇನ್ನೂ ಫೈಲ್‌ಗಳನ್ನು ಅಪ್‌ಲೋಡ್ ಮಾಡಿಲ್ಲ',
  'files.emptyHint': 'CSV, XLSX, PDF, TXT ಅಥವಾ ಚಿತ್ರಗಳನ್ನು ಅಪ್‌ಲೋಡ್ ಮಾಡಿ',

  // Failures
  'files.errLoad': 'ಫೈಲ್‌ಗಳನ್ನು ಲೋಡ್ ಮಾಡಲಾಗಲಿಲ್ಲ.',
  'files.errTrashLoad': 'ಕಸದ ಪೆಟ್ಟಿಗೆಯನ್ನು ಲೋಡ್ ಮಾಡಲಾಗಲಿಲ್ಲ.',
  'files.errUpload': 'ಅಪ್‌ಲೋಡ್ ವಿಫಲವಾಗಿದೆ. ಫೈಲ್ ಪ್ರಕಾರ ಮತ್ತು ಸರ್ವರ್ ಸಂಪರ್ಕವನ್ನು ಪರಿಶೀಲಿಸಿ.',
  'files.errUploadDb': 'ಫೈಲ್ ಅಪ್‌ಲೋಡ್ ಆಗಿದೆ, ಆದರೆ ದತ್ತಾಂಶ ಸಂಗ್ರಹ ಪರಿಷ್ಕರಣೆ ವಿಫಲವಾಗಿದೆ. ಫೈಲ್ ರೂಪವನ್ನು ಪರಿಶೀಲಿಸಿ.',
  'files.errDbUpdate': 'ದತ್ತಾಂಶ ಸಂಗ್ರಹ ಪರಿಷ್ಕರಣೆ ವಿಫಲವಾಗಿದೆ. ಫೈಲ್ ರೂಪವನ್ನು ಪರಿಶೀಲಿಸಿ.',
  'files.errToTrash': 'ಫೈಲ್ ಅನ್ನು ಕಸದ ಪೆಟ್ಟಿಗೆಗೆ ಸೇರಿಸಲಾಗಲಿಲ್ಲ.',
  'files.errRestore': 'ಕಸದ ಪೆಟ್ಟಿಗೆಯಿಂದ ಫೈಲ್ ಮರುಪಡೆಯಲಾಗಲಿಲ್ಲ.',
  'files.errPermanent': 'ಈ ಫೈಲ್ ಅನ್ನು ಕಸದ ಪೆಟ್ಟಿಗೆಯಿಂದ ಶಾಶ್ವತವಾಗಿ ಅಳಿಸಲಾಗಲಿಲ್ಲ.',
};

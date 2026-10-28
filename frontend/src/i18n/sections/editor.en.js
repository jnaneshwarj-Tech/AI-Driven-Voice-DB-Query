/**
 * StudentEditor — English chrome strings for the generic "fill any blank
 * field" modal (EditFieldModal). Values mirror the pre-redesign wording; the
 * per-column labels come from the backend, never from this file.
 */
export default {
  'editor.errLoadFields': 'Could not load this student’s editable fields.',
  'editor.errSave': 'Could not save changes.',
  'editor.nothingToSave': 'Nothing to save — no fields changed.',
  'editor.recordUpdated': 'Record updated',
  'editor.fieldsSaved': '{n} field(s) saved.',
  'editor.editTitle': 'Edit details · {name}',
  'editor.editSub': 'Fill blank fields or correct values. Identity, timestamps and lifecycle status are managed elsewhere and can’t be edited here.',
  'editor.saveN': 'Save {n} change{s}',
  'editor.loadingFields': 'Loading fields…',
  'editor.showingBlank': 'Showing {n} blank field(s)',
  'editor.showingAll': 'Showing all fields',
  'editor.searchField': 'Search a field…',
  'editor.noBlankFields': 'No blank fields — every field already has a value. Toggle to edit any field.',
  'editor.noMatches': 'No fields match your search.',
  'editor.blank': 'blank',
  'editor.enterValue': 'Enter value…',

  // EditFeesModal — fee type names and status values are backend data and
  // stay verbatim; only the surrounding chrome is translated here.
  'editor.feesTitle': 'Fees · {who}',
  'editor.feesSub': 'Admin-only. Status is verified against the canonical fee report before saving, and every change can be undone.',
  'editor.loadingFees': 'Loading fees…',
  'editor.errLoadFees': 'Could not load fees.',
  'editor.nothingFee': 'Nothing to save — no fee changes.',
  'editor.feesUpdated': 'Fees updated',
  'editor.feeRowsSaved': '{n} fee row(s) saved.',
  'editor.errSaveFees': 'Could not save fee updates.',
  'editor.year': 'Year {n}',
  'editor.total': 'Total',
  'editor.currentStatus': 'current:',
  'editor.unchanged': '— unchanged —',
  'editor.paidHint': 'Paid ₹',
  'editor.remainingHint': 'Remaining ₹',
};

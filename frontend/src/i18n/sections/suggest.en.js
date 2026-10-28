/**
 * English strings for the AI search suggestion panel
 * (src/components/SuggestionPanel.jsx).
 *
 * Scope: chrome only. `message`, `search_term` and the suggestion name/USN
 * emitted to Dashboard come from the parser and never pass through here, so
 * nothing in this file can alter what the backend receives.
 */
export default {
  'suggest.regionLabel': 'Search suggestions',
  'suggest.noRecords': 'No matching records available.',
  'suggest.match': '{pct}% match',

  // Shown between the label and the ellipsis so the name can stay bold.
  'suggest.loadingBefore': 'Loading data for',
  'suggest.loadingAfter': '…',

  'suggest.otherMatches': 'Other possible matches',
  'suggest.noExactFor': 'No exact record found for “{q}”',
  'suggest.possibleSelect': 'Possible matches found. Please select:',
  'suggest.select': 'Select',
  'suggest.cancelNone': 'Cancel — none of these',

  'suggest.multipleTitle': 'Multiple students found with similar name',
  'suggest.multipleHint': 'USN is the unique identity. Please choose:',
  'suggest.view': 'View',

  'suggest.colSelect': 'Select',
  'suggest.colUsn': 'USN',
  'suggest.colName': 'Name',
  'suggest.colMatch': 'Match',
};

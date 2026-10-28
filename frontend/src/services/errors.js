const UNSAFE_ERROR_TEXT = /traceback|sqlstate|mysql|keyerror|typeerror|execution error|internal server error|column not found/i;

/**
 * A backend `detail` is a string for the HTTPExceptions this app raises, but a
 * 422 from request-body validation arrives as an array of {loc, msg} objects.
 * Callers put the result straight into React state, so it must come out a
 * string — rendering the raw array unmounts the whole page.
 */
function detailToText(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === 'string' ? d : d?.msg))
      .filter(Boolean)
      .join('; ');
  }
  if (detail && typeof detail === 'object') {
    const inner = detail.message || detail.detail;
    return typeof inner === 'string' ? inner : '';
  }
  return '';
}

export function getUserMessage(error, fallback = 'Something went wrong. Please try again.') {
  const text = detailToText(error?.response?.data?.detail);
  return text && !UNSAFE_ERROR_TEXT.test(text) ? text : fallback;
}

const UNSAFE_ERROR_TEXT = /traceback|sqlstate|mysql|keyerror|typeerror|execution error|internal server error|column not found/i;

export function getUserMessage(error, fallback = 'Something went wrong. Please try again.') {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' && !UNSAFE_ERROR_TEXT.test(detail) ? detail : fallback;
}

/**
 * Motion preference, read once per call. CSS entrances honour this through the
 * `prefers-reduced-motion` block in src/index.css; JS-driven animation (recharts
 * series, the count-up readouts) cannot use CSS, so they ask here instead.
 */
export function prefersReducedMotion() {
  return typeof window !== 'undefined' &&
    !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

/** Duration for a JS-driven entrance: 0 when the user has asked for stillness. */
export function motionDuration(ms) {
  return prefersReducedMotion() ? 0 : ms;
}

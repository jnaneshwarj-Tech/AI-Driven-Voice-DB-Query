/**
 * CountUp — animates a numeric readout from its previous value to the value it
 * is handed. It never invents a number: the animation always terminates at the
 * prop it was given, so a card can only ever display real, loaded data.
 *
 * Presentation only — no props in, no state out, no callbacks.
 * Honours prefers-reduced-motion by rendering the final value directly.
 */
import { useEffect, useRef, useState } from 'react';
import { prefersReducedMotion } from '../utils/motionPref';

export default function CountUp({ value, duration = 620, decimals, className }) {
  const target = Number(value);
  const finite = Number.isFinite(target);
  const places = decimals !== undefined
    ? decimals
    : (finite && !Number.isInteger(target) ? 2 : 0);

  const [shown, setShown] = useState(finite ? 0 : target);
  // Always the value currently painted, never the pending one. React StrictMode
  // invokes effects twice in development; if this were advanced up front the
  // second pass would see start === target and skip the animation entirely.
  const displayed = useRef(finite ? 0 : target);
  const staticRender = useRef(prefersReducedMotion());

  useEffect(() => {
    if (!finite || staticRender.current) {
      displayed.current = target;
      setShown(target);
      return;
    }
    const start = displayed.current;
    if (start === target) { setShown(target); return; }
    let raf;
    let t0;
    const step = (ts) => {
      if (!t0) t0 = ts;
      const p = Math.min(1, (ts - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const next = start + (target - start) * eased;
      displayed.current = next;
      setShown(next);
      if (p < 1) raf = requestAnimationFrame(step);
      else { displayed.current = target; setShown(target); }
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, finite, duration]);

  if (!finite) return <span className={className}>{String(value)}</span>;
  return (
    <span className={className}>
      {shown.toLocaleString('en-IN', { minimumFractionDigits: places, maximumFractionDigits: places })}
    </span>
  );
}

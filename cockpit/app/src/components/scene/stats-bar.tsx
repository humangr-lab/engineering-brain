import { useEffect, useRef } from "react";

interface StatsBarProps {
  items: { label: string; value: number }[];
}

/**
 * Animated stats bar — counters ease from 0 to target.
 * Respects prefers-reduced-motion.
 */
export function StatsBar({ items }: StatsBarProps) {
  return (
    <div className="absolute bottom-4 left-4 flex gap-3">
      {items.map((item) => (
        <div
          key={item.label}
          className="glass rounded-[var(--radius-sm)] px-3 py-1.5"
        >
          <AnimatedCounter value={item.value} />
          <span className="ml-1.5 text-[11px] text-[var(--color-text-tertiary)]">
            {item.label}
          </span>
        </div>
      ))}
    </div>
  );
}

function AnimatedCounter({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const prevRef = useRef(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    if (reducedMotion || value === 0) {
      el.textContent = value.toLocaleString();
      prevRef.current = value;
      return;
    }

    const from = prevRef.current;
    const start = performance.now();
    const duration = 1200;

    function step() {
      const elapsed = performance.now() - start;
      const t = Math.min(elapsed / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      const current = Math.round(from + (value - from) * ease);
      if (el) el.textContent = current.toLocaleString();
      if (t < 1) requestAnimationFrame(step);
    }

    requestAnimationFrame(step);
    prevRef.current = value;
  }, [value]);

  return (
    <span
      ref={ref}
      className="text-[11px] font-medium tabular-nums text-[var(--color-text-secondary)]"
    >
      {value.toLocaleString()}
    </span>
  );
}

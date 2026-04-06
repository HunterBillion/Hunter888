"use client";

import { useRef, useEffect, useState } from "react";

/**
 * HOC wrapper that triggers Chart.js animations when the chart enters viewport.
 *
 * Instead of Chart.js animating on mount (which may happen off-screen),
 * this delays the data assignment until the container scrolls into view.
 *
 * Usage:
 *   <AnimatedChart>
 *     {(isVisible) => (
 *       <Bar data={isVisible ? realData : emptyData} options={options} />
 *     )}
 *   </AnimatedChart>
 */
interface AnimatedChartProps {
  children: (isVisible: boolean) => React.ReactNode;
  /** Threshold (0-1) of element visibility to trigger (default 0.2) */
  threshold?: number;
  /** Additional delay in ms before triggering (default 0) */
  delay?: number;
  className?: string;
  style?: React.CSSProperties;
}

export function AnimatedChart({
  children,
  threshold = 0.2,
  delay = 0,
  className,
  style,
}: AnimatedChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Check if reduced motion is preferred
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) {
      setIsVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          if (delay > 0) {
            setTimeout(() => setIsVisible(true), delay);
          } else {
            setIsVisible(true);
          }
          observer.disconnect();
        }
      },
      { threshold }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold, delay]);

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? "none" : "translateY(10px)",
        transition: "opacity 0.4s ease, transform 0.4s ease",
        ...style,
      }}
    >
      {children(isVisible)}
    </div>
  );
}

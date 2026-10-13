import { useEffect, useRef, type ReactNode } from "react";

import { cn } from "../lib/cn";

/**
 * Fades and rises into view the first time it scrolls into the viewport (300ms; see the
 * `reveal` utility). Under prefers-reduced-motion the CSS shows it at once, unanimated.
 * The flag is set straight on the DOM node, so revealing never re-renders anything.
 */
export function Reveal({ className, children }: { className?: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (typeof IntersectionObserver === "undefined") {
      node.dataset.revealed = "";
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            (entry.target as HTMLElement).dataset.revealed = "";
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.15 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className={cn("reveal", className)}>
      {children}
    </div>
  );
}

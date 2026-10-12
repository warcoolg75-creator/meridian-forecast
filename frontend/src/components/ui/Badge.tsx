import type { ReactNode } from "react";

import { cn } from "../../lib/cn";

export type BadgeTone = "positive" | "warning" | "negative" | "neutral";

// Status text sits on a tint of its own colour. Warning text is amber-800, never amber-600
// (which fails AA as text); amber-600 appears only as the dot.
const TONES: Record<BadgeTone, string> = {
  positive: cn("bg-positive-subtle text-positive"),
  warning: cn("bg-warning-subtle text-warning-text"),
  negative: cn("bg-negative-subtle text-negative"),
  neutral: cn("bg-surface-muted text-fg-muted"),
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-step-n2 font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {tone === "warning" && <span aria-hidden className="size-2 rounded-full bg-warning" />}
      {children}
    </span>
  );
}

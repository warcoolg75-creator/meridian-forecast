import type { ReactNode } from "react";

import { cn } from "../../lib/cn";

/**
 * A block that pulses where content is loading. Size it like the content it stands in
 * for, so nothing jumps when the data arrives. Decorative: wrap a group in <Loading>.
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded-control bg-line motion-reduce:animate-none", className)}
    />
  );
}

/** Tells screen readers once that `label` is loading, around the skeletons that stand in for it. */
export function Loading({
  label,
  className,
  children,
}: {
  /** What is loading, e.g. "weekly units". Read as "Loading weekly units". */
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div role="status" className={className}>
      <span className="sr-only">Loading {label}</span>
      {children}
    </div>
  );
}

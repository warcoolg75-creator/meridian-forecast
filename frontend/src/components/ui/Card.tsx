import type { HTMLAttributes } from "react";

import { cn } from "../../lib/cn";

/** Cream-50 surface, cream-200 hairline, resting shadow. There is no white in the palette. */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-card border border-line bg-surface p-6 shadow-rest", className)}
      {...props}
    />
  );
}

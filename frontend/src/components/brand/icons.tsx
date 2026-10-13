import type { ReactNode } from "react";

import { cn } from "../../lib/cn";

/** 24px line icon: 1.5px stroke in currentColor, round caps and joins. */
function LineIcon({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("size-6", className)}
    >
      {children}
    </svg>
  );
}

/** Axes, a rising history and its dashed continuation. */
export function ForecastIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <path d="M4 4v16h16" />
      <path d="M7 15l3-4 3 2 3.5-5" />
      <path d="M16.5 8 20 5.5" strokeDasharray="1.5 2.5" />
    </LineIcon>
  );
}

/** A calendar with scheduled production runs. */
export function PlanningIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <rect x="3.5" y="5" width="17" height="15" rx="2" />
      <path d="M3.5 9.5h17M8 3v4M16 3v4" />
      <path d="M7 13.5h5M10 16.5h7" />
    </LineIcon>
  );
}

/** A globe: meridians and a parallel, for market signals from everywhere. */
export function MarketIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.5 12h17" />
      <path d="M12 3.5c2.4 2.3 3.6 5.2 3.6 8.5s-1.2 6.2-3.6 8.5c-2.4-2.3-3.6-5.2-3.6-8.5S9.6 5.8 12 3.5Z" />
    </LineIcon>
  );
}

/** Menu (three lines) and close (a cross), for the mobile navigation toggle. */
export function MenuIcon({ open, className }: { open: boolean; className?: string }) {
  return (
    <LineIcon className={className}>
      {open ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
    </LineIcon>
  );
}

/** A spinning arc, for loading buttons. Still under prefers-reduced-motion. */
export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      fill="none"
      className={cn("size-4 animate-spin motion-reduce:animate-none", className)}
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity="0.3" />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** A circled exclamation mark, for error banners. */
export function AlertIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5v5.5M12 16.25v.25" />
    </LineIcon>
  );
}

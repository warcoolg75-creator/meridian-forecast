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

// ---- App and component icons: same 24px grid, 1.5px stroke, currentColor ----

/** Four tiles of a dashboard. */
export function DashboardIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <rect x="3.5" y="3.5" width="7" height="9" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="5" rx="1.5" />
      <rect x="13.5" y="11.5" width="7" height="9" rx="1.5" />
      <rect x="3.5" y="15.5" width="7" height="5" rx="1.5" />
    </LineIcon>
  );
}

/** A packed carton, for products. */
export function ProductsIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <path d="M12 3 20 7.5v9L12 21l-8-4.5v-9L12 3Z" />
      <path d="M4 7.5 12 12l8-4.5M12 12v9" />
      <path d="m8 5.25 8 4.5" />
    </LineIcon>
  );
}

/** A panel with its sidebar, and a chevron pointing the way it will move. */
export function SidebarIcon({ collapsed, className }: { collapsed: boolean; className?: string }) {
  return (
    <LineIcon className={className}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <path d="M9 4.5v15" />
      <path d={collapsed ? "m13.5 10 2 2-2 2" : "m15.5 10-2 2 2 2"} />
    </LineIcon>
  );
}

export function ChevronIcon({
  direction,
  className,
}: {
  direction: "down" | "left" | "right";
  className?: string;
}) {
  const d = { down: "m6 9 6 6 6-6", left: "m15 6-6 6 6 6", right: "m9 6 6 6-6 6" }[direction];
  return (
    <LineIcon className={className}>
      <path d={d} />
    </LineIcon>
  );
}

/** Change direction for a delta: up and to the right, down and to the right, or level. */
export function TrendIcon({
  direction,
  className,
}: {
  direction: "up" | "down" | "flat";
  className?: string;
}) {
  const d = {
    up: "M7 17 17 7M9 7h8v8",
    down: "M7 7l10 10M17 9v8H9",
    flat: "M5 12h14M15 8l4 4-4 4",
  }[direction];
  return (
    <LineIcon className={className}>
      <path d={d} />
    </LineIcon>
  );
}

/** Sort state of a table column: both ways when unsorted, else the active direction. */
export function SortIcon({
  direction,
  className,
}: {
  direction: "asc" | "desc" | null;
  className?: string;
}) {
  const d =
    direction === "asc"
      ? "M12 19V5M7 10l5-5 5 5"
      : direction === "desc"
        ? "M12 5v14M7 14l5 5 5-5"
        : "m8 9 4-4 4 4M8 15l4 4 4-4";
  return (
    <LineIcon className={className}>
      <path d={d} />
    </LineIcon>
  );
}

export function CloseIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <path d="M6 6l12 12M18 6 6 18" />
    </LineIcon>
  );
}

/** A circled tick, for success messages. */
export function CheckCircleIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m8.5 12.5 2.5 2.5 4.5-5" />
    </LineIcon>
  );
}

/** A circled "i", for neutral messages. */
export function InfoIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5.5M12 7.75V8" />
    </LineIcon>
  );
}

/** A warning triangle. Draw it in amber-600 (`text-warning`): icons may use it, text may not. */
export function WarningIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <path d="M10.3 4.6a2 2 0 0 1 3.4 0l7 12a2 2 0 0 1-1.7 3H5a2 2 0 0 1-1.7-3l7-12Z" />
      <path d="M12 9.5v4M12 16.5v.25" />
    </LineIcon>
  );
}

/** An empty tray, for empty states. */
export function EmptyIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <path d="M3.5 13.5 6 5h12l2.5 8.5v5a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5v-5Z" />
      <path d="M3.5 13.5h5l1 2h5l1-2h5" />
    </LineIcon>
  );
}

export function CalendarIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <rect x="3.5" y="5" width="17" height="15" rx="2" />
      <path d="M3.5 9.5h17M8 3v4M16 3v4" />
    </LineIcon>
  );
}

export function SearchIcon({ className }: { className?: string }) {
  return (
    <LineIcon className={className}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </LineIcon>
  );
}

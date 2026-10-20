import { useEffect, type ReactNode } from "react";

/**
 * Every /app page starts here: a title, an optional subtitle and an optional action slot
 * (right-aligned, wrapping below the title on narrow screens), then the page's content,
 * with the same width, gutters and vertical rhythm everywhere. Also sets the tab title.
 * The h1 is `#page-title`, which names <main> (AppLayout focuses <main> on navigation).
 */
export function PageScaffold({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  /** Page-level controls: primary actions, export, a date picker. */
  actions?: ReactNode;
  children?: ReactNode;
}) {
  useEffect(() => {
    document.title = `${title} · Meridian`;
  }, [title]);

  return (
    <div className="mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <h1 id="page-title" className="text-step-4">
            {title}
          </h1>
          {subtitle && <p className="max-w-3xl text-fg-muted">{subtitle}</p>}
        </div>
        {actions && (
          // Full width on a phone, so a full-width control (a toggle) does not wrap its labels.
          <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">{actions}</div>
        )}
      </header>
      {children}
    </div>
  );
}

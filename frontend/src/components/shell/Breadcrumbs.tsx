import { Link, useMatches } from "react-router";

import { cn } from "../../lib/cn";

/** Give a route `handle: { crumb: "Products" }` and it appears in the breadcrumb. */
export interface CrumbHandle {
  crumb: string;
}

function isCrumbHandle(handle: unknown): handle is CrumbHandle {
  return (
    typeof handle === "object" &&
    handle !== null &&
    typeof (handle as { crumb?: unknown }).crumb === "string"
  );
}

/**
 * The trail of matched routes that carry a crumb. The current page is plain text; the
 * ones above it are links, hidden below 640px where the top bar has no room for them.
 */
export function Breadcrumbs({ className }: { className?: string }) {
  const crumbs = useMatches()
    .filter((match) => isCrumbHandle(match.handle))
    .map((match) => ({ label: (match.handle as CrumbHandle).crumb, to: match.pathname }));
  return (
    <nav aria-label="Breadcrumb" className={cn("min-w-0", className)}>
      <ol className="flex min-w-0 items-center gap-2 text-step-n1">
        {crumbs.map((crumb, index) =>
          index === crumbs.length - 1 ? (
            <li key={crumb.to} className="min-w-0">
              <span aria-current="page" className="block truncate font-medium text-fg">
                {crumb.label}
              </span>
            </li>
          ) : (
            <li key={crumb.to} className="hidden shrink-0 items-center gap-2 sm:flex">
              <Link
                to={crumb.to}
                className="text-fg-muted underline-offset-4 hover:text-primary hover:underline"
              >
                {crumb.label}
              </Link>
              <span aria-hidden className="text-fg-subtle">
                /
              </span>
            </li>
          ),
        )}
      </ol>
    </nav>
  );
}

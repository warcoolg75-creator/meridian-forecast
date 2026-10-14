import { Link } from "react-router";

import { cn } from "../../lib/cn";

const PAGES = [
  { key: "tokens", to: "/styleguide", label: "Tokens" },
  { key: "components", to: "/styleguide/components", label: "Components" },
] as const;

/** Switches between the two review pages. */
export function StyleguideNav({ current }: { current: (typeof PAGES)[number]["key"] }) {
  return (
    <nav
      aria-label="Styleguide"
      className="flex flex-wrap items-center gap-x-4 gap-y-1 text-step-n1 font-medium"
    >
      <span className="text-primary">Meridian Forecast · design system</span>
      <span aria-hidden className="text-fg-subtle">
        |
      </span>
      {PAGES.map((page) =>
        page.key === current ? (
          <span key={page.key} aria-current="page" className="text-fg">
            {page.label}
          </span>
        ) : (
          <Link
            key={page.key}
            to={page.to}
            className={cn("text-primary underline-offset-4 hover:underline")}
          >
            {page.label}
          </Link>
        ),
      )}
    </nav>
  );
}

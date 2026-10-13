import { Link } from "react-router";

import { Wordmark } from "../../components/brand/Wordmark";
import { cn } from "../../lib/cn";
import { FOOTER_COLUMNS } from "./content";

// The default maroon focus ring is invisible on maroon-900 (1.87:1), so it is cream here.
const LINK = cn(
  "text-step-n1 text-cream-100 underline-offset-4 hover:text-cream-50 hover:underline focus-visible:outline-cream-50",
);

export function SiteFooter() {
  return (
    <footer className="bg-maroon-900">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="grid gap-12 md:grid-cols-5">
          <div className="space-y-3 md:col-span-2">
            <Wordmark tone="cream" />
            <p className="max-w-xs text-step-n1 text-maroon-100">
              Demand forecasting and production planning for manufacturers.
            </p>
          </div>
          {/* Three link columns side by side at every width, even 360px. */}
          <div className="grid grid-cols-3 gap-6 md:col-span-3">
            {FOOTER_COLUMNS.map(({ title, links }) => (
              <nav key={title} aria-label={title}>
                <h2 className="font-sans text-step-n2 font-semibold tracking-wide text-maroon-100 uppercase">
                  {title}
                </h2>
                <ul className="mt-4 space-y-3">
                  {links.map(({ label, to, href }) => (
                    <li key={label}>
                      {to ? (
                        <Link to={to} className={LINK}>
                          {label}
                        </Link>
                      ) : (
                        <a href={href} className={LINK}>
                          {label}
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </nav>
            ))}
          </div>
        </div>
        <p className="mt-12 border-t border-maroon-700 pt-6 text-step-n2 text-maroon-100">
          © {new Date().getFullYear()} Meridian Forecast
        </p>
      </div>
    </footer>
  );
}
